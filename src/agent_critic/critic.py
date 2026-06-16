"""Critic core: render the route-specific prompt, call the critic model, parse
strict JSON, enforce the consistency rule, and fall back deterministically."""

from __future__ import annotations

import json
import time

import httpx

from . import SPEC_VERSION
from .config import Config
from .models import CritiqueRequest, Envelope
from .prompts import load_template
from .selection import choose_critic

_HIGH_SEVERITIES = {"CRITICAL", "HIGH"}
_HIGH_QUALITIES = {"EXCELLENT", "GOOD"}


def _consistency_text(enabled: bool) -> str:
    if not enabled:
        return ""
    return (
        "Consistency rule: a CRITICAL or HIGH severity cannot earn EXCELLENT or "
        "GOOD quality — cap quality at ADEQUATE in that case."
    )


def render_system_prompt(config: Config, route: str) -> str:
    rubric = config.routes_by_name.get(route)
    quality_rubric = rubric.quality_rubric if rubric else "(no rubric; judge on general merit)"
    template = load_template(config.critic.prompt_template)
    return (
        template.replace("{severity_scale}", " | ".join(config.critic.severity_scale))
        .replace("{quality_scale}", " | ".join(config.critic.quality_scale))
        .replace("{route}", route)
        .replace("{quality_rubric}", quality_rubric)
        .replace("{consistency_rule}", _consistency_text(config.critic.consistency_rule))
    )


def build_messages(config: Config, request: CritiqueRequest) -> list[dict]:
    system = render_system_prompt(config, request.route)
    user = (
        "[SYSTEM PROMPT GIVEN TO THE ASSISTANT]\n"
        f"{request.system_prompt or '(none)'}\n\n"
        "[USER REQUEST]\n"
        f"{request.user_prompt or '(none)'}\n\n"
        "[ASSISTANT RESPONSE TO EVALUATE]\n"
        f"{request.assistant_response or '(empty)'}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def extract_json(text: str) -> dict | None:
    """Pull the first balanced JSON object out of a model's text output."""
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    return None
    return None


def _fallback(route: str, critic_model: str, reason: str, latency_ms: int) -> Envelope:
    return Envelope(
        spec=SPEC_VERSION,
        route=route,
        critic_model=critic_model,
        severity="OTHER",
        severity_reason=reason,
        quality="ADEQUATE",
        quality_reason="Verdict unavailable; emitting a neutral fallback.",
        meta={"latency_ms": latency_ms, "fallback": True},
    )


def _normalize(value: str | None, scale: list[str]) -> str | None:
    if not value:
        return None
    upper = value.strip().upper()
    return upper if upper in scale else None


def build_envelope(
    config: Config, request: CritiqueRequest, critic_model: str, parsed: dict, latency_ms: int
) -> Envelope:
    severity = _normalize(parsed.get("severity"), config.critic.severity_scale)
    quality = _normalize(parsed.get("quality"), config.critic.quality_scale)
    if severity is None or quality is None:
        return _fallback(
            request.route, critic_model,
            "Critic produced an out-of-scale verdict; emitting fallback.", latency_ms,
        )

    meta = {"latency_ms": latency_ms}
    if config.critic.consistency_rule and severity in _HIGH_SEVERITIES and quality in _HIGH_QUALITIES:
        meta["consistency_clamped_from"] = quality
        quality = "ADEQUATE"

    return Envelope(
        spec=SPEC_VERSION,
        route=request.route,
        critic_model=critic_model,
        severity=severity,
        severity_reason=(parsed.get("severity_reason") or "").strip() or None,
        quality=quality,
        quality_reason=(parsed.get("quality_reason") or "").strip() or None,
        meta=meta,
    )


async def critique_once(config: Config, request: CritiqueRequest) -> Envelope:
    """In-process convenience: manage a one-shot client and return an Envelope.

    Lets a host embed the critic without running the HTTP service."""
    async with httpx.AsyncClient() as client:
        return await critique(client, config, request)


async def critique(client: httpx.AsyncClient, config: Config, request: CritiqueRequest) -> Envelope:
    """Evaluate a response and return a Critique Envelope. Never raises."""
    started = time.time()
    _, model_cfg = choose_critic(config, request.generator_model, request.critic_model)
    critic_model = model_cfg.model

    payload = {
        "model": critic_model,
        "messages": build_messages(config, request),
        "stream": False,
        "temperature": config.critic.temperature,
        "max_tokens": config.critic.max_tokens,
    }
    try:
        resp = await client.post(
            model_cfg.base_url.rstrip("/") + "/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {model_cfg.api_key}"},
            timeout=httpx.Timeout(model_cfg.read_timeout, connect=model_cfg.connect_timeout),
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"].get("content", "")
    except Exception as exc:  # network/HTTP failure
        latency_ms = int((time.time() - started) * 1000)
        return _fallback(request.route, critic_model, f"Critic call failed: {exc}", latency_ms)

    latency_ms = int((time.time() - started) * 1000)
    parsed = extract_json(content)
    if parsed is None:
        return _fallback(
            request.route, critic_model,
            "Critic response was not valid JSON; emitting fallback.", latency_ms,
        )
    return build_envelope(config, request, critic_model, parsed, latency_ms)

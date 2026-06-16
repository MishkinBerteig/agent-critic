"""Shared fixtures: a tmp config and a mock-transport httpx client."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from agent_critic.config import load_config

GEMMA = "gemma-model-x"
QWEN = "qwen-model-x"

CONFIG_YAML = f"""
server: {{ host: 127.0.0.1, port: 8090 }}

critic_models:
  reviewer_gemma: {{ base_url: http://up/v1, model: {GEMMA} }}
  reviewer_qwen:  {{ base_url: http://up/v1, model: {QWEN} }}

selection:
  default_model: reviewer_gemma
  fallback_model: reviewer_qwen

critic:
  prompt_template: __PROMPT_TEMPLATE__
  max_tokens: 500
  temperature: 0.0
  consistency_rule: true

routes:
  - {{ name: coding,  quality_rubric: "be correct" }}
  - {{ name: general, quality_rubric: "be helpful" }}
"""


@pytest.fixture
def config_path(tmp_path: Path) -> str:
    prompt = tmp_path / "critic_system.txt"
    prompt.write_text(
        "Severity: {severity_scale}\nQuality: {quality_scale}\nRoute: {route}\n"
        "Rubric: {quality_rubric}\n{consistency_rule}\nReturn JSON.",
        encoding="utf-8",
    )
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        CONFIG_YAML.replace("__PROMPT_TEMPLATE__", str(prompt)), encoding="utf-8"
    )
    return str(cfg_path)


@pytest.fixture
def config(config_path: str):
    return load_config(config_path)


def make_request(**overrides):
    """A valid CritiqueRequest with all required fields filled; override any."""
    from agent_critic.models import CritiqueRequest

    base = dict(
        route="coding",
        system_prompt="You are a coding assistant.",
        user_prompt="Return the last element of a list.",
        assistant_response="def last(xs): return xs[-1]",
    )
    base.update(overrides)
    return CritiqueRequest(**base)


def make_client(content: str):
    """An httpx client whose mock transport records requests and returns the
    given critic-model `content` as the chat message."""
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client.seen = seen  # type: ignore[attr-defined]
    return client

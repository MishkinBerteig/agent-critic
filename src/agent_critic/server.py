"""FastAPI service: /v1/critique, /capabilities, /healthz."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import SPEC_VERSION
from .config import Config, load_config
from .critic import critique
from .models import CritiqueRequest


def build_capabilities(config: Config) -> dict:
    return {
        "service": "agent-critic",
        "spec": SPEC_VERSION,
        "endpoints": ["/v1/critique", "/capabilities", "/healthz"],
        "severity_scale": config.critic.severity_scale,
        "quality_scale": config.critic.quality_scale,
        "consistency_rule": config.critic.consistency_rule,
        "routes": [r.name for r in config.routes],
        "critic_models": {k: v.model for k, v in config.critic_models.items()},
        "selection": {
            "default_model": config.selection.default_model,
            "fallback_model": config.selection.fallback_model,
        },
    }


def create_app(config_path: str) -> FastAPI:
    config = load_config(config_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.client = httpx.AsyncClient()
        try:
            yield
        finally:
            await app.state.client.aclose()

    app = FastAPI(title="Agent Critic", version="0.1.0", lifespan=lifespan)
    app.state.config = config

    @app.exception_handler(RequestValidationError)
    async def on_invalid_request(request: Request, exc: RequestValidationError):
        # Surface a clean message (e.g. which required fields are missing)
        # instead of FastAPI's default 422 error array.
        messages = []
        for err in exc.errors():
            msg = str(err.get("msg", "")).removeprefix("Value error, ")
            if err.get("type") == "missing":
                loc = err.get("loc", ())
                msg = f"Missing required field(s): {loc[-1]}" if loc else msg
            messages.append(msg)
        return JSONResponse(status_code=400, content={"error": "; ".join(messages)})

    @app.post("/v1/critique")
    async def critique_endpoint(request: CritiqueRequest):
        env = await critique(app.state.client, config, request)
        return JSONResponse(env.model_dump(), headers={"X-Agent-Critic": SPEC_VERSION})

    @app.get("/capabilities")
    async def capabilities_endpoint():
        return build_capabilities(config)

    @app.get("/healthz")
    async def healthz_endpoint():
        client: httpx.AsyncClient = app.state.client
        seen: dict[str, bool] = {}
        for model_cfg in config.critic_models.values():
            if model_cfg.base_url in seen:
                continue
            try:
                resp = await client.get(
                    model_cfg.base_url.rstrip("/") + "/models",
                    headers={"Authorization": f"Bearer {model_cfg.api_key}"},
                    timeout=httpx.Timeout(5.0, connect=model_cfg.connect_timeout),
                )
                seen[model_cfg.base_url] = resp.status_code < 500
            except Exception:
                seen[model_cfg.base_url] = False
        ok = all(seen.values()) if seen else False
        return {"status": "ok" if ok else "degraded", "upstreams": seen}

    return app

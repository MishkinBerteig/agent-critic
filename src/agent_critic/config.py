"""Configuration schema and loader.

Rubrics, scales, the critic-model pool and prompt template are all data. No
application-domain prompt text ships here — rubrics are written at the category
level; the response under review carries its own system prompt at runtime.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _interpolate_env(value: Any) -> Any:
    if isinstance(value, str):

        def repl(match: re.Match) -> str:
            expr = match.group(1)
            if ":-" in expr:
                name, default = expr.split(":-", 1)
            else:
                name, default = expr, None
            resolved = os.environ.get(name.strip())
            if resolved is None:
                if default is None:
                    raise ValueError(
                        f"Environment variable {name.strip()!r} referenced but not set."
                    )
                return default
            return resolved

        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(v) for v in value]
    return value


def _resolve_path(value: str | None) -> str | None:
    if value is None:
        return None
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return str(p)


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8090


class CriticModelConfig(BaseModel):
    base_url: str
    model: str
    api_key: str = "lm-studio"
    connect_timeout: float = 10.0
    read_timeout: float | None = 600.0


class SelectionConfig(BaseModel):
    default_model: str
    fallback_model: str  # used when the default would be self-criticism


class CriticConfig(BaseModel):
    prompt_template: str = "prompts/critic_system.txt"
    max_tokens: int = 1000
    temperature: float = 0.0
    severity_scale: list[str] = ["CRITICAL", "HIGH", "OTHER", "NONE"]
    quality_scale: list[str] = ["EXCELLENT", "GOOD", "ADEQUATE", "POOR"]
    consistency_rule: bool = True


class RouteRubric(BaseModel):
    name: str
    quality_rubric: str = ""


class Config(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    critic_models: dict[str, CriticModelConfig]
    selection: SelectionConfig
    critic: CriticConfig = Field(default_factory=CriticConfig)
    routes: list[RouteRubric]

    @property
    def routes_by_name(self) -> dict[str, RouteRubric]:
        return {r.name: r for r in self.routes}

    @model_validator(mode="after")
    def _validate(self) -> Config:
        if self.selection.default_model not in self.critic_models:
            raise ValueError(
                f"selection.default_model '{self.selection.default_model}' not in critic_models."
            )
        if self.selection.fallback_model not in self.critic_models:
            raise ValueError(
                f"selection.fallback_model '{self.selection.fallback_model}' not in critic_models."
            )
        names = [r.name for r in self.routes]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate route names.")
        return self


def load_config(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    raw = _interpolate_env(raw)
    config = Config.model_validate(raw)
    config.critic.prompt_template = _resolve_path(config.critic.prompt_template)
    return config

"""Envelope + request schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from . import SPEC_VERSION

# The exchange under review. All three are required; an empty or whitespace-only
# value counts as missing.
REQUIRED_FIELDS = ("system_prompt", "user_prompt", "assistant_response")


class CritiqueRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    route: str
    system_prompt: str
    user_prompt: str
    assistant_response: str
    generator_model: str | None = None  # excluded from critic selection (no self-criticism)
    critic_model: str | None = None  # pin a specific critic

    @model_validator(mode="before")
    @classmethod
    def _require_exchange(cls, data):
        if isinstance(data, dict):
            missing = [f for f in REQUIRED_FIELDS if not str(data.get(f) or "").strip()]
            if missing:
                raise ValueError(f"Missing required field(s): {', '.join(missing)}")
        return data


class Envelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    spec: str = SPEC_VERSION
    route: str | None = None
    critic_model: str | None = None
    severity: str | None = None
    severity_reason: str | None = None
    quality: str | None = None
    quality_reason: str | None = None
    meta: dict = {}

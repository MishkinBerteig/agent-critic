"""Envelope + request schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from . import SPEC_VERSION


class CritiqueRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    route: str
    system_prompt: str = ""
    user_prompt: str = ""
    assistant_response: str = ""
    generator_model: str | None = None  # excluded from critic selection (no self-criticism)
    critic_model: str | None = None  # pin a specific critic


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

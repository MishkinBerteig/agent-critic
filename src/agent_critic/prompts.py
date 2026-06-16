"""Prompt template loading (cached) + render helpers."""

from __future__ import annotations

from pathlib import Path

_cache: dict[str, str] = {}


def load_template(path: str | Path) -> str:
    key = str(path)
    if key not in _cache:
        _cache[key] = Path(path).read_text(encoding="utf-8")
    return _cache[key]

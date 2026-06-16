"""Critic-model selection: a pool with default/fallback and a no-self-criticism
rule (never grade with the model that generated the response, unless pinned)."""

from __future__ import annotations

from .config import Config, CriticModelConfig


def choose_critic(
    config: Config, generator_model: str | None, pinned: str | None
) -> tuple[str, CriticModelConfig]:
    """Return (pool_key, model_config) for the critic to use.

    Priority: an explicit pin wins; otherwise default, then fallback, then any
    remaining pool member whose underlying model id is not the generator's.
    """
    pool = config.critic_models

    if pinned and pinned in pool:
        return pinned, pool[pinned]

    ordered_keys = [config.selection.default_model, config.selection.fallback_model]
    ordered_keys += [k for k in pool if k not in ordered_keys]

    for key in ordered_keys:
        if pool[key].model != generator_model:
            return key, pool[key]

    # Every pool member maps to the generator model — fall back to the default.
    key = config.selection.default_model
    return key, pool[key]

from agent_critic.selection import choose_critic

from .conftest import GEMMA, QWEN


def test_default_when_no_generator(config):
    key, cfg = choose_critic(config, generator_model=None, pinned=None)
    assert key == "reviewer_gemma"
    assert cfg.model == GEMMA


def test_avoids_self_criticism(config):
    # generator IS the default critic model -> must pick the fallback
    key, cfg = choose_critic(config, generator_model=GEMMA, pinned=None)
    assert key == "reviewer_qwen"
    assert cfg.model == QWEN


def test_generator_unrelated_uses_default(config):
    key, _ = choose_critic(config, generator_model="some-other-model", pinned=None)
    assert key == "reviewer_gemma"


def test_pin_overrides(config):
    key, cfg = choose_critic(config, generator_model=None, pinned="reviewer_qwen")
    assert key == "reviewer_qwen"
    assert cfg.model == QWEN


def test_unknown_pin_ignored(config):
    key, _ = choose_critic(config, generator_model=None, pinned="reviewer_zzz")
    assert key == "reviewer_gemma"

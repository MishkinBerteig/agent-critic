import pytest
from pydantic import ValidationError

from agent_critic.config import load_config


def test_loads_pool_and_routes(config):
    assert set(config.critic_models) == {"reviewer_gemma", "reviewer_qwen"}
    assert set(config.routes_by_name) == {"coding", "general"}
    assert config.selection.default_model == "reviewer_gemma"


def test_invalid_default_model(tmp_path):
    cfg = tmp_path / "bad.yaml"
    cfg.write_text(
        """
critic_models:
  a: { base_url: http://x/v1, model: m }
selection: { default_model: nope, fallback_model: a }
routes:
  - { name: general, quality_rubric: g }
""",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_config(cfg)


def test_capabilities_shape(config):
    from agent_critic.server import build_capabilities

    caps = build_capabilities(config)
    assert caps["spec"] == "agent-critic/0.1"
    assert caps["critic_models"]["reviewer_gemma"] == "gemma-model-x"
    assert "coding" in caps["routes"]

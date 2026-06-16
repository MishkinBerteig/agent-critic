from agent_critic.critic import build_envelope, extract_json

from .conftest import make_request


def test_extract_plain_json():
    assert extract_json('{"severity":"NONE"}')["severity"] == "NONE"


def test_extract_json_from_fenced_text():
    text = 'Here is my verdict:\n```json\n{"severity": "HIGH", "quality": "POOR"}\n```\n'
    parsed = extract_json(text)
    assert parsed["severity"] == "HIGH" and parsed["quality"] == "POOR"


def test_extract_json_with_nested_braces():
    parsed = extract_json('prefix {"a": {"b": 1}, "severity": "NONE"} suffix')
    assert parsed["severity"] == "NONE"
    assert parsed["a"] == {"b": 1}


def test_extract_returns_none_on_garbage():
    assert extract_json("no json here") is None


def _req():
    return make_request()


def test_build_envelope_normalizes_case(config):
    parsed = {"severity": "none", "severity_reason": "ok", "quality": "good", "quality_reason": "fine"}
    env = build_envelope(config, _req(), "gemma-model-x", parsed, 100)
    assert env.severity == "NONE"
    assert env.quality == "GOOD"
    assert env.meta["latency_ms"] == 100


def test_consistency_rule_clamps_quality(config):
    parsed = {"severity": "HIGH", "severity_reason": "bug", "quality": "EXCELLENT", "quality_reason": "nice"}
    env = build_envelope(config, _req(), "gemma-model-x", parsed, 50)
    assert env.severity == "HIGH"
    assert env.quality == "ADEQUATE"  # clamped down
    assert env.meta["consistency_clamped_from"] == "EXCELLENT"


def test_out_of_scale_falls_back(config):
    parsed = {"severity": "SUPER-BAD", "quality": "MEH"}
    env = build_envelope(config, _req(), "gemma-model-x", parsed, 10)
    assert env.meta.get("fallback") is True
    assert env.severity == "OTHER"

"""Guards on the shipped critic prompt template (prompts/critic_system.txt):
every placeholder is substituted and the rendered prompt contains no stray
template braces — the doubled-brace regression that left `{{ ... }}` in the
JSON skeleton sent to the critic model."""

from pathlib import Path

from agent_critic.config import Config
from agent_critic.critic import render_system_prompt

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "prompts" / "critic_system.txt"
PLACEHOLDERS = [
    "{severity_scale}",
    "{quality_scale}",
    "{route}",
    "{quality_rubric}",
    "{consistency_rule}",
]


def _config_with_real_template() -> Config:
    return Config.model_validate(
        {
            "critic_models": {
                "a": {"base_url": "http://x/v1", "model": "m"},
                "b": {"base_url": "http://y/v1", "model": "n"},
            },
            "selection": {"default_model": "a", "fallback_model": "b"},
            "critic": {"prompt_template": str(TEMPLATE), "consistency_rule": True},
            "routes": [{"name": "coding", "quality_rubric": "be correct"}],
        }
    )


def test_shipped_template_declares_all_placeholders():
    text = TEMPLATE.read_text(encoding="utf-8")
    for placeholder in PLACEHOLDERS:
        assert placeholder in text, f"{placeholder} missing from the shipped template"


def test_render_substitutes_every_placeholder():
    out = render_system_prompt(_config_with_real_template(), "coding")
    for placeholder in PLACEHOLDERS:
        assert placeholder not in out, f"{placeholder} left unsubstituted in rendered prompt"


def test_render_has_no_stray_template_braces():
    # The original bug rendered the JSON example as {{ ... }} because the author
    # wrote it for str.format while the renderer uses str.replace.
    out = render_system_prompt(_config_with_real_template(), "coding")
    assert "{{" not in out
    assert "}}" not in out


def test_render_emits_single_brace_json_skeleton():
    out = render_system_prompt(_config_with_real_template(), "coding")
    compact = out.replace(" ", "")
    assert '{"severity":"..."' in compact
    assert '"quality_reason":"..."}' in compact


def test_render_injects_route_and_rubric():
    out = render_system_prompt(_config_with_real_template(), "coding")
    assert "coding" in out
    assert "be correct" in out  # the route's rubric text

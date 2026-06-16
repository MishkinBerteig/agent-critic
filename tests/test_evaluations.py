"""Guards on the shipped baseline evaluation set and the harness logic that
does not need a live model. The live run is exercised by `agent-critic-eval`."""

from pathlib import Path
from types import SimpleNamespace

from agent_critic.evaluate import Case, complies, load_cases, load_rubrics

EVALDIR = Path(__file__).resolve().parent.parent / "evaluations"
SEVERITY_SCALE = {"CRITICAL", "HIGH", "OTHER", "NONE"}
QUALITY_SCALE = {"EXCELLENT", "GOOD", "ADEQUATE", "POOR"}


def _env(severity, quality, *, fallback=False):
    meta = {"fallback": True} if fallback else {}
    return SimpleNamespace(severity=severity, quality=quality, meta=meta)


def test_rubrics_load_and_are_nonempty():
    rubrics = load_rubrics(EVALDIR)
    assert rubrics
    assert all(text.strip() for text in rubrics.values())


def test_shipped_cases_are_well_formed():
    rubrics = load_rubrics(EVALDIR)
    cases = load_cases(EVALDIR)
    assert len(cases) >= 6
    assert len({c.id for c in cases}) == len(cases)  # ids unique
    for c in cases:
        assert c.route in rubrics, f"{c.id}: unknown route {c.route!r}"
        assert c.system_prompt and c.user_prompt and c.assistant_response
        assert c.expected_severity and set(c.expected_severity) <= SEVERITY_SCALE
        assert c.expected_quality and set(c.expected_quality) <= QUALITY_SCALE


def test_shipped_set_covers_both_clean_and_buggy():
    cases = load_cases(EVALDIR)
    clean = [c for c in cases if c.expected_severity == ["NONE"]]
    buggy = [c for c in cases if "HIGH" in c.expected_severity]
    assert clean and buggy, "expect a mix of clean (NONE) and error (HIGH) cases"


def test_complies_membership():
    case = Case("x", "coding", "s", "u", "a", ["NONE"], ["GOOD", "EXCELLENT"])
    assert complies(_env("NONE", "GOOD"), case)
    assert complies(_env("NONE", "EXCELLENT"), case)
    assert not complies(_env("HIGH", "GOOD"), case)  # wrong severity
    assert not complies(_env("NONE", "POOR"), case)  # wrong quality


def test_fallback_never_complies_even_if_values_match():
    case = Case("x", "coding", "s", "u", "a", ["OTHER"], ["ADEQUATE"])
    assert not complies(_env("OTHER", "ADEQUATE", fallback=True), case)

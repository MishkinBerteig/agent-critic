# Baseline evaluations

A small set of **deliberately obvious** examples for sanity-checking a critic
model. Each case is a short exchange (system prompt, user request, assistant
response) paired with the verdict a competent critic should return. They test
*baseline* capability — can the model tell a correct answer from a clearly wrong
one and emit a valid verdict — not frontier judgment on subtle cases.

The harness runs every case several times (default **5**) so you can see both
**compliance** (did the verdict match?) and **speed/consistency** (how fast,
how stable across repeats?).

## Run it

You need a working `config/config.yaml` with at least one critic model (see the
top-level [README](../README.md#configuration)).

```bash
# from the repo root, in the project venv (uv pip install -e ".[dev]")
agent-critic-eval --config config/config.yaml
# or: python -m agent_critic.evaluate --config config/config.yaml
```

Useful flags:

| Flag | Default | Purpose |
|---|---|---|
| `--config` | `config/config.yaml` | Deployment config providing the critic-model endpoint(s). |
| `--critic` | selection default | Pool **key** to pin as the critic (e.g. `reviewer_gemma`) so you evaluate one specific model. |
| `--repeats` | `5` | Runs per case — drives the speed/consistency tracking. |
| `--threshold` | `0.6` | Minimum fraction of the repeats that must comply for a case to pass. |
| `--max-latency-ms` | none | Flag cases whose mean latency exceeds this. |
| `--evaldir` | `evaluations` | Where `rubrics.yaml` and `cases/` live. |

Sample output:

```
CASE                               ROUTE    STATUS COMPLY  OBSERVED sev/qual        LATENCY ms min/mean/max
coding-correct-last-element        coding   PASS   5/5     NONE / GOOD              180 / 220 / 260
coding-offbyone-last-element       coding   PASS   5/5     HIGH / ADEQUATE          190 / 240 / 310
...
Summary: 10/10 cases passed · 49/50 runs complied · 1 fallback envelope(s) · overall latency mean 235 ms
```

Exit code is `0` when every case passes its threshold, `1` otherwise — so it can
gate a model swap in CI.

## How a case is judged

`severity` is the primary, objective axis (a clear error ⇒ `HIGH`/`CRITICAL`; a
clean answer ⇒ `NONE`). `quality` is fuzzier, so the consistency rule does much
of the work: a `HIGH`/`CRITICAL` verdict is clamped to at most `ADEQUATE`, which
is exactly what the buggy cases expect. A **fallback** envelope (the critic
couldn't produce a usable JSON verdict) never counts as compliant.

## File format

`rubrics.yaml` holds the per-route quality rubrics; the harness injects them into
the critic config at run time, so the rubric travels with this evaluation set
rather than depending on your local config's routes.

Each file in `cases/` is one example:

```json
{
  "id": "coding-offbyone-last-element",
  "route": "coding",
  "system_prompt": "You are a coding assistant. Answer with Python.",
  "user_prompt": "Write a function that returns the last element of a list.",
  "assistant_response": "def last(xs):\n    return xs[len(xs)]",
  "expected": { "severity": ["HIGH", "CRITICAL"], "quality": ["POOR", "ADEQUATE"] }
}
```

- `route` must name a route defined in `rubrics.yaml`.
- `expected.severity` / `expected.quality` may be a single string or a list of
  acceptable values (membership check) — lists absorb harmless variation between
  models on the fuzzier quality axis.

## Adding cases

Drop another `cases/*.json` file following the format above. Keep them obvious:
one clear correct answer or one clear error per case. `tests/test_evaluations.py`
validates that every shipped case is well-formed and references a known route
with in-scale expected values, so a malformed case is caught by `pytest`.

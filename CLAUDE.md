# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Agent Critic is a standalone HTTP service (FastAPI) that evaluates an AI response and returns a **Critique Envelope** — a small, versioned JSON verdict with two independent axes: `severity` (CRITICAL/HIGH/OTHER/NONE) and `quality` (EXCELLENT/GOOD/ADEQUATE/POOR). It is consumer-agnostic: it produces the verdict and the caller decides what to do with it. The envelope schema is the product; it is specified in `SPEC.md` (spec id `agent-critic/0.1`).

## Commands

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run pytest                      # full suite; critic-model client is mocked, no live models needed
uv run pytest tests/test_critic.py # single file
uv run pytest tests/test_selection.py::test_name -q   # single test

uv run ruff check src tests        # lint
uv run ruff check --fix src tests  # lint + autofix
uv run ruff format src tests       # format

agent-critic-eval --config config/config.yaml   # baseline evals: run evaluations/cases/*.json N× against a critic model

agent-critic --config config/config.yaml   # run the service (after `uv tool install .` or in the venv)
docker compose up -d                        # containerized; publishes :8090, bind-mounts config/config.yaml
```

Ruff is the linter/formatter, configured in `pyproject.toml` under `[tool.ruff]` (line-length 120; rule sets E/W/F/I/UP/B). Tests use `asyncio_mode = "auto"` (pytest-asyncio), so `async def test_*` functions run without an explicit marker.

`config/config.yaml` is gitignored. Copy `config/config.example.yaml` to it before running anything that loads config (including the service). Tests do **not** need it — `tests/conftest.py` builds its own tmp config and prompt template.

## Architecture

The request flow lives in `src/agent_critic/` and is a single pass with no persistence:

1. **`config.py`** — Pydantic schema + `load_config()`. Everything is data: the critic-model pool, severity/quality scales, per-route quality rubrics, the prompt template path, and the consistency-rule toggle. `load_config` interpolates `${VAR}` / `${VAR:-default}` env references throughout the YAML before validation, and resolves the prompt-template path. A `model_validator` enforces that `selection.default_model`/`fallback_model` exist in `critic_models` and route names are unique.
2. **`selection.py`** — `choose_critic()` picks the critic from the pool. Priority: explicit pin → `default_model` → `fallback_model` → any other member whose underlying model id is not the generator's. This is the **no-self-criticism** rule ("don't grade your own homework"): the generator model is skipped. Keep ≥2 models in the pool so a non-generator critic always exists.
3. **`prompts.py` + `prompts/critic_system.txt`** — the system prompt is a template with `{severity_scale}`, `{quality_scale}`, `{route}`, `{quality_rubric}`, `{consistency_rule}` placeholders, filled by `critic.render_system_prompt`.
4. **`critic.py`** — the core. `critique(client, config, request)` renders the prompt, POSTs to the chosen model's OpenAI-compatible `/chat/completions` (temp 0), then `extract_json` pulls the first balanced JSON object from the reply, `_normalize` validates values against the scales, and `build_envelope` applies the consistency rule (a CRITICAL/HIGH severity clamps quality to ADEQUATE, recording `consistency_clamped_from` in `meta`).
5. **`server.py`** — `create_app(config_path)` wires three endpoints: `POST /v1/critique`, `GET /capabilities`, `GET /healthz`. A single shared `httpx.AsyncClient` is created in the lifespan and reused across requests. Every critique response carries the `X-Agent-Critic: agent-critic/0.1` header.
6. **`cli.py`** — `agent-critic` console script; argparse `--config/--host/--port` over the config's server block.
7. **`evaluate.py`** — the `agent-critic-eval` console script and baseline-evaluation harness. Loads `evaluations/rubrics.yaml` + `evaluations/cases/*.json`, **injects those rubrics into the config's `routes`** (so the rubric travels with the eval set, not the deployment config), runs each case N× (default 5) via `critique`, and reports per-case severity/quality compliance + latency. Cases are deliberately simple/obvious. A fallback envelope never counts as compliant. `tests/test_evaluations.py` validates the shipped cases and the pure logic without a live model.

### Key invariant: `critique()` never raises

Every failure path — network error, non-JSON reply, out-of-scale verdict — returns a deterministic **fallback envelope** (`severity=OTHER`, `quality=ADEQUATE`, `meta.fallback=true`) via `_fallback()`. When changing `critic.py`, preserve this: callers depend on always getting a well-formed envelope. `critique_once()` is the in-process embedding entry point that manages its own one-shot client.

### Critic models

Each pool entry is an independent OpenAI-compatible endpoint (`base_url` + `model` + `api_key`), so local servers (LM Studio, vLLM, Ollama) and hosted APIs can be mixed freely. The reference deployment runs two LM Studio models that critique each other's output. `critic.max_tokens` must be generous — reasoning critics need room to think before emitting the JSON verdict.

## Conventions

- The spec version is the single constant `SPEC_VERSION` in `src/agent_critic/__init__.py`. It appears in every envelope (`spec` field), the response header, and `/capabilities`. Bump it there if the envelope schema changes, and update `SPEC.md`.
- No application-domain prompt text ships in this repo. Rubrics in config are written at the category level (`coding`, `long_form_writing`, `agentic`, `general`); the response under review supplies its own system prompt at runtime via the request body.
- `CritiqueRequest` ignores extra fields; `Envelope` allows them — clients can pass extra context and the envelope's `meta` can carry extra keys.
- `route`, `system_prompt`, `user_prompt`, and `assistant_response` are required on `CritiqueRequest` (a `model_validator` treats empty/whitespace as missing). This is request validation, distinct from the never-raises critique path: a malformed request returns HTTP 400 (via the `RequestValidationError` handler in `server.py`) naming the missing fields, whereas a downstream failure during an accepted critique returns a fallback envelope.

See `PLAN.md` for design rationale and `SPEC.md` for the full envelope schema.

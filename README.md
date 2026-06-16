# Agent Critic

**A standalone service that evaluates an AI response and returns a structured
verdict — the Critique Envelope.**

Agent Critic judges a response on two independent axes: **severity** (are there
errors or risks?) and **quality** (how well does it do its job, by a
route-specific rubric?). It is consumer-agnostic — any client can POST a
response and receive a deterministic, machine-readable verdict, then decide what
to do with it (revise, warn, block, or ignore).

> **Status:** v0.1 · **License:** MIT · **Runtime:** Python 3.12 + [uv](https://docs.astral.sh/uv/) **and** Docker · **Spec:** [`agent-critic/0.1`](./SPEC.md)

Agent Critic owns the envelope **specification** ([SPEC.md](./SPEC.md)). It runs
as an HTTP service (or embeds in-process) and is consumed by any agent harness,
gateway, or application that wants an independent verdict on a generated
response.

---

## Contents

- [Why](#why)
- [The Critique Envelope](#the-critique-envelope)
- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [Endpoints](#endpoints)
- [Configuration](#configuration)
  - [Mixing local and hosted endpoints](#mixing-local-and-hosted-endpoints)
  - [Environment variables](#environment-variables)
  - [No self-criticism](#no-self-criticism)
  - [Rubrics, scales, and the consistency rule](#rubrics-scales-and-the-consistency-rule)
- [Reference deployment](#reference-deployment)
- [Embedding in-process](#embedding-in-process)
- [Development](#development)
- [Security](#security)
- [License](#license)

---

## Why

Critique should be a reusable **protocol**, not a hidden feature of one product.
A small, versioned envelope lets any agent harness obtain an independent verdict
on a response and consume it in a context-dependent way. Agent Critic is the
reference producer of that envelope.

## The Critique Envelope

```json
{
  "spec": "agent-critic/0.1",
  "route": "coding",
  "critic_model": "gemma-4-31b-mlx",
  "severity": "HIGH",
  "severity_reason": "Off-by-one in the loop bound drops the last record.",
  "quality": "ADEQUATE",
  "quality_reason": "Correct shape but misses an edge case and lacks validation.",
  "meta": { "latency_ms": 210 }
}
```

- **Severity:** `CRITICAL | HIGH | OTHER | NONE` — the single highest that applies.
- **Quality:** `EXCELLENT | GOOD | ADEQUATE | POOR` — judged with the route's rubric.
- **Consistency rule:** a `CRITICAL`/`HIGH` severity cannot earn `EXCELLENT`/`GOOD`
  quality (quality is clamped to `ADEQUATE`).

The full, versioned schema and conventions live in [SPEC.md](./SPEC.md).

## How it works

```
inputs: route, system_prompt, user_prompt, assistant_response (+ optional generator_model / critic_model)
→ select critic model (pool + default/fallback, excluding the generator)
→ render critic prompt (severity scale + route quality rubric + consistency rule)
→ call the critic model (temp 0)
→ parse strict JSON; normalize + apply consistency rule
→ on any failure, emit a deterministic fallback envelope (never raise)
→ return the envelope
```

## Quick start

### Docker (recommended)

```bash
cp config/config.example.yaml config/config.yaml   # then edit for your models
docker compose up -d
curl http://localhost:8090/capabilities
```

The container publishes port **8090** and reads `config/config.yaml` via a
bind-mount (edit + restart, no rebuild).

### Native (Python + uv)

```bash
uv tool install .
agent-critic --config config/config.yaml
```

### First critique

```bash
curl http://localhost:8090/v1/critique -H 'Content-Type: application/json' -d '{
  "route":"coding",
  "system_prompt":"You are a coding assistant.",
  "user_prompt":"Return the last element of a list.",
  "assistant_response":"def last(xs): return xs[len(xs)]",
  "generator_model":"qwen3.6-35b-a3b"
}'
```

## Endpoints

| Method & path | Purpose |
|---|---|
| `POST /v1/critique` | Evaluate a response → Critique Envelope. |
| `GET /capabilities` | Spec version, scales, routes/rubrics, critic-model pool. |
| `GET /healthz` | Liveness + critic-model reachability. |

Every critique response carries the `X-Agent-Critic: agent-critic/0.1` header.

**Request body** for `/v1/critique`:

| Field | Required | Notes |
|---|---|---|
| `route` | yes | Selects the quality rubric. |
| `system_prompt`, `user_prompt`, `assistant_response` | no | The exchange under review. |
| `generator_model` | no | Excluded from critic selection (no self-criticism). |
| `critic_model` | no | Pin a specific critic from the pool. |

## Configuration

All behavior is data in `config/config.yaml` (copy from
`config/config.example.yaml`). Rubrics are written at the **category** level; the
response under review carries its own system prompt at runtime — no
application-domain text ships here.

### Mixing local and hosted endpoints

Each critic model is an independent OpenAI-compatible endpoint with its own
`base_url` and `api_key`. Mix local servers (LM Studio, llama.cpp, vLLM, Ollama)
and hosted APIs (OpenAI, Together, …) freely; any value can interpolate an
environment variable as `${VAR}` or `${VAR:-default}`.

```yaml
critic_models:
  reviewer_local:  { base_url: http://localhost:1234/v1, model: gemma-4-31b-mlx, api_key: lm-studio }
  reviewer_remote: { base_url: https://api.openai.com/v1, model: gpt-4o, api_key: "${OPENAI_API_KEY}" }
```

### Environment variables

Any config value may reference an environment variable:

- `${VAR}` — **required**; config loading fails with a clear error if it is unset.
- `${VAR:-default}` — **optional**; falls back to `default` when unset.

The configs in this repo reference:

| Variable | Used by | Required? | Notes |
|---|---|---|---|
| `LM_STUDIO_BASE` | critic-model `base_url`s (reference deployment) | No (has a default) | Repoints the whole local pool at once, e.g. `http://host.docker.internal:12345/v1`. |
| `OPENAI_API_KEY` | hosted critic `api_key` (example) | Only if you use a hosted endpoint that needs a key | Referenced as `${OPENAI_API_KEY}` (no default), so loading fails loudly if it's missing. |

Add your own as needed — any `${VAR}` works. In Docker, set them under
`environment:` in `docker-compose.yaml` (where `LM_STUDIO_BASE` is already set).
Never commit real keys.

### No self-criticism

A request may include the `generator_model` id; the critic then **avoids
choosing that model** ("don't grade your own homework"), falling back to another
pool member. Keep at least two models in the pool so the rule can always find a
non-generator critic. A request may also `critic_model`-pin a specific reviewer.

### Rubrics, scales, and the consistency rule

`severity_scale`, `quality_scale`, the per-route `quality_rubric`s, and
`consistency_rule` are all config. The default rubrics cover `long_form_writing`,
`coding`, `agentic`, and `general` (common assistant task categories). Set
`max_tokens` generously — reasoning critics need room to think before emitting
the JSON verdict.

## Reference deployment

The committed `config/config.example.yaml` is a template. The actual local
deployment in this environment (`config/config.yaml`, gitignored) uses LM Studio
on `127.0.0.1:12345`:

| Pool key | Model | Role |
|---|---|---|
| reviewer_gemma | `gemma-4-31b-mlx` | default critic (non-reasoning → reliable JSON, fast) |
| reviewer_qwen | `qwen3.6-35b-a3b` | fallback (used when gemma would be the generator) |

So a qwen-generated answer is judged by gemma and vice versa. `critic.max_tokens`
is `1000`, `temperature` `0.0`, `consistency_rule` on. The model `base_url`s
default to `${LM_STUDIO_BASE:-http://127.0.0.1:12345/v1}`.

## Embedding in-process

To use the critic without the HTTP service:

```python
import asyncio
from agent_critic.config import load_config
from agent_critic.models import CritiqueRequest
from agent_critic.critic import critique_once

cfg = load_config("config/config.yaml")
env = asyncio.run(critique_once(cfg, CritiqueRequest(
    route="coding", assistant_response="def last(xs): return xs[len(xs)]")))
print(env.severity, env.quality)
```

## Development

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run pytest            # unit tests; mocked critic-model client, no live models needed
```

Layout: `src/agent_critic/` (`config`, `models`, `selection`, `prompts`,
`critic`, `server`, `cli`); tests under `tests/`. See [PLAN.md](./PLAN.md) for
design notes and [SPEC.md](./SPEC.md) for the envelope schema.

## Security

There is **no authentication yet**. The Docker deployment binds `0.0.0.0` — only
expose it on a trusted network, or place an authenticating reverse proxy in
front. Never commit real API keys; pass them via environment variables
referenced as `${VAR}` in the config.

## License

[MIT](./LICENSE) © 2026 Mishkin Berteig

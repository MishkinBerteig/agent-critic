# Agent Critic — Implementation Plan

Status: **planning** · License: TBD (intended open-source) · Runtime: Python + uv **and** Docker

## 1. Purpose

Agent Critic is a standalone service that evaluates a model response and returns
a structured **Critique Envelope**: an independent, deterministic verdict on a
response's *severity* (are there errors?) and *quality* (how well does it do its
job, judged by a route-specific rubric?).

It is designed to become a small, reusable **protocol** that any agent harness
can consume in a configurable, context-dependent way — not a one-off feature of
a single product. Agent Critic owns the envelope **specification**.

Agent Critic is consumer-agnostic: any client — an agent harness, a routing
gateway, or an application — can POST a generated response and receive a verdict,
then decide what to do with it (revise, warn, block, or ignore). It runs as an
HTTP service or embeds in-process.

## 2. The Critique Envelope (the standard)

`SPEC.md` (a Phase 1 deliverable) defines a versioned, vendor-neutral schema:

```json
{
  "spec": "agent-critic/0.1",
  "route": "coding",
  "critic_model": "<model-id>",
  "severity": "HIGH",
  "severity_reason": "Off-by-one in the loop bound drops the last record.",
  "quality": "ADEQUATE",
  "quality_reason": "Correct shape but misses an edge case and lacks validation.",
  "meta": { "latency_ms": 210 }
}
```

- **Severity scale:** `CRITICAL | HIGH | OTHER | NONE` — exactly one value, the
  single highest that applies.
- **Quality scale:** `EXCELLENT | GOOD | ADEQUATE | POOR` — judged with the
  rubric for the request's route type only.
- **Consistency rule:** a `CRITICAL` or `HIGH` severity cannot earn `EXCELLENT`
  or `GOOD` quality.
- **Detection convention:** services advertise support via an
  `X-Agent-Critic: agent-critic/0.1` header and a `/capabilities` endpoint.

The envelope is returned as structured data. *Placement* into a host response
stream (top-level field, terminal chunk, content trailer) is the consumer's job
and is documented in SPEC.md as a recommended convention, not enforced here.

## 3. Evaluation model

The critic receives four inputs and a route type, then prompts a critic model:

```
inputs: route_type, system_prompt, last_user_prompt, last_assistant_response
→ select rubric by route_type
→ render critic prompt (severity rubric + route quality rubric + scales + consistency rule)
→ call critic model (temp 0, small max_tokens)
→ parse strict JSON; on failure emit a deterministic fallback envelope
→ return envelope
```

### Critic-model selection & no self-criticism
The critic maintains a pool of available critic models. The request may include
the **id of the model that generated the response**; the critic then avoids
choosing that model (no self-criticism), falling back to another pool member.
The request may also pin a specific critic model. This keeps the
"don't grade your own homework" policy configurable on either side of the
contract.

## 4. Public interface

- `POST /v1/critique` — body: `{ route, system_prompt, user_prompt, assistant_response, generator_model?, critic_model? }` → returns a Critique Envelope.
- `GET  /capabilities` — spec version, available routes/rubrics, critic-model pool.
- `GET  /healthz` — liveness + critic-model reachability.

A thin library entry point (`critique(...) -> Envelope`) is also exposed so the
service can be embedded in-process instead of over HTTP.

## 5. Configuration (everything generic lives here)

Rubrics, scales, the critic-model pool, and prompt templates are all data. No
application-domain prompt text ships in this repo — rubrics are written at the
*category* level (writing, coding, agentic, general), and the response under
review carries its own system prompt at runtime.

```yaml
server: { host: 127.0.0.1, port: 8090 }

critic_models:
  reviewer_a: { base_url: http://127.0.0.1:8083/v1, model: <model-a> }
  reviewer_b: { base_url: http://127.0.0.1:8082/v1, model: <model-b> }

selection:
  default_model: reviewer_a
  fallback_model: reviewer_b      # used when default would be self-criticism

critic:
  prompt_template: prompts/critic_system.txt
  max_tokens: 200
  temperature: 0.0
  severity_scale: [CRITICAL, HIGH, OTHER, NONE]
  quality_scale:  [EXCELLENT, GOOD, ADEQUATE, POOR]
  consistency_rule: true

routes:
  - name: long_form_writing
    quality_rubric: |
      - Obeys all stated style/format constraints from the system prompt.
      - Follows the required multi-step process and asks for feedback in turn.
      - Clear thesis, coherent structure, logical flow.
      - Genuine insight and depth rather than filler.
  - name: coding
    quality_rubric: |
      - Correct and free of logic errors.
      - Complete; handles relevant edge cases.
      - Readable, idiomatic, maintainable.
      - Safe; no obvious security or data-loss issues.
  - name: agentic
    quality_rubric: |
      - Right tools/actions, sensibly sequenced.
      - Real progress toward or completion of the goal.
      - Efficient; avoids redundant steps.
      - Safe side effects; verifies results.
  - name: general
    quality_rubric: |
      - Accurate; no fabrication.
      - Relevant and direct.
      - Clear and appropriately concise.
      - Helpful and complete without padding.
```

## 6. Tech stack

- **Python 3.12, managed by `uv`.** `pyproject.toml`; installable via
  `uv tool install .` → console script `agent-critic`. uv owns the environment.
- **Docker.** A uv-based `Dockerfile` + `docker-compose.yaml`. Both run modes
  are first-class and documented.
- FastAPI + uvicorn (server), httpx (async critic-model client), pydantic
  (config + envelope schema), PyYAML (config).
- Binds `127.0.0.1` by default; **no authentication yet** — see Risks.

## 7. Repository layout

```
README.md   PLAN.md   SPEC.md   LICENSE   pyproject.toml   .gitignore
Dockerfile  docker-compose.yaml  .dockerignore
config/  config.example.yaml   config.yaml (gitignored)
prompts/ critic_system.txt
src/agent_critic/
  cli.py  config.py  models.py        # envelope + request schemas
  selection.py                        # critic-model pool + no-self-criticism
  prompts.py  critic.py               # render prompt, call model, parse
  server.py                           # /v1/critique, /capabilities, /healthz
tests/ test_config.py test_critic.py test_selection.py test_envelope.py
```

## 8. Build phases

1. **Scaffold + SPEC.md v0.1** — pyproject, `.gitignore`, README, example
   config, critic prompt template, Dockerfile + compose, the envelope spec.
2. **Config + envelope schema** — pydantic models, loader, validation.
3. **Selection** — critic-model pool, default/fallback, no-self-criticism.
4. **Critic core** — prompt render with per-route rubric, model call, strict
   JSON parse, consistency rule, deterministic fallback envelope.
5. **Service** — `/v1/critique`, `/capabilities`, `/healthz`, detection header.
6. **Library entry point** — in-process `critique(...)`.
7. **Docs** — README, SPEC finalize, container + native run guides.

## 9. Testing strategy

- Unit tests with a mocked critic-model client (no live models in CI).
- Golden fixtures covering each route's rubric and the consistency rule, plus a
  known-good verdict regression case.
- Parser tests for malformed model output → fallback envelope.
- A manual smoke test against a live local critic model via `curl` — no specific
  agent harness assumed.

## 10. Risks & mitigations

- **Malformed critic output** → strict parse with a deterministic fallback
  envelope; never raise to the caller.
- **Self-criticism** → enforced via generator-model exclusion + fallback.
- **Rubric drift across consumers** → versioned `SPEC.md`; envelope carries its
  `spec` field.
- **No auth, local-only bind** → documented prominently before any exposure.

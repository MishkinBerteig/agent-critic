# Critique Envelope Specification — `agent-critic/0.1`

A versioned, vendor-neutral schema for an independent verdict on an AI
assistant response. Any service may produce it; any consumer may place it into
its own response in a context-dependent way.

## Envelope

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

| Field | Type | Notes |
|-------|------|-------|
| `spec` | string | Always `agent-critic/<version>`. This document is `0.1`. |
| `route` | string | The route/category the response was judged under. |
| `critic_model` | string | Model that produced the verdict (never the generator, unless pinned). |
| `severity` | enum | One of the severity scale, the single highest that applies. |
| `severity_reason` | string | One-sentence justification. |
| `quality` | enum | One of the quality scale, judged with the route's rubric. |
| `quality_reason` | string | One-sentence justification. |
| `meta` | object | Free-form; includes `latency_ms`. May include `fallback: true`. |

### Severity scale (errors / risk)

`CRITICAL | HIGH | OTHER | NONE` — exactly one value, the single highest that
applies.

- **CRITICAL** — unsafe, harmful, or catastrophically wrong.
- **HIGH** — clear factual/logical error that defeats the response's purpose.
- **OTHER** — minor issues, or the verdict could not be fully determined.
- **NONE** — no detected errors.

### Quality scale (fitness for purpose)

`EXCELLENT | GOOD | ADEQUATE | POOR` — judged with the rubric for the request's
route only.

### Consistency rule

A `CRITICAL` or `HIGH` severity **cannot** earn `EXCELLENT` or `GOOD` quality.
Producers must clamp quality to at most `ADEQUATE` when this is violated.

## Detection convention

A service that speaks this spec advertises it via:

- the response header `X-Agent-Critic: agent-critic/0.1`, and
- a `GET /capabilities` endpoint listing the spec version, available
  routes/rubrics, and the critic-model pool.

## Placement (consumer's job, not enforced here)

How the envelope is attached to a host response is the consumer's decision. The
recommended conventions for OpenAI-compatible responses:

- **Non-streaming:** a top-level `critique` field on the response object.
- **Streaming (chat):** on the terminal `finish_reason: "stop"` chunk.
- **Responses API:** on the terminal `response.completed` object.
- **Trailer:** appended to the assistant content for strict clients.

## Request contract

`POST /v1/critique`

```json
{
  "route": "coding",
  "system_prompt": "…",
  "user_prompt": "…",
  "assistant_response": "…",
  "generator_model": "qwen3.6-35b-a3b",   // optional: excluded from critic selection
  "critic_model": "gemma-4-31b-mlx"        // optional: pin a specific critic
}
```

`route`, `system_prompt`, `user_prompt`, and `assistant_response` are
**required**; an empty or whitespace-only value for one of the three exchange
fields counts as missing. A request missing any of them is rejected with HTTP
`400` and a body naming the missing field(s):

```json
{ "error": "Missing required field(s): user_prompt, assistant_response" }
```

A well-formed request returns a Critique Envelope. The fallback-envelope
guarantee covers *internal* failures only — once a request is accepted, any
downstream failure (critic-model error, unparseable output) yields a
deterministic fallback envelope rather than an error to the caller.

# Contributing to Agent Critic

Thanks for your interest in improving Agent Critic. It's a small, focused
project — a standalone service that produces the [Critique Envelope](./SPEC.md) —
so contributions that keep it simple and well-tested are very welcome.

## Development setup

Agent Critic uses Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/MishkinBerteig/agent-critic.git
cd agent-critic
uv venv --python 3.12
uv pip install -e ".[dev]"
```

## Tests & code style

```bash
uv run pytest                 # unit tests — mocked critic-model client, no live model needed
uv run ruff check src tests   # lint
uv run ruff format src tests  # format
```

Please make sure `pytest` and `ruff check` are both green before opening a pull
request, and add tests for any behavior you change.

## Pull requests & commits

- Branch off `main`, and keep each pull request focused on a single change.
- Make sure the tests and linter pass.
- Update the docs (`README.md`, `SPEC.md`, etc.) when your change affects them.
- Write commit messages with a short summary line followed by these three
  sections:

  ```
  <short summary line>

  ## Problem
  What is wrong, missing, or needed — and why it matters.

  ## Solution
  What you changed and the approach you took.

  ## Verification
  How you confirmed it works (tests run, commands, observed output).
  ```

## Reporting issues

Found a bug or have an idea? Please
[open an issue](https://github.com/MishkinBerteig/agent-critic/issues).

## Contributing to the evaluations library

The [`evaluations/`](./evaluations/) folder holds a set of simple, "obvious"
example exchanges used to sanity-check a critic model's baseline capability. New
cases are a great, low-friction way to contribute — see
[`evaluations/README.md`](./evaluations/README.md) for the full format.

To add a case, drop a new `evaluations/cases/<name>.json` file:

```json
{
  "id": "general-capital-wrong",
  "route": "general",
  "system_prompt": "You are a helpful assistant.",
  "user_prompt": "What is the capital of France?",
  "assistant_response": "The capital of France is Berlin.",
  "expected": { "severity": ["HIGH", "CRITICAL"], "quality": ["POOR", "ADEQUATE"] }
}
```

Guidelines:

- `route` must name a route defined in
  [`evaluations/rubrics.yaml`](./evaluations/rubrics.yaml).
- `expected.severity` / `expected.quality` may be a single string or a list of
  acceptable values (membership check).
- **Keep cases obvious** — one clearly correct answer or one clear error each.
  These test baseline capability, not frontier judgment, so avoid subtle or
  tricky examples.
- Run the suite against a model with `agent-critic-eval --config config/config.yaml`,
  and validate the case files with `uv run pytest tests/test_evaluations.py`.

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](./LICENSE).

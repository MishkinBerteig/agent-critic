# uv-based image. Deps installed system-wide; exposes the `agent-critic` script.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .

COPY prompts ./prompts
COPY config ./config

EXPOSE 8090

CMD ["agent-critic", "--config", "config/config.yaml"]

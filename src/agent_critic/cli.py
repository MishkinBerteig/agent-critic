"""Console entry point: `agent-critic --config config/config.yaml`."""

from __future__ import annotations

import argparse

import uvicorn

from .server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent-critic")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config YAML.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    app = create_app(args.config)
    config = app.state.config
    host = args.host or config.server.host
    port = args.port or config.server.port
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

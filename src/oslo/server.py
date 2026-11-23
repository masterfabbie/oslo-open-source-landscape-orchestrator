"""Entry point of ``oslo-server``."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import uvicorn

from .api import create_app
from .db import SchemaError, create_engine, upgrade_database
from .settings import Settings, SettingsError


async def _prepare_database(database_url: str) -> None:
    """Migrate the schema before serving, so an unusable database fails clearly."""
    engine = create_engine(database_url)
    try:
        backup = await upgrade_database(engine, database_url)
    finally:
        await engine.dispose()
    if backup:
        print(f"Database migrated; backup before the migration: {backup}")


def main() -> None:
    parser = argparse.ArgumentParser(description="OSLO server")
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--mock",
        action="store_true",
        help="connect to the built-in simulated landscape instead of real hosts",
    )
    args = parser.parse_args()

    try:
        settings = Settings.from_env()
    except SettingsError as exc:
        sys.exit(f"Configuration error: {exc}")
    if os.environ.get("LO_API_TOKEN"):
        print(
            "LO_API_TOKEN is no longer used and is ignored. Sign in with a user; create "
            "personal API tokens under 'My account'.",
            file=sys.stderr,
        )
    try:
        asyncio.run(_prepare_database(settings.database_url))
    except SchemaError as exc:
        sys.exit(f"Database error: {exc}")

    transport = None
    if args.mock:
        from .mock.landscape import MockLandscape, default_landscape_config
        from .mock.transport import MockLandscapeTransport

        transport = MockLandscapeTransport(MockLandscape.from_dict(default_landscape_config()))
        print("Using the simulated landscape. Hosts: sapapp1 (offset 0), sapdb1 (offset 10000).")

    app = create_app(settings, transport=transport, run_scheduler=True)
    if transport is not None:
        # The simulated hosts download the bundle OSLO offers and trust its configured key.
        transport.landscape.bundle_source = app.state.bundles.files
        transport.landscape.bundle_key_source = lambda: app.state.bundles.public_key
        # sapapp1 has an old version from the bootstrap package, sapdb1 none.
        sapapp1 = transport.landscape.host("sapapp1")
        sapapp1.bundle_version, sapapp1.bundle_key = "0.9.0", "auto"
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

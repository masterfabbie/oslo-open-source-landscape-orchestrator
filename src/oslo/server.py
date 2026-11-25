"""Entry point of ``oslo-server``."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Mapping

import uvicorn

from .api import create_app
from .crypto import SecretBox
from .db import SchemaError, create_engine, create_session_factory, upgrade_database
from .servertls import (
    TlsError,
    load_key_and_chain,
    remove_private_files,
    write_private_files,
)
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


def tls_files(
    args: argparse.Namespace, settings: Settings, env: Mapping[str, str]
) -> tuple[str | None, str | None]:
    """Certificate and key files for uvicorn, or (None, None) for plain HTTP.

    Files given with --ssl-certfile/--ssl-keyfile (or OSLO_TLS_CERT/OSLO_TLS_KEY) win over the
    certificate stored in the database, which --tls or OSLO_TLS=1 switches on.
    """
    certfile = args.ssl_certfile or env.get("OSLO_TLS_CERT")
    keyfile = args.ssl_keyfile or env.get("OSLO_TLS_KEY")
    if certfile or keyfile:
        if not (certfile and keyfile):
            raise TlsError("Give both the certificate file and the key file")
        for path in (certfile, keyfile):
            if not os.path.isfile(path):
                raise TlsError(f"{path} does not exist")
        return certfile, keyfile
    if not (args.tls or env.get("OSLO_TLS", "").lower() in ("1", "true", "yes")):
        return None, None
    stored = asyncio.run(_stored_tls(settings))
    if stored is None:
        raise TlsError(
            "No certificate is stored. Create one under Administration → HTTPS or with "
            "oslo-tls-cert, or start without --tls."
        )
    key, chain = stored
    return write_private_files(key, chain)


async def _stored_tls(settings: Settings) -> tuple[str, str] | None:
    engine = create_engine(settings.database_url)
    try:
        await upgrade_database(engine, settings.database_url)  # nothing to do once migrated
        async with create_session_factory(engine)() as session:
            return await load_key_and_chain(session, SecretBox(settings.secret_key))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="OSLO server")
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--mock",
        action="store_true",
        help="connect to the built-in simulated landscape instead of real hosts",
    )
    parser.add_argument(
        "--tls",
        action="store_true",
        help="serve HTTPS with the certificate stored under Administration → HTTPS (or OSLO_TLS=1)",
    )
    parser.add_argument("--ssl-certfile", help="serve HTTPS with this certificate (chain)")
    parser.add_argument("--ssl-keyfile", help="the private key of --ssl-certfile")
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
    try:
        certfile, keyfile = tls_files(args, settings, os.environ)
    except TlsError as exc:
        sys.exit(f"HTTPS error: {exc}")

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
    config = uvicorn.Config(
        app, host=args.host, port=args.port, ssl_certfile=certfile, ssl_keyfile=keyfile
    )
    config.load()  # reads certificate and key into the SSL context
    if certfile:
        # Files written from the database are no longer needed: the key stays in memory only.
        remove_private_files(certfile)
        print(f"Serving HTTPS on port {args.port}.")
    uvicorn.Server(config).run()


if __name__ == "__main__":
    main()

"""Database engine, sessions and schema migrations.

The schema is managed with Alembic; the migrations are in the package ``migrations``.
``upgrade_database`` runs at server start: it creates a new database, takes over a database
of the last version before Alembic, and migrates an older one after making a backup copy.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base
from .settings import DEFAULT_DATABASE_URL, env_value

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
# Revision that matches the schema of the last version before Alembic (schema 2).
BASELINE_REVISION = "0001"
# That version recorded its schema in this table.
LEGACY_SCHEMA_TABLE = "schema_info"
LEGACY_SCHEMA_VERSION = 2
BACKUPS_KEPT = 5


def create_engine(database_url: str) -> AsyncEngine:
    engine = create_async_engine(database_url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


class SchemaError(Exception):
    """The database cannot be used with this version."""


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def head_revision() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert head is not None
    return head


def _state(connection: Any) -> tuple[str, str | None]:
    """("empty" | "legacy" | "managed", current revision)."""
    tables = set(inspect(connection).get_table_names())
    if "alembic_version" in tables:
        return "managed", MigrationContext.configure(connection).get_current_revision()
    if not tables:
        return "empty", None
    version = None
    if LEGACY_SCHEMA_TABLE in tables:
        version = connection.execute(text(f"SELECT version FROM {LEGACY_SCHEMA_TABLE}")).scalar()
    if version != LEGACY_SCHEMA_VERSION:
        raise SchemaError(
            f"The database was created by an incompatible version (schema {version or 1}). "
            "Delete it or point OSLO_DATABASE_URL to a new database; the inventory has to be "
            "set up again."
        )
    return "legacy", None


def _run(connection: Any, action: str, revision: str = "head") -> None:
    config = alembic_config()
    config.attributes["connection"] = connection
    if action == "stamp":
        command.stamp(config, revision)
    else:
        command.upgrade(config, revision)


# Tables that versions before Alembic added later with create_all; a database of such a
# version may lack them. Their definition has not changed since the baseline.
LEGACY_LATE_TABLES = ("host_agent_info", "host_tags", "system_tags")


def _take_over_legacy(connection: Any) -> None:
    # Add the late tables that are still missing so the database matches the baseline,
    # then record the baseline and run the newer migrations.
    tables = [Base.metadata.tables[name] for name in LEGACY_LATE_TABLES]
    Base.metadata.create_all(connection, tables=tables)
    _run(connection, "stamp", BASELINE_REVISION)
    _run(connection, "upgrade")


def sqlite_file(database_url: str) -> Path | None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
        return None
    return Path(url.database)


def backup_sqlite(database: Path, keep: int = BACKUPS_KEPT) -> Path:
    """Copy the database file next to it and keep only the ``keep`` newest copies."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    target = database.with_name(f"{database.name}.bak-{stamp}")
    shutil.copy2(database, target)
    backups = sorted(database.parent.glob(f"{database.name}.bak-*"))
    for old in backups[:-keep]:
        old.unlink()
    return target


async def upgrade_database(engine: AsyncEngine, database_url: str) -> Path | None:
    """Bring the database to the newest schema. Returns the backup made, if any.

    A SQLite file is copied before existing data is migrated. Raises :class:`SchemaError`
    for databases this version cannot use.
    """
    async with engine.connect() as connection:
        state, current = await connection.run_sync(_state)
    head = head_revision()
    if state == "managed" and current == head:
        return None
    if state == "managed":
        known = {s.revision for s in ScriptDirectory.from_config(alembic_config()).walk_revisions()}
        if current not in known:
            raise SchemaError(
                f"The database has schema revision {current}, which this version does not "
                "know. It was probably migrated by a newer version."
            )

    backup = None
    database = sqlite_file(database_url)
    if state != "empty" and database is not None and database.exists():
        await engine.dispose()  # no open connections while the file is copied
        backup = backup_sqlite(database)

    async with engine.begin() as connection:
        if state == "legacy":
            await connection.run_sync(_take_over_legacy)
        else:
            await connection.run_sync(_run, "upgrade")
    return backup


async def current_revision(engine: AsyncEngine) -> str | None:
    async with engine.connect() as connection:
        state, current = await connection.run_sync(_state)
    return current if state == "managed" else None


def main() -> None:
    """``oslo-db``: show or migrate the schema of the database in OSLO_DATABASE_URL."""
    parser = argparse.ArgumentParser(description="OSLO database schema")
    parser.add_argument("action", choices=("current", "upgrade", "history"))
    args = parser.parse_args()

    if args.action == "history":
        for script in ScriptDirectory.from_config(alembic_config()).walk_revisions():
            print(f"{script.revision}  {script.doc}")
        return

    database_url = env_value(os.environ, "DATABASE_URL", DEFAULT_DATABASE_URL)

    async def run() -> None:
        engine = create_engine(database_url)
        try:
            if args.action == "current":
                current = await current_revision(engine)
                print(f"current: {current or 'none'}, newest: {head_revision()}")
            else:
                backup = await upgrade_database(engine, database_url)
                if backup:
                    print(f"Backup: {backup}")
                print(f"Schema is at revision {await current_revision(engine)}")
        finally:
            await engine.dispose()

    try:
        asyncio.run(run())
    except SchemaError as exc:
        sys.exit(f"Database error: {exc}")

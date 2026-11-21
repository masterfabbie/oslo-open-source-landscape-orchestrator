from __future__ import annotations

import sqlite3
import sys

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine as create_sync_engine

from oslo import db
from oslo.db import (
    SchemaError,
    backup_sqlite,
    create_engine,
    current_revision,
    head_revision,
    upgrade_database,
)
from oslo.models import Base

pytestmark = pytest.mark.anyio


def url_of(path) -> str:
    return f"sqlite+aiosqlite:///{path}"


async def upgrade(path):
    engine = create_engine(url_of(path))
    try:
        backup = await upgrade_database(engine, url_of(path))
        return backup, await current_revision(engine)
    finally:
        await engine.dispose()


def tables(path) -> set[str]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {name for (name,) in rows}


async def test_new_database_is_created_by_migrations(tmp_path):
    path = tmp_path / "new.db"
    backup, revision = await upgrade(path)
    assert backup is None and revision == head_revision()
    assert {"hosts", "systems", "host_tags", "alembic_version"} <= tables(path)
    assert "schema_info" not in tables(path)

    # Nothing to do the second time, and no backup.
    assert await upgrade(path) == (None, head_revision())
    assert list(tmp_path.glob("new.db.bak-*")) == []


def test_models_match_migrations(tmp_path):
    """Fails when a model changes without a migration."""
    import asyncio

    path = tmp_path / "compare.db"
    asyncio.run(upgrade(path))
    engine = create_sync_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
        actions = connection.exec_driver_sql("PRAGMA foreign_key_list(activities)").fetchall()
    engine.dispose()
    assert _without_inline_fk_ondelete(diff) == []
    # The inline foreign keys of migration 0004 do have ON DELETE SET NULL.
    assert {(row[3], row[6]) for row in actions} >= {
        ("host_id", "SET NULL"),
        ("parent_id", "SET NULL"),
    }


def _fk_key(constraint) -> tuple:
    return (
        constraint.table.name,
        tuple(element.parent.name for element in constraint.elements),
        tuple(element.target_fullname for element in constraint.elements),
    )


def _without_inline_fk_ondelete(diff: list) -> list:
    """Drop remove/add pairs of the same foreign key that differ only in ON DELETE.

    Migration 0004 adds foreign keys with ALTER TABLE ADD COLUMN ... REFERENCES; SQLAlchemy
    does not read ON DELETE of such column constraints back from SQLite.
    """
    removed = {_fk_key(d[1]) for d in diff if d[0] == "remove_fk"}
    added = {_fk_key(d[1]) for d in diff if d[0] == "add_fk"}
    same = removed & added
    return [d for d in diff if not (d[0] in ("remove_fk", "add_fk") and _fk_key(d[1]) in same)]


def legacy_database(path) -> None:
    """A database as the last version before migrations left it, without host_tags."""
    # The baseline migration creates exactly the tables of that version.
    engine = create_sync_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        db._run(connection, "upgrade", "0001")
        connection.exec_driver_sql("DROP TABLE alembic_version")
        connection.exec_driver_sql("DROP TABLE host_tags")
    engine.dispose()
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE schema_info (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_info VALUES (2)")
        connection.execute(
            "INSERT INTO hosts (name, address, https, verify_tls, sapcontrol_port_offset) "
            "VALUES ('sapapp1', '127.0.0.1', 0, 1, 0)"
        )


async def test_legacy_database_is_taken_over_with_backup(tmp_path):
    path = tmp_path / "landscape.db"
    legacy_database(path)

    backup, revision = await upgrade(path)

    assert revision == head_revision()
    assert backup is not None and backup.exists()
    assert backup.name.startswith("landscape.db.bak-")
    assert "schema_info" in tables(backup)  # the copy is the state before
    assert "schema_info" not in tables(path)
    assert "host_tags" in tables(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM hosts").fetchall() == [("sapapp1",)]


async def test_older_revision_is_migrated_with_backup(tmp_path):
    path = tmp_path / "landscape.db"
    engine = create_engine(url_of(path))
    async with engine.begin() as connection:
        await connection.run_sync(db._run, "upgrade", "0001")
    await engine.dispose()

    backup, revision = await upgrade(path)
    assert revision == head_revision() and backup is not None


async def test_unusable_databases_are_refused(tmp_path):
    first = tmp_path / "schema1.db"
    with sqlite3.connect(first) as connection:
        connection.execute("CREATE TABLE systems (id INTEGER PRIMARY KEY, sid VARCHAR(8))")
    with pytest.raises(SchemaError, match="incompatible version"):
        await upgrade(first)

    newer = tmp_path / "newer.db"
    await upgrade(newer)
    with sqlite3.connect(newer) as connection:
        connection.execute("UPDATE alembic_version SET version_num = '9999'")
    with pytest.raises(SchemaError, match="9999"):
        await upgrade(newer)


def test_only_the_newest_backups_are_kept(tmp_path):
    database = tmp_path / "landscape.db"
    database.write_text("data")
    for _ in range(7):
        backup_sqlite(database)
    assert len(list(tmp_path.glob("landscape.db.bak-*"))) == 5
    assert database.read_text() == "data"


def test_lo_db_command(tmp_path, monkeypatch, capsys):
    path = tmp_path / "cli.db"
    monkeypatch.setenv("OSLO_DATABASE_URL", url_of(path))

    def run(action: str) -> str:
        monkeypatch.setattr(sys, "argv", ["oslo-db", action])
        db.main()
        return capsys.readouterr().out

    assert "current: none" in run("current")
    assert f"Schema is at revision {head_revision()}" in run("upgrade")
    assert f"current: {head_revision()}" in run("current")
    history = run("history")
    assert "0001" in history and "0002" in history


async def test_template_chains_become_graphs(tmp_path):
    """Migration 0008: existing steps keep their behavior (target type of the template, the
    previous step as predecessor, every parameter asked for); custom operations lock and run
    on their own as before."""
    path = tmp_path / "chains.db"
    engine = create_engine(url_of(path))
    async with engine.begin() as connection:
        await connection.run_sync(db._run, "upgrade", "0007")
    await engine.dispose()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO custom_operations (id, key, name, agent_operation, target, "
            "instance_types, ordering, role, mass, timeout_seconds, created_at) VALUES "
            "(1, 'oslo_test', 'Test', 'OSLO_TEST', 'SYSTEM', '', 'parallel', 'operator', 1, 60, "
            "'2026-11-20')"
        )
        connection.execute(
            "INSERT INTO custom_operation_parameters (operation_id, position, name, label, "
            "type, required) VALUES (1, 1, 'RC', 'Exit code', 'INTEGER', 0)"
        )
        connection.execute(
            "INSERT INTO operation_templates (id, key, name, target, role, mass, created_at) "
            "VALUES (1, 'chain', 'Chain', 'SYSTEM', 'operator', 1, '2026-11-20')"
        )
        for position, operation in ((1, "oslo_test"), (2, "stop")):
            connection.execute(
                "INSERT INTO template_steps (template_id, position, operation, parameters, "
                "on_error) VALUES (1, ?, ?, '{}', 'stop')",
                (position, operation),
            )

    await upgrade(path)
    with sqlite3.connect(path) as connection:
        steps = connection.execute(
            "SELECT position, target_type, targets, after, ask FROM template_steps "
            "ORDER BY position"
        ).fetchall()
        flags = connection.execute("SELECT locks, standalone FROM custom_operations").fetchall()
    assert steps == [(1, "SYSTEM", "[]", "[]", '["RC"]'), (2, "SYSTEM", "[]", "[1]", "[]")]
    assert flags == [(1, 1)]

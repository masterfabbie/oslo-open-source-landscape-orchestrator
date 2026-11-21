"""Alembic environment. Runs on the connection that ``db.upgrade_database`` passes in."""

from __future__ import annotations

from alembic import context

from oslo.models import Base

connection = context.config.attributes["connection"]
context.configure(
    connection=connection,
    target_metadata=Base.metadata,
    # SQLite can change columns only by rebuilding the table; batch mode does that.
    render_as_batch=True,
    compare_type=True,
)
with context.begin_transaction():
    context.run_migrations()

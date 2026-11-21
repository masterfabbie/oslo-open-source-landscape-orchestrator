"""Structured log entries for the timeline of the activity page.

Adds three optional columns to activity_log: event, subject and data. Plain ADD COLUMN, so
SQLite does not rebuild the table. Autogenerate also proposed rebuilding the foreign keys of
activities from migration 0004; that is only the reflection gap described there and was
removed.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activity_log", sa.Column("event", sa.String(length=16), nullable=True))
    op.add_column("activity_log", sa.Column("subject", sa.String(length=255), nullable=True))
    op.add_column("activity_log", sa.Column("data", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("activity_log") as batch_op:
        batch_op.drop_column("data")
        batch_op.drop_column("subject")
        batch_op.drop_column("event")

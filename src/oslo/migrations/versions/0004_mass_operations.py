"""Mass operations and host operations: parent, host and options of activities

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-18

SQLite cannot add foreign keys with Alembic's add_column, and batch mode would rebuild the
table: dropping the old one with foreign keys on would delete the activity log through
ON DELETE CASCADE. SQLite does allow ALTER TABLE ADD COLUMN with a REFERENCES clause, so
that is used directly.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE activities ADD COLUMN host_id INTEGER "
            "REFERENCES hosts (id) ON DELETE SET NULL"
        )
        op.execute(
            "ALTER TABLE activities ADD COLUMN parent_id INTEGER "
            "REFERENCES activities (id) ON DELETE SET NULL"
        )
    else:
        op.add_column(
            "activities",
            sa.Column("host_id", sa.Integer(), sa.ForeignKey("hosts.id", ondelete="SET NULL")),
        )
        op.add_column(
            "activities",
            sa.Column(
                "parent_id", sa.Integer(), sa.ForeignKey("activities.id", ondelete="SET NULL")
            ),
        )
    op.add_column("activities", sa.Column("options", sa.Text(), nullable=True))
    op.create_index("ix_activities_parent_id", "activities", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_activities_parent_id", "activities")
    with op.batch_alter_table("activities") as batch_op:
        batch_op.drop_column("options")
        batch_op.drop_column("parent_id")
        batch_op.drop_column("host_id")

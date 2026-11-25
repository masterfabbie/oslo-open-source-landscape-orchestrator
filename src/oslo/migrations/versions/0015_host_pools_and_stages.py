"""Hosts in pools (pool_hosts) and a stage per host.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pool_hosts",
        sa.Column("host_id", sa.Integer(), nullable=False),
        sa.Column("pool_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pool_id"], ["pools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("host_id"),
    )
    op.create_index(op.f("ix_pool_hosts_pool_id"), "pool_hosts", ["pool_id"], unique=False)
    op.add_column("hosts", sa.Column("stage", sa.String(length=16), nullable=True))


def downgrade() -> None:
    raise NotImplementedError("Migrations only go forward; restore the backup copy instead.")

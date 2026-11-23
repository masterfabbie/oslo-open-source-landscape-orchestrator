"""OSLO operations bundle: uploaded bundles and the state of each host.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operation_bundles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.Column("files", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_by", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256"),
    )
    # Plain ADD COLUMN: no rebuild of the hosts table.
    op.add_column("hosts", sa.Column("bundle_version", sa.String(length=32), nullable=True))
    op.add_column("hosts", sa.Column("bundle_integrity", sa.String(length=16), nullable=True))
    op.add_column(
        "hosts", sa.Column("bundle_checked_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    raise NotImplementedError("Migrations only go forward; restore the backup copy instead.")

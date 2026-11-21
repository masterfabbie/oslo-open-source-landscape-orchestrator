"""Stage per system (columns of the overview) and platform settings.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Added without a batch rebuild of systems (see migration 0004).
    op.add_column("systems", sa.Column("stage", sa.String(length=16), nullable=True))
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    raise NotImplementedError("Migrations only go forward; restore the backup copy instead.")

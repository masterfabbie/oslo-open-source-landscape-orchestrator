"""Categories of custom operations and operation templates (menus of the landscape).

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("custom_operations", "operation_templates"):
        op.add_column(
            table,
            sa.Column("category", sa.String(length=128), nullable=False, server_default=""),
        )


def downgrade() -> None:
    raise NotImplementedError("Migrations only go forward; restore the backup copy instead.")

"""Name of a schedule (Operations → Schedules).

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schedules", sa.Column("name", sa.String(length=128), nullable=True))


def downgrade() -> None:
    raise NotImplementedError("Migrations only go forward; restore the backup copy instead.")

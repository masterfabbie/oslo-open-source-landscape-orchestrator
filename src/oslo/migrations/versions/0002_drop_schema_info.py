"""Drop the table schema_info of the version before migrations

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17

Alembic records the schema in alembic_version now. Databases created by migrations never
had schema_info, hence the check.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "schema_info" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("schema_info")


def downgrade() -> None:
    op.create_table("schema_info", sa.Column("version", sa.Integer(), nullable=False))
    op.execute("INSERT INTO schema_info (version) VALUES (2)")

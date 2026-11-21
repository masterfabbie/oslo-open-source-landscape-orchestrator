"""Trusted certificates for HTTPS to hosts, and checking the host name per host.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Added without a batch rebuild of hosts (see migration 0004).
    op.add_column(
        "hosts",
        sa.Column("verify_hostname", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "trusted_certificates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("pem", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=95), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
    )


def downgrade() -> None:
    raise NotImplementedError("Migrations only go forward; restore the backup copy instead.")

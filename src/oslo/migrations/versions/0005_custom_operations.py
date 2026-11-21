"""Custom operations and their parameters

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18

Autogenerate also proposed rebuilding the foreign keys of activities from migration 0004;
that is only the reflection gap described there and was removed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_operations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("agent_operation", sa.String(length=128), nullable=False),
        sa.Column("target", sa.String(length=16), nullable=False),
        sa.Column("instance_types", sa.String(length=255), nullable=False),
        sa.Column("ordering", sa.String(length=16), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("mass", sa.Boolean(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_table(
        "custom_operation_parameters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("default", sa.String(length=255), nullable=True),
        sa.Column("pattern", sa.String(length=255), nullable=True),
        sa.Column("help", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["operation_id"], ["custom_operations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id", "name"),
    )
    with op.batch_alter_table("custom_operation_parameters", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_custom_operation_parameters_operation_id"),
            ["operation_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("custom_operation_parameters", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_custom_operation_parameters_operation_id"))

    op.drop_table("custom_operation_parameters")
    op.drop_table("custom_operations")

"""Baseline: schema of the last version before migrations

Revision ID: 0001
Revises:
Create Date: 2026-11-17

The tables as created by the last version without migrations. Databases of that version
are stamped with this revision instead of running it (see db.upgrade_database).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("hostagent_port", sa.Integer(), nullable=True),
        sa.Column("https", sa.Boolean(), nullable=False),
        sa.Column("verify_tls", sa.Boolean(), nullable=False),
        sa.Column("sapcontrol_port_offset", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("os_name", sa.String(length=255), nullable=True),
        sa.Column("os_version", sa.String(length=255), nullable=True),
        sa.Column("cpu_count", sa.Integer(), nullable=True),
        sa.Column("memory_kb", sa.Integer(), nullable=True),
        sa.Column("reachable", sa.Boolean(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_discovery_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "pools",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "sids",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=8), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "systems",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "databases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("instance_name", sa.String(length=255), nullable=True),
        sa.Column("vendor", sa.String(length=64), nullable=True),
        sa.Column("release", sa.String(length=64), nullable=True),
        sa.Column("last_status", sa.String(length=16), nullable=False),
        sa.Column("status_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("host_id", "name", "type"),
    )
    op.create_table(
        "host_agent_info",
        sa.Column("host_id", sa.Integer(), nullable=False),
        sa.Column("release", sa.String(length=16), nullable=False),
        sa.Column("patch", sa.String(length=16), nullable=True),
        sa.Column("details", sa.String(length=255), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("host_id"),
    )
    op.create_table(
        "host_tags",
        sa.Column("host_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("host_id", "key"),
    )
    op.create_table(
        "instances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host_id", sa.Integer(), nullable=False),
        sa.Column("sid_id", sa.Integer(), nullable=False),
        sa.Column("system_id", sa.Integer(), nullable=True),
        sa.Column("number", sa.String(length=2), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("sap_version_info", sa.String(length=255), nullable=True),
        sa.Column("features", sa.String(length=255), nullable=True),
        sa.Column("start_priority", sa.String(length=16), nullable=True),
        sa.Column("last_status", sa.String(length=16), nullable=False),
        sa.Column("status_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sid_id"], ["sids.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["system_id"], ["systems.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("host_id", "sid_id", "number"),
    )
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_instances_system_id"), ["system_id"], unique=False)

    op.create_table(
        "pool_systems",
        sa.Column("system_id", sa.Integer(), nullable=False),
        sa.Column("pool_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["pool_id"], ["pools.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["system_id"], ["systems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("system_id"),
    )
    with op.batch_alter_table("pool_systems", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pool_systems_pool_id"), ["pool_id"], unique=False)

    op.create_table(
        "system_dependencies",
        sa.Column("system_id", sa.Integer(), nullable=False),
        sa.Column("depends_on_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["depends_on_id"], ["systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["system_id"], ["systems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("system_id", "depends_on_id"),
    )
    op.create_table(
        "system_tags",
        sa.Column("system_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["system_id"], ["systems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("system_id", "key"),
    )
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_label", sa.String(length=255), nullable=False),
        sa.Column("system_id", sa.Integer(), nullable=True),
        sa.Column("instance_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["system_id"], ["systems.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_activities_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_activities_system_id"), ["system_id"], unique=False)

    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("activity_log", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_activity_log_activity_id"), ["activity_id"], unique=False
        )

    op.create_table(
        "activity_systems",
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("system_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["system_id"], ["systems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("activity_id", "system_id"),
    )


def downgrade() -> None:
    op.drop_table("activity_systems")
    with op.batch_alter_table("activity_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_activity_log_activity_id"))

    op.drop_table("activity_log")
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_activities_system_id"))
        batch_op.drop_index(batch_op.f("ix_activities_status"))

    op.drop_table("activities")
    op.drop_table("system_tags")
    op.drop_table("system_dependencies")
    with op.batch_alter_table("pool_systems", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_pool_systems_pool_id"))

    op.drop_table("pool_systems")
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_instances_system_id"))

    op.drop_table("instances")
    op.drop_table("host_tags")
    op.drop_table("host_agent_info")
    op.drop_table("databases")
    op.drop_table("systems")
    op.drop_table("sids")
    op.drop_table("pools")
    op.drop_table("hosts")

"""Operation templates as graphs with targets per step; flags of custom operations.

- custom_operations: ``locks`` (locks instance, system or host) and ``standalone`` (also
  outside templates), both on for existing operations.
- activities: ``locks``; table ``activity_hosts`` for the hosts a template locks.
- template_steps: ``target_type``, ``targets`` (fixed ids, empty: the selection of the run),
  ``after`` (predecessors) and ``ask`` (parameters asked for at the start). Existing steps
  keep their behavior: the template's target type, the selection, the previous step as
  predecessor, every parameter asked for as before.

Columns are only added (no batch rebuild): rebuilding activities or operation_templates
would delete their log entries or steps through ON DELETE CASCADE (see migration 0004).

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "custom_operations",
        sa.Column("locks", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "custom_operations",
        sa.Column("standalone", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "activities", sa.Column("locks", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.create_table(
        "activity_hosts",
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("host_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("activity_id", "host_id"),
    )
    for name in ("target_type", "targets", "after", "ask"):
        default = "" if name == "target_type" else "[]"
        column_type = sa.String(length=16) if name == "target_type" else sa.Text()
        op.add_column(
            "template_steps",
            sa.Column(name, column_type, nullable=False, server_default=default),
        )

    connection = op.get_bind()
    targets = dict(connection.execute(sa.text("SELECT id, target FROM operation_templates")).all())
    parameters: dict[str, list[str]] = {}
    for key, name in connection.execute(
        sa.text(
            "SELECT o.key, p.name FROM custom_operation_parameters p "
            "JOIN custom_operations o ON o.id = p.operation_id ORDER BY p.position"
        )
    ):
        parameters.setdefault(key, []).append(name)
    steps = connection.execute(
        sa.text("SELECT id, template_id, position, operation FROM template_steps")
    ).all()
    for step_id, template_id, position, operation in steps:
        connection.execute(
            sa.text(
                "UPDATE template_steps SET target_type = :target_type, after = :after, "
                "ask = :ask WHERE id = :id"
            ),
            {
                "id": step_id,
                "target_type": targets.get(template_id, ""),
                "after": json.dumps([position - 1] if position > 1 else []),
                "ask": json.dumps(parameters.get(operation, [])),
            },
        )


def downgrade() -> None:
    raise NotImplementedError("Migrations only go forward; restore the backup copy instead.")

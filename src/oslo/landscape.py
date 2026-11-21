"""What the landscape page shows: systems, hosts and the operations a user may run.

The interface loads one snapshot (``landscape_snapshot``) and filters it in the browser. It
is reloaded when the event stream (``events.py``) reports a change.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .attention import attention_items, load_exceptions, load_rules, overview_columns
from .catalog import Catalog, OperationDef
from .clients import SoapError
from .connections import ClientFactory
from .crypto import SecretError
from .discovery import instance_status
from .models import STATUS_UNKNOWN, Activity, Host, Instance, Pool, System, User
from .operations import ACTIVE_STATUSES
from .roles import instance_type_key
from .systems import depends_on_sids
from .users import has_role


def system_status(system: System) -> str:
    """Overall status of a system from the stored status of its instances.

    Diagnostics agents are left out, as in system operations.
    """
    instances = [i for i in system.instances if not i.is_agent] or system.instances
    statuses = {instance.last_status for instance in instances}
    if not statuses:
        return STATUS_UNKNOWN
    if statuses == {"GREEN"}:
        return "GREEN"
    if statuses == {"GRAY"}:
        return "GRAY"
    if "RED" in statuses:
        return "RED"
    if statuses == {STATUS_UNKNOWN}:
        return STATUS_UNKNOWN
    return "YELLOW"


def instance_type(instance: Instance) -> str | None:
    """One of filters.TYPE_VALUES, e.g. "abap", or None if unknown."""
    key = instance_type_key(instance.features)
    return key.removeprefix("itype.") if key else None


async def all_systems(session: AsyncSession) -> list[System]:
    return list(
        await session.scalars(
            select(System)
            .order_by(System.name)
            .options(
                selectinload(System.instances).selectinload(Instance.host),
                selectinload(System.instances).selectinload(Instance.sid),
                selectinload(System.depends_on),
                selectinload(System.pool),
            )
        )
    )


async def all_hosts(session: AsyncSession) -> list[Host]:
    query = select(Host).order_by(Host.name).options(selectinload(Host.instances))
    return list(await session.scalars(query))


async def active_by_system(session: AsyncSession) -> dict[int, Activity]:
    """Running activity per system, including systems touched through dependencies."""
    rows = await session.scalars(
        select(Activity)
        .where(Activity.status.in_(ACTIVE_STATUSES))
        .options(selectinload(Activity.systems))
    )
    active: dict[int, Activity] = {}
    for activity in rows:
        for system_id in {activity.system_id, *(s.id for s in activity.systems)}:
            if system_id:
                active[system_id] = activity
    return active


async def active_by_host(session: AsyncSession) -> dict[int, Activity]:
    """Running host operation per host, e.g. a discovery."""
    rows = await session.scalars(
        select(Activity).where(Activity.status.in_(ACTIVE_STATUSES), Activity.host_id.is_not(None))
    )
    return {activity.host_id: activity for activity in rows}


def _activity(activity: Activity | None) -> dict[str, Any] | None:
    if activity is None:
        return None
    return {"id": activity.id, "kind": activity.kind, "status": activity.status}


def operation_row(operation: OperationDef) -> dict[str, Any]:
    """An operation of the catalog for the interface."""
    custom = operation.custom
    template = operation.template
    if template is not None:
        parameters = [p.__dict__ for p in template.run_parameters()]
    else:
        parameters = [p.__dict__ for p in custom.parameters] if custom else []
    return {
        "key": operation.key,
        # Translation keys per target type for built-in operations.
        "labels": {t.value: operation.label_key(t) for t in operation.targets},
        "name": operation.name,
        "description": (template or custom).description if (template or custom) else None,
        "targets": sorted(t.value for t in operation.targets),
        "mass": operation.mass,
        "danger": operation.danger,
        # Custom operations and templates run through /<targets>/<id>/operations/<key>.
        "custom": custom is not None or template is not None,
        "template": template is not None,
        "locks": custom.locks if custom else True,
        "standalone": operation.standalone,
        "role": operation.role.value,
        # Translation keys (built-in) or names (custom operations) of the steps.
        "steps": [step.label_key() for step in template.steps] if template else [],
        # Empty: every instance type (see customspec.spec_applies).
        "instance_types": list(custom.instance_types) if custom else [],
        "parameters": parameters,
    }


def _operations(catalog: Catalog, user: User) -> list[dict[str, Any]]:
    # Operations only for template steps, and templates with fixed targets only, are not
    # run from the landscape.
    return [
        operation_row(operation)
        for operation in catalog.all()
        if has_role(user, operation.role) and operation.standalone and operation.targets
    ]


async def landscape_snapshot(session: AsyncSession, catalog: Catalog, user: User) -> dict[str, Any]:
    systems = await all_systems(session)
    hosts = await all_hosts(session)
    pools = list(await session.scalars(select(Pool).order_by(Pool.name)))
    active = await active_by_system(session)
    host_active = await active_by_host(session)
    names = {s.id: s.name for s in systems}
    system_rows = []
    for system in systems:
        depends = depends_on_sids(system)
        instances = sorted(system.instances, key=lambda i: (i.is_agent, i.priority, i.label))
        system_rows.append(
            {
                "id": system.id,
                "name": system.name,
                "description": system.description,
                "status": system_status(system),
                "pool": {"id": system.pool.id, "name": system.pool.name} if system.pool else None,
                "stage": system.stage,
                "tags": system.tag_list,
                "depends_on": [names.get(d.id, d.name) for d in system.depends_on],
                "activity": _activity(active.get(system.id)),
                "instances": [
                    {
                        "id": i.id,
                        "label": i.label,
                        "sid": i.sid.name,
                        "number": i.number,
                        "host": {"id": i.host.id, "name": i.host.name, "tags": i.host.tag_list},
                        "hostname": i.hostname,
                        "role": i.role.value,
                        "type": instance_type(i),
                        "agent": i.is_agent,
                        "status": i.last_status,
                        "status_checked_at": i.status_checked_at,
                        "start_priority": i.start_priority,
                        # From ListInstances, e.g. "753, patch 1100, changelist 2200000".
                        "version": i.sap_version_info,
                        "depends_on": depends.get(i.id, []),
                    }
                    for i in instances
                ],
            }
        )
    host_rows = [
        {
            "id": h.id,
            "name": h.name,
            "address": h.address,
            "reachable": h.reachable,
            "hostagent_version": h.hostagent_version,
            "os": " ".join(p for p in (h.os_name, h.os_version) if p) or None,
            "tags": h.tag_list,
            "last_discovery_at": h.last_discovery_at,
            "last_error": h.last_error,
            "instance_count": len(h.instances),
            "activity": _activity(host_active.get(h.id)),
        }
        for h in hosts
    ]
    return {
        "user": {"name": user.username, "role": user.role},
        "systems": system_rows,
        "hosts": host_rows,
        "pools": [{"id": p.id, "name": p.name} for p in pools],
        "operations": _operations(catalog, user),
    }


async def read_processes(
    session: AsyncSession, instance: Instance, clients: ClientFactory
) -> dict[str, Any]:
    """Processes of an instance from GetProcessList of its sapstartsrv, read now.

    The stored status of the instance is updated, as by "refresh status". If the
    sapstartsrv cannot be queried, ``error`` says why and the list is empty.
    """
    try:
        async with clients.sapcontrol(instance.host, int(instance.number), instance.sid) as sap:
            processes = await sap.get_process_list()
    except (SoapError, SecretError) as exc:
        instance.last_status = STATUS_UNKNOWN
        instance.status_checked_at = datetime.now(UTC)
        await session.commit()
        return {"status": STATUS_UNKNOWN, "processes": [], "error": str(exc)}
    instance.last_status = instance_status(processes)
    instance.status_checked_at = datetime.now(UTC)
    await session.commit()
    return {
        "status": instance.last_status,
        "processes": [
            {
                "name": p.name,
                "description": p.description,
                "status": p.dispstatus.name,
                "text": p.textstatus,
                "started": p.starttime,
                "elapsed": p.elapsedtime,
                "pid": p.pid,
            }
            for p in processes
        ],
        "error": None,
    }


def _counts(values: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


async def overview_snapshot(session: AsyncSession, catalog: Catalog, user: User) -> dict[str, Any]:
    """The overview: key figures, the status matrix (pools × stages) and what needs
    attention by the rules (attention.py) and the user's exceptions."""
    systems = await all_systems(session)
    hosts = await all_hosts(session)
    pools = list(await session.scalars(select(Pool).order_by(Pool.name)))
    active = await active_by_system(session)
    statuses = {s.id: system_status(s) for s in systems}
    since = datetime.now(UTC) - timedelta(hours=24)
    recent = list(
        await session.scalars(
            select(Activity.status).where(
                Activity.requested_at >= since, Activity.parent_id.is_(None)
            )
        )
    )
    instances = [i for s in systems for i in s.instances]
    rules = await load_rules(session)
    exceptions = await load_exceptions(session, user)
    items = await attention_items(
        session, catalog, systems, hosts, statuses, set(active), rules, exceptions
    )
    return {
        "kpis": {
            "systems": {"total": len(systems), "by": _counts(list(statuses.values()))},
            "instances": {
                "total": len(instances),
                "by": _counts([i.last_status for i in instances]),
            },
            "hosts": {
                "total": len(hosts),
                "by": _counts(
                    [
                        "UNKNOWN" if h.reachable is None else ("GREEN" if h.reachable else "RED")
                        for h in hosts
                    ]
                ),
            },
            "activities": {"total": len(recent), "by": _counts(recent)},
        },
        "columns": overview_columns(systems),
        "pools": [{"id": p.id, "name": p.name, "description": p.description} for p in pools],
        "systems": [
            {
                "id": s.id,
                "name": s.name,
                "pool_id": s.pool.id if s.pool else None,
                "stage": s.stage,
                "status": statuses[s.id],
                "activity": _activity(active.get(s.id)),
                "instances": [
                    {"id": i.id, "label": i.label, "status": i.last_status, "agent": i.is_agent}
                    for i in sorted(s.instances, key=lambda i: (i.is_agent, i.priority, i.label))
                ],
            }
            for s in systems
        ],
        "attention": [item.to_dict() for item in items],
        "exceptions": exceptions.to_dict(),
        "rules": {name: rule["enabled"] for name, rule in rules.items()},
    }

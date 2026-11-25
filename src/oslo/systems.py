"""Systems as user-defined groups of instances.

Discovery leaves new instances unassigned. The user creates systems from them, e.g. an ABAP
system together with the HANA instance of its database, and may mix SIDs freely. Only
instances that belong to a system can be started or stopped.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import STAGES, Activity, Instance, Sid, System, activity_systems
from .operations import ACTIVE_STATUSES
from .pools import assign_pool
from .roles import Role

NAME_MAX_LENGTH = 64


class SystemChangeError(ValueError):
    """A requested change of a system is not allowed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def suggest_name(instances: Iterable[Instance]) -> str:
    """Name proposal: the SID of the ABAP or Java instances, else of the central services,
    else the first SID. Database instances and diagnostics agents come last."""
    preference = {Role.APPLICATION: 0, Role.CENTRAL: 1, Role.DATABASE: 2, Role.AGENT: 3}
    ordered = sorted(
        instances, key=lambda i: (preference[i.role], i.sid.name, i.number)
    )
    return ordered[0].sid.name if ordered else ""


def depends_on_sids(system: System) -> dict[int, list[str]]:
    """instance id -> other SIDs of the same system the instance needs, for display only.

    Application servers need the database and the central services; central services,
    databases and diagnostics agents need nothing within the system. This follows the
    order of system operations (see :mod:`roles`).
    """
    needed = {
        instance.sid.name
        for instance in system.instances
        if instance.role in (Role.DATABASE, Role.CENTRAL)
    }
    result: dict[int, list[str]] = {}
    for instance in system.instances:
        if instance.role is Role.APPLICATION:
            result[instance.id] = sorted(needed - {instance.sid.name})
        else:
            result[instance.id] = []
    return result


async def unassigned_instances(session: AsyncSession) -> list[Instance]:
    rows = await session.scalars(
        select(Instance)
        .where(Instance.system_id.is_(None))
        .options(selectinload(Instance.host), selectinload(Instance.sid))
    )
    return sorted(rows, key=lambda i: (i.sid.name, i.number, i.host.name))


async def suggestions(session: AsyncSession) -> dict[int, System]:
    """Unassigned instance id -> the one system that already holds instances of its SID.

    Nothing is assigned automatically; the user confirms each suggestion. If instances of
    a SID are spread over several systems, there is no suggestion.
    """
    rows = await session.execute(
        select(Instance.sid_id, Instance.system_id)
        .where(Instance.system_id.is_not(None))
        .distinct()
    )
    systems_by_sid: dict[int, set[int]] = {}
    for sid_id, system_id in rows:
        systems_by_sid.setdefault(sid_id, set()).add(system_id)
    result: dict[int, System] = {}
    for instance in await session.scalars(select(Instance).where(Instance.system_id.is_(None))):
        candidates = systems_by_sid.get(instance.sid_id, set())
        if len(candidates) == 1:
            system = await session.get(System, next(iter(candidates)))
            if system is not None:
                result[instance.id] = system
    return result


async def _ensure_idle(session: AsyncSession, system_id: int) -> None:
    active = await session.scalar(
        select(Activity.id)
        .outerjoin(activity_systems)
        .where(
            Activity.status.in_(ACTIVE_STATUSES),
            (activity_systems.c.system_id == system_id) | (Activity.system_id == system_id),
        )
        .limit(1)
    )
    if active is not None:
        raise SystemChangeError(
            "busy", f"Activity {active} is still running for this system; try again later"
        )


async def _check_name(session: AsyncSession, name: str, system_id: int | None = None) -> str:
    name = name.strip()
    if not name:
        raise SystemChangeError("name_missing", "The system needs a name")
    if len(name) > NAME_MAX_LENGTH:
        raise SystemChangeError("name_too_long", f"At most {NAME_MAX_LENGTH} characters")
    query = select(System.id).where(func.lower(System.name) == name.lower())
    if system_id is not None:
        query = query.where(System.id != system_id)
    if await session.scalar(query) is not None:
        raise SystemChangeError("name_taken", f"A system named {name} already exists")
    return name


async def _unassigned(session: AsyncSession, instance_ids: Iterable[int]) -> list[Instance]:
    ids = set(instance_ids)
    if not ids:
        raise SystemChangeError("no_instances", "Select at least one instance")
    instances = list(
        await session.scalars(
            select(Instance).where(Instance.id.in_(ids)).options(selectinload(Instance.sid))
        )
    )
    if unknown := ids - {instance.id for instance in instances}:
        raise SystemChangeError("unknown_instance", f"Unknown instances: {sorted(unknown)}")
    if assigned := [instance.label for instance in instances if instance.system_id is not None]:
        raise SystemChangeError(
            "assigned", "Already assigned to a system: " + ", ".join(sorted(assigned))
        )
    return instances


async def create_system(
    session: AsyncSession,
    name: str,
    instance_ids: Iterable[int],
    *,
    pool_id: int | None = None,
    description: str | None = None,
) -> System:
    """Create a system from unassigned instances. The caller commits."""
    name = await _check_name(session, name)
    instances = await _unassigned(session, instance_ids)
    system = System(name=name, description=(description or "").strip() or None)
    session.add(system)
    await session.flush()
    for instance in instances:
        instance.system_id = system.id
    if pool_id is not None:
        await assign_pool(session, system.id, pool_id)
    await session.flush()
    return system


async def assign_instances(
    session: AsyncSession, system_id: int, instance_ids: Iterable[int]
) -> None:
    """Add unassigned instances to an existing system. The caller commits."""
    if await session.get(System, system_id) is None:
        raise SystemChangeError("unknown_system", "System not found")
    await _ensure_idle(session, system_id)
    for instance in await _unassigned(session, instance_ids):
        instance.system_id = system_id
    await session.flush()


async def unassign_instance(session: AsyncSession, system_id: int, instance_id: int) -> None:
    """Take an instance out of its system. The caller commits."""
    instance = await session.get(Instance, instance_id)
    if instance is None or instance.system_id != system_id:
        raise SystemChangeError("unknown_instance", "The instance is not part of this system")
    await _ensure_idle(session, system_id)
    instance.system_id = None
    await session.flush()


async def update_system(
    session: AsyncSession,
    system_id: int,
    name: str,
    description: str | None,
    stage: str | None | object = ...,
) -> None:
    """Name, description and stage (one of STAGES or None; left out: unchanged)."""
    system = await session.get(System, system_id)
    if system is None:
        raise SystemChangeError("unknown_system", "System not found")
    if stage is not ... and stage not in (None, *STAGES):
        raise SystemChangeError("unknown_stage", f"Unknown stage {stage}")
    system.name = await _check_name(session, name, system_id)
    system.description = (description or "").strip() or None
    if stage is not ...:
        system.stage = stage
    await session.flush()


async def delete_system(session: AsyncSession, system_id: int) -> None:
    """Delete a system; its instances become unassigned. The caller commits."""
    system = await session.get(System, system_id, options=[selectinload(System.instances)])
    if system is None:
        raise SystemChangeError("unknown_system", "System not found")
    await _ensure_idle(session, system_id)
    for instance in system.instances:
        instance.system_id = None
    await session.delete(system)
    await session.flush()


async def sids_of_system(session: AsyncSession, system_id: int) -> list[Sid]:
    rows = await session.scalars(
        select(Sid)
        .join(Instance, Instance.sid_id == Sid.id)
        .where(Instance.system_id == system_id)
        .distinct()
        .order_by(Sid.name)
    )
    return list(rows)

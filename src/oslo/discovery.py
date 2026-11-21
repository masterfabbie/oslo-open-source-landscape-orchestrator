"""Discovery: read what runs on a host and store it in the inventory.

New instances are not assigned to a system; the user groups them into systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .clients import SoapError
from .clients.hostagent import CimObject, HostAgentClient, HostAgentVersion
from .clients.hostagent import Database as AgentDatabase
from .clients.sapcontrol import OSProcess, StateColor, SystemInstance
from .connections import ClientFactory
from .models import STATUS_UNKNOWN, Database, Host, HostAgentInfo, Instance, Sid


class DiscoveryError(Exception):
    """The host agent could not be queried."""


@dataclass
class DiscoveryResult:
    instances_added: list[str] = field(default_factory=list)
    instances_updated: list[str] = field(default_factory=list)
    # In the inventory but no longer reported by the host. They are kept, not deleted.
    instances_missing: list[str] = field(default_factory=list)
    databases_added: list[str] = field(default_factory=list)
    databases_updated: list[str] = field(default_factory=list)
    databases_missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def instance_status(processes: list[OSProcess]) -> str:
    """Overall status of an instance from its processes."""
    colors = {process.dispstatus for process in processes}
    if not colors or colors == {StateColor.GRAY}:
        return StateColor.GRAY.name
    if colors == {StateColor.GREEN}:
        return StateColor.GREEN.name
    if StateColor.RED in colors:
        return StateColor.RED.name
    return StateColor.YELLOW.name


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _apply_computer_system(host: Host, computer: CimObject) -> None:
    for operating_system in computer.find("ITSAMOperatingSystem")[:1]:
        host.os_name = operating_system.value("Name") or None
        host.os_version = operating_system.value("Version") or None
        host.cpu_count = _int_or_none(operating_system.value("CPU Count"))
        host.memory_kb = _int_or_none(operating_system.value("TotalVisibleMemorySize"))


def _own_entry(instance: Instance, system_instances: list[SystemInstance]) -> SystemInstance | None:
    number = int(instance.number)
    candidates = [entry for entry in system_instances if entry.instance_nr == number]
    for entry in candidates:
        if entry.hostname == instance.hostname:
            return entry
    return candidates[0] if len(candidates) == 1 else None


async def _read_instance_details(
    host: Host, instance: Instance, sid: Sid, clients: ClientFactory
) -> str | None:
    """Update status, features and priority from sapstartsrv. Returns a warning on failure."""
    try:
        async with clients.sapcontrol(host, int(instance.number), sid) as sapcontrol:
            processes = await sapcontrol.get_process_list()
            system_instances = await sapcontrol.get_system_instance_list()
    except SoapError as exc:
        instance.last_status = STATUS_UNKNOWN
        return f"{sid.name}/{instance.number}: sapstartsrv could not be queried ({exc})"
    instance.last_status = instance_status(processes)
    entry = _own_entry(instance, system_instances)
    if entry is not None:
        instance.features = "|".join(entry.features)
        instance.start_priority = entry.start_priority
    return None


async def _read_version(agent: HostAgentClient) -> tuple[HostAgentVersion | None, str | None]:
    """Version of the host agent and a warning if it could not be read.

    A failure does not fail the discovery; the last known version is kept.
    """
    try:
        version = await agent.get_version()
    except SoapError as exc:
        return None, f"Host agent version could not be read ({exc})"
    if version is None:
        return None, "Host agent version could not be read (output not recognized)"
    return version, None


async def discover_host(
    session: AsyncSession, host: Host, clients: ClientFactory
) -> DiscoveryResult:
    """Query the host agent and sapstartsrv of ``host`` and update the inventory.

    The caller commits the session. On :class:`DiscoveryError` the host is marked as
    unreachable and the rest of the inventory is left unchanged.
    """
    now = datetime.now(UTC)
    host.last_discovery_at = now
    try:
        async with clients.hostagent(host) as agent:
            computer = await agent.get_computer_system()
            agent_instances = await agent.list_instances()
            agent_databases = await agent.list_databases()
            version, version_warning = await _read_version(agent)
    except SoapError as exc:
        host.reachable = False
        host.last_error = str(exc)
        raise DiscoveryError(str(exc)) from exc

    host.reachable = True
    host.last_error = None
    _apply_computer_system(host, computer)
    result = DiscoveryResult()
    if version_warning:
        result.warnings.append(version_warning)
    if version is not None:
        info = await session.get(HostAgentInfo, host.id)
        if info is None:
            info = HostAgentInfo(host_id=host.id)
            session.add(info)
        info.release = version.release
        info.patch = version.patch or None
        info.details = version.details[:255] or None
        info.checked_at = now

    rows = await session.execute(
        select(Instance, Sid).join(Sid, Instance.sid_id == Sid.id).where(
            Instance.host_id == host.id
        )
    )
    known_instances = {(sid.name, instance.number): instance for instance, sid in rows}
    sids = {sid.name: sid for sid in await session.scalars(select(Sid))}

    seen: set[tuple[str, str]] = set()
    for found in agent_instances:
        key = (found.sid, found.system_number)
        label = f"{found.sid}/{found.system_number}"
        seen.add(key)
        sid = sids.get(found.sid)
        if sid is None:
            sid = sids[found.sid] = Sid(name=found.sid)
            session.add(sid)
        instance = known_instances.get(key)
        if instance is None:
            instance = Instance(host=host, sid=sid, number=found.system_number)
            session.add(instance)
            result.instances_added.append(label)
        else:
            result.instances_updated.append(label)
        instance.hostname = found.hostname
        instance.sap_version_info = found.sap_version_info or None
        instance.status_checked_at = now
        warning = await _read_instance_details(host, instance, sid, clients)
        if warning:
            result.warnings.append(warning)
    result.instances_missing = [
        f"{sid}/{number}" for sid, number in sorted(known_instances.keys() - seen)
    ]

    await _store_databases(session, host, agent_databases, now, result)
    await session.flush()
    await session.refresh(host, ["agent_info"])
    return result


async def _store_databases(
    session: AsyncSession,
    host: Host,
    agent_databases: list[AgentDatabase],
    now: datetime,
    result: DiscoveryResult,
) -> None:
    rows = await session.scalars(select(Database).where(Database.host_id == host.id))
    known = {(database.name, database.type): database for database in rows}
    seen: set[tuple[str, str]] = set()
    for found in agent_databases:
        key = (found.name, found.type)
        seen.add(key)
        database = known.get(key)
        if database is None:
            database = Database(host=host, name=found.name, type=found.type)
            session.add(database)
            result.databases_added.append(found.name)
        else:
            result.databases_updated.append(found.name)
        database.instance_name = found.properties.get("Database/InstanceName")
        database.vendor = found.properties.get("Database/Vendor")
        database.release = found.properties.get("Database/Release")
        database.last_status = found.status.name
        database.status_checked_at = now
    result.databases_missing = sorted(name for name, _ in known.keys() - seen)

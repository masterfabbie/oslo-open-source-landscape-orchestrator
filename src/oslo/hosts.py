"""Changing the connection data of a host after it was created."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Activity, Host, Instance, activity_systems
from .operations import ACTIVE_STATUSES

MAX_PORT_OFFSET = 15000


class HostChangeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Connection:
    """Connection data of a host; ``None`` in an optional field means "leave unchanged"."""

    name: str | None = None
    address: str | None = None
    # 0 resets to the default port (1128, or 1129 with HTTPS).
    hostagent_port: int | None = None
    https: bool | None = None
    verify_tls: bool | None = None
    sapcontrol_port_offset: int | None = None


async def _ensure_idle(session: AsyncSession, host: Host) -> None:
    instances = select(Instance.id).where(Instance.host_id == host.id)
    systems = select(Instance.system_id).where(
        Instance.host_id == host.id, Instance.system_id.is_not(None)
    )
    active = await session.scalar(
        select(Activity.id)
        .outerjoin(activity_systems)
        .where(
            Activity.status.in_(ACTIVE_STATUSES),
            or_(
                Activity.instance_id.in_(instances),
                Activity.system_id.in_(systems),
                activity_systems.c.system_id.in_(systems),
            ),
        )
        .limit(1)
    )
    if active is not None:
        raise HostChangeError(
            "busy", f"Activity {active} is still running on this host; try again later"
        )


async def update_connection(session: AsyncSession, host: Host, change: Connection) -> None:
    """Apply ``change`` to ``host``. The caller commits.

    Raises :class:`HostChangeError` for invalid values, a name already in use or a running
    activity on the host. The new data is not checked against the host; a discovery does.
    """
    name = host.name if change.name is None else change.name.strip()
    if not name or len(name) > 255:
        raise HostChangeError("invalid_input", "The name must have 1 to 255 characters")
    address = host.address if change.address is None else change.address.strip() or name
    if len(address) > 255:
        raise HostChangeError("invalid_input", "The address may have at most 255 characters")
    port = host.hostagent_port if change.hostagent_port is None else change.hostagent_port
    if port is not None and port != 0 and not 1 <= port <= 65535:
        raise HostChangeError("invalid_input", "The port must be between 1 and 65535")
    offset = (
        host.sapcontrol_port_offset
        if change.sapcontrol_port_offset is None
        else change.sapcontrol_port_offset
    )
    if not 0 <= offset <= MAX_PORT_OFFSET:
        raise HostChangeError("invalid_input", f"The offset must be 0 to {MAX_PORT_OFFSET}")
    taken = await session.scalar(
        select(Host.id).where(func.lower(Host.name) == name.lower(), Host.id != host.id)
    )
    if taken is not None:
        raise HostChangeError("host_exists", f"A host named {name} already exists")
    await _ensure_idle(session, host)

    host.name = name
    host.address = address
    host.hostagent_port = port or None
    if change.https is not None:
        host.https = change.https
    if change.verify_tls is not None:
        host.verify_tls = change.verify_tls
    host.sapcontrol_port_offset = offset

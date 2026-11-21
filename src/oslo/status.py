"""Read the current status of instances and databases without changing anything."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .clients import SoapError
from .connections import ClientFactory
from .crypto import SecretError
from .discovery import instance_status
from .models import STATUS_UNKNOWN, Database, Host, Instance


async def refresh_databases(
    session: AsyncSession, hosts: Iterable[Host], clients: ClientFactory
) -> list[str]:
    """Update the stored status of the known databases on ``hosts`` (ListDatabases).

    Returns a warning per host that could not be queried; those keep their old status.
    The caller commits.
    """
    warnings = []
    now = datetime.now(UTC)
    for host in hosts:
        known = {
            (database.name, database.type): database
            for database in await session.scalars(
                select(Database).where(Database.host_id == host.id)
            )
        }
        if not known:
            continue
        try:
            async with clients.hostagent(host) as agent:
                reported = await agent.list_databases()
        except (SoapError, SecretError) as exc:
            warnings.append(f"Databases on {host.name} could not be queried ({exc})")
            continue
        for found in reported:
            database = known.get((found.name, found.type))
            if database is not None:
                database.last_status = found.status.name
                database.status_checked_at = now
    return warnings


async def _read(instance: Instance, clients: ClientFactory) -> tuple[str, str | None]:
    try:
        async with clients.sapcontrol(
            instance.host, int(instance.number), instance.sid
        ) as sapcontrol:
            return instance_status(await sapcontrol.get_process_list()), None
    except (SoapError, SecretError) as exc:
        return STATUS_UNKNOWN, f"{instance.label}: sapstartsrv could not be queried ({exc})"


async def refresh_system(
    session: AsyncSession, system_id: int, clients: ClientFactory
) -> list[str]:
    """Read the status of all instances of a system, diagnostics agents included, and of
    the databases on their hosts. Returns warnings; the caller commits.

    The instances are queried in parallel. An instance that cannot be queried gets the
    status UNKNOWN.
    """
    instances = list(
        await session.scalars(
            select(Instance)
            .where(Instance.system_id == system_id)
            .options(selectinload(Instance.host), selectinload(Instance.sid))
        )
    )
    results = await asyncio.gather(*(_read(instance, clients) for instance in instances))
    now = datetime.now(UTC)
    warnings = []
    for instance, (status, warning) in zip(instances, results, strict=True):
        instance.last_status = status
        instance.status_checked_at = now
        if warning:
            warnings.append(warning)
    hosts = {instance.host.id: instance.host for instance in instances}
    warnings += await refresh_databases(session, hosts.values(), clients)
    return warnings

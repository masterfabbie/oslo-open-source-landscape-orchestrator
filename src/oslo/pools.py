"""Assignment of systems and hosts to pools."""

from __future__ import annotations

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import config_log
from .models import Host, Pool, System, pool_hosts, pool_systems


class UnknownPoolError(ValueError):
    pass


async def assign_pool(session: AsyncSession, system_id: int, pool_id: int | None) -> None:
    """Put a system into a pool, or take it out with ``None``. The caller commits."""
    if pool_id is not None and await session.get(Pool, pool_id) is None:
        raise UnknownPoolError(f"Unknown pool: {pool_id}")
    before = await session.scalar(
        select(pool_systems.c.pool_id).where(pool_systems.c.system_id == system_id)
    )
    if before != pool_id:
        ids = {i for i in (before, pool_id) if i is not None}
        pools = dict(
            (await session.execute(select(Pool.id, Pool.name).where(Pool.id.in_(ids)))).all()
        )
        system = await session.scalar(select(System.name).where(System.id == system_id))
        old, new = pools.get(before), pools.get(pool_id)  # type: ignore[arg-type]
        config_log.record(session, "system", system_id, system or "?", {"pool": [old, new]})
        for pool, removed in ((before, True), (pool_id, False)):
            if pool is not None:
                config_log.record(
                    session,
                    "pool",
                    pool,
                    pools[pool],
                    {"systems": [system, None] if removed else [None, system]},
                )
    await session.execute(delete(pool_systems).where(pool_systems.c.system_id == system_id))
    if pool_id is not None:
        await session.execute(insert(pool_systems).values(system_id=system_id, pool_id=pool_id))


async def assign_host_pool(session: AsyncSession, host_id: int, pool_id: int | None) -> None:
    """Put a host into a pool, or take it out with ``None``. The caller commits."""
    if pool_id is not None and await session.get(Pool, pool_id) is None:
        raise UnknownPoolError(f"Unknown pool: {pool_id}")
    before = await session.scalar(
        select(pool_hosts.c.pool_id).where(pool_hosts.c.host_id == host_id)
    )
    if before != pool_id:
        ids = {i for i in (before, pool_id) if i is not None}
        pools = dict(
            (await session.execute(select(Pool.id, Pool.name).where(Pool.id.in_(ids)))).all()
        )
        host = await session.scalar(select(Host.name).where(Host.id == host_id))
        old, new = pools.get(before), pools.get(pool_id)  # type: ignore[arg-type]
        config_log.record(session, "host", host_id, host or "?", {"pool": [old, new]})
        for pool, removed in ((before, True), (pool_id, False)):
            if pool is not None:
                config_log.record(
                    session,
                    "pool",
                    pool,
                    pools[pool],
                    {"hosts": [host, None] if removed else [None, host]},
                )
    await session.execute(delete(pool_hosts).where(pool_hosts.c.host_id == host_id))
    if pool_id is not None:
        await session.execute(insert(pool_hosts).values(host_id=host_id, pool_id=pool_id))
    # The relationship of a loaded host would still show the old pool.
    loaded = await session.get(Host, host_id)
    if loaded is not None:
        await session.refresh(loaded, ["pool"])

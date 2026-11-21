"""Assignment of systems to pools."""

from __future__ import annotations

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Pool, pool_systems


class UnknownPoolError(ValueError):
    pass


async def assign_pool(session: AsyncSession, system_id: int, pool_id: int | None) -> None:
    """Put a system into a pool, or take it out with ``None``. The caller commits."""
    if pool_id is not None and await session.get(Pool, pool_id) is None:
        raise UnknownPoolError(f"Unknown pool: {pool_id}")
    await session.execute(delete(pool_systems).where(pool_systems.c.system_id == system_id))
    if pool_id is not None:
        await session.execute(insert(pool_systems).values(system_id=system_id, pool_id=pool_id))

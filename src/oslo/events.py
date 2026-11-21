"""Change notifications for the interface as Server-Sent Events.

The stream does not carry data, only "something changed": the browser then reloads what it
shows. A change is detected from a small fingerprint of the database (newest log entry,
running activities, newest status reads and discoveries). Polling the database keeps this
independent of where a change came from: activities, status reads, the API or another
server process on the same database.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import Activity, ActivityLogEntry, Host, Instance, System
from .operations import ACTIVE_STATUSES

# Comment line sent while nothing changes, so proxies keep the connection open.
KEEPALIVE_SECONDS = 15.0


async def fingerprint(session: AsyncSession) -> str:
    row = (
        await session.execute(
            select(
                select(func.max(ActivityLogEntry.id)).scalar_subquery(),
                select(func.max(Activity.id)).scalar_subquery(),
                select(func.count(Activity.id))
                .where(Activity.status.in_(ACTIVE_STATUSES))
                .scalar_subquery(),
                select(func.max(Activity.finished_at)).scalar_subquery(),
                select(func.max(Instance.status_checked_at)).scalar_subquery(),
                select(func.count(Instance.id)).scalar_subquery(),
                select(func.max(Host.last_discovery_at)).scalar_subquery(),
                select(func.count(System.id)).scalar_subquery(),
            )
        )
    ).one()
    return "|".join("" if value is None else str(value) for value in row)


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


async def change_events(
    session_factory: async_sessionmaker[AsyncSession],
    sleep: Callable[[float], Awaitable[None]],
    *,
    interval: float,
    disconnected: Callable[[], Awaitable[bool]],
    limit: int | None = None,
) -> AsyncIterator[str]:
    """``hello`` at once, then ``change`` whenever the fingerprint changes.

    ``limit`` ends the stream after that many events (for tests).
    """
    sent = 0
    async with session_factory() as session:
        last = await fingerprint(session)
    yield _event("hello", {"version": last})
    sent += 1
    idle = 0.0
    while limit is None or sent < limit:
        await sleep(interval)
        if await disconnected():
            return
        async with session_factory() as session:
            current = await fingerprint(session)
        if current != last:
            last = current
            idle = 0.0
            yield _event("change", {"version": current})
            sent += 1
        else:
            idle += interval
            if idle >= KEEPALIVE_SECONDS:
                idle = 0.0
                yield ": keepalive\n\n"

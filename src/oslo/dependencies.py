"""Dependencies between SAP systems and the order of operations that follows from them.

A system can depend on other systems, typically an ABAP system on the system of its
database, which in real landscapes has its own SID. Starting a system starts its
dependencies first; stopping it stops the system first and then its dependencies, unless
a dependency is still required by a system outside the operation.

The functions work on plain id graphs so they can be tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import System, system_dependencies

Graph = Mapping[int, Iterable[int]]


async def load_graph(session: AsyncSession) -> dict[int, set[int]]:
    """system id -> ids of the systems it depends on."""
    graph: dict[int, set[int]] = {}
    rows = await session.execute(
        select(system_dependencies.c.system_id, system_dependencies.c.depends_on_id)
    )
    for system_id, depends_on_id in rows:
        graph.setdefault(system_id, set()).add(depends_on_id)
    return graph


def dependency_closure(root: int, graph: Graph) -> set[int]:
    """``root`` and everything it depends on, directly or indirectly."""
    seen = {root}
    pending = [root]
    while pending:
        for dependency in graph.get(pending.pop(), ()):
            if dependency not in seen:
                seen.add(dependency)
                pending.append(dependency)
    return seen


def would_create_cycle(system_id: int, depends_on_id: int, graph: Graph) -> bool:
    """Whether letting ``system_id`` depend on ``depends_on_id`` closes a cycle."""
    return system_id in dependency_closure(depends_on_id, graph)


def start_order(systems: Iterable[int], graph: Graph, key: Callable[[int], object]) -> list[int]:
    """Dependencies before the systems that need them; ties are broken by ``key``.

    The graph must not contain cycles; the API prevents them.
    """
    remaining = set(systems)
    ordered: list[int] = []
    while remaining:
        ready = sorted(
            (s for s in remaining if not (set(graph.get(s, ())) & remaining)), key=key
        )
        if not ready:
            raise ValueError("Dependency cycle between systems")
        ordered += ready
        remaining -= set(ready)
    return ordered


def required_by(graph: Graph) -> dict[int, set[int]]:
    reverse: dict[int, set[int]] = {}
    for system_id, dependencies in graph.items():
        for dependency in dependencies:
            reverse.setdefault(dependency, set()).add(system_id)
    return reverse


@dataclass(frozen=True)
class SystemPlan:
    root: int
    # Every system the operation may touch.
    involved: set[int]
    start: list[int]
    stop: list[int]
    # Dependencies that a stop leaves running -> systems outside the stop that need them.
    kept_running: dict[int, set[int]] = field(default_factory=dict)


def plan(root: int, graph: Graph, key: Callable[[int], object]) -> SystemPlan:
    involved = dependency_closure(root, graph)
    reverse = required_by(graph)

    # A dependency is only stopped if every system that needs it is stopped as well.
    stopping = set(involved)
    kept: dict[int, set[int]] = {}
    changed = True
    while changed:
        changed = False
        for system in sorted(stopping - {root}):
            outside = reverse.get(system, set()) - stopping
            if outside:
                stopping.discard(system)
                kept[system] = outside
                changed = True

    return SystemPlan(
        root=root,
        involved=involved,
        start=start_order(involved, graph, key),
        stop=list(reversed(start_order(stopping, graph, key))),
        kept_running=kept,
    )


class DependencyError(ValueError):
    """A requested dependency is not allowed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def set_dependencies(session: AsyncSession, system_id: int, depends_on: set[int]) -> None:
    """Replace the dependencies of a system. The caller commits.

    Raises :class:`DependencyError` for unknown systems, a dependency on itself or a cycle.
    """
    if system_id in depends_on:
        raise DependencyError("self", "A system cannot depend on itself")
    known = set(await session.scalars(select(System.id).where(System.id.in_(depends_on))))
    if unknown := depends_on - known:
        raise DependencyError("unknown", f"Unknown systems: {sorted(unknown)}")

    graph = await load_graph(session)
    graph[system_id] = set()
    for dependency in depends_on:
        if would_create_cycle(system_id, dependency, graph):
            raise DependencyError("cycle", "The dependency would create a cycle")
    graph[system_id] = set(depends_on)

    await session.execute(
        delete(system_dependencies).where(system_dependencies.c.system_id == system_id)
    )
    if depends_on:
        await session.execute(
            insert(system_dependencies),
            [{"system_id": system_id, "depends_on_id": d} for d in sorted(depends_on)],
        )

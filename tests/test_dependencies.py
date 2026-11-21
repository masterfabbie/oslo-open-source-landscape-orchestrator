from __future__ import annotations

import pytest

from oslo.dependencies import (
    dependency_closure,
    plan,
    start_order,
    would_create_cycle,
)

# 1 = ABAP system, 2 = its HANA system, 3 = second ABAP system on the same HANA,
# 4 = a system the HANA system depends on (e.g. a shared file server system).
GRAPH = {1: {2}, 3: {2}, 2: {4}}
NAMES = {1: "AB1", 2: "HDB", 3: "AB2", 4: "NFS"}


def key(system_id: int) -> str:
    return NAMES[system_id]


def test_closure():
    assert dependency_closure(1, GRAPH) == {1, 2, 4}
    assert dependency_closure(4, GRAPH) == {4}


def test_cycle_detection():
    assert would_create_cycle(4, 1, GRAPH)
    assert would_create_cycle(2, 1, GRAPH)
    assert not would_create_cycle(1, 3, GRAPH)


def test_start_order_puts_dependencies_first():
    assert start_order({1, 2, 3, 4}, GRAPH, key) == [4, 2, 1, 3]


def test_start_order_rejects_cycles():
    with pytest.raises(ValueError, match="cycle"):
        start_order({1, 2}, {1: {2}, 2: {1}}, key)


def test_plan_for_system_with_shared_dependency():
    result = plan(1, GRAPH, key)
    assert result.involved == {1, 2, 4}
    assert result.start == [4, 2, 1]
    # HDB is still needed by AB2, so the stop leaves it and therefore NFS running.
    assert result.stop == [1]
    assert result.kept_running == {2: {3}, 4: {2}}


def test_plan_stops_whole_chain_when_nothing_else_needs_it():
    result = plan(1, {1: {2}, 2: {4}}, key)
    assert result.start == [4, 2, 1]
    assert result.stop == [1, 2, 4]
    assert result.kept_running == {}


def test_plan_for_system_without_dependencies():
    result = plan(3, {}, key)
    assert (result.involved, result.start, result.stop) == ({3}, [3], [3])

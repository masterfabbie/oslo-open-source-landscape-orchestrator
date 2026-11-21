from __future__ import annotations

import pytest

from oslo.mock.landscape import MockLandscape, Status


def statuses(landscape: MockLandscape) -> dict[str, Status]:
    now = landscape.clock()
    return {inst.kind: inst.status(now) for _, inst in landscape.system_instances("DEV")}


def test_instance_start_takes_start_duration(landscape, clock):
    instance = landscape.host("sapapp1").instance(0)
    assert instance.status(clock()) is Status.STOPPED

    assert landscape.start_instance(instance) is True
    assert instance.status(clock()) is Status.STARTING
    clock.advance(2.9)
    assert instance.status(clock()) is Status.STARTING
    clock.advance(0.1)
    assert instance.status(clock()) is Status.RUNNING


def test_start_is_noop_when_already_starting_or_running(landscape, clock):
    instance = landscape.host("sapapp1").instance(0)
    landscape.start_instance(instance)
    assert landscape.start_instance(instance) is False
    clock.advance(3)
    assert landscape.start_instance(instance) is False
    assert instance.status(clock()) is Status.RUNNING


def test_stop_and_restart(landscape, clock):
    instance = landscape.host("sapapp1").instance(0)
    landscape.start_instance(instance)
    clock.advance(3)

    landscape.restart_instance(instance)
    assert instance.status(clock()) is Status.STOPPING
    clock.advance(2)
    assert instance.status(clock()) is Status.STARTING
    assert instance.started_at(clock()) == clock()
    clock.advance(3)
    assert instance.status(clock()) is Status.RUNNING

    landscape.stop_instance(instance)
    clock.advance(2)
    assert instance.status(clock()) is Status.STOPPED
    assert instance.started_at(clock()) is None


def test_start_system_follows_priority_order(single_sid_landscape, clock):
    landscape = single_sid_landscape
    landscape.start_system("DEV")
    assert statuses(landscape) == {
        "HDB": Status.STARTING,
        "ASCS": Status.STOPPED,
        "ABAP": Status.STOPPED,
    }
    clock.advance(3)
    assert statuses(landscape) == {
        "HDB": Status.RUNNING,
        "ASCS": Status.STARTING,
        "ABAP": Status.STOPPED,
    }
    clock.advance(3)
    assert statuses(landscape)["ABAP"] is Status.STARTING
    clock.advance(3)
    assert set(statuses(landscape).values()) == {Status.RUNNING}


def test_stop_system_runs_in_reverse_order(single_sid_landscape, clock):
    landscape = single_sid_landscape
    landscape.start_system("DEV")
    clock.advance(9)

    landscape.stop_system("DEV")
    assert statuses(landscape) == {
        "HDB": Status.RUNNING,
        "ASCS": Status.RUNNING,
        "ABAP": Status.STOPPING,
    }
    clock.advance(4)
    assert statuses(landscape) == {
        "HDB": Status.STOPPING,
        "ASCS": Status.STOPPED,
        "ABAP": Status.STOPPED,
    }


def test_start_system_can_be_limited_to_kinds(single_sid_landscape, clock):
    landscape = single_sid_landscape
    landscape.start_system("DEV", {"HDB"})
    clock.advance(10)
    assert statuses(landscape) == {
        "HDB": Status.RUNNING,
        "ASCS": Status.STOPPED,
        "ABAP": Status.STOPPED,
    }


def test_database_follows_its_instance(landscape, clock):
    host = landscape.host("sapdb1")
    database = host.databases[0]
    assert landscape.database_status(host, database) is Status.STOPPED
    landscape.start_instance(host.instance(2))
    clock.advance(3)
    assert landscape.database_status(host, database) is Status.RUNNING


def test_unknown_instance_kind_is_rejected():
    config = {"hosts": [{"name": "h", "instances": [{"sid": "X", "nr": 0, "kind": "NOPE"}]}]}
    with pytest.raises(ValueError, match="NOPE"):
        MockLandscape.from_dict(config)

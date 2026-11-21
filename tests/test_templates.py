"""Operation templates (chains of operations) and schedules."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import test_mass
from conftest import hold_activities, make_user
from oslo.models import Schedule
from oslo.schedules import next_run
from test_custom import OSLO_TEST
from test_mass import client

pytestmark = pytest.mark.anyio

app, api, transport = test_mass.app, test_mass.api, test_mass.transport

SYSTEM_LO_TEST = OSLO_TEST | {"key": "oslo_test", "target": "SYSTEM", "role": "operator"}


def chain(*steps, target_type: str = "SYSTEM", **extra) -> dict:
    """A template whose steps run one after another, each on the selection unless given."""
    numbered = []
    for position, step in enumerate(steps, start=1):
        step = step if isinstance(step, dict) else {"operation": step}
        numbered.append(
            {"target_type": target_type, "after": [position - 1] if position > 1 else []}
            | step
            | {"position": position}
        )
    return (
        {"key": "kernel_update", "name": "Kernel update", "role": "operator"}
        | extra
        | {"steps": numbered}
    )


async def define(api, body) -> dict:
    response = await api.post("/api/templates", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def run(app, api, path: str, body: dict | None = None) -> dict:
    response = await api.post(path, json=body or {})
    assert response.status_code == 202, response.text
    activity_id = response.json()["id"]
    await app.state.runner.wait(activity_id)
    return (await api.get(f"/api/activities/{activity_id}")).json()


async def refused(api, body, code: int, error: str) -> None:
    response = await api.post("/api/templates", json=body)
    assert response.status_code == code, (body, response.text)
    assert response.json()["detail"]["code"] == error, response.text


async def test_define_templates(app, api):
    await api.post("/api/custom-operations", json=SYSTEM_LO_TEST)
    body = chain(
        {"operation": "oslo_test", "parameters": {"RC": "0", "SLEEP": "1"}, "ask": ["A", "RC"]},
        "stop",
        {"operation": "start", "on_error": "continue"},
    )
    template = await define(api, body)
    assert [s["name"] for s in template["steps"]] == ["Test operation", "stop", "start"]
    assert template["valid"] and template["selection"] == "SYSTEM"
    assert template["steps"][0]["parameters"] == {"RC": "0", "SLEEP": "1"}
    assert template["steps"][2]["after"] == [2] and template["steps"][0]["ask"] == ["A", "RC"]

    oslo_test = {"operation": "oslo_test", "parameters": {"RC": "0"}}
    for wrong, code, error in [
        (chain("stop", key="start"), 422, "template_key"),
        (chain("stop", key="oslo_test"), 409, "template_key_taken"),  # a custom operation
        (body, 409, "template_key_taken"),
        (chain("discover", key="x"), 422, "template_step"),  # a host operation on a system
        (chain(oslo_test | {"parameters": {"NOPE": "1"}}, key="x"), 422, "template_step"),
        (chain(oslo_test | {"parameters": {"RC": "x"}}, key="x"), 422, "template_step"),
        (chain(oslo_test | {"ask": ["NOPE"]}, key="x"), 422, "template_step"),
        # RC is required: it needs a value or must be asked for.
        (chain({"operation": "oslo_test"}, key="x"), 422, "template_step"),
        (chain("stop", key="x", role="viewer"), 422, "template_role"),
        (
            chain(
                {"operation": "discover", "on_error": "stop_and_start"}, key="x", target_type="HOST"
            ),
            422,
            "invalid_input",
        ),
        (chain("stop", {"operation": "start", "after": [7]}, key="x"), 422, "template_step"),
        (chain({"operation": "stop", "after": [2]}, "start", key="x"), 422, "template_cycle"),
        (
            chain(
                "stop",
                {"operation": "discover", "target_type": "HOST"},
                key="x",
                role="configurator",
            ),
            422,
            "template_selection",
        ),
        (chain({"operation": "stop", "targets": [99]}, key="x"), 422, "template_step"),
    ]:
        await refused(api, wrong, code, error)

    # A custom operation used by a template cannot be deleted.
    custom = (await api.get("/api/custom-operations")).json()[0]
    assert (await api.delete(f"/api/custom-operations/{custom['id']}")).status_code == 409
    # Templates appear in the catalog; a run asks only for the parameters marked "ask".
    operations = {op["key"]: op for op in (await api.get("/api/landscape")).json()["operations"]}
    offered = operations["kernel_update"]
    assert offered["template"] and offered["targets"] == ["SYSTEM"]
    assert offered["steps"] == ["Test operation", "op.stop_system", "op.start_system"]
    assert [p["name"] for p in offered["parameters"]] == ["1.A", "1.RC"]
    assert offered["parameters"][1]["default"] == "0"

    changed = chain("restart", name="Restart only")
    updated = await api.put(f"/api/templates/{template['id']}", json=changed)
    assert updated.json()["name"] == "Restart only" and len(updated.json()["steps"]) == 1
    async with client(app, await make_user(app, "conf", "configurator")) as configurator:
        assert (await configurator.get("/api/templates")).status_code == 403
    assert (await api.delete(f"/api/templates/{template['id']}")).status_code == 204
    assert app.state.catalog.get("kernel_update") is None


async def test_run_a_chain(app, api, landscape):
    await api.post("/api/custom-operations", json=SYSTEM_LO_TEST)
    first = {"operation": "oslo_test", "parameters": {"RC": "0", "SLEEP": "1", "A": "prep"}}
    await define(api, chain(first | {"ask": ["A"]}, "stop", "start"))
    result = await run(
        app, api, "/api/systems/1/operations/kernel_update", {"parameters": {"1.A": "run"}}
    )
    assert result["status"] == "SUCCEEDED", result
    assert result["kind"] == "TEMPLATE" and result["target_label"] == "A"
    assert [c["kind"] for c in result["children"]] == ["CUSTOM", "STOP", "START"]
    assert all(c["status"] == "SUCCEEDED" for c in result["children"])
    steps = [e["message"] for e in result["entries"] if e["event"] == "step"]
    assert steps == ["Step 1/3: Test operation", "Step 2/3: Stop", "Step 3/3: Start"]
    # The value of the run replaces the template's value.
    run_args = next(iter(landscape.operation_runs.values())).arguments
    assert "run" in run_args and "prep" not in run_args
    assert result["options"]["values"]["1"]["PARAM-A"] == "run"
    assert result["options"]["selection"] == [1]
    # Values that are not asked for are fixed.
    fixed = await api.post(
        "/api/systems/1/operations/kernel_update", json={"parameters": {"1.RC": "3"}}
    )
    assert fixed.status_code == 422 and "Fixed in the template" in fixed.text


async def test_parallel_steps_and_several_predecessors(app, api):
    """Two discoveries on fixed hosts run at the same time; the restart on the selection
    waits for both."""
    body = {
        "key": "rediscover",
        "name": "Rediscover and restart",
        "role": "configurator",
        "steps": [
            {"position": 1, "operation": "discover", "target_type": "HOST", "targets": [1]},
            {"position": 2, "operation": "discover", "target_type": "HOST", "targets": [2]},
            {"position": 3, "operation": "restart", "target_type": "SYSTEM", "after": [1, 2]},
        ],
    }
    template = await define(api, body)
    assert template["steps"][0]["target_labels"] == [{"id": 1, "label": "sapapp1"}]
    result = await run(
        app,
        api,
        "/api/mass-operations",
        {"operation": "rediscover", "target_type": "SYSTEM", "target_ids": [1, 2]},
    )
    assert result["status"] == "SUCCEEDED", result
    # One run with the selection of two systems: its restart step is a mass operation.
    assert result["target_type"] == "TEMPLATE" and result["target_label"].endswith("2 systems")
    kinds = [(c["kind"], c["target_type"]) for c in result["children"]]
    assert kinds == [("DISCOVER", "HOST"), ("DISCOVER", "HOST"), ("RESTART", "MASS")]
    messages = [e["message"] for e in result["entries"]]
    # Both discoveries started before either finished.
    assert messages.index("Step 2/3: Discovery") < messages.index("Step 1/3: Discovery succeeded")
    assert messages.index("Step 3/3: Restart") > messages.index("Step 2/3: Discovery succeeded")


async def test_parallel_locking_steps_are_refused(app, api):
    await api.post("/api/custom-operations", json=SYSTEM_LO_TEST | {"locks": False})
    both = [
        {"position": 1, "operation": "stop", "target_type": "SYSTEM"},
        {"position": 2, "operation": "restart", "target_type": "SYSTEM"},
    ]
    await refused(api, {"key": "x", "name": "x", "steps": both}, 422, "template_parallel")
    # Fixed targets that share system C (A depends on it).
    fixed = [s | {"targets": [t]} for s, t in zip(both, (1, 3), strict=True)]
    await refused(api, {"key": "x", "name": "x", "steps": fixed}, 422, "template_parallel")
    # Different systems, or an operation that locks nothing, may run at the same time.
    apart = [s | {"targets": [t]} for s, t in zip(both, (3, 3), strict=True)]
    apart[0] = {
        "position": 1,
        "operation": "oslo_test",
        "target_type": "SYSTEM",
        "parameters": {"RC": "0"},
    }
    await define(api, {"key": "reading", "name": "Reading", "steps": apart})
    other = [both[0] | {"targets": [1]}, both[1] | {"targets": [2]}]
    await refused(api, {"key": "y", "name": "y", "steps": other}, 422, "template_parallel")


async def test_template_with_fixed_targets(app, api):
    await define(api, chain({"operation": "restart", "targets": [3]}, key="fixed"))
    template = (await api.get("/api/templates")).json()[0]
    assert template["selection"] is None
    # Not offered in the landscape (nothing to select), started as it is.
    keys = {op["key"] for op in (await api.get("/api/landscape")).json()["operations"]}
    assert "fixed" not in keys
    result = await run(app, api, f"/api/templates/{template['id']}/run")
    assert result["status"] == "SUCCEEDED" and result["target_label"] == "Kernel update"
    assert [c["target_label"] for c in result["children"]] == ["C"]
    extra = await api.post(f"/api/templates/{template['id']}/run", json={"target_ids": [1]})
    assert extra.status_code == 422

    await define(api, chain("restart", key="dialog"))
    dialog = next(t for t in (await api.get("/api/templates")).json() if t["key"] == "dialog")
    assert (await api.post(f"/api/templates/{dialog['id']}/run", json={})).status_code == 404
    started = await run(app, api, f"/api/templates/{dialog['id']}/run", {"target_ids": [3]})
    assert started["status"] == "SUCCEEDED"


async def test_error_behavior(app, api):
    await api.post("/api/custom-operations", json=SYSTEM_LO_TEST)
    failing = {"operation": "oslo_test", "parameters": {"RC": "3", "SLEEP": "1"}}

    await define(api, chain(failing, "start"))
    stopped = await run(app, api, "/api/systems/1/operations/kernel_update")
    assert stopped["status"] == "FAILED" and len(stopped["children"]) == 1
    assert "Step 1/2: Test operation ended FAILED" in stopped["error"]

    await define(api, chain(failing | {"on_error": "continue"}, "start", key="go_on"))
    partly = await run(app, api, "/api/systems/1/operations/go_on")
    assert partly["status"] == "PARTIAL" and len(partly["children"]) == 2
    assert "1 of 2 steps failed" in partly["error"]

    await define(
        api, chain("stop", failing | {"on_error": "stop_and_start"}, "restart", key="safe")
    )
    safe = await run(app, api, "/api/systems/1/operations/safe")
    assert safe["status"] == "FAILED"
    assert [c["kind"] for c in safe["children"]] == ["STOP", "CUSTOM", "START"]
    assert safe["children"][2]["status"] == "SUCCEEDED"
    assert "Step 3/3: not started" in [e["message"] for e in safe["entries"]]


async def test_template_holds_the_lock_and_can_be_cancelled(app, api):
    await define(api, chain("start", "stop"))  # the systems are stopped: start waits
    gate = hold_activities(app)
    response = await api.post("/api/systems/1/operations/kernel_update", json={})
    parent = response.json()["id"]
    await asyncio.sleep(0.05)
    # Another operation on the system waits for the template to end.
    assert (await api.post("/api/systems/1/start")).status_code == 409
    cancelled = await api.post(f"/api/activities/{parent}/cancel")
    gate.set()
    assert cancelled.status_code == 200, cancelled.text
    result = cancelled.json()
    assert result["status"] == "CANCELLED"
    assert [c["status"] for c in result["children"]] == ["CANCELLED"]


async def test_role_of_a_template(app, api):
    template = await define(api, chain("restart", role="configurator"))
    async with client(app, await make_user(app, "op", "operator")) as operator:
        response = await operator.post("/api/systems/1/operations/kernel_update", json={})
        assert response.status_code == 403
        run = await operator.post(f"/api/templates/{template['id']}/run", json={"target_ids": [1]})
        assert run.status_code == 403


async def test_building_blocks(app, api):
    await api.post("/api/systems/3/restart")
    await api.post("/api/systems/3/restart")
    await asyncio.sleep(0.05)
    blocks = (await api.get("/api/templates-blocks")).json()
    assert blocks["top"] == ["restart"] and blocks["favorites"] == []
    saved = await api.put("/api/me/favorites", json={"operations": ["stop", "nothing", "stop"]})
    assert saved.status_code == 200 and saved.json()["favorites"] == ["stop"]
    assert (await api.get("/api/templates-blocks")).json()["favorites"] == ["stop"]


# --- schedules ----------------------------------------------------------------------------

BERLIN = ZoneInfo("Europe/Berlin")


def schedule(**fields) -> Schedule:
    base = {"recurrence": "daily", "weekdays": "1234567", "last_run_at": None, "run_at": None}
    return Schedule(**(base | fields))


def test_next_run():
    monday_noon = datetime(2026, 11, 23, 11, 0, tzinfo=UTC)  # 12:00 in Berlin
    daily = schedule(time_of_day="22:00")
    assert next_run(daily, monday_noon, BERLIN) == datetime(2026, 11, 23, 21, 0, tzinfo=UTC)
    weekend = schedule(time_of_day="06:30", weekdays="67")
    assert next_run(weekend, monday_noon, BERLIN) == datetime(2026, 11, 28, 5, 30, tzinfo=UTC)
    summer = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    assert next_run(daily, summer, BERLIN) == datetime(2026, 7, 1, 20, 0, tzinfo=UTC)  # CEST

    once = schedule(recurrence="once", run_at=monday_noon + timedelta(hours=3))
    assert next_run(once, monday_noon, BERLIN) == monday_noon + timedelta(hours=3)
    once.last_run_at = monday_noon
    assert next_run(once, monday_noon, BERLIN) is None

    every = schedule(recurrence="interval", interval_minutes=60)
    assert next_run(every, monday_noon, BERLIN) == monday_noon
    every.last_run_at = monday_noon
    assert next_run(every, monday_noon, BERLIN) == monday_noon + timedelta(hours=1)


async def test_schedules_start_operations(app, api):
    scheduler = app.state.scheduler
    now = datetime(2026, 11, 23, 11, 0, tzinfo=UTC)
    scheduler.now = lambda: now
    await define(api, chain("restart"))
    body = {
        "operation": "kernel_update",
        "target_type": "SYSTEM",
        "target_ids": [1],
        "recurrence": "once",
        "run_at": (now + timedelta(minutes=10)).isoformat(),
    }
    created = await api.post("/api/schedules", json=body)
    assert created.status_code == 201, created.text
    planned = created.json()
    assert (
        planned["next_run_at"].startswith("2026-11-23T11:10") and planned["created_by"] == "admin"
    )

    assert await scheduler.tick() == []  # not yet due
    now += timedelta(minutes=11)
    [activity_id] = await scheduler.tick()
    await app.state.runner.wait(activity_id)
    activity = (await api.get(f"/api/activities/{activity_id}")).json()
    assert activity["kind"] == "TEMPLATE" and activity["requested_by"] == "admin (schedule 1)"
    done = (await api.get("/api/schedules")).json()[0]
    assert done["enabled"] is False and done["next_run_at"] is None
    assert done["last_activity_id"] == activity_id
    assert await scheduler.tick() == []  # once only

    # A daily schedule on two systems runs the template once with both as its selection.
    daily = body | {"recurrence": "daily", "time_of_day": "22:00", "target_ids": [1, 2]}
    daily.pop("run_at")
    created = (await api.post("/api/schedules", json=daily)).json()
    assert created["next_run_at"].startswith("2026-11-23T21:00")
    now = datetime(2026, 11, 23, 21, 0, 30, tzinfo=UTC)
    [run_id] = await scheduler.tick()
    await app.state.runner.wait(run_id)
    both = (await api.get(f"/api/activities/{run_id}")).json()
    assert both["target_type"] == "TEMPLATE" and both["children"][0]["target_type"] == "MASS"
    again = next(s for s in (await api.get("/api/schedules")).json() if s["id"] == created["id"])
    assert again["next_run_at"].startswith("2026-11-24T21:00")

    # A template with fixed targets is scheduled without targets.
    await define(api, chain({"operation": "restart", "targets": [3]}, key="fixed"))
    fixed = body | {"operation": "fixed", "target_type": "", "target_ids": []}
    fixed["run_at"] = (now + timedelta(minutes=5)).isoformat()
    assert (await api.post("/api/schedules", json=fixed)).status_code == 201
    wrong = await api.post("/api/schedules", json=fixed | {"target_ids": [1]})
    assert wrong.json()["detail"]["code"] == "schedule_targets"
    now += timedelta(minutes=6)
    [fixed_id] = await scheduler.tick()
    await app.state.runner.wait(fixed_id)
    assert (await api.get(f"/api/activities/{fixed_id}")).json()["status"] == "SUCCEEDED"


async def test_schedule_checks(app, api):
    base = {
        "operation": "start",
        "target_type": "SYSTEM",
        "target_ids": [1],
        "recurrence": "interval",
    }
    cases = [
        (base | {"interval_minutes": 1}, 422, "schedule_time"),
        (base | {"recurrence": "daily", "time_of_day": "25:00"}, 422, "schedule_time"),
        (base | {"recurrence": "once"}, 422, "schedule_time"),
        (base | {"operation": "nothing", "interval_minutes": 60}, 422, "schedule_operation"),
        (base | {"target_type": "HOST", "interval_minutes": 60}, 422, "schedule_operation"),
    ]
    for body, code, error in cases:
        response = await api.post("/api/schedules", json=body)
        assert response.status_code == code, (body, response.text)
        assert response.json()["detail"]["code"] == error
    async with client(app, await make_user(app, "view", "viewer")) as viewer:
        refused = await viewer.post("/api/schedules", json=base | {"interval_minutes": 60})
        assert refused.status_code == 403
    async with client(app, await make_user(app, "op", "operator")) as operator:
        ok = await operator.post("/api/schedules", json=base | {"interval_minutes": 60})
        assert ok.status_code == 201
    # The user lost the role: the run is refused and recorded.
    users = (await api.get("/api/users")).json()
    op_id = next(u["id"] for u in users if u["username"] == "op")
    await api.patch(f"/api/users/{op_id}", json={"role": "viewer"})
    assert await app.state.scheduler.tick() == []
    record = (await api.get("/api/schedules")).json()[0]
    assert "no longer has the role operator" in record["last_error"]
    assert (await api.delete(f"/api/schedules/{record['id']}")).status_code == 204

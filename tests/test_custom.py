"""Custom operations (operations.d of the host agent) and cancelling activities."""

from __future__ import annotations

import asyncio

import pytest

import test_mass
from conftest import hold_activities, make_user
from oslo.catalog import CategoryError, check_category
from oslo.customops import ParameterError, parameter_values
from oslo.customspec import CustomSpec, ParameterSpec, service_subtype
from oslo.models import Instance, System
from test_mass import client, sign_in

pytestmark = pytest.mark.anyio

# Same fixtures as the mass operations: systems A (DEV/01), B (DEV/00), C (HDV/02).
app, api, transport = test_mass.app, test_mass.api, test_mass.transport

OSLO_TEST = {
    "key": "oslo_test",
    "name": "Test operation",
    "agent_operation": "OSLO_TEST",
    "target": "INSTANCE",
    "role": "operator",
    "timeout_seconds": 60,
    "parameters": [
        {"name": "A", "label": "Text"},
        {"name": "SLEEP", "label": "Duration", "type": "INTEGER", "default": "2"},
        {"name": "RC", "label": "Exit code", "type": "INTEGER", "required": True},
    ],
}


def spec(*parameters: ParameterSpec) -> CustomSpec:
    return CustomSpec(1, "T", None, "OSLO_TEST", "HOST", (), "parallel", 60, parameters)


def log(activity: dict) -> list[str]:
    return [entry["message"] for entry in activity["entries"]]


async def finished(app, api, activity_id: int) -> dict:
    await app.state.runner.wait(activity_id)
    return (await api.get(f"/api/activities/{activity_id}")).json()


# --- values ---------------------------------------------------------------------------------


def test_parameter_values():
    text = ParameterSpec("A", "A", "STRING", False, None, None, None)
    number = ParameterSpec("N", "N", "INTEGER", True, None, None, None)
    flag = ParameterSpec("F", "F", "BOOLEAN", False, None, None, None)
    own = ParameterSpec("P", "P", "STRING", False, None, r"\d{3}", None)
    values = parameter_values(spec(text, number, flag, own), {"N": 5, "F": "true", "P": "793"})
    # The empty optional text is not passed at all.
    assert values == {"PARAM-N": "5", "PARAM-F": "true", "PARAM-P": "793"}
    assert parameter_values(spec(flag), {})["PARAM-F"] == "false"
    with pytest.raises(ParameterError) as problems:
        parameter_values(spec(text, number, own), {"A": "a;rm -rf /", "N": "x", "P": "79"})
    assert set(problems.value.problems) == {"A", "N", "P"}
    with pytest.raises(ParameterError, match="N: required"):
        parameter_values(spec(number), {"N": " "})


def test_service_subtype():
    def Inst(features):  # noqa: N802
        return Instance(features=features)

    def Sys(*instances):  # noqa: N802
        return System(instances=list(instances))

    abap, java = Inst("ABAP|GATEWAY|ICMAN|IGS"), Inst("J2EE|IGS")
    scs, hana, agent = Inst("MESSAGESERVER|ENQUE"), Inst("HDB|HDB_WORKER"), Inst("SMDAGENT")
    assert service_subtype(abap, Sys(abap, scs)) == "Instance_Application_Server/ABAP"
    assert service_subtype(scs, Sys(abap, scs)) == "Instance_SCS/ABAP"
    assert service_subtype(scs, Sys(java, scs)) == "Instance_SCS/J2EE"
    assert service_subtype(hana, Sys(abap, hana)) == "Instance_System_HDB/ABAP"
    assert service_subtype(agent, None) == "Instance_Diag_Agnt/SolMan"


# --- API ------------------------------------------------------------------------------------


async def create(api, body=OSLO_TEST) -> dict:
    response = await api.post("/api/custom-operations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_define_custom_operations(app, api):
    operation = await create(api)
    assert [p["name"] for p in operation["parameters"]] == ["A", "SLEEP", "RC"]
    assert (await api.post("/api/custom-operations", json=OSLO_TEST)).status_code == 409
    builtin = OSLO_TEST | {"key": "start"}
    assert (await api.post("/api/custom-operations", json=builtin)).status_code == 422
    bad_default = OSLO_TEST | {
        "key": "x",
        "parameters": [{"name": "N", "label": "N", "type": "INTEGER", "default": "a"}],
    }
    assert (await api.post("/api/custom-operations", json=bad_default)).status_code == 422

    listed = {op["key"]: op for op in (await api.get("/api/operations")).json()}
    assert listed["oslo_test"]["custom"] and listed["oslo_test"]["targets"] == ["INSTANCE"]
    assert listed["oslo_test"]["parameters"][2]["required"]

    changed = OSLO_TEST | {"name": "Renamed", "parameters": [{"name": "RC", "label": "RC"}]}
    response = await api.put(f"/api/custom-operations/{operation['id']}", json=changed)
    assert response.json()["name"] == "Renamed" and len(response.json()["parameters"]) == 1
    assert app.state.catalog.get("oslo_test").custom.name == "Renamed"

    async with client(app, await make_user(app, "conf", "configurator")) as configurator:
        assert (await configurator.get("/api/custom-operations")).status_code == 403
        response = await configurator.post("/api/custom-operations", json=OSLO_TEST)
        assert response.status_code == 403

    assert (await api.delete(f"/api/custom-operations/{operation['id']}")).status_code == 204
    assert app.state.catalog.get("oslo_test") is None


def test_check_category():
    assert check_category(None) == "" and check_category("  ") == ""
    assert check_category(" Automation /  Kernel  update ") == "Automation/Kernel update"
    for bad in ("a/b/c", "a/", "/b", "x" * 41, "cat.oslo", "Automation/cat.x"):
        with pytest.raises(CategoryError):
            check_category(bad)


async def test_categories_of_operations(app, api):
    body = OSLO_TEST | {"category": "Automation / Kernel"}
    response = await api.post("/api/custom-operations", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["category"] == "Automation/Kernel"
    for bad in ("a/b/c", "cat.instance_agent"):
        body = OSLO_TEST | {"key": "x", "category": bad}
        response = await api.post("/api/custom-operations", json=body)
        assert response.status_code == 422, response.text

    listed = {op["key"]: op for op in (await api.get("/api/operations")).json()}
    assert listed["oslo_test"]["category"] == "Automation/Kernel"
    # Built-in operations: start, stop, restart stay without a category (buttons).
    assert listed["start"]["category"] == ""
    assert listed["register"]["category"] == "cat.instance_agent"
    assert listed["update_bundle"]["category"] == "cat.oslo"
    landscape = (await api.get("/api/landscape")).json()
    rows = {op["key"]: op for op in landscape["operations"]}
    assert rows["oslo_test"]["category"] == "Automation/Kernel"


async def test_run_on_instance(app, api, landscape):
    await create(api)
    async with client(app, await make_user(app, "op", "operator")) as operator:
        body = {"parameters": {"A": "hello", "RC": 0}}
        response = await operator.post("/api/instances/2/operations/oslo_test", json=body)
        assert response.status_code == 202, response.text
        result = await finished(app, api, response.json()["id"])
    assert result["status"] == "SUCCEEDED" and result["kind"] == "CUSTOM"
    messages = log(result)
    assert any(m.startswith("Started on sapapp1, operation ") for m in messages)
    assert any("hook successfully executed" in m for m in messages)
    assert not any("Executing" in m for m in messages)
    run = next(iter(landscape.operation_runs.values()))
    # In the order of Command: SAPSYSTEMNAME SAPSYSTEM SERVICE_SUBTYPE PARAM-A -SLEEP -RC
    assert run.arguments == ["DEV", "00", "Instance_Application_Server/ABAP", "hello", "2", "0"]

    missing = await api.post("/api/instances/2/operations/oslo_test", json={"parameters": {}})
    assert missing.status_code == 422 and "RC: required" in missing.text
    assert (await api.post("/api/systems/1/operations/oslo_test", json={})).status_code == 404
    assert (await api.post("/api/instances/2/operations/nothing", json={})).status_code == 404


async def test_script_that_ends_between_two_calls(app, api, landscape):
    """The results come without fault although IsOperationFinished said "not yet"; the host
    agent forgets the operation then (seen on a real host)."""
    await create(api)
    landscape.finish_between_calls = True
    body = {"parameters": {"RC": 0, "SLEEP": 0}}
    response = await api.post("/api/instances/2/operations/oslo_test", json=body)
    assert response.status_code == 202, response.text
    result = await finished(app, api, response.json()["id"])
    assert result["status"] == "SUCCEEDED", result
    assert any("hook successfully executed" in m for m in log(result))


async def test_failed_script(app, api):
    await create(api)
    body = {"parameters": {"RC": 3}}
    response = await api.post("/api/instances/2/operations/oslo_test", json=body)
    result = await finished(app, api, response.json()["id"])
    assert result["status"] == "FAILED"
    assert "exit code = 3" in result["error"]


async def test_timeout_cancels_on_the_host(app, api, landscape):
    await create(api)
    body = {"parameters": {"RC": 0, "SLEEP": 500}}
    response = await api.post("/api/instances/2/operations/oslo_test?timeout=10", json=body)
    result = await finished(app, api, response.json()["id"])
    assert result["status"] == "FAILED"
    assert not landscape.operation_runs  # cancelled and forgotten by the host agent


async def test_role_of_the_operation(app, api):
    await create(api, OSLO_TEST | {"role": "admin"})
    async with client(app, await make_user(app, "op", "operator")) as operator:
        body = {"parameters": {"RC": 0}}
        response = await operator.post("/api/instances/2/operations/oslo_test", json=body)
        assert response.status_code == 403
        operations = (await operator.get("/api/operations")).json()
        assert all(op["key"] != "oslo_test" for op in operations)
    async with client(app, await make_user(app, "view", "viewer")) as viewer:
        response = await viewer.post("/api/instances/2/operations/oslo_test", json=body)
        assert response.status_code == 403


async def test_run_on_system_by_roles(app, api, landscape):
    """System A (DEV/01) and B (DEV/00) in one system with C: roles order the instances."""
    ids = {i["label"]: i["id"] for i in (await api.get("/api/instances")).json()}
    for system in (1, 2):
        await api.delete(f"/api/systems/{system}")
    await api.post(
        "/api/systems/3/instances", json={"instance_ids": [ids["DEV/00"], ids["DEV/01"]]}
    )
    await create(api, OSLO_TEST | {"target": "SYSTEM", "ordering": "roles"})
    body = {"parameters": {"RC": 0, "SLEEP": 1}}
    response = await api.post("/api/systems/3/operations/oslo_test", json=body)
    assert response.status_code == 202, response.text
    result = await finished(app, api, response.json()["id"])
    assert result["status"] == "SUCCEEDED"
    started = [m for m in log(result) if "Started on" in m]
    assert len(started) == 3
    # The application server comes after the database and the central services.
    assert started[-1].startswith("DEV/00: Started on sapapp1")


async def test_run_on_host(app, api, landscape):
    await create(api, OSLO_TEST | {"target": "HOST", "parameters": []})
    response = await api.post("/api/hosts/2/operations/oslo_test", json={})
    result = await finished(app, api, response.json()["id"])
    assert result["status"] == "SUCCEEDED", log(result)
    run = next(iter(landscape.operation_runs.values()))
    assert run.host == "sapdb1" and run.arguments == []


async def test_operation_that_locks_nothing(app, api):
    """A read-only script runs beside a running stop and does not block other activities."""
    await create(api, OSLO_TEST | {"locks": False})
    gate = hold_activities(app)
    stop = (await api.post("/api/systems/2/stop")).json()["id"]
    await asyncio.sleep(0.05)
    body = {"parameters": {"RC": 0, "SLEEP": 5}}
    reading = await api.post("/api/instances/2/operations/oslo_test", json=body)
    assert reading.status_code == 202, reading.text
    await asyncio.sleep(0.05)
    gate.set()
    await app.state.runner.wait(stop)
    # While the script runs, the system can be started again.
    start = await api.post("/api/systems/2/start")
    assert start.status_code == 202, start.text
    for activity in (reading.json()["id"], start.json()["id"]):
        assert (await finished(app, api, activity))["status"] == "SUCCEEDED"
    operations = {o["key"]: o for o in (await api.get("/api/operations")).json()}
    assert operations["oslo_test"]["locks"] is False


async def test_operation_only_for_templates(app, api):
    await create(api, OSLO_TEST | {"standalone": False})
    assert (await api.post("/api/instances/2/operations/oslo_test", json={})).status_code == 404
    mass = {"operation": "oslo_test", "target_type": "INSTANCE", "target_ids": [2]}
    assert (await api.post("/api/mass-operations", json=mass)).status_code == 422
    landscape = (await api.get("/api/landscape")).json()
    assert "oslo_test" not in {o["key"] for o in landscape["operations"]}
    # As a step of a template it runs.
    step = {"operation": "oslo_test", "target_type": "INSTANCE", "parameters": {"RC": "0"}}
    body = {"key": "only", "name": "Only", "steps": [step]}
    assert (await api.post("/api/templates", json=body)).status_code == 201
    response = await api.post("/api/instances/2/operations/only", json={})
    assert response.status_code == 202, response.text
    assert (await finished(app, api, response.json()["id"]))["status"] == "SUCCEEDED"


async def test_cancel_custom_operation(app, api, landscape):
    await create(api)
    gate = hold_activities(app)
    body = {"parameters": {"RC": 0, "SLEEP": 30}}
    response = await api.post("/api/instances/2/operations/oslo_test", json=body)
    activity_id = response.json()["id"]
    await asyncio.sleep(0.05)
    async with client(app, await make_user(app, "op", "operator")) as operator:
        cancelled = await operator.post(f"/api/activities/{activity_id}/cancel")
    gate.set()
    assert cancelled.status_code == 200, cancelled.text
    result = cancelled.json()
    assert result["status"] == "CANCELLED"
    assert any("Cancelled by op" in m for m in log(result))
    assert not landscape.operation_runs
    again = await api.post(f"/api/activities/{activity_id}/cancel")
    assert again.status_code == 409
    assert (await api.post("/api/activities/999/cancel")).status_code == 404


async def test_cancel_start_only_stops_waiting(app, api):
    gate = hold_activities(app)
    activity_id = (await api.post("/api/systems/1/start")).json()["id"]
    await asyncio.sleep(0.05)
    result = (await api.post(f"/api/activities/{activity_id}/cancel")).json()
    gate.set()
    assert result["status"] == "CANCELLED"
    assert any("keep running" in m or "already requested" in m for m in log(result)), log(result)
    async with client(app, await make_user(app, "view", "viewer")) as viewer:
        assert (await viewer.post(f"/api/activities/{activity_id}/cancel")).status_code == 403


async def test_cancel_mass_operation(app, api):
    await create(api)
    gate = hold_activities(app)
    body = {
        "operation": "oslo_test",
        "target_type": "INSTANCE",
        "target_ids": [1, 2, 3],
        "parallel": 1,
        "parameters": {"RC": 0, "SLEEP": 30},
    }
    response = await api.post("/api/mass-operations", json=body)
    assert response.status_code == 202, response.text
    parent_id = response.json()["id"]
    await asyncio.sleep(0.05)
    result = (await api.post(f"/api/activities/{parent_id}/cancel")).json()
    gate.set()
    assert result["status"] == "CANCELLED"
    statuses = {child["status"] for child in result["children"]}
    assert "CANCELLED" in statuses and "SUCCEEDED" not in statuses

    wrong = body | {"parameters": {}}
    assert (await api.post("/api/mass-operations", json=wrong)).status_code == 422


# --- web ------------------------------------------------------------------------------------


async def test_custom_operations_in_the_browser(app, api, landscape):
    """The pages of custom operations use the API with the session cookie."""
    headers = {"X-OSLO-Request": "1"}
    async with sign_in(app) as browser:
        assert (await browser.get("/operations/custom")).status_code == 200
        body = OSLO_TEST | {"instance_types": ["abap"]}
        created = await browser.post("/api/custom-operations", json=body, headers=headers)
        assert created.status_code == 201, created.text
        assert (await browser.get(f"/operations/custom/{created.json()['id']}")).status_code == 200
        taken = await browser.post("/api/custom-operations", json=body, headers=headers)
        assert taken.status_code == 409

        # Only the ABAP application server (instance 2) gets the operation.
        refused = await browser.post(
            "/api/instances/1/operations/oslo_test", json={"parameters": {"RC": 0}}, headers=headers
        )
        assert refused.status_code == 422
        started = await browser.post(
            "/api/instances/2/operations/oslo_test", json={"parameters": {"RC": 0}}, headers=headers
        )
        assert started.status_code == 202
        await app.state.runner.wait(started.json()["id"])
        activity = (await browser.get(f"/api/activities/{started.json()['id']}")).json()
        assert activity["status"] == "SUCCEEDED"
        assert activity["options"]["parameters"] == {"PARAM-SLEEP": "2", "PARAM-RC": "0"}
        data = (await browser.get("/api/landscape")).json()
        offered = {op["key"]: op for op in data["operations"]}
        assert offered["oslo_test"]["instance_types"] == ["abap"]

    await make_user(app, "conf", "configurator")
    async with sign_in(app, "conf") as configurator:
        assert (await configurator.get("/operations/custom")).status_code == 403
        assert (await configurator.get("/operations/templates")).status_code == 403
        # The Operations area shows them only the schedules.
        area = await configurator.get("/operations")
        assert area.headers["location"] == "/operations/schedules"
        page = (await configurator.get("/operations/schedules")).text
        assert 'href="/operations/custom"' not in page and 'href="/operations/schedules"' in page


async def test_cancel_in_the_browser(app, api):
    gate = hold_activities(app)
    activity_id = (await api.post("/api/systems/1/start")).json()["id"]
    await asyncio.sleep(0.05)
    headers = {"X-OSLO-Request": "1"}
    async with sign_in(app) as browser:
        # The activity page cancels through the API with the session cookie.
        response = await browser.post(f"/api/activities/{activity_id}/cancel", headers=headers)
        gate.set()
        assert response.status_code == 200 and response.json()["status"] == "CANCELLED"
        again = await browser.post(f"/api/activities/{activity_id}/cancel", headers=headers)
        assert again.status_code == 409

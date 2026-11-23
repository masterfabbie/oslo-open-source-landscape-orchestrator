from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest

from conftest import PASSWORD, hold_activities, make_user
from oslo import catalog
from oslo.api import create_app
from oslo.crypto import generate_secret_key
from oslo.mock.landscape import Status
from oslo.mock.transport import MockLandscapeTransport
from oslo.models import User
from oslo.operations import TargetType
from oslo.settings import Settings

pytestmark = pytest.mark.anyio

APP_HOST = {"name": "sapapp1", "address": "127.0.0.1", "username": "devadm", "password": "mock"}
DB_HOST = APP_HOST | {"name": "sapdb1", "hostagent_port": 11128, "sapcontrol_port_offset": 10000}


def test_catalog():
    keys = [op.key for op in catalog.for_target(TargetType.SYSTEM)]
    assert keys == ["start", "stop", "restart"]
    assert [op.key for op in catalog.for_target(TargetType.HOST)] == ["discover"]
    assert catalog.for_target(TargetType.HOST, User(role="operator")) == []
    assert catalog.get("stop").label_key(TargetType.SYSTEM) == "op.stop_system"
    assert catalog.get("stop").label_key(TargetType.INSTANCE) == "op.stop"
    assert catalog.get("nothing") is None


@pytest.fixture
async def app(tmp_path, landscape, clock, transport):
    settings = Settings(
        secret_key=generate_secret_key(), database_url=f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"
    )

    async def fake_sleep(seconds: float) -> None:
        clock.advance(seconds)
        await asyncio.sleep(0)

    application = create_app(
        settings, transport=transport, poll_interval=1.0, sleep=fake_sleep, clock=clock
    )
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
def transport(landscape) -> MockLandscapeTransport:
    return MockLandscapeTransport(landscape)


def client(app, token: str | None = None) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
    )


@pytest.fixture
async def api(app):
    """Admin client; systems A (DEV/01), B (DEV/00), C (HDV/02); A and B depend on C."""
    async with client(app, await make_user(app)) as admin:
        for body in (APP_HOST, DB_HOST):
            host = (await admin.post("/api/hosts", json=body)).json()
            assert (await admin.post(f"/api/hosts/{host['id']}/discover")).status_code == 200
        ids = {i["label"]: i["id"] for i in (await admin.get("/api/instances")).json()}
        for name, label in (("A", "DEV/01"), ("B", "DEV/00"), ("C", "HDV/02")):
            body = {"name": name, "instance_ids": [ids[label]]}
            assert (await admin.post("/api/systems", json=body)).status_code == 201
        for system in (1, 2):
            await admin.put(f"/api/systems/{system}/dependencies", json={"depends_on": [3]})
        yield admin


async def run_mass(app, api, **body) -> dict:
    response = await api.post("/api/mass-operations", json=body)
    assert response.status_code == 202, response.text
    parent = response.json()
    assert parent["target_type"] == "MASS"
    await app.state.runner.wait(parent["id"])
    return (await api.get(f"/api/activities/{parent['id']}")).json()


def log(activity: dict) -> list[str]:
    return [entry["message"] for entry in activity["entries"]]


async def test_list_operations(app, api):
    keys = {op["key"]: op for op in (await api.get("/api/operations")).json()}
    agent = {"register", "unregister", "reregister"}
    assert set(keys) == {"start", "stop", "restart", "discover"} | agent
    assert keys["discover"]["targets"] == ["HOST"]
    async with client(app, await make_user(app, "op", "operator")) as operator:
        offered = {o["key"] for o in (await operator.get("/api/operations")).json()}
        assert offered == {"start", "stop", "restart"} | agent


async def test_mass_start_follows_dependencies(app, api, landscape, clock):
    result = await run_mass(
        app, api, operation="start", target_type="SYSTEM", target_ids=[1, 2, 3], parallel=5
    )
    assert result["status"] == "SUCCEEDED", log(result)
    assert result["target_label"] == "3 systems"
    assert len(result["children"]) == 3
    started = [m for m in log(result) if "started" in m]
    # C first; A and B only after C succeeded, then both at once.
    assert started[0].startswith("System C:")
    assert {s.split(":")[0] for s in started[1:]} == {"System A", "System B"}
    c_done = log(result).index(
        next(m for m in log(result) if m.startswith("System C: activity") and "SUCCEEDED" in m)
    )
    assert all(log(result).index(s) > c_done for s in started[1:])
    assert {c["requested_by"] for c in result["children"]} == {"admin"}
    assert all(c["parent_id"] == result["id"] for c in result["children"])
    assert log(result)[-1] == "Finished: 3 succeeded, 0 failed, 0 skipped"
    for host, nr in (("sapapp1", 0), ("sapapp1", 1), ("sapdb1", 2)):
        assert landscape.host(host).instance(nr).status(clock()) is Status.RUNNING


async def test_mass_stop_goes_dependents_first(app, api):
    await run_mass(app, api, operation="start", target_type="SYSTEM", target_ids=[1, 2, 3])
    result = await run_mass(
        app, api, operation="stop", target_type="SYSTEM", target_ids=[3, 1, 2], parallel=5
    )
    assert result["status"] == "SUCCEEDED", log(result)
    started = [m.split(":")[0] for m in log(result) if "started" in m]
    assert started[-1] == "System C"


async def test_shared_dependency_waits_for_the_sibling(app, api):
    """A and B both need C; B waits until A releases C instead of failing."""
    result = await run_mass(app, api, operation="start", target_type="SYSTEM", target_ids=[1, 2])
    assert result["status"] == "SUCCEEDED", log(result)
    assert [c["target_label"] for c in result["children"]] == ["A", "B"]


async def test_parallel_one_runs_one_after_another(app, api):
    result = await run_mass(
        app, api, operation="start", target_type="INSTANCE", target_ids=[1, 2, 3], parallel=1
    )
    assert result["status"] == "SUCCEEDED", log(result)
    lines = log(result)
    events = [m for m in lines if "activity" in m]
    # started, finished, started, finished, ...
    assert ["started" in m for m in events] == [True, False, True, False, True, False]


async def test_failures_continue_or_stop(app, api, transport):
    transport.remove_port(11128)  # host agent of sapdb1: C cannot be started
    partial = await run_mass(
        app, api, operation="start", target_type="INSTANCE", target_ids=[3, 1, 2], parallel=1
    )
    assert partial["status"] == "PARTIAL"
    assert partial["error"] == "2 succeeded, 1 failed, 0 skipped"

    await run_mass(app, api, operation="stop", target_type="INSTANCE", target_ids=[1, 2])
    halted = await run_mass(
        app,
        api,
        operation="start",
        target_type="INSTANCE",
        target_ids=[3, 1, 2],
        parallel=1,
        stop_on_error=True,
    )
    assert halted["status"] == "FAILED"
    assert halted["error"] == "0 succeeded, 1 failed, 2 skipped"
    assert sum("not started" in m for m in log(halted)) == 2

    # A dependency that fails skips the systems that need it.
    systems = await run_mass(
        app, api, operation="start", target_type="SYSTEM", target_ids=[1, 3], parallel=5
    )
    assert systems["status"] == "FAILED"
    assert any("System A: skipped, a dependency failed" == m for m in log(systems))


async def test_target_busy_outside_the_mass_operation_is_skipped(app, api):
    gate = hold_activities(app)
    single = await api.post("/api/instances/3/start")
    assert single.status_code == 202
    result = await run_mass(app, api, operation="start", target_type="SYSTEM", target_ids=[3])
    gate.set()
    await app.state.runner.wait(single.json()["id"])
    assert result["status"] == "FAILED"
    assert any("skipped, Activity" in m and "is still running" in m for m in log(result))


async def test_mass_discovery_and_roles(app, api):
    result = await run_mass(app, api, operation="discover", target_type="HOST", target_ids=[1, 2])
    assert result["status"] == "SUCCEEDED", log(result)
    child = (await api.get(f"/api/activities/{result['children'][0]['id']}")).json()
    assert child["target_type"] == "HOST" and child["kind"] == "DISCOVER"
    assert any(m.startswith("Discovery: 0 instances new, 2 updated") for m in log(child))

    async with client(app, await make_user(app, "op", "operator")) as operator:
        body = {"operation": "discover", "target_type": "HOST", "target_ids": [1]}
        assert (await operator.post("/api/mass-operations", json=body)).status_code == 403
        body = {"operation": "stop", "target_type": "HOST", "target_ids": [1]}
        assert (await operator.post("/api/mass-operations", json=body)).status_code == 422
    async with client(app, await make_user(app, "view", "viewer")) as viewer:
        body = {"operation": "start", "target_type": "SYSTEM", "target_ids": [1]}
        assert (await viewer.post("/api/mass-operations", json=body)).status_code == 403
    body = {"operation": "start", "target_type": "SYSTEM", "target_ids": [99]}
    assert (await api.post("/api/mass-operations", json=body)).status_code == 404
    body = body | {"target_ids": [1], "parallel": 50}
    assert (await api.post("/api/mass-operations", json=body)).status_code == 422


# --- web ----------------------------------------------------------------------------------


@asynccontextmanager
async def sign_in(app, username: str = "admin") -> AsyncIterator[httpx.AsyncClient]:
    async with client(app) as browser:
        await browser.post("/login", data={"username": username, "password": PASSWORD})
        yield browser


async def test_mass_operation_in_the_browser(app, api):
    """The landscape page starts mass operations through the API with the session cookie."""
    async with sign_in(app) as browser:
        body = {"operation": "start", "target_type": "SYSTEM", "target_ids": [1, 2, 3]}
        refused = await browser.post("/api/mass-operations", json=body)
        assert refused.status_code == 403  # without the header of the interface
        headers = {"X-OSLO-Request": "1"}
        response = await browser.post("/api/mass-operations", json=body, headers=headers)
        assert response.status_code == 202, response.text
        parent_id = response.json()["id"]
        await app.state.runner.wait(parent_id)
        detail = (await browser.get(f"/api/activities/{parent_id}")).json()
        assert detail["target_type"] == "MASS" and detail["options"]["parallel"] == 5
        assert len(detail["children"]) == 3
        assert {c["parent_id"] for c in detail["children"]} == {parent_id}
        page = (await browser.get(f"/activities/{parent_id + 1}")).text
        assert 'src="/static/app/activity.js?v=' in page
        # The old page for mass operations is gone; the landscape does it now.
        assert (await browser.get("/mass")).status_code == 404


async def test_host_operations_in_the_browser(app, api):
    headers = {"X-OSLO-Request": "1"}
    body = {"operation": "discover", "target_type": "HOST", "target_ids": [1]}
    async with sign_in(app) as browser:
        started = await browser.post("/api/mass-operations", json=body, headers=headers)
        assert started.status_code == 202
        await app.state.runner.wait(started.json()["id"])

    await make_user(app, "op", "operator")
    async with sign_in(app, "op") as operator:
        data = (await operator.get("/api/landscape")).json()
        assert "discover" not in {op["key"] for op in data["operations"]}
        refused = await operator.post("/api/mass-operations", json=body, headers=headers)
        assert refused.status_code == 403  # discovery needs a configurator

    await make_user(app, "view", "viewer")
    async with sign_in(app, "view") as viewer:
        data = (await viewer.get("/api/landscape")).json()
        assert data["operations"] == []  # a viewer may run nothing


async def test_steps_of_a_mass_operation(app, api):
    parent = await run_mass(
        app, api, operation="stop", target_type="SYSTEM", target_ids=[1, 2], parallel=2
    )
    steps = (await api.get(f"/api/steps?activity_id={parent['id']}")).json()
    # One step per target, all naming the mass operation; the mass operation itself is none.
    assert sorted(s["target_label"] for s in steps) == ["A", "B"]
    assert {s["activity_id"] for s in steps} == {parent["id"]}
    assert parent["id"] not in {s["id"] for s in (await api.get("/api/steps")).json()}
    assert (await api.get("/api/steps?activity_id=999")).status_code == 404

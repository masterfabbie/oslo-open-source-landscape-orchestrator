from __future__ import annotations

import asyncio

import httpx
import pytest

from conftest import hold_activities, make_user, stopped_config
from oslo.api import create_app
from oslo.crypto import generate_secret_key
from oslo.mock.landscape import MockLandscape, Status
from oslo.mock.transport import MockLandscapeTransport
from oslo.settings import Settings

pytestmark = pytest.mark.anyio

APP_HOST = {
    "name": "sapapp1",
    "address": "127.0.0.1",
    "username": "devadm",
    "password": "mock",
}
DB_HOST = APP_HOST | {"name": "sapdb1", "hostagent_port": 11128, "sapcontrol_port_offset": 10000}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        secret_key=generate_secret_key(),
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'ops.db'}",
    )


@pytest.fixture
def transport(landscape) -> MockLandscapeTransport:
    return MockLandscapeTransport(landscape)


@pytest.fixture
def make_app(settings, transport, clock):
    """App whose operation tracking runs on the fake clock: each poll advances it by 1 s."""

    async def fake_sleep(seconds: float) -> None:
        clock.advance(seconds)
        await asyncio.sleep(0)

    def factory():
        return create_app(
            settings, transport=transport, poll_interval=1.0, sleep=fake_sleep, clock=clock
        )

    return factory


@pytest.fixture
async def app(make_app):
    application = make_app()
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def api(app, settings):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {await make_user(app)}"},
    ) as client:
        for body in (APP_HOST, DB_HOST):
            host = (await client.post("/api/hosts", json=body)).json()
            assert (await client.post(f"/api/hosts/{host['id']}/discover")).status_code == 200
        # As in a real landscape: the ABAP system and the system of its HANA database.
        ids = {i["number"]: i["id"] for i in (await client.get("/api/instances")).json()}
        for name, numbers in (("DEV", ("00", "01")), ("HDV", ("02",))):
            body = {"name": name, "instance_ids": [ids[n] for n in numbers]}
            assert (await client.post("/api/systems", json=body)).status_code == 201
        yield client


async def instance_id(api: httpx.AsyncClient, number: str) -> int:
    instances = (await api.get("/api/instances")).json()
    return next(i["id"] for i in instances if i["number"] == number)


async def system_id(api: httpx.AsyncClient, name: str) -> int:
    return next(s["id"] for s in (await api.get("/api/systems")).json() if s["name"] == name)


async def statuses(api: httpx.AsyncClient) -> dict[str, str]:
    """Instance number -> stored status; 00 and 01 belong to DEV, 02 to HDV."""
    systems = (await api.get("/api/systems")).json()
    return {i["number"]: i["last_status"] for s in systems for i in s["instances"]}


async def depend(api: httpx.AsyncClient, name: str, *on: str) -> None:
    ids = [await system_id(api, other) for other in on]
    response = await api.put(
        f"/api/systems/{await system_id(api, name)}/dependencies", json={"depends_on": ids}
    )
    assert response.status_code == 200, response.text


async def run(app, api: httpx.AsyncClient, path: str) -> dict:
    """Submit an operation, wait for it and return the finished activity with its log."""
    response = await api.post(path)
    assert response.status_code == 202, response.text
    activity = response.json()
    assert activity["status"] == "PENDING"
    await app.state.runner.wait(activity["id"])
    return (await api.get(f"/api/activities/{activity['id']}")).json()


def messages(activity: dict) -> list[str]:
    return [entry["message"] for entry in activity["entries"]]


async def test_start_instance(app, api, landscape, clock):
    dialog = await instance_id(api, "00")

    activity = await run(app, api, f"/api/instances/{dialog}/start")

    assert activity["status"] == "SUCCEEDED"
    assert (activity["kind"], activity["target_type"]) == ("START", "INSTANCE")
    assert activity["target_label"] == "DEV/00"
    assert activity["error"] is None
    assert activity["started_at"] and activity["finished_at"]
    assert messages(activity) == [
        "Start of DEV/00 requested via host agent of sapapp1",
        "Instance status: YELLOW",
        "Instance status: GREEN",
        "Finished successfully",
    ]
    assert landscape.host("sapapp1").instance(0).status(clock()) is Status.RUNNING
    assert await statuses(api) == {"00": "GREEN", "01": "GRAY", "02": "GRAY"}


async def test_stop_and_restart_instance(app, api, landscape, clock):
    dialog = await instance_id(api, "00")
    await run(app, api, f"/api/instances/{dialog}/start")

    restart = await run(app, api, f"/api/instances/{dialog}/restart")
    assert restart["status"] == "SUCCEEDED"
    assert messages(restart) == [
        "Stop of DEV/00 requested via host agent of sapapp1",
        "Instance status: YELLOW",
        "Instance status: GRAY",
        "Start of DEV/00 requested via host agent of sapapp1",
        "Instance status: YELLOW",
        "Instance status: GREEN",
        "Finished successfully",
    ]

    stop = await run(app, api, f"/api/instances/{dialog}/stop")
    assert stop["status"] == "SUCCEEDED"
    assert landscape.host("sapapp1").instance(0).status(clock()) is Status.STOPPED
    assert (await statuses(api))["00"] == "GRAY"


async def test_start_and_stop_system_without_dependencies(app, api):
    dev = await system_id(api, "DEV")

    start = await run(app, api, f"/api/systems/{dev}/start")
    assert start["status"] == "SUCCEEDED"
    assert start["target_label"] == "DEV"
    # Central services (priority 1) first, then the dialog instance (priority 3).
    # The HANA system is not touched.
    assert messages(start) == [
        "System DEV status: DEV/00:GRAY DEV/01:GRAY",
        "Start of DEV/01 requested via host agent of sapapp1",
        "System DEV status: DEV/00:GRAY DEV/01:YELLOW",
        "System DEV status: DEV/00:GRAY DEV/01:GREEN",
        "Start of DEV/00 requested via host agent of sapapp1",
        "System DEV status: DEV/00:YELLOW DEV/01:GREEN",
        "System DEV status: DEV/00:GREEN DEV/01:GREEN",
        "Finished successfully",
    ]
    assert await statuses(api) == {"00": "GREEN", "01": "GREEN", "02": "GRAY"}

    stop = await run(app, api, f"/api/systems/{dev}/stop")
    assert stop["status"] == "SUCCEEDED"
    requests = [m for m in messages(stop) if " requested " in m]
    assert requests == [
        "Stop of DEV/00 requested via host agent of sapapp1",
        "Stop of DEV/01 requested via host agent of sapapp1",
    ]
    assert await statuses(api) == {"00": "GRAY", "01": "GRAY", "02": "GRAY"}


async def test_system_already_in_target_state(app, api):
    dev = await system_id(api, "DEV")
    await run(app, api, f"/api/systems/{dev}/start")

    again = await run(app, api, f"/api/systems/{dev}/start")

    assert again["status"] == "SUCCEEDED"
    assert messages(again) == [
        "System DEV status: DEV/00:GREEN DEV/01:GREEN",
        "System DEV is already running",
        "Finished successfully",
    ]


async def test_start_system_starts_dependencies_first(app, api):
    await depend(api, "DEV", "HDV")

    start = await run(app, api, f"/api/systems/{await system_id(api, 'DEV')}/start")

    assert start["status"] == "SUCCEEDED"
    assert messages(start) == [
        "Start order including dependencies: HDV, DEV",
        "System HDV status: HDV/02:GRAY",
        "Start of HDV/02 requested via host agent of sapdb1",
        "System HDV status: HDV/02:YELLOW",
        "System HDV status: HDV/02:GREEN",
        "System DEV status: DEV/00:GRAY DEV/01:GRAY",
        "Start of DEV/01 requested via host agent of sapapp1",
        "System DEV status: DEV/00:GRAY DEV/01:YELLOW",
        "System DEV status: DEV/00:GRAY DEV/01:GREEN",
        "Start of DEV/00 requested via host agent of sapapp1",
        "System DEV status: DEV/00:YELLOW DEV/01:GREEN",
        "System DEV status: DEV/00:GREEN DEV/01:GREEN",
        "Finished successfully",
    ]
    assert set((await statuses(api)).values()) == {"GREEN"}


async def test_stop_system_stops_dependencies_afterwards(app, api):
    await depend(api, "DEV", "HDV")
    dev = await system_id(api, "DEV")
    await run(app, api, f"/api/systems/{dev}/start")

    stop = await run(app, api, f"/api/systems/{dev}/stop")

    assert stop["status"] == "SUCCEEDED"
    log = messages(stop)
    assert log[0] == "Stop order including dependencies: DEV, HDV"
    assert [m for m in log if " requested " in m] == [
        "Stop of DEV/00 requested via host agent of sapapp1",
        "Stop of DEV/01 requested via host agent of sapapp1",
        "Stop of HDV/02 requested via host agent of sapdb1",
    ]
    assert log.index("System DEV status: DEV/00:GRAY DEV/01:GRAY") < log.index(
        "Stop of HDV/02 requested via host agent of sapdb1"
    )
    assert set((await statuses(api)).values()) == {"GRAY"}


async def test_restart_system_with_dependency(app, api):
    await depend(api, "DEV", "HDV")
    dev = await system_id(api, "DEV")
    await run(app, api, f"/api/systems/{dev}/start")

    restart = await run(app, api, f"/api/systems/{dev}/restart")

    assert restart["status"] == "SUCCEEDED"
    orders = [m for m in messages(restart) if " order including " in m]
    assert orders == [
        "Stop order including dependencies: DEV, HDV",
        "Start order including dependencies: HDV, DEV",
    ]
    requests = [m.split(" requested")[0] for m in messages(restart) if " requested " in m]
    assert requests == [
        "Stop of DEV/00",
        "Stop of DEV/01",
        "Stop of HDV/02",
        "Start of HDV/02",
        "Start of DEV/01",
        "Start of DEV/00",
    ]
    assert set((await statuses(api)).values()) == {"GREEN"}


async def test_stopping_a_dependency_leaves_dependent_systems_alone(app, api):
    await depend(api, "DEV", "HDV")
    await run(app, api, f"/api/systems/{await system_id(api, 'DEV')}/start")

    stop = await run(app, api, f"/api/systems/{await system_id(api, 'HDV')}/stop")

    assert stop["status"] == "SUCCEEDED"
    assert await statuses(api) == {"00": "GREEN", "01": "GREEN", "02": "GRAY"}


async def test_dependency_without_instances_fails(app, api):
    await depend(api, "DEV", "HDV")
    assert (await api.delete("/api/hosts/2")).status_code == 204  # HDV loses its instance

    activity = await run(app, api, f"/api/systems/{await system_id(api, 'DEV')}/start")

    assert activity["status"] == "FAILED"
    assert activity["error"] == (
        "System HDV has no instances in the inventory that are started or stopped with the system"
    )
    assert (await statuses(api))["00"] == "GRAY"


async def test_dependency_blocks_concurrent_activities(app, api):
    await depend(api, "DEV", "HDV")
    first = await api.post(f"/api/systems/{await system_id(api, 'DEV')}/start")
    assert first.status_code == 202

    # The HANA instance belongs to HDV, which the running DEV start covers as well.
    second = await api.post(f"/api/instances/{await instance_id(api, '02')}/stop")
    assert second.status_code == 409
    assert "START DEV" in second.json()["detail"]

    await app.state.runner.wait(first.json()["id"])
    activity = (await api.get(f"/api/activities/{first.json()['id']}")).json()
    assert activity["status"] == "SUCCEEDED"


async def test_timeout_fails_the_activity(app, api, landscape):
    landscape.start_duration = 10_000
    dialog = await instance_id(api, "00")

    activity = await run(app, api, f"/api/instances/{dialog}/start?timeout=10")

    assert activity["status"] == "FAILED"
    assert activity["error"] == "Timeout after 10 s: instance is YELLOW, expected GREEN"
    assert messages(activity)[-1] == activity["error"]
    assert (await statuses(api))["00"] == "YELLOW"


async def test_wrong_credentials_fail_the_activity(app, api):
    await api.put("/api/hosts/1/credentials", json={"username": "devadm", "password": "wrong"})
    dialog = await instance_id(api, "00")

    activity = await run(app, api, f"/api/instances/{dialog}/start")

    assert activity["status"] == "FAILED"
    assert activity["error"] == (
        "StartInstance at the host agent of sapapp1 was rejected (Invalid Credentials): "
        "user or password are wrong. The request used the credentials of host sapapp1 "
        "(devadm). Check the credentials of host sapapp1; the host agent usually expects "
        "sapadm."
    )
    assert (await statuses(api))["00"] == "GRAY"


async def test_system_operation_needs_only_host_credentials(app, api, landscape):
    """sapstartsrv rejects administration for sapadm; system operations do not need it."""
    landscape.strict_sapstartsrv_auth = True
    await api.put("/api/hosts/1/credentials", json={"username": "sapadm", "password": "mock"})
    dev = await system_id(api, "DEV")

    assert (await run(app, api, f"/api/systems/{dev}/start"))["status"] == "SUCCEEDED"
    assert (await run(app, api, f"/api/systems/{dev}/stop"))["status"] == "SUCCEEDED"
    assert (await statuses(api))["00"] == "GRAY"


async def test_rejected_status_read_is_explained(app, api, transport):
    """A sapstartsrv that refuses to report the process list names the credentials used."""

    async def refuse(request: httpx.Request) -> httpx.Response:
        body = (
            '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">'
            "<SOAP-ENV:Body><SOAP-ENV:Fault><faultcode>SOAP-ENV:Server</faultcode>"
            "<faultstring>Permission denied</faultstring></SOAP-ENV:Fault>"
            "</SOAP-ENV:Body></SOAP-ENV:Envelope>"
        )
        return httpx.Response(500, content=body.encode())

    transport._transports[50013].handle_async_request = refuse

    activity = await run(app, api, f"/api/instances/{await instance_id(api, '00')}/start")

    assert activity["status"] == "FAILED"
    assert activity["error"] == (
        "GetProcessList at the sapstartsrv of instance DEV/00 on sapapp1 was rejected "
        "(Permission denied): the user is not authorized. The request used no credentials "
        "of SID DEV, so those of host sapapp1 (devadm). Administrative calls at "
        "sapstartsrv need a user such as devadm: store credentials for SID DEV in the "
        "configuration of system DEV."
    )


async def test_unreachable_sapstartsrv_during_instance_start(app, api, transport):
    transport.remove_port(50013)
    dialog = await instance_id(api, "00")

    activity = await run(app, api, f"/api/instances/{dialog}/start?timeout=10")

    assert activity["status"] == "FAILED"
    assert "instance is UNKNOWN" in activity["error"]


async def test_unreadable_status_ends_in_timeout(app, api, transport):
    transport.remove_port(50113)  # sapstartsrv of the central services instance

    activity = await run(app, api, f"/api/systems/{await system_id(api, 'DEV')}/start?timeout=10")

    assert activity["status"] == "FAILED"
    assert activity["error"] == (
        "Timeout after 10 s: system DEV is DEV/00:GRAY DEV/01:UNKNOWN, expected all GREEN"
    )


async def test_unreachable_host_agent_fails_the_system_operation(app, api, transport):
    transport.remove_port(1128)  # host agent of sapapp1

    activity = await run(app, api, f"/api/systems/{await system_id(api, 'DEV')}/start")

    assert activity["status"] == "FAILED"
    assert activity["error"].startswith(
        "StartInstance for DEV/01: the host agent of sapapp1 could not be reached"
    )


async def test_only_one_activity_per_system(app, api):
    dialog = await instance_id(api, "00")
    dev = await system_id(api, "DEV")

    first = await api.post(f"/api/instances/{dialog}/start")
    assert first.status_code == 202
    second = await api.post(f"/api/systems/{dev}/stop")
    assert second.status_code == 409
    assert "START DEV/00" in second.json()["detail"]
    # Another system is not blocked.
    other = await api.post(f"/api/systems/{await system_id(api, 'HDV')}/start")
    assert other.status_code == 202

    await app.state.runner.wait(first.json()["id"])
    third = await api.post(f"/api/systems/{dev}/stop")
    assert third.status_code == 202
    await app.state.runner.wait(third.json()["id"])
    await app.state.runner.wait(other.json()["id"])


async def test_system_with_instances_of_two_sids(app, api, landscape, clock):
    """One system may hold the HANA instance of its database; priorities order the start."""
    hdv = await system_id(api, "HDV")
    assert (await api.delete(f"/api/systems/{hdv}")).status_code == 204
    dev = await system_id(api, "DEV")
    body = {"instance_ids": [await instance_id(api, "02")]}
    assert (await api.post(f"/api/systems/{dev}/instances", json=body)).status_code == 200

    start = await run(app, api, f"/api/systems/{dev}/start")

    assert start["status"] == "SUCCEEDED"
    requested = [m for m in messages(start) if m.endswith(("sapapp1", "sapdb1"))]
    assert requested == [
        "Start of HDV/02 requested via host agent of sapdb1",
        "Start of DEV/01 requested via host agent of sapapp1",
        "Start of DEV/00 requested via host agent of sapapp1",
    ]
    assert messages(start)[0] == "System DEV status: DEV/00:GRAY DEV/01:GRAY HDV/02:GRAY"
    assert await statuses(api) == {"00": "GREEN", "01": "GREEN", "02": "GREEN"}

    stop = await run(app, api, f"/api/systems/{dev}/stop")
    requested = [m for m in messages(stop) if m.endswith(("sapapp1", "sapdb1"))]
    assert [m.split()[2] for m in requested] == ["DEV/00", "DEV/01", "HDV/02"]
    assert landscape.host("sapdb1").instance(2).status(clock()) is Status.STOPPED


async def test_unassigned_instance_cannot_be_operated(app, api):
    dev = await system_id(api, "DEV")
    dialog = await instance_id(api, "00")
    assert (await api.delete(f"/api/systems/{dev}/instances/{dialog}")).status_code == 204

    response = await api.post(f"/api/instances/{dialog}/start")

    assert response.status_code == 409
    assert "not assigned" in response.json()["detail"]


async def test_system_cannot_change_while_active(app, api):
    dev = await system_id(api, "DEV")
    gate = hold_activities(app)  # keeps the activity running while the changes are tried
    first = await api.post(f"/api/systems/{dev}/start")
    assert first.status_code == 202

    removed = await api.delete(f"/api/systems/{dev}/instances/{await instance_id(api, '00')}")
    assert removed.status_code == 409
    assert (await api.delete(f"/api/systems/{dev}")).status_code == 409

    gate.set()
    await app.state.runner.wait(first.json()["id"])
    assert (await api.delete(f"/api/systems/{dev}")).status_code == 204


async def test_activity_list_is_newest_first(app, api):
    dialog = await instance_id(api, "00")
    await run(app, api, f"/api/instances/{dialog}/start")
    await run(app, api, f"/api/instances/{dialog}/stop")

    listed = (await api.get("/api/activities")).json()
    assert [(a["kind"], a["status"]) for a in listed] == [
        ("STOP", "SUCCEEDED"),
        ("START", "SUCCEEDED"),
    ]
    assert "entries" not in listed[0]
    assert len((await api.get("/api/activities?limit=1")).json()) == 1


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/instances/999/start", 404),
        ("/api/systems/999/stop", 404),
        ("/api/instances/1/explode", 422),
        ("/api/instances/1/start?timeout=1", 422),
        ("/api/activities/999", 404),
    ],
)
async def test_invalid_requests(api, path, expected):
    method = "GET" if "activities" in path else "POST"
    assert (await api.request(method, path)).status_code == expected


async def test_activities_interrupted_by_restart_are_marked_failed(make_app, settings, landscape):
    landscape.start_duration = 10_000

    first = make_app()
    async with first.router.lifespan_context(first):
        headers = {"Authorization": f"Bearer {await make_user(first)}"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=first), base_url="http://test", headers=headers
        ) as client:
            host = (await client.post("/api/hosts", json=APP_HOST)).json()
            await client.post(f"/api/hosts/{host['id']}/discover")
            body = {"name": "DEV", "instance_ids": [1, 2]}
            assert (await client.post("/api/systems", json=body)).status_code == 201
            activity = (await client.post("/api/instances/1/start")).json()
            await asyncio.sleep(0)
    # Leaving the lifespan shuts the server down while the activity is still running.

    second = make_app()
    async with second.router.lifespan_context(second):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=second), base_url="http://test", headers=headers
        ) as client:
            stored = (await client.get(f"/api/activities/{activity['id']}")).json()
            assert stored["status"] == "FAILED"
            assert "Interrupted" in stored["error"]
            # The system is free for new operations again.
            assert (await client.post("/api/instances/1/stop")).status_code == 202


async def test_database_status_follows_operations(app, api):
    async def database_statuses() -> set[str]:
        host = (await api.get("/api/hosts/2")).json()
        return {database["last_status"] for database in host["databases"]}

    assert await database_statuses() == {"STOPPED"}

    await run(app, api, f"/api/systems/{await system_id(api, 'HDV')}/start")
    assert await database_statuses() == {"RUNNING"}

    hana = await instance_id(api, "02")
    await run(app, api, f"/api/instances/{hana}/stop")
    assert await database_statuses() == {"STOPPED"}


async def test_database_refresh_failure_does_not_fail_the_activity(app, api, transport):
    hana = await instance_id(api, "02")
    original = transport._transports[11128].handle_async_request
    calls = {"count": 0}

    async def flaky(request):
        # The start request itself succeeds; the later database query finds the agent down.
        calls["count"] += 1
        if calls["count"] > 1:
            raise httpx.ConnectError("host agent went away")
        return await original(request)

    transport._transports[11128].handle_async_request = flaky
    activity = await run(app, api, f"/api/instances/{hana}/start")
    assert activity["status"] == "SUCCEEDED"


# --- roles: parallel start, diagnostics agents, duplicate instance numbers ---------------

APP2_HOST = APP_HOST | {"name": "sapapp2", "hostagent_port": 6128, "sapcontrol_port_offset": 5000}


@pytest.fixture
async def extended_api(settings, extended_landscape, clock):
    """One system with all instances of the extended landscape: HDV/02, DEV/01, DEV/00 on
    sapapp1 and sapapp2, and the diagnostics agent DAA/98."""

    async def fake_sleep(seconds: float) -> None:
        clock.advance(seconds)
        await asyncio.sleep(0)

    application = create_app(
        settings,
        transport=MockLandscapeTransport(extended_landscape),
        poll_interval=1.0,
        sleep=fake_sleep,
        clock=clock,
    )
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://test",
            headers={"Authorization": f"Bearer {await make_user(application)}"},
        ) as client:
            for body in (APP_HOST, DB_HOST, APP2_HOST):
                host = (await client.post("/api/hosts", json=body)).json()
                response = await client.post(f"/api/hosts/{host['id']}/discover")
                assert response.status_code == 200, response.text
            ids = [i["id"] for i in (await client.get("/api/instances")).json()]
            body = {"name": "DEV", "instance_ids": ids}
            assert (await client.post("/api/systems", json=body)).status_code == 201
            yield application, client


async def test_labels_and_roles(extended_api):
    _, api = extended_api
    instances = {i["label"]: i["role"] for i in (await api.get("/api/instances")).json()}
    assert instances == {
        "DEV/01": "central",
        "DEV/00 (sapapp1)": "application",
        "DAA/98": "agent",
        "HDV/02": "database",
        "DEV/00 (sapapp2)": "application",
    }


async def test_system_start_runs_database_and_central_services_in_parallel(
    extended_api, extended_landscape, clock
):
    app, api = extended_api
    dev = await system_id(api, "DEV")

    start = await run(app, api, f"/api/systems/{dev}/start")

    assert start["status"] == "SUCCEEDED", start["error"]
    log = messages(start)
    requested = [
        m.split(" requested")[0].removeprefix("Start of ") for m in log if " requested" in m
    ]
    assert requested == ["HDV/02", "DEV/01", "DEV/00 (sapapp1)", "DEV/00 (sapapp2)"]
    # Both were requested before either was running.
    first_green = next(i for i, m in enumerate(log) if "GREEN" in m)
    assert log.index("Start of DEV/01 requested via host agent of sapapp1") < first_green
    # Application servers only after database and central services run.
    app_request = log.index("Start of DEV/00 (sapapp1) requested via host agent of sapapp1")
    assert any("DEV/01:GREEN" in m and "HDV/02:GREEN" in m for m in log[:app_request])
    # The diagnostics agent is not part of the system operation.
    assert not any("DAA" in m for m in log)


async def test_system_stop_leaves_diagnostics_agent_running(
    extended_api, extended_landscape, clock
):
    app, api = extended_api
    dev = await system_id(api, "DEV")
    await run(app, api, f"/api/systems/{dev}/start")

    stop = await run(app, api, f"/api/systems/{dev}/stop")

    assert stop["status"] == "SUCCEEDED", stop["error"]
    requested = [m.split(" requested")[0] for m in messages(stop) if " requested" in m]
    assert requested == [
        "Stop of DEV/00 (sapapp1)",
        "Stop of DEV/00 (sapapp2)",
        "Stop of DEV/01",
        "Stop of HDV/02",
    ]
    agent = extended_landscape.host("sapapp1").instance(98)
    assert agent.status(clock()) is Status.RUNNING

    # The agent can still be operated on its own.
    daa = next(i["id"] for i in (await api.get("/api/instances")).json() if i["sid"] == "DAA")
    single = await run(app, api, f"/api/instances/{daa}/stop")
    assert single["status"] == "SUCCEEDED"
    assert agent.status(clock()) is Status.STOPPED


async def test_host_agent_version_is_stored(extended_api):
    _, api = extended_api
    hosts = (await api.get("/api/hosts")).json()
    assert {h["hostagent_version"] for h in hosts} == {"7.22 PL72"}


async def test_system_with_virtual_hostnames(settings, clock):
    """Instances under virtual hostnames are started and stopped with their hostname."""
    config = stopped_config()
    config["hosts"][0]["instances"][0]["hostname"] = "sapdevcs"  # DEV/01
    config["hosts"][0]["instances"][1]["hostname"] = "sapdevci"  # DEV/00
    virtual = MockLandscape.from_dict(config, clock=clock)

    async def fake_sleep(seconds: float) -> None:
        clock.advance(seconds)
        await asyncio.sleep(0)

    application = create_app(
        settings,
        transport=MockLandscapeTransport(virtual),
        poll_interval=1.0,
        sleep=fake_sleep,
        clock=clock,
    )
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://test",
            headers={"Authorization": f"Bearer {await make_user(application)}"},
        ) as client:
            host = (await client.post("/api/hosts", json=APP_HOST)).json()
            await client.post(f"/api/hosts/{host['id']}/discover")
            body = {"name": "DEV", "instance_ids": [1, 2]}
            system = (await client.post("/api/systems", json=body)).json()

            start = await run(application, client, f"/api/systems/{system['id']}/start")
            assert start["status"] == "SUCCEEDED", start["error"]
            stop = await run(application, client, f"/api/systems/{system['id']}/stop")
            assert stop["status"] == "SUCCEEDED", stop["error"]
    assert virtual.host("sapapp1").instance(0).status(clock()) is Status.STOPPED


async def test_host_connection_cannot_change_during_activity(app, api):
    first = await api.post(f"/api/systems/{await system_id(api, 'DEV')}/start")
    assert first.status_code == 202

    busy = await api.patch("/api/hosts/1", json={"address": "localhost"})
    assert busy.status_code == 409 and "still running" in busy.json()["detail"]
    other = await api.patch("/api/hosts/2", json={"address": "127.0.0.1"})
    assert other.status_code == 200  # the HANA host is not part of the DEV start

    await app.state.runner.wait(first.json()["id"])
    assert (await api.patch("/api/hosts/1", json={"address": "127.0.0.1"})).status_code == 200

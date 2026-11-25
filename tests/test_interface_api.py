"""API parts for the browser interface: session cookie, landscape snapshot, processes,
event stream, texts and security headers."""

from __future__ import annotations

import asyncio

import pytest

import test_mass
from conftest import make_user
from oslo.events import change_events, fingerprint
from test_mass import client, sign_in

pytestmark = pytest.mark.anyio

app, api, transport = test_mass.app, test_mass.api, test_mass.transport


async def test_api_accepts_the_session_cookie(app, api):
    async with sign_in(app) as web:
        assert (await web.get("/api/systems")).status_code == 200
        # Changes need the header that other sites cannot send.
        refused = await web.post("/api/systems/1/refresh")
        assert refused.status_code == 403 and "X-OSLO-Request" in refused.text
        allowed = await web.post("/api/systems/1/refresh", headers={"X-OSLO-Request": "1"})
        assert allowed.status_code == 200
    async with client(app) as anonymous:
        assert (await anonymous.get("/api/systems")).status_code == 401


async def test_cookie_keeps_the_roles(app, api):
    await make_user(app, "view", "viewer")
    async with sign_in(app, "view") as web:
        headers = {"X-OSLO-Request": "1"}
        assert (await web.post("/api/systems/1/start", headers=headers)).status_code == 403
        assert (await web.get("/api/landscape")).status_code == 200


async def test_landscape_snapshot(app, api):
    data = (await api.get("/api/landscape")).json()
    assert [s["name"] for s in data["systems"]] == ["A", "B", "C"]
    system_a = data["systems"][0]
    assert system_a["depends_on"] == ["C"] and system_a["activity"] is None
    instance = system_a["instances"][0]
    assert instance["label"] == "DEV/01" and instance["host"]["name"] == "sapapp1"
    assert instance["role"] == "central" and instance["type"] == "scs"
    assert {h["name"] for h in data["hosts"]} == {"sapapp1", "sapdb1"}
    keys = {op["key"]: op for op in data["operations"]}
    assert keys["start"]["labels"]["SYSTEM"] == "op.start_system"
    assert keys["stop"]["danger"] and keys["discover"]["targets"] == ["HOST"]
    assert data["user"] == {"name": "admin", "role": "admin"}

    async with client(app, await make_user(app, "op", "operator")) as operator:
        ops = {op["key"] for op in (await operator.get("/api/landscape")).json()["operations"]}
    assert "start" in ops and "discover" not in ops  # discovery needs a configurator


async def test_processes_are_read_live(app, api, transport):
    ids = {i["label"]: i["id"] for i in (await api.get("/api/instances")).json()}
    data = (await api.get(f"/api/instances/{ids['DEV/00']}/processes")).json()
    assert data["error"] is None and data["status"] in ("GREEN", "GRAY")
    assert data["processes"] and {"name", "status", "text", "pid"} <= set(data["processes"][0])
    assert (await api.get("/api/instances/99/processes")).status_code == 404

    transport.remove_port(50013)  # sapstartsrv of DEV/00
    down = (await api.get(f"/api/instances/{ids['DEV/00']}/processes")).json()
    assert down["status"] == "UNKNOWN" and down["error"] and down["processes"] == []


async def test_event_stream(app, api):
    factory = app.state.context.session_factory
    before = await fingerprint(factory())
    seen: list[str] = []
    changed = False

    async def sleep(_: float) -> None:
        nonlocal changed
        if not changed:
            changed = True
            await api.post("/api/systems/1/start")
        await asyncio.sleep(0)

    async def connected() -> bool:
        return False

    async for event in change_events(factory, sleep, interval=1, disconnected=connected, limit=2):
        seen.append(event)
    assert seen[0].startswith("event: hello") and before in seen[0]
    assert seen[1].startswith("event: change")

    app.state.events_limit = 1
    response = await api.get("/api/events")
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.startswith("event: hello")


async def test_texts_and_headers(app, api):
    response = await api.get("/api/i18n", headers={"Accept-Language": "de"})
    data = response.json()
    assert data["language"] == "de" and data["texts"]["nav.landscape"] == "Landschaft"
    assert "script-src 'self'" in response.headers["content-security-policy"]
    page = await client(app).get("/login")
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert "onsubmit=" not in page.text and "onclick=" not in page.text


async def test_activities_of_a_system_instance_and_host(app, api):
    """The detail panel shows the last activities of what is selected."""
    ids = {i["label"]: i["id"] for i in (await api.get("/api/instances")).json()}
    system_a = (await api.post("/api/systems/1/start")).json()["id"]  # A depends on C
    await app.state.runner.wait(system_a)
    instance_b = (await api.post(f"/api/instances/{ids['DEV/00']}/stop")).json()["id"]
    await app.state.runner.wait(instance_b)
    discovery = (
        await api.post(
            "/api/mass-operations",
            json={"operation": "discover", "target_type": "HOST", "target_ids": [1]},
        )
    ).json()["id"]
    await app.state.runner.wait(discovery)

    def ids_of(response) -> list[int]:
        assert response.status_code == 200, response.text
        return [a["id"] for a in response.json()]

    assert ids_of(await api.get("/api/activities?system_id=1")) == [system_a]
    # System C was started as dependency of A.
    assert ids_of(await api.get("/api/activities?system_id=3")) == [system_a]
    assert ids_of(await api.get("/api/activities?system_id=2")) == [instance_b]
    assert ids_of(await api.get(f"/api/activities?instance_id={ids['DEV/01']}")) == [system_a]
    assert ids_of(await api.get(f"/api/activities?instance_id={ids['DEV/00']}")) == [instance_b]
    host_ops = ids_of(await api.get("/api/activities?host_id=1"))
    assert host_ops == [discovery + 1]  # the child of the mass operation
    assert ids_of(await api.get("/api/activities?system_id=1&limit=1")) == [system_a]
    assert (await api.get("/api/activities?instance_id=99")).status_code == 404


async def test_log_entries_carry_the_timeline(app, api):
    activity_id = (await api.post("/api/systems/1/restart")).json()["id"]
    await app.state.runner.wait(activity_id)
    entries = (await api.get(f"/api/activities/{activity_id}")).json()["entries"]
    events = [(e["event"], e["subject"]) for e in entries if e["event"]]
    # Everything was stopped, so the restart only had to start (dependency C first).
    assert events.index(("request_start", "HDV/02")) < events.index(("request_start", "DEV/01"))
    statuses = [e["data"] for e in entries if e["event"] == "status"]
    assert statuses and all(set(d) <= {"DEV/01", "HDV/02"} for d in statuses)
    assert any(d.get("DEV/01") == "GREEN" for d in statuses)
    plain = [e for e in entries if e["event"] is None]
    assert plain and all(e["data"] is None for e in plain)


async def test_parts_for_the_form_pages(app, api):
    # Name proposal for a new system: the SID of the application instance, not of HANA.
    await api.delete("/api/systems/2")
    await api.delete("/api/systems/3")
    suggestion = await api.get("/api/systems/suggestion?instance_ids=2&instance_ids=3")
    assert suggestion.json() == {"name": "DEV"}
    assert (await api.get("/api/systems/suggestion")).json() == {"name": ""}
    # The type of an instance comes with it.
    instances = {i["label"]: i for i in (await api.get("/api/instances")).json()}
    assert instances["HDV/02"]["type_key"] == "itype.hana"
    assert instances["DEV/00"]["type_key"] == "itype.abap"
    # Platform information for admins.
    platform = (await api.get("/api/platform")).json()
    assert platform["database"] == "sqlite+aiosqlite" and platform["session_hours"] == 8
    await make_user(app, "op", "operator")
    async with sign_in(app, "op") as operator:
        assert (await operator.get("/api/platform")).status_code == 403


async def test_steps_of_a_single_operation(app, api):
    started = (await api.post("/api/systems/3/start")).json()
    await app.state.runner.wait(started["id"])
    steps = (await api.get("/api/steps")).json()
    # A single operation is one step, and its own top-level activity.
    step = next(s for s in steps if s["id"] == started["id"])
    assert step["activity_id"] == started["id"] and step["kind"] == "START"
    assert step["target_label"] == "C" and step["status"] == "SUCCEEDED"
    assert step["started_at"] and step["finished_at"]
    assert [s["id"] for s in steps] == sorted((s["id"] for s in steps), reverse=True)
    # The old list of all log entries is gone.
    assert (await api.get("/api/activity-log")).status_code == 404

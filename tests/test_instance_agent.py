"""Register, unregister and re-register the instance agent (sapstartsrv) of an instance."""

from __future__ import annotations

import pytest

import test_mass

pytestmark = pytest.mark.anyio

# Systems A (DEV/01, instance 1), B (DEV/00, instance 2), C (HDV/02, instance 3); stopped.
app, api, transport = test_mass.app, test_mass.api, test_mass.transport


async def run(app, api, path: str, body: dict | None = None) -> dict:
    response = await api.post(path, json=body) if body else await api.post(path)
    assert response.status_code == 202, response.text
    activity_id = response.json()["id"]
    await app.state.runner.wait(activity_id)
    return (await api.get(f"/api/activities/{activity_id}")).json()


def messages(activity: dict) -> list[str]:
    return [e["message"] for e in activity["entries"]]


async def test_unregister_and_register(app, api, landscape):
    agent = landscape.host("sapapp1").instance(1)
    unregistered = await run(app, api, "/api/instances/1/unregister")
    assert unregistered["status"] == "SUCCEEDED", messages(unregistered)
    assert not agent.service_running
    lines = messages(unregistered)
    # The host agent's lines come into the log.
    assert "saphostcontrol: 'sapstartsrv -unreg' successfully executed" in lines
    assert "UnregisterInstanceService succeeded" in lines
    instance = next(i for i in (await api.get("/api/instances")).json() if i["id"] == 1)
    assert instance["last_status"] == "UNKNOWN"
    assert (await api.get("/api/instances/1/processes")).json()["error"]

    registered = await run(app, api, "/api/instances/1/register")
    assert registered["status"] == "SUCCEEDED", messages(registered)
    assert agent.service_running
    assert "saphostcontrol: Executing 'sapstartsrv -reg'" in messages(registered)
    assert "sapstartsrv answers; instance status: GRAY" in messages(registered)
    done = [e for e in registered["entries"] if e["event"] in ("op_started", "op_done")]
    assert [e["event"] for e in done] == ["op_started", "op_done"]
    assert {e["subject"] for e in done} == {"DEV/01"}


async def test_reregister_is_refused_while_processes_run(app, api):
    started = await run(app, api, "/api/instances/2/start")
    assert started["status"] == "SUCCEEDED"
    refused = await run(app, api, "/api/instances/2/reregister")
    assert refused["status"] == "FAILED"
    assert "Processes of the instance are still running" in refused["error"]
    assert not any("RegisterInstanceService" in m for m in messages(refused))

    await run(app, api, "/api/instances/2/stop")
    again = await run(app, api, "/api/instances/2/reregister")
    assert again["status"] == "SUCCEEDED", messages(again)
    calls = [m for m in messages(again) if m.endswith("InstanceService succeeded")]
    assert calls == ["UnregisterInstanceService succeeded", "RegisterInstanceService succeeded"]


async def test_unregister_goes_ahead_without_an_answer(app, api, landscape):
    landscape.host("sapapp1").instance(1).service_running = False
    result = await run(app, api, "/api/instances/1/unregister")
    assert result["status"] == "SUCCEEDED"
    assert "sapstartsrv does not answer; going ahead" in messages(result)


async def test_only_for_instances_and_in_the_catalog(app, api):
    assert (await api.post("/api/systems/1/register")).status_code == 422
    operations = {o["key"]: o for o in (await api.get("/api/landscape")).json()["operations"]}
    assert operations["register"]["targets"] == ["INSTANCE"]
    assert operations["unregister"]["danger"] and operations["reregister"]["danger"]
    assert operations["reregister"]["labels"] == {"INSTANCE": "op.reregister"}
    # As a mass operation on two instances.
    body = {"operation": "reregister", "target_type": "INSTANCE", "target_ids": [1, 3]}
    mass = await run(app, api, "/api/mass-operations", body)
    assert mass["status"] == "SUCCEEDED" and len(mass["children"]) == 2

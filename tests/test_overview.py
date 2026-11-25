"""The overview: status matrix of pools and stages, and "needs attention" by rules."""

from __future__ import annotations

import pytest

import test_mass
from conftest import make_user
from test_custom import OSLO_TEST
from test_mass import client

pytestmark = pytest.mark.anyio

# Systems A (DEV/01), B (DEV/00), C (HDV/02); A and B depend on C. All stopped.
app, api, transport = test_mass.app, test_mass.api, test_mass.transport


async def overview(api) -> dict:
    response = await api.get("/api/overview")
    assert response.status_code == 200, response.text
    return response.json()


def rules_of(data: dict) -> list[str]:
    return [item["rule"] for item in data["attention"]]


async def test_matrix_of_pools_and_stages(api):
    pool = (await api.post("/api/pools", json={"name": "ERP"})).json()
    await api.put("/api/systems/1/pool", json={"pool_id": pool["id"]})
    stage = await api.patch("/api/systems/1", json={"name": "A", "stage": "sandbox"})
    assert stage.status_code == 200 and stage.json()["stage"] == "sandbox"
    await api.patch("/api/systems/2", json={"name": "B", "stage": "production"})
    # A rename without "stage" keeps it.
    await api.patch("/api/systems/2", json={"name": "B2"})
    bad = await api.patch("/api/systems/2", json={"name": "B2", "stage": "moon"})
    assert bad.status_code == 422

    data = await overview(api)
    # Development, quality and production always; sandbox because A has it; "" for C.
    assert data["columns"] == ["sandbox", "development", "quality", "production", ""]
    systems = {s["name"]: s for s in data["systems"]}
    assert systems["A"]["pool_id"] == pool["id"] and systems["A"]["stage"] == "sandbox"
    assert systems["B2"]["stage"] == "production" and systems["C"]["stage"] is None
    assert [i["label"] for i in systems["A"]["instances"]] == ["DEV/01"]
    assert data["kpis"]["systems"] == {"total": 3, "by": {"GRAY": 3}}
    assert data["pools"] == [{"id": pool["id"], "name": "ERP", "description": None}]
    landscape = (await api.get("/api/landscape")).json()
    assert {s["name"]: s["stage"] for s in landscape["systems"]}["A"] == "sandbox"


async def test_attention_rules(app, api):
    await api.patch("/api/systems/2", json={"name": "B", "stage": "production"})
    data = await overview(api)
    # Stopped production system B; the others have no stage that counts.
    assert rules_of(data) == ["stopped_systems"]
    assert data["attention"][0]["values"]["system"] == "B"
    assert data["attention"][0]["link"] == "/landscape?system=2"

    # A failed custom operation shows up, until a later run of it on the same target succeeds.
    await api.post("/api/custom-operations", json=OSLO_TEST)
    failed = await api.post("/api/instances/2/operations/oslo_test", json={"parameters": {"RC": 3}})
    await app.state.runner.wait(failed.json()["id"])
    data = await overview(api)
    assert rules_of(data)[0] == "failed_activities"
    assert data["attention"][0]["severity"] == "error"
    assert data["attention"][0]["values"]["id"] == failed.json()["id"]

    rules = (await api.get("/api/attention-rules")).json()
    assert rules["rules"]["failed_activities"]["hours"] == 24
    hidden = {"failed_activities": {"hide_operations": ["oslo_test"]}}
    assert (await api.put("/api/attention-rules", json={"rules": hidden})).status_code == 200
    assert "failed_activities" not in rules_of(await overview(api))
    await api.put("/api/attention-rules", json={"rules": {}})
    assert "failed_activities" in rules_of(await overview(api))

    succeeded = await api.post(
        "/api/instances/2/operations/oslo_test", json={"parameters": {"RC": 0}}
    )
    await app.state.runner.wait(succeeded.json()["id"])
    assert "failed_activities" not in rules_of(await overview(api))

    for wrong in (
        {"nothing": {}},
        {"failed_activities": {"hours": "x"}},
        {"failed_activities": {"color": 1}},
        {"system_status": {"statuses": ["PURPLE"]}},
    ):
        assert (await api.put("/api/attention-rules", json={"rules": wrong})).status_code == 422
    async with client(app, await make_user(app, "op", "operator")) as operator:
        refused = await operator.put("/api/attention-rules", json={"rules": {}})
        assert refused.status_code == 403
        assert (await operator.get("/api/attention-rules")).status_code == 200


async def test_failures_of_frequent_schedules_are_hidden(app, api):
    await api.post("/api/custom-operations", json=OSLO_TEST)
    body = {
        "operation": "oslo_test",
        "target_type": "INSTANCE",
        "target_ids": [2],
        "parameters": {"RC": 3},
        "recurrence": "interval",
        "interval_minutes": 60,
    }
    assert (await api.post("/api/schedules", json=body)).status_code == 201
    [activity] = await app.state.scheduler.tick()
    await app.state.runner.wait(activity)
    assert "failed_activities" not in rules_of(await overview(api))
    every_30 = {"failed_activities": {"hide_scheduled_every_minutes": 30}}
    await api.put("/api/attention-rules", json={"rules": every_30})
    assert "failed_activities" in rules_of(await overview(api))


async def test_exceptions_per_user(app, api):
    await api.patch("/api/systems/2", json={"name": "B", "stage": "production"})
    async with client(app, await make_user(app, "view", "viewer")) as viewer:
        assert rules_of(await overview(viewer)) == ["stopped_systems"]
        saved = await viewer.put("/api/me/attention", json={"hidden_systems": [2]})
        assert saved.status_code == 200 and saved.json()["hidden_systems"] == [2]
        assert rules_of(await overview(viewer)) == []
        await viewer.put("/api/me/attention", json={"disabled_rules": ["stopped_systems"]})
        data = await overview(viewer)
        assert data["attention"] == [] and data["exceptions"]["disabled_rules"] == [
            "stopped_systems"
        ]
        wrong = await viewer.put("/api/me/attention", json={"disabled_rules": ["nope"]})
        assert wrong.status_code == 422
    # Others still see it.
    assert rules_of(await overview(api)) == ["stopped_systems"]


async def test_unreachable_host_and_stale_discovery(app, api, landscape):
    host = (await api.post("/api/hosts", json={"name": "offline", "hostagent_port": 4711})).json()
    await api.post(f"/api/hosts/{host['id']}/discover")
    data = await overview(api)
    unreachable = [i for i in data["attention"] if i["rule"] == "host_unreachable"]
    assert [i["values"]["host"] for i in unreachable] == ["offline"]
    stale = {"stale_discovery": {"enabled": True, "days": 0}}
    await api.put("/api/attention-rules", json={"rules": stale})
    assert "stale_discovery" in rules_of(await overview(api))


async def test_empty_overview(api):
    await api.delete("/api/systems/1")
    await api.delete("/api/systems/2")
    await api.delete("/api/systems/3")
    data = await overview(api)
    assert data["systems"] == [] and data["kpis"]["systems"]["total"] == 0
    assert data["columns"] == ["development", "quality", "production"]

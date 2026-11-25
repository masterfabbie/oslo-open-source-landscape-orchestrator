"""Hosts in pools, the stage of a host and the context parameters OSLO_STAGE and OSLO_POOL."""

from __future__ import annotations

import pytest

import test_mass
from conftest import make_user
from oslo.customspec import instance_arguments
from oslo.models import Host, Instance, Pool, Sid, System
from test_custom import OSLO_TEST, finished
from test_mass import client

pytestmark = pytest.mark.anyio

app, api, transport = test_mass.app, test_mass.api, test_mass.transport


async def pool(api, name: str) -> int:
    response = await api.post("/api/pools", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_hosts_in_pools_and_stages(app, api):
    erp = await pool(api, "ERP")
    response = await api.put("/api/hosts/1/pool", json={"pool_id": erp})
    assert response.status_code == 200 and response.json()["pool_id"] == erp
    assert (await api.put("/api/hosts/1/pool", json={"pool_id": 99})).status_code == 422
    assert (await api.put("/api/hosts/99/pool", json={"pool_id": erp})).status_code == 404
    listed = (await api.get(f"/api/pools/{erp}")).json()
    assert listed["host_ids"] == [1] and listed["system_ids"] == []

    response = await api.put("/api/hosts/1/stage", json={"stage": "quality"})
    assert response.status_code == 200 and response.json()["stage"] == "quality"
    assert (await api.put("/api/hosts/1/stage", json={"stage": "qas"})).status_code == 422
    host = (await api.get("/api/hosts/1")).json()
    assert host["stage"] == "quality" and host["pool_id"] == erp
    row = next(h for h in (await api.get("/api/landscape")).json()["hosts"] if h["id"] == 1)
    assert row["stage"] == "quality" and row["pool"] == {"id": erp, "name": "ERP"}

    # Another pool, then none; deleting a pool takes its hosts out.
    other = await pool(api, "CRM")
    await api.put("/api/hosts/1/pool", json={"pool_id": other})
    assert (await api.get(f"/api/pools/{erp}")).json()["host_ids"] == []
    assert (await api.delete(f"/api/pools/{other}")).status_code == 204
    assert (await api.get("/api/hosts/1")).json()["pool_id"] is None

    changes = (await api.get("/api/config-changes", params={"object_type": "host"})).json()
    fields = {f for c in changes for f in c["changes"]}
    assert {"pool", "stage"} <= fields
    async with client(app, await make_user(app, "op", "operator")) as operator:
        assert (await operator.put("/api/hosts/1/stage", json={"stage": None})).status_code == 403


def test_context_parameters():
    host = Host(name="sapapp1", stage="quality")
    host.pool = Pool(name="Hosts")
    instance = Instance(number="00", hostname="sapapp1", features="ABAP")
    instance.host, instance.sid = host, Sid(name="DEV")
    system = System(name="DEV", instances=[instance])
    system.pool = None
    arguments = instance_arguments(instance, system)
    assert arguments["OSLO_STAGE"] == "qas" and arguments["OSLO_POOL"] == "Hosts"
    system.stage, system.pool = "preprod", Pool(name="ERP")
    arguments = instance_arguments(instance, system)
    assert arguments["OSLO_STAGE"] == "pre" and arguments["OSLO_POOL"] == "ERP"
    host.stage, host.pool, system.stage, system.pool = None, None, None, None
    assert "OSLO_STAGE" not in instance_arguments(instance, system)
    assert "OSLO_POOL" not in instance_arguments(instance, system)


async def test_scripts_get_stage_and_pool(app, api, landscape):
    assert (await api.post("/api/custom-operations", json=OSLO_TEST)).status_code == 201
    host_operation = OSLO_TEST | {"key": "oslo_host", "target": "HOST"}
    assert (await api.post("/api/custom-operations", json=host_operation)).status_code == 201
    erp = await pool(api, "ERP")
    await api.put("/api/hosts/1/stage", json={"stage": "development"})
    await api.put("/api/hosts/1/pool", json={"pool_id": erp})

    async def arguments(path: str) -> list[str]:
        landscape.operation_runs.clear()
        response = await api.post(path, json={"parameters": {"RC": 0}})
        assert response.status_code == 202, response.text
        assert (await finished(app, api, response.json()["id"]))["status"] == "SUCCEEDED"
        return next(iter(landscape.operation_runs.values())).arguments

    # The system has neither stage nor pool: those of the host.
    assert (await arguments("/api/instances/2/operations/oslo_test"))[-2:] == ["dev", "ERP"]
    systems = (await api.get("/api/landscape")).json()["systems"]
    system_id = next(s["id"] for s in systems if any(i["id"] == 2 for i in s["instances"]))
    crm = await pool(api, "CRM")
    name = next(s["name"] for s in systems if s["id"] == system_id)
    await api.patch(f"/api/systems/{system_id}", json={"name": name, "stage": "production"})
    await api.put(f"/api/systems/{system_id}/pool", json={"pool_id": crm})
    assert (await arguments("/api/instances/2/operations/oslo_test"))[-2:] == ["prd", "CRM"]
    assert (await arguments("/api/hosts/1/operations/oslo_host"))[-2:] == ["dev", "ERP"]


async def test_unreachable_hosts_by_stage(app, api):
    host = (await api.post("/api/hosts", json={"name": "offline", "hostagent_port": 4711})).json()
    await api.put(f"/api/hosts/{host['id']}/stage", json={"stage": "development"})
    await api.post(f"/api/hosts/{host['id']}/discover")

    async def unreachable() -> list[str]:
        items = (await api.get("/api/overview")).json()["attention"]
        return [i["values"]["host"] for i in items if i["rule"] == "host_unreachable"]

    assert await unreachable() == ["offline"]
    only = {"host_unreachable": {"enabled": True, "stages": ["production"]}}
    assert (await api.put("/api/attention-rules", json={"rules": only})).status_code == 200
    assert await unreachable() == []
    bad = {"host_unreachable": {"enabled": True, "stages": ["bad"]}}
    assert (await api.put("/api/attention-rules", json={"rules": bad})).status_code == 422

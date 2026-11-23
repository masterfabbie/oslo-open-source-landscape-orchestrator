"""Export and import of the configuration (Administration → Import/Export)."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import pytest

import test_mass
from conftest import make_user
from oslo.api import create_app
from oslo.crypto import generate_secret_key
from oslo.settings import Settings
from test_custom import OSLO_TEST
from test_mass import client

pytestmark = pytest.mark.anyio

# Systems A (DEV/01), B (DEV/00), C (HDV/02); A and B depend on C. Hosts with credentials.
app, api, transport = test_mass.app, test_mass.api, test_mass.transport

ALL = [
    "hosts",
    "sids",
    "pools",
    "systems",
    "custom_operations",
    "templates",
    "schedules",
    "attention_rules",
    "certificates",
]
PASSWORD = "export-secret-1"


@asynccontextmanager
async def second_oslo(tmp_path, transport, clock):
    """Another, empty OSLO against the same simulated landscape."""
    settings = Settings(
        secret_key=generate_secret_key(), database_url=f"sqlite+aiosqlite:///{tmp_path / 'b.db'}"
    )

    async def fake_sleep(seconds: float) -> None:
        clock.advance(seconds)
        await asyncio.sleep(0)

    other = create_app(
        settings, transport=transport, poll_interval=1.0, sleep=fake_sleep, clock=clock
    )
    async with other.router.lifespan_context(other):
        async with client(other, await make_user(other)) as admin:
            yield other, admin


async def configure(api) -> None:
    """A pool, tags, a custom operation, a template with fixed targets and a schedule."""
    pool = (await api.post("/api/pools", json={"name": "ERP", "description": "Product"})).json()
    await api.put("/api/systems/1/pool", json={"pool_id": pool["id"]})
    await api.put("/api/systems/1/tags", json={"tags": ["dev", "sla=1"]})
    await api.patch("/api/systems/3", json={"name": "C", "stage": "production"})
    assert (await api.post("/api/custom-operations", json=OSLO_TEST)).status_code == 201
    template = {
        "key": "stop_and_test",
        "name": "Stop and test",
        "role": "operator",
        "steps": [
            {"operation": "stop", "target_type": "SYSTEM", "targets": [1]},
            {
                "operation": "oslo_test",
                "target_type": "INSTANCE",
                "targets": [2],
                "after": [1],
                "parameters": {"RC": "0"},
            },
        ],
    }
    created = await api.post("/api/templates", json=template)
    assert created.status_code == 201, created.text
    schedule = {
        "name": "Nightly stop",
        "operation": "stop_and_test",
        "target_type": "",
        "recurrence": "daily",
        "time_of_day": "22:00",
    }
    assert (await api.post("/api/schedules", json=schedule)).status_code == 201


async def export(api, parts=ALL, password: str | None = PASSWORD) -> dict:
    response = await api.post("/api/export", json={"parts": parts, "password": password})
    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    return response.json()


async def run_import(api, data, *, mode="add", password=PASSWORD, apply=True) -> dict:
    body = {"data": data, "mode": mode, "password": password, "apply": apply}
    response = await api.post("/api/import", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def actions(report: dict, part: str) -> dict[str, str]:
    return {i["name"]: i["action"] for i in report["items"] if i["part"] == part}


async def test_export_holds_names_and_encrypted_passwords(api):
    await configure(api)
    data = await export(api)
    assert data["format"] == "oslo-export" and data["version"] == 1
    hosts = {h["name"]: h for h in data["hosts"]}
    assert hosts["sapapp1"]["username"] == "devadm"
    text = json.dumps(data)
    assert '"mock"' not in text  # the password of the hosts, never in plain text
    system = next(s for s in data["systems"] if s["name"] == "A")
    assert system["pool"] == "ERP" and system["tags"] == ["dev", "sla=1"]
    assert system["depends_on"] == ["C"]
    assert system["instances"] == [{"host": "sapapp1", "sid": "DEV", "number": "01"}]
    steps = data["templates"][0]["steps"]
    assert steps[0]["targets"] == [{"system": "A"}]
    assert steps[1]["targets"] == [{"host": "sapapp1", "sid": "DEV", "number": "00"}]
    assert data["schedules"][0]["name"] == "Nightly stop"
    assert data["custom_operations"][0]["parameters"][2]["name"] == "RC"

    # Without a password no passwords at all; parts can be left out.
    plain = await export(api, ["hosts"], password=None)
    assert plain["credentials"] is None and "password" not in plain["hosts"][0]
    assert "systems" not in plain
    bad = await api.post("/api/export", json={"parts": ["users"]})
    assert bad.status_code == 422


async def test_import_into_another_oslo(api, tmp_path, transport, clock):
    await configure(api)
    data = await export(api)
    async with second_oslo(tmp_path, transport, clock) as (other, admin):
        # A preview keeps nothing.
        preview = await run_import(admin, data, apply=False)
        assert preview["applied"] is False and preview["counts"]["created"] > 0
        assert (await admin.get("/api/hosts")).json() == []

        first = await run_import(admin, data)
        assert actions(first, "hosts") == {"sapapp1": "created", "sapdb1": "created"}
        hosts = (await admin.get("/api/hosts")).json()
        assert all(h["has_credentials"] for h in hosts)
        assert actions(first, "pools") == {"ERP": "created"}
        # Instances come from a discovery, which the import does not run.
        assert set(actions(first, "systems").values()) == {"failed"}
        assert (
            "discovery"
            in first["items"][[i["part"] for i in first["items"]].index("systems")]["message"]
        )
        assert actions(first, "custom_operations") == {"oslo_test": "created"}
        assert actions(first, "templates") == {"stop_and_test": "failed"}

        for host in hosts:
            assert (await admin.post(f"/api/hosts/{host['id']}/discover")).status_code == 200
        second = await run_import(admin, data)
        assert actions(second, "hosts") == {"sapapp1": "skipped", "sapdb1": "skipped"}
        assert actions(second, "systems") == {"A": "created", "B": "created", "C": "created"}
        assert actions(second, "templates") == {"stop_and_test": "created"}
        assert actions(second, "schedules") == {"Nightly stop": "created"}
        systems = {s["name"]: s for s in (await admin.get("/api/systems")).json()}
        assert systems["C"]["stage"] == "production"
        assert systems["A"]["tags"] == ["dev", "sla=1"]
        assert systems["A"]["depends_on_ids"] == [systems["C"]["id"]]
        # Discovered with the imported credentials, the hosts are reachable.
        assert all(h["reachable"] for h in (await admin.get("/api/hosts")).json())

        # Importing once more changes nothing in mode "add".
        third = await run_import(admin, data)
        assert third["counts"]["created"] == 0 and third["counts"]["failed"] == 0


async def test_update_mode_and_passwords(api, tmp_path, transport, clock):
    data = await export(api, ["hosts", "pools"])
    async with second_oslo(tmp_path, transport, clock) as (other, admin):
        # Without the export password the hosts come without their passwords.
        report = await run_import(admin, data, password=None)
        assert any(i["action"] == "warning" for i in report["items"])
        assert not any(h["has_credentials"] for h in (await admin.get("/api/hosts")).json())
        wrong = await admin.post(
            "/api/import", json={"data": data, "password": "wrong-password", "apply": True}
        )
        assert wrong.status_code == 422 and "transfer_password" in wrong.text

        data["hosts"][0]["address"] = "127.0.0.2"
        report = await run_import(admin, data, mode="update")
        assert actions(report, "hosts")["sapapp1"] == "updated"
        hosts = {h["name"]: h for h in (await admin.get("/api/hosts")).json()}
        assert hosts["sapapp1"]["address"] == "127.0.0.2" and hosts["sapapp1"]["has_credentials"]

        # One broken item fails alone.
        data["hosts"].append({"name": ""})
        report = await run_import(admin, data, mode="update")
        assert actions(report, "hosts")[""] == "failed"
        assert actions(report, "hosts")["sapdb1"] == "updated"


async def test_bad_files_and_rights(app, api):
    for data, code in (
        ({"format": "something"}, "transfer_format"),
        ({"format": "oslo-export", "version": 99}, "transfer_version"),
    ):
        response = await api.post("/api/import", json={"data": data})
        assert response.status_code == 422 and code in response.text
    async with client(app, await make_user(app, "conf", "configurator")) as conf:
        assert (await conf.post("/api/export", json={"parts": ["hosts"]})).status_code == 403
        assert (await conf.post("/api/import", json={"data": {}})).status_code == 403

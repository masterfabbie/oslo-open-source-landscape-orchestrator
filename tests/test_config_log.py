"""The configuration log (Activities → Configuration): changes in a user's name."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import test_mass
from conftest import make_user
from oslo.models import ConfigChange
from test_mass import client

pytestmark = pytest.mark.anyio

# Systems A (DEV/01), B (DEV/00), C (HDV/02); A and B depend on C.
app, api, transport = test_mass.app, test_mass.api, test_mass.transport


async def changes(api, **query) -> list[dict]:
    response = await api.get("/api/config-changes", params=query)
    assert response.status_code == 200, response.text
    return response.json()


async def test_changes_of_a_host(api):
    # A discovery writes status and versions: not configuration.
    assert (await api.post("/api/hosts/1/discover")).status_code == 200
    before = len(await changes(api))
    changed = await api.patch("/api/hosts/1", json={"address": "10.0.0.9", "https": True})
    assert changed.status_code == 200
    # Saving the same values again is no change.
    await api.patch("/api/hosts/1", json={"address": "10.0.0.9"})
    await api.put("/api/hosts/1/credentials", json={"username": "sapadm", "password": "new"})
    await api.put("/api/hosts/1/tags", json={"tags": ["dev", "sla=1"]})
    await api.put("/api/hosts/1/tags", json={"tags": ["sla=2"]})

    entries = await changes(api, object_type="host", object_id=1)
    assert len(await changes(api)) == before + 4
    tags, again, credentials, connection = entries[:4]
    assert connection["action"] == "updated" and connection["username"] == "admin"
    assert connection["object_name"] == "sapapp1"
    assert connection["changes"]["address"][1] == "10.0.0.9"
    assert connection["changes"]["https"] == [False, True]
    # Secrets are never stored, only that they changed.
    assert credentials["changes"]["password_encrypted"] == [None, "(changed)"]
    assert "new" not in str(credentials) and "username" in credentials["changes"]
    assert again["changes"]["tags"] == [None, "dev, sla=1"]
    assert tags["changes"]["tags"] == ["dev, sla=1", "sla=2"]


async def test_hosts_created_together_and_deleted(api):
    created = await api.post("/api/hosts/batch", json={"names": ["sapapp7", "sapapp8"]})
    assert created.status_code == 201
    ids = {h["name"]: h["id"] for h in created.json()}
    new = [e for e in await changes(api, object_type="host") if e["action"] == "created"]
    # One entry each, with its own id, although both were saved in one go.
    assert {(e["object_name"], e["object_id"]) for e in new[:2]} == set(ids.items())
    assert new[0]["changes"]["address"][1] in ids
    assert (await api.delete(f"/api/hosts/{ids['sapapp7']}")).status_code == 204
    deleted = (await changes(api, object_type="host", object_id=ids["sapapp7"]))[0]
    assert deleted["action"] == "deleted"


async def test_changes_of_systems_pools_and_dependencies(api):
    pool = (await api.post("/api/pools", json={"name": "ERP"})).json()
    await api.put("/api/systems/1/pool", json={"pool_id": pool["id"]})
    await api.put("/api/systems/1/dependencies", json={"depends_on": []})
    renamed = await api.patch("/api/systems/1", json={"name": "A", "stage": "production"})
    assert renamed.status_code == 200, renamed.text
    await api.delete("/api/systems/1/instances/1")

    system = await changes(api, object_type="system", object_id=1)
    assert system[0]["changes"]["instances"][0].startswith("DEV/01")
    assert system[1]["changes"]["stage"] == [None, "production"]
    assert system[2]["changes"]["depends_on"] == ["C", None]
    assert system[3]["changes"]["pool"] == [None, "ERP"]
    pools = await changes(api, object_type="pool", object_id=pool["id"])
    assert pools[0]["changes"]["systems"] == [None, "A"]
    assert pools[1]["action"] == "created"


async def test_who_sees_what(app, api):
    await api.post("/api/users", json={"username": "op", "password": "x" * 12, "role": "operator"})
    await api.patch("/api/hosts/2", json={"address": "sapdb1.example"})
    users = await changes(api, object_type="user")
    assert users and users[0]["object_name"] == "op"
    assert "password_hash" in users[0]["changes"]
    assert "$" not in str(users[0]["changes"])  # no password hash
    async with client(app, await make_user(app, "view", "viewer")) as viewer:
        seen = await changes(viewer)
        assert seen and all(e["object_type"] != "user" for e in seen)
        assert (await changes(viewer, username="admin", object_type="host"))[0]["object_id"] == 2
        assert (await viewer.get("/api/config-log-settings")).json() == {"retention_days": 365}
        refused = await viewer.put("/api/config-log-settings", json={"retention_days": 30})
        assert refused.status_code == 403
    # Changes not made in a user's name (here: directly in the database) are not recorded.
    count = len(await changes(api))
    await make_user(app, "direct", "viewer")
    assert len(await changes(api)) == count


async def test_old_entries_are_deleted(app, api):
    assert (
        await api.put("/api/config-log-settings", json={"retention_days": 30})
    ).status_code == 200
    assert (
        await api.put("/api/config-log-settings", json={"retention_days": 0})
    ).status_code == 422
    async with app.state.session_factory() as session:
        session.add(
            ConfigChange(
                changed_at=datetime.now(UTC) - timedelta(days=31),
                username="admin",
                object_type="host",
                object_id=1,
                object_name="sapapp1",
                action="updated",
                changes="{}",
            )
        )
        await session.commit()
    old = [e for e in await changes(api) if e["changed_at"] < "2026"]
    total = len(await changes(api))
    await app.state.scheduler.tick()
    assert len(await changes(api)) == total - 1 - len(old)
    # The retention itself is a change of the platform.
    platform = await changes(api, object_type="platform")
    assert platform[0]["changes"]["value"] in (["30", "30"], [None, "30"], ["365", "30"])


async def test_preview_keeps_nothing_and_an_import_is_summed_up(api):
    data = (await api.post("/api/export", json={"parts": ["pools"]})).json()
    data["pools"].append({"name": "CRM", "description": None})
    count = len(await changes(api))
    preview = await api.post("/api/import", json={"data": data, "apply": False})
    assert preview.status_code == 200
    assert len(await changes(api)) == count
    applied = await api.post("/api/import", json={"data": data, "apply": True})
    assert applied.status_code == 200
    entries = await changes(api)
    summary = next(e for e in entries if e["object_type"] == "import")
    assert summary["action"] == "imported" and summary["changes"]["created"] == [None, 1]
    assert any(e["object_type"] == "pool" and e["object_name"] == "CRM" for e in entries)

from __future__ import annotations

import sqlite3

import httpx
import pytest

from conftest import make_user
from oslo.api import create_app
from oslo.crypto import generate_secret_key
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
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'api.db'}",
    )


@pytest.fixture
async def api(settings, landscape):
    app = create_app(settings, transport=MockLandscapeTransport(landscape))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {await make_user(app)}"},
        ) as client:
            yield client


async def create_host(api: httpx.AsyncClient, body: dict) -> dict:
    response = await api.post("/api/hosts", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_health_needs_no_token(api):
    response = await api.get("/health", headers={"Authorization": ""})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize("header", ["", "Bearer wrong-token", "Basic abc"])
async def test_api_requires_token(api, header):
    response = await api.get("/api/hosts", headers={"Authorization": header})
    assert response.status_code == 401


async def test_create_and_list_hosts(api):
    host = await create_host(api, APP_HOST)
    assert host["name"] == "sapapp1"
    assert host["has_credentials"] is True
    assert host["reachable"] is None
    assert "password" not in host and "password_encrypted" not in host

    listed = (await api.get("/api/hosts")).json()
    assert [h["name"] for h in listed] == ["sapapp1"]


async def test_address_defaults_to_name(api):
    host = await create_host(api, {"name": "somehost"})
    assert host["address"] == "somehost"
    assert host["has_credentials"] is False


async def test_duplicate_host_is_rejected(api):
    await create_host(api, APP_HOST)
    response = await api.post("/api/hosts", json=APP_HOST)
    assert response.status_code == 409


async def test_username_without_password_is_rejected(api):
    response = await api.post("/api/hosts", json={"name": "h", "username": "u"})
    assert response.status_code == 422


async def test_password_is_stored_encrypted(api, settings):
    await create_host(api, APP_HOST | {"password": "very-secret-value"})
    database_file = settings.database_url.removeprefix("sqlite+aiosqlite:///")
    with sqlite3.connect(database_file) as connection:
        (stored,) = connection.execute("SELECT password_encrypted FROM hosts").fetchone()
    assert stored and "very-secret-value" not in stored


async def test_discover_fills_inventory(api):
    host = await create_host(api, APP_HOST)

    response = await api.post(f"/api/hosts/{host['id']}/discover")
    assert response.status_code == 200
    assert response.json()["instances_added"] == ["DEV/01", "DEV/00"]

    detail = (await api.get(f"/api/hosts/{host['id']}")).json()
    assert detail["reachable"] is True
    assert detail["os_name"] == "Linux"
    assert [i["number"] for i in detail["instances"]] == ["00", "01"]
    assert detail["instances"][0]["features"] == "ABAP|GATEWAY|ICMAN|IGS"
    assert {(i["sid"], i["system_id"]) for i in detail["instances"]} == {("DEV", None)}
    assert detail["databases"] == []
    assert (await api.get("/api/systems")).json() == []


async def discover_hosts(api, *bodies: dict) -> dict[str, int]:
    """Discover the hosts; returns instance label -> instance id."""
    for body in bodies:
        host = await create_host(api, body)
        assert (await api.post(f"/api/hosts/{host['id']}/discover")).status_code == 200
    instances = (await api.get("/api/instances")).json()
    return {f"{i['sid']}/{i['number']}": i["id"] for i in instances}


async def create_system(api, name: str, *instance_ids: int, **extra) -> dict:
    body = {"name": name, "instance_ids": list(instance_ids)} | extra
    response = await api.post("/api/systems", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_system_from_instances_of_two_sids(api):
    ids = await discover_hosts(api, APP_HOST, DB_HOST)
    assert set(ids) == {"DEV/00", "DEV/01", "HDV/02"}
    unassigned = (await api.get("/api/instances", params={"unassigned": True})).json()
    assert len(unassigned) == 3

    system = await create_system(api, "DEV", *ids.values(), description="Development")
    assert (system["name"], system["description"]) == ("DEV", "Development")
    assert sorted(f"{i['sid']}/{i['number']}" for i in system["instances"]) == sorted(ids)
    assert (await api.get("/api/instances", params={"unassigned": True})).json() == []
    assert (await api.get(f"/api/systems/{system['id']}")).json()["name"] == "DEV"

    db_detail = (await api.get("/api/hosts/2")).json()
    assert [d["name"] for d in db_detail["databases"]] == ["HDV@HDV", "SYSTEMDB@HDV"]


async def test_create_system_errors(api):
    ids = await discover_hosts(api, APP_HOST)
    await create_system(api, "DEV", ids["DEV/00"])

    taken = await api.post("/api/systems", json={"name": "dev", "instance_ids": [ids["DEV/01"]]})
    assert taken.status_code == 409 and "already exists" in taken.json()["detail"]
    assigned = await api.post("/api/systems", json={"name": "X", "instance_ids": [ids["DEV/00"]]})
    assert assigned.status_code == 409 and "DEV/00" in assigned.json()["detail"]
    unknown = await api.post("/api/systems", json={"name": "X", "instance_ids": [99]})
    assert unknown.status_code == 422
    pool = await api.post(
        "/api/systems", json={"name": "X", "instance_ids": [ids["DEV/01"]], "pool_id": 99}
    )
    assert pool.status_code == 422
    assert [s["name"] for s in (await api.get("/api/systems")).json()] == ["DEV"]


async def test_assign_suggest_unassign_and_delete(api):
    ids = await discover_hosts(api, APP_HOST, DB_HOST)
    system = await create_system(api, "DEV", ids["DEV/00"])

    listed = {i["id"]: i for i in (await api.get("/api/instances")).json()}
    assert listed[ids["DEV/01"]]["suggested_system_id"] == system["id"]
    assert listed[ids["HDV/02"]]["suggested_system_id"] is None

    response = await api.post(
        f"/api/systems/{system['id']}/instances",
        json={"instance_ids": [ids["DEV/01"], ids["HDV/02"]]},
    )
    assert response.status_code == 200
    assert len(response.json()["instances"]) == 3

    path = f"/api/systems/{system['id']}/instances/{ids['HDV/02']}"
    assert (await api.delete(path)).status_code == 204
    assert (await api.delete(path)).status_code == 422

    renamed = await api.patch(f"/api/systems/{system['id']}", json={"name": "Development"})
    assert renamed.json()["name"] == "Development"

    assert (await api.delete(f"/api/systems/{system['id']}")).status_code == 204
    assert (await api.get("/api/systems")).json() == []
    unassigned = (await api.get("/api/instances", params={"unassigned": True})).json()
    assert len(unassigned) == 3


async def test_discover_unreachable_host_returns_502(api):
    host = await create_host(api, APP_HOST | {"hostagent_port": 4711})

    response = await api.post(f"/api/hosts/{host['id']}/discover")
    assert response.status_code == 502
    assert "Connection refused" in response.json()["detail"]

    detail = (await api.get(f"/api/hosts/{host['id']}")).json()
    assert detail["reachable"] is False
    assert "Connection refused" in detail["last_error"]


async def test_set_credentials(api):
    host = await create_host(api, {"name": "sapapp1", "address": "127.0.0.1"})
    credentials = {"username": "devadm", "password": "mock"}

    response = await api.put(f"/api/hosts/{host['id']}/credentials", json=credentials)
    assert response.status_code == 204
    assert (await api.get(f"/api/hosts/{host['id']}")).json()["username"] == "devadm"

    await api.post(f"/api/hosts/{host['id']}/discover")
    (sid,) = (await api.get("/api/sids")).json()
    assert (sid["name"], sid["has_credentials"]) == ("DEV", False)
    response = await api.put(f"/api/sids/{sid['id']}/credentials", json=credentials)
    assert response.status_code == 204
    assert (await api.get("/api/sids")).json()[0]["has_credentials"] is True


async def test_delete_host_removes_its_instances(api):
    ids = await discover_hosts(api, APP_HOST)
    await create_system(api, "DEV", *ids.values())

    assert (await api.delete("/api/hosts/1")).status_code == 204
    assert (await api.get("/api/hosts")).json() == []
    assert (await api.get("/api/instances")).json() == []
    assert (await api.get("/api/systems")).json()[0]["instances"] == []


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/hosts/99"),
        ("DELETE", "/api/hosts/99"),
        ("POST", "/api/hosts/99/discover"),
    ],
)
async def test_unknown_host_returns_404(api, method, path):
    assert (await api.request(method, path)).status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PUT", "/api/sids/99/credentials", {"username": "u", "password": "p"}),
        ("GET", "/api/systems/99", None),
        ("PATCH", "/api/systems/99", {"name": "X"}),
        ("DELETE", "/api/systems/99", None),
        ("POST", "/api/systems/99/instances", {"instance_ids": [1]}),
        ("POST", "/api/systems/99/start", None),
    ],
)
async def test_unknown_system_or_sid_returns_404(api, method, path, body):
    assert (await api.request(method, path, json=body)).status_code == 404


async def discover_both(api) -> tuple[int, int]:
    """Two systems as in a real landscape: DEV (ABAP) and HDV (its HANA database)."""
    ids = await discover_hosts(api, APP_HOST, DB_HOST)
    dev = await create_system(api, "DEV", ids["DEV/00"], ids["DEV/01"])
    hdv = await create_system(api, "HDV", ids["HDV/02"])
    return dev["id"], hdv["id"]


async def test_set_dependencies(api):
    dev, hdv = await discover_both(api)

    response = await api.put(f"/api/systems/{dev}/dependencies", json={"depends_on": [hdv]})
    assert response.status_code == 200
    assert response.json()["depends_on_ids"] == [hdv]

    systems = {s["name"]: s for s in (await api.get("/api/systems")).json()}
    assert systems["HDV"]["required_by_ids"] == [dev]

    cleared = await api.put(f"/api/systems/{dev}/dependencies", json={"depends_on": []})
    assert cleared.json()["depends_on_ids"] == []


@pytest.mark.parametrize(
    ("depends_on", "message"),
    [("self", "itself"), ("unknown", "Unknown systems"), ("cycle", "cycle")],
)
async def test_invalid_dependencies(api, depends_on, message):
    dev, hdv = await discover_both(api)
    if depends_on == "cycle":
        await api.put(f"/api/systems/{hdv}/dependencies", json={"depends_on": [dev]})
    target = {"self": [dev], "unknown": [999], "cycle": [hdv]}[depends_on]

    response = await api.put(f"/api/systems/{dev}/dependencies", json={"depends_on": target})

    assert response.status_code == 422
    assert message in response.json()["detail"]


async def test_dependencies_of_unknown_system(api):
    response = await api.put("/api/systems/99/dependencies", json={"depends_on": []})
    assert response.status_code == 404


async def test_pools(api):
    dev, hdv = await discover_both(api)

    created = await api.post("/api/pools", json={"name": "xDV", "description": "Development"})
    assert created.status_code == 201
    pool = created.json()
    assert (pool["name"], pool["system_ids"]) == ("xDV", [])
    assert (await api.post("/api/pools", json={"name": "xDV"})).status_code == 409

    assigned = await api.put(f"/api/systems/{dev}/pool", json={"pool_id": pool["id"]})
    assert assigned.status_code == 200 and assigned.json()["pool_id"] == pool["id"]
    assert (await api.get("/api/pools")).json()[0]["system_ids"] == [dev]

    unknown = await api.put(f"/api/systems/{hdv}/pool", json={"pool_id": 99})
    assert unknown.status_code == 422
    assert (await api.put("/api/systems/99/pool", json={"pool_id": None})).status_code == 404

    cleared = await api.put(f"/api/systems/{dev}/pool", json={"pool_id": None})
    assert cleared.json()["pool_id"] is None

    await api.put(f"/api/systems/{dev}/pool", json={"pool_id": pool["id"]})
    assert (await api.delete(f"/api/pools/{pool['id']}")).status_code == 204
    assert (await api.get("/api/pools")).json() == []
    systems = {s["name"]: s for s in (await api.get("/api/systems")).json()}
    assert systems["DEV"]["pool_id"] is None
    assert (await api.delete("/api/pools/99")).status_code == 404


async def test_tags_and_tag_filter(api):
    dev, hdv = await discover_both(api)

    saved = await api.put(f"/api/systems/{dev}/tags", json={"tags": ["dev", "SLA=1"]})
    assert saved.status_code == 200 and saved.json()["tags"] == ["dev", "sla=1"]
    await api.put(f"/api/systems/{hdv}/tags", json={"tags": ["sla=2"]})
    host = await api.put("/api/hosts/2/tags", json={"tags": ["dev", "db"]})
    assert host.json()["tags"] == ["db", "dev"]

    def names(response) -> list[str]:
        return [s["name"] for s in response.json()]

    assert names(await api.get("/api/systems", params={"tag": "sla"})) == ["DEV", "HDV"]
    assert names(await api.get("/api/systems", params={"tag": "sla=2"})) == ["HDV"]
    assert names(await api.get("/api/systems", params={"tag": ["dev", "sla=2"]})) == [
        "DEV",
        "HDV",
    ]
    assert names(await api.get("/api/hosts", params={"tag": "db"})) == ["sapdb1"]

    invalid = await api.put(f"/api/systems/{dev}/tags", json={"tags": ["bad tag"]})
    assert invalid.status_code == 422
    assert (await api.put("/api/systems/99/tags", json={"tags": []})).status_code == 404
    cleared = await api.put(f"/api/systems/{dev}/tags", json={"tags": []})
    assert cleared.json()["tags"] == []


async def test_refresh_system(api, landscape):
    dev, _ = await discover_both(api)
    landscape.start_instance(landscape.host("sapapp1").instance(0))

    response = await api.post(f"/api/systems/{dev}/refresh")

    assert response.status_code == 200
    body = response.json()
    assert body["warnings"] == []
    statuses = {i["number"]: i["last_status"] for i in body["system"]["instances"]}
    assert statuses == {"00": "YELLOW", "01": "GRAY"}
    assert (await api.post("/api/systems/99/refresh")).status_code == 404


async def test_refresh_reports_unreachable_instances(settings, landscape):
    transport = MockLandscapeTransport(landscape)
    app = create_app(settings, transport=transport)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {await make_user(app)}"},
        ) as client:
            dev, _ = await discover_both(client)
            transport.remove_port(50013)
            body = (await client.post(f"/api/systems/{dev}/refresh")).json()
    assert len(body["warnings"]) == 1
    assert body["warnings"][0].startswith("DEV/00: sapstartsrv could not be queried")
    statuses = {i["number"]: i["last_status"] for i in body["system"]["instances"]}
    assert statuses["00"] == "UNKNOWN"


async def test_update_host_connection(api):
    host = await create_host(api, APP_HOST | {"hostagent_port": 4711})
    await create_host(api, {"name": "other"})
    path = f"/api/hosts/{host['id']}"

    # Wrong port first: the discovery fails; after the change it works.
    assert (await api.post(f"{path}/discover")).status_code == 502
    changed = await api.patch(path, json={"hostagent_port": 0, "name": "app1"})
    assert changed.status_code == 200
    body = changed.json()
    assert (body["name"], body["hostagent_port"], body["address"]) == ("app1", None, "127.0.0.1")
    assert (await api.post(f"{path}/discover")).status_code == 200

    unchanged = (await api.patch(path, json={})).json()
    assert unchanged["name"] == "app1" and unchanged["has_credentials"] is True
    https = (await api.patch(path, json={"https": True, "verify_tls": False})).json()
    assert (https["https"], https["verify_tls"]) == (True, False)

    assert (await api.patch(path, json={"name": "OTHER"})).status_code == 409
    assert (await api.patch(path, json={"hostagent_port": 70000})).status_code == 422
    assert (await api.patch("/api/hosts/99", json={})).status_code == 404

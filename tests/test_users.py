from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from conftest import PASSWORD, make_user
from oslo import usercli
from oslo.api import create_app
from oslo.crypto import generate_secret_key
from oslo.mock.transport import MockLandscapeTransport
from oslo.models import User
from oslo.permissions import required_role
from oslo.settings import Settings
from oslo.users import (
    SESSION_LIFETIME_SECONDS,
    Role,
    UserError,
    check_password,
    create_session,
    has_role,
    hash_password,
    parse_session,
    verify_password,
)

pytestmark = pytest.mark.anyio


# --- units --------------------------------------------------------------------------------


def test_password_hashing():
    stored = hash_password("a long password!")
    assert stored.startswith("scrypt$") and "a long password" not in stored
    assert verify_password("a long password!", stored)
    assert not verify_password("a long password?", stored)
    assert not verify_password("x", "garbage")
    assert hash_password("same") != hash_password("same")  # salted
    with pytest.raises(UserError):
        check_password("too short")


def test_session_cookie():
    user = User(id=7, session_epoch=3)
    value = create_session("key-a", user, now=1000)
    assert parse_session("key-a", value, now=1000) == (7, 3)
    assert parse_session("key-a", value, now=1000 + SESSION_LIFETIME_SECONDS + 1) is None
    assert parse_session("key-b", value, now=1000) is None
    assert parse_session("key-a", None) is None
    assert parse_session("key-a", "garbage") is None
    user_id, epoch, expires, signature = value.split(".")
    assert parse_session("key-a", f"8.{epoch}.{expires}.{signature}", now=1000) is None


def test_roles_build_on_each_other():
    operator = User(role="operator")
    assert has_role(operator, Role.VIEWER) and has_role(operator, Role.OPERATOR)
    assert not has_role(operator, Role.CONFIGURATOR)
    assert has_role(User(role="admin"), Role.CONFIGURATOR)
    assert not has_role(User(role="bogus"), Role.VIEWER)


@pytest.mark.parametrize(
    ("method", "path", "role"),
    [
        ("GET", "/systems", Role.VIEWER),
        ("POST", "/systems/{system_id}/refresh", Role.VIEWER),
        ("POST", "/systems/{system_id}/{operation}", Role.OPERATOR),
        ("POST", "/instances/{instance_id}/{operation}", Role.OPERATOR),
        ("POST", "/hosts", Role.CONFIGURATOR),
        ("PUT", "/systems/{system_id}/tags", Role.CONFIGURATOR),
        ("GET", "/configuration", Role.CONFIGURATOR),
        ("GET", "/configuration/hosts/new", Role.CONFIGURATOR),
        ("GET", "/operations", Role.VIEWER),
        ("GET", "/operations/custom", Role.ADMIN),
        ("POST", "/operations/custom/{operation_id}", Role.ADMIN),
        ("GET", "/operations/templates", Role.ADMIN),
        ("GET", "/users", Role.ADMIN),
        ("GET", "/administration", Role.ADMIN),
        ("POST", "/me/tokens", Role.VIEWER),
        ("POST", "/account/password", Role.VIEWER),
    ],
)
def test_required_roles(method, path, role):
    assert required_role(method, path) is role


# --- application --------------------------------------------------------------------------


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        secret_key=generate_secret_key(),
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'users.db'}",
    )


@pytest.fixture
async def app(settings, landscape, clock):
    async def fake_sleep(seconds: float) -> None:
        clock.advance(seconds)
        await asyncio.sleep(0)

    application = create_app(
        settings,
        transport=MockLandscapeTransport(landscape),
        poll_interval=1.0,
        sleep=fake_sleep,
        clock=clock,
    )
    async with application.router.lifespan_context(application):
        yield application


def client_for(app, token: str | None = None) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
    )


APP_HOST = {"name": "sapapp1", "address": "127.0.0.1", "username": "devadm", "password": "mock"}


async def test_api_roles(app):
    tokens = {role: await make_user(app, role, role) for role in ("viewer", "operator")}
    tokens |= {role: await make_user(app, role, role) for role in ("configurator", "admin")}

    async with client_for(app, tokens["configurator"]) as configurator:
        assert (await configurator.post("/api/hosts", json=APP_HOST)).status_code == 201
        assert (await configurator.post("/api/hosts/1/discover")).status_code == 200
        body = {"name": "DEV", "instance_ids": [1, 2]}
        assert (await configurator.post("/api/systems", json=body)).status_code == 201
        assert (await configurator.get("/api/users")).status_code == 403
        assert (await configurator.post("/api/systems/1/start")).status_code == 202

    async with client_for(app, tokens["viewer"]) as viewer:
        assert (await viewer.get("/api/systems")).status_code == 200
        assert (await viewer.post("/api/systems/1/refresh")).status_code == 200
        forbidden = await viewer.post("/api/systems/1/stop")
        assert forbidden.status_code == 403 and "operator" in forbidden.json()["detail"]
        assert (await viewer.post("/api/hosts", json={"name": "x"})).status_code == 403

    await app.state.runner.wait(1)
    async with client_for(app, tokens["operator"]) as operator:
        stop = await operator.post("/api/systems/1/stop")
        assert stop.status_code == 202 and stop.json()["requested_by"] == "operator"
        await app.state.runner.wait(stop.json()["id"])
        assert (await operator.put("/api/systems/1/tags", json={"tags": []})).status_code == 403

    async with client_for(app, tokens["admin"]) as admin:
        listed = (await admin.get("/api/activities")).json()
        assert [a["requested_by"] for a in listed] == ["operator", "configurator"]
        assert len((await admin.get("/api/users")).json()) == 4


async def test_api_rejects_missing_invalid_expired_and_inactive_tokens(app):
    token = await make_user(app, "admin", "admin")
    async with client_for(app) as anonymous:
        assert (await anonymous.get("/api/hosts")).status_code == 401
    async with client_for(app, "oslo_wrong") as wrong:
        assert (await wrong.get("/api/hosts")).status_code == 401

    async with client_for(app, token) as admin:
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        expired = await admin.post("/api/me/tokens", json={"name": "old", "expires_at": past})
        assert expired.status_code == 201
        created = await admin.post(
            "/api/users", json={"username": "bob", "role": "viewer", "password": "start password 1"}
        )
        bob = created.json()
        assert bob["must_change_password"] is True
    async with client_for(app, expired.json()["token"]) as old:
        assert (await old.get("/api/hosts")).status_code == 401

    bob_token = await make_user(app, "bob2", "viewer")
    async with client_for(app, token) as admin:
        users = {u["username"]: u["id"] for u in (await admin.get("/api/users")).json()}
        await admin.patch(f"/api/users/{users['bob2']}", json={"active": False})
    async with client_for(app, bob_token) as deactivated:
        assert (await deactivated.get("/api/hosts")).status_code == 401


async def test_api_own_tokens_and_user_management(app):
    token = await make_user(app, "admin", "admin")
    async with client_for(app, token) as admin:
        me = (await admin.get("/api/me")).json()
        assert (me["username"], me["role"]) == ("admin", "admin")

        created = (await admin.post("/api/me/tokens", json={"name": "script"})).json()
        assert created["token"].startswith("oslo_") and created["info"]["name"] == "script"
        listed = (await admin.get("/api/me/tokens")).json()
        assert [t["name"] for t in listed] == ["tests", "script"]
        assert "token" not in listed[1] and created["token"].startswith(listed[1]["prefix"])
        token_id = created["info"]["id"]
        assert (await admin.delete(f"/api/me/tokens/{token_id}")).status_code == 204
        assert (await admin.delete(f"/api/me/tokens/{token_id}")).status_code == 404

        body = {"username": "Ops.One", "role": "operator", "password": "start password 1"}
        user = (await admin.post("/api/users", json=body)).json()
        assert user["username"] == "ops.one"
        assert (await admin.post("/api/users", json=body)).status_code == 409
        short = body | {"username": "x", "password": "short"}
        assert (await admin.post("/api/users", json=short)).status_code == 422

        changed = await admin.patch(f"/api/users/{user['id']}", json={"role": "configurator"})
        assert changed.json()["role"] == "configurator"
        reset = await admin.put(
            f"/api/users/{user['id']}/password", json={"password": "another password"}
        )
        assert reset.status_code == 204

        last = await admin.patch(f"/api/users/{me['id']}", json={"role": "viewer"})
        assert last.status_code == 409 and "last active admin" in last.json()["detail"]
        assert (await admin.patch("/api/users/99", json={})).status_code == 404


# --- web ----------------------------------------------------------------------------------


async def test_setup_creates_the_first_admin(app):
    code = app.state.setup_code
    assert code and len(code) == 20
    async with client_for(app) as browser:
        assert (await browser.get("/")).headers["location"] == "/setup"
        assert (await browser.get("/login")).headers["location"] == "/setup"
        assert "Setup code" in (await browser.get("/setup")).text

        form = {
            "code": "wrong",
            "username": "chief",
            "password": PASSWORD,
            "password_repeat": PASSWORD,
        }
        assert (
            (await browser.post("/setup", data=form))
            .headers["location"]
            .endswith("error=setup_code")
        )
        mismatch = form | {"code": code, "password_repeat": "other"}
        assert (
            (await browser.post("/setup", data=mismatch))
            .headers["location"]
            .endswith("error=password_mismatch")
        )
        done = await browser.post("/setup", data=form | {"code": code})
        assert done.headers["location"] == "/?notice=setup_done"
        assert (await browser.get("/administration")).status_code == 200  # signed in as admin

        assert app.state.setup_code is None
        assert (await browser.get("/setup")).headers["location"] == "/login"
        again = await browser.post("/setup", data=form | {"code": code, "username": "x"})
        assert again.headers["location"] == "/login"


async def sign_in(browser: httpx.AsyncClient, username: str, password: str = PASSWORD):
    return await browser.post("/login", data={"username": username, "password": password})


async def test_lockout_after_failed_attempts(app):
    await make_user(app, "admin", "admin")
    async with client_for(app) as browser:
        for _ in range(5):
            assert (await sign_in(browser, "admin", "wrong")).status_code == 401
        # Locked: even the right password is refused for a minute.
        assert (await sign_in(browser, "admin")).status_code == 401
    async with app.state.session_factory() as session:
        user = await session.get(User, 1)
        user.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    async with client_for(app) as browser:
        assert (await sign_in(browser, "admin")).status_code == 303


HEADERS = {"X-OSLO-Request": "1"}


async def test_roles_in_the_interface(app):
    """The pages call the API with the session cookie; the roles apply as with tokens."""
    await make_user(app, "admin", "admin")
    await make_user(app, "viewer", "viewer")
    await make_user(app, "operator", "operator")
    async with client_for(app) as admin:
        await sign_in(admin, "admin")
        await admin.post("/api/hosts", json=APP_HOST, headers=HEADERS)
        await admin.post("/api/hosts/1/discover", headers=HEADERS)
        body = {"name": "DEV", "instance_ids": [1, 2]}
        assert (await admin.post("/api/systems", json=body, headers=HEADERS)).status_code == 201

    async with client_for(app) as viewer:
        await sign_in(viewer, "viewer")
        page = (await viewer.get("/landscape")).text
        assert ">Configuration</a>" not in page and ">Administration</a>" not in page
        assert (await viewer.get("/configuration")).status_code == 403
        assert (await viewer.post("/api/systems/1/start", headers=HEADERS)).status_code == 403
        assert (await viewer.post("/api/systems/1/refresh", headers=HEADERS)).status_code == 200
        assert (await viewer.get("/account")).status_code == 200

    async with client_for(app) as operator:
        await sign_in(operator, "operator")
        started = await operator.post("/api/systems/1/start", headers=HEADERS)
        assert started.status_code == 202
        activity = (await operator.get(f"/api/activities/{started.json()['id']}")).json()
        assert activity["requested_by"] == "operator"
        await app.state.runner.wait(activity["id"])


async def test_start_password_must_be_changed(app):
    await make_user(app, "admin", "admin")
    async with client_for(app) as admin:
        await sign_in(admin, "admin")
        body = {"username": "newbie", "role": "operator", "password": "start password 1"}
        created = await admin.post("/api/users", json=body, headers=HEADERS)
        assert created.status_code == 201 and created.json()["must_change_password"]

    async with client_for(app) as newbie:
        response = await sign_in(newbie, "newbie", "start password 1")
        assert response.headers["location"] == "/account/password"
        blocked = await newbie.get("/landscape")
        assert blocked.headers["location"].startswith("/account/password")
        # The API is locked as well until the password is changed.
        assert (await newbie.get("/api/landscape")).status_code == 403

        def change(**values):
            data = {
                "current": "start password 1",
                "password": "my own password",
                "password_repeat": "my own password",
            } | values
            return newbie.post("/account/password", data=data)

        assert (await change(current="wrong")).headers["location"].endswith("password_wrong")
        assert (await change(password_repeat="x")).headers["location"].endswith("password_mismatch")
        same = await change(password="start password 1", password_repeat="start password 1")
        assert same.headers["location"].endswith("password_same")
        assert (await change()).headers["location"] == "/account?notice=password_changed"
        assert (await newbie.get("/landscape")).status_code == 200


async def test_role_change_ends_sessions_and_last_admin_stays(app):
    await make_user(app, "admin", "admin")
    await make_user(app, "other", "operator")
    async with client_for(app) as other, client_for(app) as admin:
        await sign_in(other, "other")
        assert (await other.get("/")).status_code == 200
        await sign_in(admin, "admin")

        saved = await admin.patch("/api/users/2", json={"role": "viewer"}, headers=HEADERS)
        assert saved.status_code == 200
        assert (await other.get("/")).headers["location"].startswith("/login")

        demote = await admin.patch("/api/users/1", json={"role": "operator"}, headers=HEADERS)
        assert demote.status_code == 409
        reset = await admin.put(
            "/api/users/2/password", json={"password": "fresh start pw"}, headers=HEADERS
        )
        assert reset.status_code == 204
        assert (await admin.get("/administration/users/2")).status_code == 200
        assert (await admin.get("/administration/users/99")).status_code == 404


async def test_own_tokens_with_the_session_cookie(app):
    await make_user(app, "admin", "admin")
    async with client_for(app) as browser:
        await sign_in(browser, "admin")
        body = {"name": "monitoring"}
        created = await browser.post("/api/me/tokens", json=body, headers=HEADERS)
        token = created.json()["token"]
        assert token.startswith("oslo_")
        async with client_for(app, token) as script:
            assert (await script.get("/api/me")).json()["username"] == "admin"
        token_id = created.json()["info"]["id"]
        deleted = await browser.delete(f"/api/me/tokens/{token_id}", headers=HEADERS)
        assert deleted.status_code == 204
        async with client_for(app, token) as script:
            assert (await script.get("/api/me")).status_code == 401


def test_lo_user_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OSLO_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}")
    monkeypatch.setattr(usercli.getpass, "getpass", lambda prompt="": PASSWORD)

    def run(*args: str) -> str:
        monkeypatch.setattr(sys, "argv", ["oslo-user", *args])
        usercli.main()
        return capsys.readouterr().out

    assert "User root created (admin)" in run("add", "Root", "--role", "admin")
    assert "root" in run("list") and "admin" in run("list")
    assert "Password of root set" in run("passwd", "root")
    with pytest.raises(SystemExit, match="already exists"):
        run("add", "root")
    with pytest.raises(SystemExit, match="No user"):
        run("passwd", "ghost")

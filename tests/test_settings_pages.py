"""Editing pools, creating several hosts at once, and the display preferences of a user
(language and color scheme in "My account")."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from conftest import make_user
from test_mass import client
from test_web import HEADERS, anonymous, app, browser, settings, sign_in  # noqa: F401

pytestmark = pytest.mark.anyio


async def test_edit_a_pool(app):  # noqa: F811
    async with client(app, await make_user(app)) as admin:
        erp = (await admin.post("/api/pools", json={"name": "ERP", "description": "x"})).json()
        await admin.post("/api/pools", json={"name": "CRM"})

        changed = await admin.patch(f"/api/pools/{erp['id']}", json={"name": " S/4 ERP "})
        assert changed.status_code == 200
        # Only the name changes; the description stays.
        assert changed.json()["name"] == "S/4 ERP" and changed.json()["description"] == "x"
        cleared = await admin.patch(f"/api/pools/{erp['id']}", json={"description": ""})
        assert cleared.json()["description"] is None and cleared.json()["name"] == "S/4 ERP"
        assert (await admin.get(f"/api/pools/{erp['id']}")).json()["system_ids"] == []

        taken = await admin.patch(f"/api/pools/{erp['id']}", json={"name": "CRM"})
        assert taken.status_code == 409
        blank = await admin.patch(f"/api/pools/{erp['id']}", json={"name": "  "})
        assert blank.status_code == 422
        assert (await admin.patch("/api/pools/99", json={"name": "X"})).status_code == 404

    async with client(app, await make_user(app, "op", "operator")) as op:
        assert (await op.patch(f"/api/pools/{erp['id']}", json={"name": "Y"})).status_code == 403
        assert (await op.get(f"/api/pools/{erp['id']}")).status_code == 200


async def test_create_several_hosts(app):  # noqa: F811
    async with client(app, await make_user(app)) as admin:
        body = {
            "names": ["sapapp1", " sapapp2 ", "sapdb1", ""],
            "https": True,
            "verify_hostname": False,
            "username": "sapadm",
            "password": "secret",
        }
        created = await admin.post("/api/hosts/batch", json=body)
        assert created.status_code == 201, created.text
        hosts = created.json()
        assert [h["name"] for h in hosts] == ["sapapp1", "sapapp2", "sapdb1"]
        assert all(h["address"] == h["name"] for h in hosts)
        assert all(h["https"] and not h["verify_hostname"] and h["has_credentials"] for h in hosts)

        # All or none: one existing name stops the whole batch.
        again = await admin.post("/api/hosts/batch", json={"names": ["sapapp3", "SAPAPP1"]})
        assert again.status_code == 409 and "sapapp1" in again.text
        assert len((await admin.get("/api/hosts")).json()) == 3
        for names, message in (
            (["a", "A"], "more than once"),
            (["a b"], "spaces"),
            ([" ", ""], "No host name"),
        ):
            refused = await admin.post("/api/hosts/batch", json={"names": names})
            assert refused.status_code == 422 and message in refused.text
        half = await admin.post("/api/hosts/batch", json={"names": ["x"], "username": "u"})
        assert half.status_code == 422

    async with client(app, await make_user(app, "op", "operator")) as op:
        assert (await op.post("/api/hosts/batch", json={"names": ["x"]})).status_code == 403


async def test_preferences_in_the_api(app):  # noqa: F811
    async with client(app, await make_user(app)) as admin:
        assert (await admin.get("/api/me/preferences")).json() == {
            "language": "",
            "theme": "system",
            "time": "browser",
        }
        saved = await admin.put("/api/me/preferences", json={"language": "de", "theme": "dark"})
        assert saved.json() == {"language": "de", "theme": "dark", "time": "browser"}
        # Only what is given changes.
        saved = await admin.put("/api/me/preferences", json={"theme": "light"})
        assert saved.json() == {"language": "de", "theme": "light", "time": "browser"}
        saved = await admin.put("/api/me/preferences", json={"time": "utc"})
        assert saved.json()["time"] == "utc"
        assert (await admin.put("/api/me/preferences", json={"time": "cet"})).status_code == 422
        assert (await admin.get("/api/i18n")).json()["language"] == "de"
        bad = await admin.put("/api/me/preferences", json={"theme": "pink"})
        assert bad.status_code == 422
    # Every role has its own preferences.
    async with client(app, await make_user(app, "view", "viewer")) as viewer:
        assert (await viewer.put("/api/me/preferences", json={"language": "en"})).status_code == 200
        assert (await viewer.get("/api/me/preferences")).json()["language"] == "en"


async def test_preferences_shape_the_pages(browser):  # noqa: F811
    page = (await browser.get("/account")).text
    assert '<html lang="en">' in page  # no choice yet: the browser's language, system colors

    await browser.put(
        "/api/me/preferences", json={"language": "de", "theme": "dark"}, headers=HEADERS
    )
    page = (await browser.get("/account")).text
    assert '<html lang="de" data-theme="dark">' in page
    # The chosen language wins over the browser and the language cookie.
    browser.cookies.set("oslo_lang", "en")
    page = (await browser.get("/account", headers={"accept-language": "en"})).text
    assert '<html lang="de" data-theme="dark">' in page

    # Signed in, there is no language switch in the header; "My account" decides.
    assert 'href="/language/' not in page
    await browser.put(
        "/api/me/preferences", json={"language": "en", "theme": "system"}, headers=HEADERS
    )
    assert '<html lang="en">' in (await browser.get("/account")).text


async def test_language_switch_without_sign_in(anonymous):  # noqa: F811
    response = await anonymous.get("/language/de?next=/login")
    assert response.status_code == 303 and response.cookies.get("oslo_lang") == "de"
    await sign_in(anonymous)
    # Nothing was stored for the user before; the cookie decides.
    assert (await anonymous.get("/api/me/preferences")).json()["language"] == ""
    assert '<html lang="de">' in (await anonymous.get("/account")).text


async def test_schedules_area(browser, app):  # noqa: F811
    from test_web import add_hosts

    await add_hosts(browser)
    body = {
        "name": " Morning restart ",
        "operation": "start",
        "target_type": "SYSTEM",
        "target_ids": [1],
        "recurrence": "daily",
        "time_of_day": "06:30",
        "weekdays": "12345",
    }
    created = await browser.post("/api/schedules", json=body, headers=HEADERS)
    assert created.status_code == 201, created.text
    schedule = created.json()
    assert schedule["name"] == "Morning restart" and schedule["last_status"] is None
    # Times carry their zone, so that browsers do not read them as local time.
    assert schedule["next_run_at"].endswith(("Z", "+00:00"))
    assert schedule["created_at"].endswith(("Z", "+00:00"))
    one = await browser.get(f"/api/schedules/{schedule['id']}")
    assert one.status_code == 200 and one.json()["time_of_day"] == "06:30"
    assert (await browser.get("/api/schedules/99")).status_code == 404
    unnamed = await browser.post("/api/schedules", json=body | {"name": "  "}, headers=HEADERS)
    assert unnamed.json()["name"] is None

    # A run fills in the status of its activity.
    app.state.scheduler.now = lambda: datetime(2030, 1, 7, 6, 31, tzinfo=UTC)  # a Monday
    await app.state.scheduler.tick()
    listed = {s["id"]: s for s in (await browser.get("/api/schedules")).json()}
    await app.state.runner.wait(listed[schedule["id"]]["last_activity_id"])
    listed = {s["id"]: s for s in (await browser.get("/api/schedules")).json()}
    assert listed[schedule["id"]]["last_status"] in ("SUCCEEDED", "FAILED", "RUNNING")
    time = (await browser.get("/api/server-time")).json()
    assert time["timezone"] == "Europe/Berlin" and time["now"].startswith("2030-01-07")

    page = await browser.get(f"/operations/schedules/{schedule['id']}")
    assert page.status_code == 200 and '"page": "schedule"' in page.text
    # The old address leads to the new place.
    moved = await browser.get("/activities?tab=schedules")
    assert moved.status_code in (302, 303) and moved.headers["location"] == "/operations/schedules"


async def test_schedules_for_operators_only(app):  # noqa: F811
    import httpx

    for name, role in (("op", "operator"), ("view", "viewer")):
        await make_user(app, name, role)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as web:
        await sign_in(web, "op")
        page = await web.get("/operations/schedules")
        assert page.status_code == 200
        # Operators see only the schedules in the Operations area.
        assert 'href="/operations/schedules"' in page.text
        assert 'href="/operations/custom"' not in page.text
        assert (await web.get("/operations/custom")).status_code == 403
        redirect = await web.get("/operations")
        assert redirect.headers["location"] == "/operations/schedules"
        await web.post("/logout")
        await sign_in(web, "view")
        assert (await web.get("/operations/schedules")).status_code == 403
        assert 'href="/operations"' not in (await web.get("/activities")).text


async def test_times_carry_their_zone(browser, app):  # noqa: F811
    """The API sends every time in UTC with its zone, so that browsers convert it; the
    page tells the browser whether to show UTC or local time."""
    from test_web import add_hosts, boot_of

    await add_hosts(browser)
    host = (await browser.get("/api/hosts/1")).json()
    started = await browser.post("/api/instances/1/start", headers=HEADERS)
    await app.state.runner.wait(started.json()["id"])
    activity = (await browser.get(f"/api/activities/{started.json()['id']}")).json()
    users = (await browser.get("/api/users")).json()
    for value in (
        host["last_discovery_at"],
        activity["requested_at"],
        activity["entries"][0]["timestamp"],
        users[0]["created_at"],
    ):
        assert value.endswith(("Z", "+00:00")), value

    assert boot_of((await browser.get("/landscape")).text)["time_display"] == "browser"
    await browser.put("/api/me/preferences", json={"time": "utc"}, headers=HEADERS)
    assert boot_of((await browser.get("/landscape")).text)["time_display"] == "utc"

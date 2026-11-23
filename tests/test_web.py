"""Web interface: sign-in, setup, languages and the shells of the React pages.

What the pages show comes from the REST API (tests in test_api.py, test_interface_api.py,
test_overview.py and others); here: that each address delivers the right app with its start
data, that old addresses lead to the new pages, and the areas' navigation.
"""

from __future__ import annotations

import asyncio
import json
import re

import httpx
import pytest

from conftest import PASSWORD, make_user
from oslo.api import create_app
from oslo.crypto import generate_secret_key
from oslo.mock.transport import MockLandscapeTransport
from oslo.settings import Settings
from oslo.web.i18n import TEXTS, instance_type_key, pick_language, translate
from oslo.web.routes import SESSION_COOKIE

pytestmark = pytest.mark.anyio

CREDENTIALS = {"username": "devadm", "password": "mock"}
APP_HOST = {"name": "sapapp1", "address": "127.0.0.1"} | CREDENTIALS
DB_HOST = APP_HOST | {"name": "sapdb1", "hostagent_port": 11128, "sapcontrol_port_offset": 10000}
# Changing API calls with the session cookie need this header (see test_interface_api.py).
HEADERS = {"X-OSLO-Request": "1"}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        secret_key=generate_secret_key(),
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'web.db'}",
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


@pytest.fixture
async def anonymous(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await make_user(app)  # the admin "admin"; without any user, pages lead to /setup
        yield client


async def sign_in(client: httpx.AsyncClient, username: str = "admin") -> httpx.Response:
    response = await client.post("/login", data={"username": username, "password": PASSWORD})
    assert response.status_code == 303, response.text
    return response


@pytest.fixture
async def browser(anonymous):
    """A browser signed in as admin."""
    await sign_in(anonymous)
    return anonymous


async def add_hosts(browser: httpx.AsyncClient) -> None:
    """Through the API like the pages: hosts 1 (sapapp1) and 2 (sapdb1), systems 1 (DEV:
    instances 1, 2) and 2 (HDV: instance 3), pool 1 (ERP)."""
    for body in (APP_HOST, DB_HOST):
        host = (await browser.post("/api/hosts", json=body, headers=HEADERS)).json()
        await browser.post(f"/api/hosts/{host['id']}/discover", headers=HEADERS)
    for name, ids in (("DEV", [1, 2]), ("HDV", [3])):
        body = {"name": name, "instance_ids": ids}
        assert (await browser.post("/api/systems", json=body, headers=HEADERS)).status_code == 201
    pool = await browser.post("/api/pools", json={"name": "ERP"}, headers=HEADERS)
    assert pool.status_code == 201


def boot_of(page: str) -> dict:
    """Start data of a React page."""
    match = re.search(r'<script type="application/json" id="oslo-boot">(.*?)</script>', page, re.S)
    assert match, "no start data"
    return json.loads(match.group(1))


# --- sessions and translations -----------------------------------------------------------


def test_every_text_has_both_languages():
    for key, (english, german) in TEXTS.items():
        assert english and german, key
        assert re.findall(r"{(\w+)}", english) == re.findall(r"{(\w+)}", german), key


def test_translate_and_language_choice():
    assert translate("de", "nav.overview") == "Übersicht"
    assert translate("en", "nav.overview") == "Overview"
    assert translate("de", "no.such.key") == "no.such.key"
    assert translate("en", "error.discovery_failed", detail="x").endswith(": x")
    assert pick_language("de", "en-US") == "de"
    assert pick_language(None, "de-DE,de;q=0.9,en;q=0.8") == "de"
    assert pick_language(None, "fr-FR") == "en"
    assert pick_language("xx", None) == "en"


def test_instance_type_from_features():
    assert instance_type_key("HDB|HDB_WORKER") == "itype.hana"
    assert instance_type_key("MESSAGESERVER|ENQUE") == "itype.scs"
    assert instance_type_key("ABAP|GATEWAY|ICMAN|IGS") == "itype.abap"
    assert instance_type_key("ABAP|J2EE|GATEWAY") == "itype.dual"
    assert instance_type_key(None) is None


# --- sign in -----------------------------------------------------------------------------


# (address, app, page of the app) of every React page.
APP_PAGES = [
    ("/", "overview", None),
    ("/landscape", "landscape", None),
    ("/activities", "activities", "activities"),
    ("/activities?tab=logs", "activities", "logs"),
    ("/configuration/hosts", "configuration", "hosts"),
    ("/configuration/hosts/new", "configuration", "host_new"),
    ("/configuration/hosts/1", "configuration", "host"),
    ("/configuration/systems", "configuration", "systems"),
    ("/configuration/systems/unassigned", "configuration", "unassigned"),
    ("/configuration/systems/new", "configuration", "system_new"),
    ("/configuration/systems/1", "configuration", "system"),
    ("/configuration/pools", "configuration", "pools"),
    ("/configuration/pools/new", "configuration", "pool_new"),
    ("/configuration/pools/1", "configuration", "pool"),
    ("/operations/schedules", "operations", "schedules"),
    ("/operations/schedules/new", "operations", "schedule_new"),
    ("/operations/custom", "operations", "customs"),
    ("/operations/custom/new", "operations", "custom_new"),
    ("/operations/templates", "templates", None),
    ("/administration", "administration", "general"),
    ("/administration/users", "administration", "users"),
    ("/administration/users/new", "administration", "user_new"),
    ("/administration/users/1", "administration", "user"),
    ("/administration/attention", "administration", "attention"),
    ("/administration/certificates", "administration", "certificates"),
    ("/administration/certificates/new", "administration", "certificate_new"),
    ("/administration/transfer", "administration", "transfer"),
    ("/account", "account", None),
]


@pytest.mark.parametrize("path", [p for p, _, _ in APP_PAGES] + ["/hosts/1", "/systems/1"])
async def test_pages_require_login(anonymous, path):
    response = await anonymous.get(path)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


async def test_login_with_wrong_password(anonymous):
    response = await anonymous.post("/login", data={"username": "admin", "password": "wrong"})
    assert response.status_code == 401
    assert "Sign-in failed." in response.text
    assert SESSION_COOKIE not in response.cookies
    unknown = await anonymous.post("/login", data={"username": "nobody", "password": PASSWORD})
    assert unknown.status_code == 401


async def test_login_sets_protected_cookie_and_returns_to_page(anonymous):
    redirect = await anonymous.get("/activities")
    assert redirect.headers["location"] == "/login?next=%2Factivities"

    response = await anonymous.post(
        "/login", data={"username": "admin", "password": PASSWORD, "next": "/activities"}
    )
    assert response.headers["location"] == "/activities"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert (await anonymous.get("/activities")).status_code == 200


@pytest.mark.parametrize("target", ["https://evil.example/", "//evil.example", "/\\evil"])
async def test_login_does_not_redirect_to_other_sites(anonymous, target):
    data = {"username": "admin", "password": PASSWORD, "next": target}
    response = await anonymous.post("/login", data=data)
    assert response.headers["location"] == "/"


async def test_logout(browser):
    assert (await browser.post("/logout")).headers["location"] == "/login"
    assert (await browser.get("/")).status_code == 303


async def test_cross_site_post_is_rejected(browser):
    body = {"current": PASSWORD, "password": "x" * 20, "password_repeat": "x" * 20}
    response = await browser.post(
        "/account/password", data=body, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403


async def test_api_token_is_not_accepted_as_session_on_pages(anonymous, app):
    token = await make_user(app, "script", "viewer")
    response = await anonymous.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 303


# --- the React pages -----------------------------------------------------------------------


@pytest.mark.parametrize(("path", "app_name", "page"), APP_PAGES)
async def test_each_address_delivers_its_app(browser, path, app_name, page):
    await add_hosts(browser)
    response = await browser.get(path)
    assert response.status_code == 200, path
    assert f'src="/static/app/{app_name}.js?v=' in response.text
    assert 'href="/static/app/app.css?v=' in response.text
    assert '<div id="oslo-app">' in response.text
    boot = boot_of(response.text)
    assert boot.get("page") == page and boot["user"] == {"name": "admin", "role": "admin"}
    assert boot["texts"]["nav.landscape"] == "Landscape"
    if path.endswith("/1"):
        assert boot["id"] == 1
    for item in ("Overview", "Landscape", "Activities", "Configuration", "Administration"):
        assert f">{item}</a>" in response.text


async def test_activity_page(browser, app):
    await add_hosts(browser)
    started = await browser.post("/api/instances/1/start", headers=HEADERS)
    await app.state.runner.wait(started.json()["id"])
    await browser.get("/language/de")
    page = (await browser.get("/activities/1")).text
    assert 'src="/static/app/activity.js?v=' in page and boot_of(page)["activity_id"] == 1
    # German texts for the page come with it; the log itself stays English.
    assert boot_of(page)["texts"]["activity.FAILED"] == "fehlgeschlagen"


@pytest.mark.parametrize(
    "path",
    [
        "/hosts/99",
        "/systems/99",
        "/activities/99",
        "/configuration/hosts/99",
        "/configuration/systems/99",
        "/configuration/pools/99",
        "/operations/schedules/99",
        "/operations/custom/99",
        "/administration/users/99",
    ],
)
async def test_unknown_targets(browser, path):
    assert (await browser.get(path)).status_code == 404


async def test_old_addresses_lead_to_the_new_pages(browser):
    await add_hosts(browser)
    for old, new in (
        ("/configuration", "/configuration/hosts"),
        ("/configuration?tab=systems", "/configuration/systems"),
        ("/configuration?tab=pools", "/configuration/pools"),
        ("/configuration?tab=operations", "/operations/custom"),
        ("/operations", "/operations/custom"),
        ("/administration?tab=users", "/administration/users"),
        ("/hosts", "/landscape?tab=hosts"),
        # The landscape's detail panel replaces the pages of a host and a system.
        ("/hosts/2", "/landscape?tab=hosts&host=2"),
        ("/systems/1", "/landscape?system=1"),
    ):
        assert (await browser.get(old)).headers["location"] == new, old


async def test_roles_of_the_pages(app, anonymous):
    await make_user(app, "view", "viewer")
    await sign_in(anonymous, "view")
    for path in ("/", "/landscape", "/activities", "/account"):
        assert (await anonymous.get(path)).status_code == 200, path
    for path in ("/configuration/hosts", "/operations/custom", "/administration"):
        assert (await anonymous.get(path)).status_code == 403, path
    page = (await anonymous.get("/")).text
    assert boot_of(page)["user"]["role"] == "viewer"
    assert 'href="/configuration"' not in page and 'href="/operations"' not in page


async def test_areas_have_a_navigation_on_the_left(browser):
    hosts = (await browser.get("/configuration/hosts")).text
    assert 'class="section-nav"' in hosts
    assert '<a href="/configuration/hosts" aria-current="page">Hosts</a>' in hosts
    assert '<a href="/configuration/systems" >Systems</a>' in hosts
    # Pages below a sub-area keep it marked.
    new = (await browser.get("/configuration/hosts/new")).text
    assert '<a href="/configuration/hosts" aria-current="page">Hosts</a>' in new
    operations = (await browser.get("/operations/custom")).text
    assert '<a href="/operations/custom" aria-current="page">Custom operations</a>' in operations
    assert '<a href="/operations/templates" >Operation templates</a>' in operations
    users = (await browser.get("/administration/users/new")).text
    assert '<a href="/administration/users" aria-current="page">Users</a>' in users
    assert '<a href="/administration" >General</a>' in users
    # Pages outside the areas have no such navigation.
    assert "section-nav" not in (await browser.get("/activities")).text


async def test_navigation_names_in_german(browser):
    await browser.get("/language/de")
    page = (await browser.get("/")).text
    for item in ("Übersicht", "Landschaft", "Aktivitäten", "Konfiguration", "Operationen"):
        assert f">{item}</a>" in page
    assert ">Administration</a>" in page
    await browser.get("/language/en")
    page = (await browser.get("/")).text
    for item in ("Overview", "Landscape", "Activities", "Configuration", "Operations"):
        assert f">{item}</a>" in page


async def test_language_switch_only_before_signing_in(anonymous):
    login = (await anonymous.get("/login")).text
    assert 'href="/language/de?next=/login"' in login
    await sign_in(anonymous)
    browser = anonymous
    page = (await browser.get("/activities?tab=logs&notice=pool_created")).text
    # Signed in, the language is chosen in "My account".
    assert 'href="/language/' not in page
    assert "Pool created." in page  # notices of the address are shown above the app
    # Without a chosen language, the cookie still decides.
    response = await browser.get("/language/de?next=/activities?tab=logs")
    assert response.headers["location"] == "/activities?tab=logs"
    assert boot_of((await browser.get("/")).text).get("language") == "de"
    unknown = await browser.get("/language/xx")
    assert unknown.status_code == 303


async def test_accept_language_header_selects_german(anonymous):
    page = await anonymous.get("/login", headers={"Accept-Language": "de-DE,de;q=0.9"})
    assert "Anmelden" in page.text


async def test_static_files_are_served(anonymous):
    response = await anonymous.get("/static/style.css")
    assert response.status_code == 200 and "text/css" in response.headers["content-type"]
    script = await anonymous.get("/static/ui.js")
    assert script.status_code == 200 and "data-confirm" in script.text
    for app_name in ("overview", "configuration", "administration", "account", "operations"):
        assert (await anonymous.get(f"/static/app/{app_name}.js")).status_code == 200


async def test_logo_and_favicon(anonymous):
    page = (await anonymous.get("/login")).text
    assert 'rel="icon"' in page and "/static/favicon.png" in page
    # One logo for light and one for dark colors; the style sheet shows the right one.
    assert "/static/oslo-logo.png" in page and "/static/oslo-logo-dark.png" in page
    # The small logo in the header, on every page.
    assert "/static/oslo-header.png" in page and "/static/oslo-header-dark.png" in page
    # Without a signed-in user the page follows the colors of the operating system.
    assert "<html lang=\"en\">" in page
    names = ("favicon.png", "apple-touch-icon.png", "oslo-logo.png", "oslo-logo-dark.png")
    for name in (*names, "oslo-header.png", "oslo-header-dark.png"):
        image = await anonymous.get(f"/static/{name}")
        assert image.status_code == 200 and image.headers["content-type"] == "image/png"


async def test_pages_have_a_strict_content_security_policy(browser):
    policy = (await browser.get("/")).headers["content-security-policy"]
    assert "default-src 'self'" in policy and "unsafe-inline" not in policy

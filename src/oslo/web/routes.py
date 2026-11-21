"""Web interface: the server renders sign-in, setup, the forced password change and the
shell of the React pages (frontend/), which load their data from the REST API.

Every page except sign-in and setup is a React app (app_page.html with start data). Old
addresses of the server-rendered pages lead to their React counterparts.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..catalog import Catalog
from ..connections import ClientFactory
from ..crypto import SecretBox
from ..filters import PARAMS as FILTER_PARAMS
from ..models import Activity, CustomOperation, Host, System, User
from ..operations import OperationRunner
from ..permissions import required_role
from ..settings import Settings
from ..users import (
    SESSION_COOKIE,
    SESSION_LIFETIME_SECONDS,
    Role,
    UserError,
    authenticate,
    create_session,
    create_user,
    has_role,
    session_user,
    set_password,
    user_count,
    verify_password,
)
from .i18n import LANGUAGE_COOKIE, LANGUAGES, all_texts, pick_language, translate

WEB_DIR = Path(__file__).parent

templates = Jinja2Templates(directory=WEB_DIR / "templates")


@dataclass
class AppContext:
    """What the request handlers need from the application."""

    settings: Settings
    secret_box: SecretBox
    clients: ClientFactory
    session_factory: async_sessionmaker[AsyncSession]
    runner: OperationRunner
    catalog: Catalog


class LoginRequiredError(Exception):
    def __init__(self, next_path: str) -> None:
        self.next_path = next_path


class SetupRequiredError(Exception):
    """No user exists yet; the first admin has to be created."""


class PasswordChangeRequiredError(Exception):
    """The user signed in with a start password and must choose a new one."""


# --- dependencies -----------------------------------------------------------------------


def get_context(request: Request) -> AppContext:
    return request.app.state.context


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with get_context(request).session_factory() as session:
        yield session


DbSessionDep = Annotated[AsyncSession, Depends(get_session)]


async def require_login(request: Request, session: DbSessionDep) -> User:
    """The signed-in user, if the page allows the user's role (see permissions.py)."""
    secret_key = get_context(request).settings.secret_key
    user = await session_user(session, secret_key, request.cookies.get(SESSION_COOKIE))
    if user is None:
        if await user_count(session) == 0:
            raise SetupRequiredError()
        path = request.url.path if request.method == "GET" else "/"
        raise LoginRequiredError(path)
    route = request.scope.get("route")
    template = getattr(route, "path", request.url.path)
    if user.must_change_password and not template.startswith("/account/password"):
        raise PasswordChangeRequiredError()
    needed = required_role(request.method, template)
    if not has_role(user, needed):
        raise HTTPException(403, f"Requires the role {needed}")
    request.state.user = user
    return user


def check_origin(request: Request) -> None:
    """Reject form posts from other sites, in addition to the SameSite cookie."""
    origin = request.headers.get("origin")
    if request.method == "POST" and origin and origin != "null":
        if urlsplit(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, "Cross-site request rejected")


Context = Annotated[AppContext, Depends(get_context)]
CurrentUser = Annotated[User, Depends(require_login)]
DbSession = Annotated[AsyncSession, Depends(get_session)]

public = APIRouter(dependencies=[Depends(check_origin)], include_in_schema=False)
pages = APIRouter(
    dependencies=[Depends(require_login), Depends(check_origin)], include_in_schema=False
)


# --- rendering --------------------------------------------------------------------------


def _language(request: Request) -> str:
    return pick_language(
        request.cookies.get(LANGUAGE_COOKIE), request.headers.get("accept-language")
    )


# Areas with a navigation on the left: path prefix -> title and [(href, text key)].
SECTIONS: dict[str, dict[str, Any]] = {
    "/configuration": {
        "title": "nav.configuration",
        "items": [
            ("/configuration/hosts", "tab.hosts"),
            ("/configuration/systems", "tab.systems"),
            ("/configuration/pools", "tab.pools"),
        ],
    },
    "/operations": {
        "title": "nav.operations",
        "items": [
            ("/operations/custom", "tab.custom_operations"),
            ("/operations/templates", "tpl.title"),
        ],
    },
    "/administration": {
        "title": "nav.administration",
        "items": [
            ("/administration", "tab.general"),
            ("/administration/users", "tab.users"),
            ("/administration/attention", "ov.attention"),
        ],
    },
}


def _section(path: str) -> dict[str, Any] | None:
    """The area of a path with the sub-area to mark (the longest matching item)."""
    for prefix, section in SECTIONS.items():
        if path == prefix or path.startswith(prefix + "/"):
            matching = [
                href for href, _ in section["items"] if path == href or path.startswith(href + "/")
            ]
            return section | {"current": max(matching, key=len, default=None)}
    return None


def render(request: Request, name: str, status_code: int = 200, **context: Any) -> HTMLResponse:
    language = _language(request)

    def t(key: str, **values: object) -> str:
        return translate(language, key, **values)

    query = request.query_params
    notice = error = None
    if query.get("notice"):
        values = {k[2:]: v for k, v in query.items() if k.startswith("n_")}
        notice = t(f"notice.{query['notice']}", **values)
    if query.get("error"):
        values = {k[2:]: v for k, v in query.items() if k.startswith("e_")}
        error = t(f"error.{query['error']}", **values)
    kept = [(k, v) for k, v in query.multi_items() if k == "tab" or k in FILTER_PARAMS]
    user = getattr(request.state, "user", None)
    context = {
        "t": t,
        "user": user,
        "can": lambda role: user is not None and has_role(user, Role(role)),
        "language": language,
        "languages": LANGUAGES,
        "path": request.url.path,
        "section": _section(request.url.path),
        # Current page for the language switch, without one-off notices.
        "here": request.url.path + (f"?{urlencode(kept)}" if kept else ""),
        "notice": notice,
        "error": error,
    } | context
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def redirect(path: str, **params: Any) -> RedirectResponse:
    """Redirect after a POST; ``params`` carry the notice or error to show."""
    query = urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    separator = "&" if "?" in path else "?"
    return RedirectResponse(f"{path}{separator}{query}" if query else path, status_code=303)


def _safe_next(target: str | None) -> str:
    """Only allow redirects to paths of this application."""
    if target and target.startswith("/") and not target.startswith(("//", "/\\")):
        return target
    return "/"


APP_DIR = WEB_DIR / "static" / "app"
_asset_versions: dict[str, tuple[float, str]] = {}


def asset_url(name: str) -> str:
    """URL of a built file of the browser interface with a content hash, so a new build is
    loaded at once even though the names stay the same."""
    path = APP_DIR / name
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return f"/static/app/{name}"
    cached = _asset_versions.get(name)
    if cached is None or cached[0] != mtime:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        cached = _asset_versions[name] = (mtime, digest)
    return f"/static/app/{name}?v={cached[1]}"


templates.env.globals["asset_url"] = asset_url


def _boot(request: Request, user: User, **extra: Any) -> dict[str, Any]:
    """Start data of a React page: language, all texts, the user and the time zone of
    schedules."""
    language = _language(request)
    return {
        "language": language,
        "texts": all_texts(language),
        "user": {"name": user.username, "role": user.role},
        "timezone": get_context(request).settings.timezone,
    } | extra


def app_page(request: Request, user: User, app: str, title_key: str, **extra: Any) -> HTMLResponse:
    """A page rendered by a React app (frontend/src/<app>); ``extra`` goes to its start
    data, e.g. the page of the app and an id."""
    return render(
        request,
        "app_page.html",
        title=translate(_language(request), title_key),
        app=app,
        boot=_boot(request, user, **extra),
        wide=True,
    )


async def _exists(session: AsyncSession, model: type, ident: int) -> None:
    if await session.get(model, ident) is None:
        raise HTTPException(404, "Not found")


# --- sign in, language ------------------------------------------------------------------


def _set_session_cookie(request: Request, response: Response, secret_key: str, user: User) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session(secret_key, user),
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )


@public.get("/login")
async def login_form(request: Request, session: DbSessionDep, next: str = "/") -> Response:
    if await user_count(session) == 0:
        return RedirectResponse("/setup", status_code=303)
    return render(request, "login.html", next=_safe_next(next), invalid=False)


@public.post("/login")
async def login(
    request: Request,
    context: Context,
    session: DbSessionDep,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/",
) -> Response:
    user = await authenticate(session, username, password)
    await session.commit()  # keep the counter of failed attempts
    if user is None:
        return render(
            request,
            "login.html",
            status_code=401,
            next=_safe_next(next),
            invalid=True,
            username=username,
        )
    target = "/account/password" if user.must_change_password else _safe_next(next)
    response = RedirectResponse(target, status_code=303)
    _set_session_cookie(request, response, context.settings.secret_key, user)
    return response


@public.post("/logout")
async def logout() -> Response:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@public.get("/setup")
async def setup_form(request: Request, session: DbSessionDep) -> Response:
    if await user_count(session) > 0:
        return RedirectResponse("/login", status_code=303)
    return render(request, "setup.html")


@public.post("/setup")
async def setup(
    request: Request,
    context: Context,
    session: DbSessionDep,
    code: Annotated[str, Form()] = "",
    username: Annotated[str, Form()] = "",
    display_name: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    password_repeat: Annotated[str, Form()] = "",
) -> Response:
    """Create the first admin with the one-time setup code printed at server start."""
    if await user_count(session) > 0:
        return RedirectResponse("/login", status_code=303)
    expected = request.app.state.setup_code or ""
    if not expected or not secrets.compare_digest(code.strip().encode(), expected.encode()):
        return redirect("/setup", error="setup_code")
    if password != password_repeat:
        return redirect("/setup", error="password_mismatch")
    try:
        user = await create_user(session, username, password, Role.ADMIN, display_name=display_name)
    except UserError as exc:
        await session.rollback()
        return redirect("/setup", error=exc.code)
    await session.commit()
    request.app.state.setup_code = None
    response = redirect("/", notice="setup_done")
    _set_session_cookie(request, response, context.settings.secret_key, user)
    return response


@public.get("/language/{code}")
async def set_language(code: str, next: str = "/") -> Response:
    response = RedirectResponse(_safe_next(next), status_code=303)
    if code in LANGUAGES:
        response.set_cookie(LANGUAGE_COOKIE, code, max_age=365 * 24 * 3600, samesite="lax")
    return response


# --- pages (React) ----------------------------------------------------------------------


def _go(path: str) -> Response:
    return RedirectResponse(path, status_code=303)


@pages.get("/")
async def overview(request: Request, user: CurrentUser) -> HTMLResponse:
    """Key figures, status matrix and "needs attention" (frontend/src/overview)."""
    return app_page(request, user, "overview", "nav.overview")


@pages.get("/landscape")
async def landscape(request: Request, user: CurrentUser) -> HTMLResponse:
    """Systems and hosts with the detail panel (frontend/src/landscape)."""
    return app_page(request, user, "landscape", "nav.landscape")


# The landscape's detail panel replaces the former pages of a system and a host.
@pages.get("/hosts")
async def hosts_redirect() -> Response:
    return _go("/landscape?tab=hosts")


@pages.get("/hosts/{host_id}")
async def host_redirect(host_id: int, session: DbSession) -> Response:
    await _exists(session, Host, host_id)
    return _go(f"/landscape?tab=hosts&host={host_id}")


@pages.get("/systems/{system_id}")
async def system_redirect(system_id: int, session: DbSession) -> Response:
    await _exists(session, System, system_id)
    return _go(f"/landscape?system={system_id}")


@pages.get("/activities")
async def activities(request: Request, user: CurrentUser, tab: str | None = None) -> HTMLResponse:
    page = "logs" if tab == "logs" else "activities"
    return app_page(request, user, "activities", "nav.activities", page=page)


@pages.get("/activities/{activity_id}")
async def activity_detail(
    request: Request, activity_id: int, session: DbSession, user: CurrentUser
) -> HTMLResponse:
    """Live view of an activity (frontend/src/activity)."""
    await _exists(session, Activity, activity_id)
    return app_page(request, user, "activity", "activity.title", activity_id=activity_id)


@pages.get("/configuration")
async def configuration(tab: str | None = None) -> Response:
    """The configuration starts with the hosts; ``tab`` keeps old links working."""
    if tab == "operations":
        return _go("/operations/custom")
    return _go(f"/configuration/{tab if tab in ('systems', 'pools') else 'hosts'}")


def _configuration(request: Request, user: User, page: str, **extra: Any) -> HTMLResponse:
    return app_page(request, user, "configuration", "nav.configuration", page=page, **extra)


@pages.get("/configuration/hosts")
async def configuration_hosts(request: Request, user: CurrentUser) -> HTMLResponse:
    return _configuration(request, user, "hosts")


@pages.get("/configuration/hosts/new")
async def new_host(request: Request, user: CurrentUser) -> HTMLResponse:
    return _configuration(request, user, "host_new")


@pages.get("/configuration/hosts/{host_id}")
async def configure_host(
    request: Request, host_id: int, session: DbSession, user: CurrentUser
) -> HTMLResponse:
    await _exists(session, Host, host_id)
    return _configuration(request, user, "host", id=host_id)


@pages.get("/configuration/systems")
async def configuration_systems(request: Request, user: CurrentUser) -> HTMLResponse:
    return _configuration(request, user, "systems")


@pages.get("/configuration/systems/unassigned")
async def configuration_unassigned(request: Request, user: CurrentUser) -> HTMLResponse:
    return _configuration(request, user, "unassigned")


@pages.get("/configuration/systems/new")
async def new_system(request: Request, user: CurrentUser) -> HTMLResponse:
    return _configuration(request, user, "system_new")


@pages.get("/configuration/systems/{system_id}")
async def configure_system(
    request: Request, system_id: int, session: DbSession, user: CurrentUser
) -> HTMLResponse:
    await _exists(session, System, system_id)
    return _configuration(request, user, "system", id=system_id)


@pages.get("/configuration/pools")
async def configuration_pools(request: Request, user: CurrentUser) -> HTMLResponse:
    return _configuration(request, user, "pools")


@pages.get("/configuration/pools/new")
async def new_pool(request: Request, user: CurrentUser) -> HTMLResponse:
    return _configuration(request, user, "pool_new")


@pages.get("/operations")
async def operations_area() -> Response:
    return _go("/operations/custom")


@pages.get("/operations/custom")
async def custom_operations(request: Request, user: CurrentUser) -> HTMLResponse:
    return app_page(request, user, "operations", "tab.custom_operations", page="customs")


@pages.get("/operations/custom/new")
async def new_custom_operation(request: Request, user: CurrentUser) -> HTMLResponse:
    return app_page(request, user, "operations", "custom.add", page="custom_new")


@pages.get("/operations/custom/{operation_id}")
async def custom_operation(
    request: Request, operation_id: int, session: DbSession, user: CurrentUser
) -> HTMLResponse:
    await _exists(session, CustomOperation, operation_id)
    return app_page(request, user, "operations", "custom.operation", page="custom", id=operation_id)


@pages.get("/operations/templates")
async def templates_page(request: Request, user: CurrentUser) -> HTMLResponse:
    """Operation templates: list and graph editor (frontend/src/templates)."""
    return app_page(request, user, "templates", "tpl.title")


def _administration(request: Request, user: User, page: str, **extra: Any) -> HTMLResponse:
    return app_page(request, user, "administration", "nav.administration", page=page, **extra)


@pages.get("/administration")
async def administration(request: Request, user: CurrentUser, tab: str | None = None) -> Response:
    if tab == "users":
        return _go("/administration/users")
    return _administration(request, user, "general")


@pages.get("/administration/users")
async def users_page(request: Request, user: CurrentUser) -> HTMLResponse:
    return _administration(request, user, "users")


@pages.get("/administration/users/new")
async def new_user(request: Request, user: CurrentUser) -> HTMLResponse:
    return _administration(request, user, "user_new")


@pages.get("/administration/users/{user_id}")
async def user_page(
    request: Request, user_id: int, session: DbSession, user: CurrentUser
) -> HTMLResponse:
    await _exists(session, User, user_id)
    return _administration(request, user, "user", id=user_id)


@pages.get("/administration/attention")
async def attention_rules(request: Request, user: CurrentUser) -> HTMLResponse:
    return _administration(request, user, "attention")


@pages.get("/account")
async def account(request: Request, user: CurrentUser) -> HTMLResponse:
    return app_page(request, user, "account", "account.title")


# --- password (server-rendered: also the first sign-in with a start password) ------------


@pages.get("/account/password")
async def password_form(request: Request, user: CurrentUser) -> HTMLResponse:
    return render(request, "password.html")


@pages.post("/account/password")
async def change_password(
    request: Request,
    context: Context,
    session: DbSession,
    user: CurrentUser,
    current: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    password_repeat: Annotated[str, Form()] = "",
) -> Response:
    if not verify_password(current, user.password_hash):
        return redirect("/account/password", error="password_wrong")
    if password != password_repeat:
        return redirect("/account/password", error="password_mismatch")
    if password == current:
        return redirect("/account/password", error="password_same")
    try:
        set_password(user, password)
    except UserError as exc:
        return redirect("/account/password", error=exc.code)
    await session.commit()
    # The change ended all sessions; this browser gets a new one.
    response = redirect("/account", notice="password_changed")
    _set_session_cookie(request, response, context.settings.secret_key, user)
    return response


# --- registration -----------------------------------------------------------------------


def register_web(app: FastAPI, context: AppContext) -> None:
    app.state.context = context

    @app.exception_handler(LoginRequiredError)
    async def to_login(_: Request, exc: LoginRequiredError) -> Response:
        return redirect("/login", next=exc.next_path if exc.next_path != "/" else None)

    @app.exception_handler(SetupRequiredError)
    async def to_setup(_: Request, __: SetupRequiredError) -> Response:
        return RedirectResponse("/setup", status_code=303)

    @app.exception_handler(PasswordChangeRequiredError)
    async def to_password(_: Request, __: PasswordChangeRequiredError) -> Response:
        return redirect("/account/password", notice="password_change_required")

    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    app.include_router(public)
    app.include_router(pages)

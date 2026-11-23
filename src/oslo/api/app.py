"""REST API of the orchestrator."""

# No "from __future__ import annotations" here: FastAPI resolves the annotations of the
# route functions at runtime, and they refer to names local to create_app.

import asyncio
import base64
import binascii
import json
import secrets
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import __version__, config_log
from ..attention import (
    DEFAULT_RULES,
    Exceptions,
    RuleError,
    load_exceptions,
    load_rules,
    save_exceptions,
    save_rules,
)
from ..bundle import BundleError, bootstrap_archive
from ..bundles import BundleStore, save_bundle
from ..bundles import activate as activate_stored_bundle
from ..bundles import load_settings as load_bundle_settings
from ..bundles import save_settings as save_bundle_settings
from ..catalog import Catalog, OperationDef
from ..connections import ClientFactory
from ..crypto import SecretBox
from ..customops import (
    CustomOperationError,
    ParameterError,
    parameter_values,
    save_operation,
    save_parameter,
)
from ..db import create_engine, create_session_factory, upgrade_database
from ..dependencies import DependencyError, set_dependencies
from ..discovery import DiscoveryError, discover_host
from ..events import change_events
from ..hosts import Connection, HostChangeError, update_connection
from ..landscape import landscape_snapshot, operation_row, overview_snapshot, read_processes
from ..models import (
    Activity,
    ApiToken,
    ConfigChange,
    CustomOperation,
    Host,
    HostTag,
    Instance,
    OperationBundle,
    OperationTemplate,
    PlatformSetting,
    Pool,
    Schedule,
    Sid,
    System,
    SystemTag,
    TrustedCertificate,
    User,
    activity_systems,
)
from ..operations import (
    DEFAULT_TIMEOUT_SECONDS,
    NotActiveError,
    NotAssignedError,
    OperationConflictError,
    OperationKind,
    OperationRunner,
    TargetNotFoundError,
    TargetType,
)
from ..permissions import required_role
from ..pools import UnknownPoolError, assign_pool
from ..schedules import ScheduleError, Scheduler, save_schedule
from ..settings import Settings
from ..status import refresh_system
from ..systems import (
    SystemChangeError,
    assign_instances,
    create_system,
    delete_system,
    suggest_name,
    suggestions,
    unassign_instance,
    update_system,
)
from ..tags import TagError, matches, parse_tags, replace_tags
from ..templates import TemplateError, save_template, steps_using, template_values
from ..tls import CertificateError, CertificateInfo, fetch_certificate, parse_pem
from ..transfer import TransferError, export_configuration, import_configuration
from ..users import (
    API_REQUEST_HEADER,
    SESSION_COOKIE,
    SESSION_LIFETIME_SECONDS,
    Role,
    UserError,
    create_token,
    create_user,
    get_preferences,
    get_setting,
    has_role,
    session_user,
    set_password,
    set_preferences,
    set_setting,
    token_user,
    update_user,
    user_count,
)
from ..web import AppContext, register_web
from ..web.i18n import LANGUAGE_COOKIE, all_texts, pick_language
from .schemas import (
    ActivityDetail,
    ActivityOut,
    AttentionExceptionsIn,
    AttentionRulesIn,
    BuildingBlocksOut,
    BundleSettingsIn,
    BundleUploadIn,
    CertificateOut,
    ConfigChangeOut,
    ConfigLogSettings,
    Credentials,
    CustomOperationIn,
    CustomOperationOut,
    DependenciesIn,
    DiscoveryOut,
    ExportIn,
    FavoritesIn,
    HostBatchCreate,
    HostCertificateOut,
    HostCreate,
    HostDetail,
    HostOut,
    HostUpdate,
    ImportIn,
    ImportReportOut,
    InstanceIds,
    InstanceListOut,
    InstanceOut,
    MassOperationIn,
    NewTokenOut,
    OperationOut,
    PasswordReset,
    PoolAssignment,
    PoolCreate,
    PoolOut,
    PoolUpdate,
    PreferencesIn,
    PreferencesOut,
    RefreshOut,
    RunIn,
    ScheduleIn,
    ScheduleOut,
    SidOut,
    StepOut,
    SystemCreate,
    SystemOut,
    SystemUpdate,
    TagsIn,
    TemplateIn,
    TemplateOut,
    TemplateRunIn,
    TokenCreate,
    TokenOut,
    TrustedCertificateIn,
    TrustedCertificateOut,
    UserCreate,
    UserOut,
    UserUpdate,
)

# User setting with the favorite operations of the template editor, comma separated.
FAVORITES = "favorites.operations"

# Status codes of SystemChangeError.code; everything else is 422.
_CHANGE_STATUS = {
    "unknown_system": 404,
    "unknown_stage": 422,
    "name_taken": 409,
    "assigned": 409,
    "busy": 409,
}


def _aware(value: datetime) -> datetime:
    """SQLite returns times without zone; they are stored in UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _systems_query():
    return (
        select(System)
        # Alphabetical regardless of case ("abc" next to "ABD", not after "Z").
        .order_by(func.lower(System.name), System.name)
        .options(
            selectinload(System.instances).selectinload(Instance.sid),
            selectinload(System.depends_on),
            selectinload(System.required_by),
            selectinload(System.pool),
        )
    )


CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)


def _touches_system(system_id: int, *, whole_system: bool = False):
    """Activities whose locked systems include the system (dependencies included).
    ``whole_system``: only operations on whole systems, not on single other instances."""
    locked = Activity.id.in_(
        select(activity_systems.c.activity_id).where(activity_systems.c.system_id == system_id)
    )
    condition = (Activity.system_id == system_id) | locked
    if whole_system:
        return condition & Activity.instance_id.is_(None)
    return condition


def create_app(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    poll_interval: float = 2.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
    run_scheduler: bool = False,
) -> FastAPI:
    """Build the application.

    ``transport`` replaces the network for connections to managed hosts; it is meant for
    tests and for running against the simulated landscape. ``poll_interval``, ``sleep``
    and ``clock`` control how running operations are tracked.
    """
    secret_box = SecretBox(settings.secret_key)
    clients = ClientFactory(secret_box, transport=transport)
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    catalog = Catalog()
    runner = OperationRunner(
        session_factory, clients, poll_interval=poll_interval, sleep=sleep, clock=clock
    )
    config_log.install()
    # The active OSLO operations bundle, which hosts download (bundles.py).
    bundle_store = BundleStore()
    runner.bundle_store = bundle_store
    # Starts due schedules every 30 seconds; tests call scheduler.tick() themselves.
    scheduler = Scheduler(session_factory, runner, catalog, ZoneInfo(settings.timezone))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await upgrade_database(engine, settings.database_url)
        await runner.recover_interrupted()
        async with session_factory() as session:
            await catalog.reload(session)
            await clients.load_trusted(session)
            await bundle_store.load(session)
            if await user_count(session) == 0:
                # One-time code for creating the first admin on the page /setup.
                code = "-".join(secrets.token_hex(3).upper() for _ in range(3))
                app.state.setup_code = code
                print(
                    f"No user exists yet. Open /setup and create the first admin with the "
                    f"setup code {code}",
                    file=sys.stderr,
                    flush=True,
                )
        scheduling = (
            asyncio.create_task(scheduler.run(), name="scheduler")
            if app.state.run_scheduler
            else None
        )
        yield
        if scheduling is not None:
            scheduling.cancel()
            await asyncio.gather(scheduling, return_exceptions=True)
        await runner.shutdown()
        await engine.dispose()

    bearer = HTTPBearer(auto_error=False)

    async def get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    Session = Annotated[AsyncSession, Depends(get_session)]

    async def require_user(
        request: Request,
        session: Session,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> User:
        """The user of the personal API token or, for the browser interface, of the session
        cookie, if the route allows the user's role.

        With the cookie, calls that change something must carry the header X-OSLO-Request:
        other sites cannot send it (no CORS), so they cannot act in the user's name.
        """
        if credentials is not None:
            user = await token_user(session, credentials.credentials)
            await session.commit()  # records when the token was last used
        else:
            user = await session_user(
                session, settings.secret_key, request.cookies.get(SESSION_COOKIE)
            )
            if user is not None:
                if request.method not in ("GET", "HEAD") and (
                    request.headers.get(API_REQUEST_HEADER) != "1"
                ):
                    raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing header X-OSLO-Request")
                if user.must_change_password:
                    raise HTTPException(
                        status.HTTP_403_FORBIDDEN, "Change the start password first"
                    )
        if user is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Missing, invalid or expired API token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        route = request.scope.get("route")
        needed = required_role(request.method, getattr(route, "path", request.url.path))
        if not has_role(user, needed):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires the role {needed}")
        request.state.user = user
        # Changes of this request are recorded in the configuration log in the user's name.
        config_log.set_actor(user.username)
        return user

    CurrentUser = Annotated[User, Depends(require_user)]

    app = FastAPI(
        title="OSLO",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # The interface description under /api/docs is readable without a token; it contains
    # no inventory data. Every call to a route needs a personal API token, and the role of
    # its user must allow the route (see permissions.py).
    api = FastAPI(
        title="OSLO API",
        version=__version__,
        dependencies=[Depends(require_user)],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    async def load_host(session: AsyncSession, host_id: int) -> Host:
        host = await session.scalar(
            select(Host)
            .where(Host.id == host_id)
            .options(
                selectinload(Host.instances).selectinload(Instance.sid),
                selectinload(Host.databases),
            )
        )
        if host is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Host not found")
        return host

    TagFilter = Annotated[
        list[str],
        Query(description='Only entries with one of these tags, e.g. "dev" or "sla=1"'),
    ]

    def parsed_tags(body: TagsIn) -> dict[str, str]:
        try:
            return parse_tags(body.tags)
        except TagError as exc:
            raise HTTPException(422, str(exc)) from exc

    @api.get("/hosts", response_model=list[HostOut])
    async def list_hosts(session: Session, tag: TagFilter = []) -> list[Host]:  # noqa: B006
        hosts = list(await session.scalars(select(Host).order_by(Host.name)))
        return [h for h in hosts if matches(h.tags, tag)] if tag else hosts

    @api.put("/hosts/{host_id}/tags", response_model=HostOut)
    async def set_host_tags(host_id: int, body: TagsIn, session: Session) -> Host:
        host = await load_host(session, host_id)
        replace_tags(host.tags, HostTag, parsed_tags(body))
        await session.commit()
        return host

    @api.post("/hosts", response_model=HostOut, status_code=status.HTTP_201_CREATED)
    async def create_host(body: HostCreate, session: Session) -> Host:
        if (body.username is None) != (body.password is None):
            raise HTTPException(
                422,
                "username and password must be given together",
            )
        host = Host(
            name=body.name,
            address=body.address or body.name,
            hostagent_port=body.hostagent_port,
            https=body.https,
            verify_tls=body.verify_tls,
            verify_hostname=body.verify_hostname,
            sapcontrol_port_offset=body.sapcontrol_port_offset,
            username=body.username,
            password_encrypted=secret_box.encrypt(body.password) if body.password else None,
        )
        host.agent_info = None  # nothing read yet; avoids a lazy load
        host.tags = []
        session.add(host)
        try:
            await session.commit()
        except IntegrityError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Host '{body.name}' already exists"
            ) from exc
        return host

    @api.post("/hosts/batch", response_model=list[HostOut], status_code=status.HTTP_201_CREATED)
    async def create_hosts(body: HostBatchCreate, session: Session) -> list[Host]:
        """Create several hosts at once (names separated by commas in the interface), all or
        none. Each host is reached under its name."""
        if (body.username is None) != (body.password is None):
            raise HTTPException(422, "username and password must be given together")
        names = [n.strip() for n in body.names if n.strip()]
        if not names:
            raise HTTPException(422, "No host name given")
        if any(len(n) > 255 or any(c.isspace() for c in n) for n in names):
            raise HTTPException(422, "Host names must not contain spaces")
        twice = sorted({n for n in names if [m.lower() for m in names].count(n.lower()) > 1})
        if twice:
            raise HTTPException(422, f"Given more than once: {', '.join(twice)}")
        existing = list(
            await session.scalars(
                select(Host.name).where(func.lower(Host.name).in_([n.lower() for n in names]))
            )
        )
        if existing:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Hosts already exist: {', '.join(sorted(existing))}"
            )
        hosts = []
        for name in names:
            host = Host(
                name=name,
                address=name,
                hostagent_port=body.hostagent_port,
                https=body.https,
                verify_tls=body.verify_tls,
                verify_hostname=body.verify_hostname,
                sapcontrol_port_offset=body.sapcontrol_port_offset,
                username=body.username,
                password_encrypted=secret_box.encrypt(body.password) if body.password else None,
            )
            host.agent_info = None
            host.tags = []
            session.add(host)
            hosts.append(host)
        await session.commit()
        return hosts

    @api.get("/hosts/{host_id}", response_model=HostDetail)
    async def get_host(host_id: int, session: Session) -> Host:
        return await load_host(session, host_id)

    @api.patch("/hosts/{host_id}", response_model=HostOut)
    async def update_host(host_id: int, body: HostUpdate, session: Session) -> Host:
        """Change connection data. Not checked against the host; run a discovery afterwards."""
        host = await load_host(session, host_id)
        try:
            await update_connection(session, host, Connection(**body.model_dump()))
        except HostChangeError as exc:
            await session.rollback()
            code = {"busy": 409, "host_exists": 409}.get(exc.code, 422)
            raise HTTPException(code, str(exc)) from exc
        await session.commit()
        return host

    @api.put("/hosts/{host_id}/credentials", status_code=status.HTTP_204_NO_CONTENT)
    async def set_host_credentials(host_id: int, body: Credentials, session: Session) -> Response:
        host = await load_host(session, host_id)
        host.username = body.username
        host.password_encrypted = secret_box.encrypt(body.password)
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @api.delete("/hosts/{host_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_host(host_id: int, session: Session) -> Response:
        host = await load_host(session, host_id)
        await session.delete(host)
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @api.post("/hosts/{host_id}/certificate", response_model=HostCertificateOut)
    async def host_certificate(host_id: int, session: Session) -> object:
        """Read the certificate the host agent shows, without checking it, so that an admin
        can compare its fingerprint and trust it."""
        host = await load_host(session, host_id)
        address, port = host.address, host.hostagent_port or 1129
        await session.rollback()  # end the read transaction while waiting for the host
        try:
            info = await app.state.fetch_certificate(address, port)
        except CertificateError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
        trusted_id = await session.scalar(
            select(TrustedCertificate.id).where(TrustedCertificate.fingerprint == info.fingerprint)
        )
        return {**certificate_fields(info), "pem": info.pem, "trusted_id": trusted_id}

    @api.post("/hosts/{host_id}/discover", response_model=DiscoveryOut)
    async def discover(host_id: int, session: Session) -> object:
        host = await load_host(session, host_id)
        try:
            result = await discover_host(session, host, clients)
        except DiscoveryError as exc:
            await session.commit()  # keep the "unreachable" marker on the host
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"Host agent could not be queried: {exc}"
            ) from exc
        await session.commit()
        return result

    async def load_system(session: AsyncSession, system_id: int) -> System:
        session.expire_all()
        system = await session.scalar(_systems_query().where(System.id == system_id))
        if system is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "System not found")
        return system

    async def change(session: AsyncSession, operation: Awaitable[object]) -> None:
        try:
            await operation
        except SystemChangeError as exc:
            await session.rollback()
            raise HTTPException(_CHANGE_STATUS.get(exc.code, 422), str(exc)) from exc
        except UnknownPoolError as exc:
            await session.rollback()
            raise HTTPException(422, str(exc)) from exc
        await session.commit()

    @api.get("/instances", response_model=list[InstanceListOut])
    async def list_instances(
        session: Session,
        unassigned: Annotated[
            bool, Query(description="Only instances that belong to no system")
        ] = False,
    ) -> list[dict[str, object]]:
        query = select(Instance).options(selectinload(Instance.sid)).order_by(Instance.id)
        if unassigned:
            query = query.where(Instance.system_id.is_(None))
        proposed = await suggestions(session)
        result = []
        for instance in await session.scalars(query):
            data = InstanceOut.model_validate(instance).model_dump()
            suggestion = proposed.get(instance.id)
            data["suggested_system_id"] = suggestion.id if suggestion else None
            result.append(data)
        return result

    @api.get("/sids", response_model=list[SidOut])
    async def list_sids(session: Session) -> list[Sid]:
        return list(await session.scalars(select(Sid).order_by(Sid.name)))

    @api.put("/sids/{sid_id}/credentials", status_code=status.HTTP_204_NO_CONTENT)
    async def set_sid_credentials(sid_id: int, body: Credentials, session: Session) -> Response:
        """Credentials of <sid>adm for the sapstartsrv of the instances of this SID."""
        sid = await session.get(Sid, sid_id)
        if sid is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "SID not found")
        sid.username = body.username
        sid.password_encrypted = secret_box.encrypt(body.password)
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @api.get("/systems", response_model=list[SystemOut])
    async def list_systems(session: Session, tag: TagFilter = []) -> list[System]:  # noqa: B006
        systems = list(await session.scalars(_systems_query()))
        return [s for s in systems if matches(s.tags, tag)] if tag else systems

    @api.put("/systems/{system_id}/tags", response_model=SystemOut)
    async def set_system_tags(system_id: int, body: TagsIn, session: Session) -> System:
        system = await load_system(session, system_id)
        replace_tags(system.tags, SystemTag, parsed_tags(body))
        await session.commit()
        return await load_system(session, system_id)

    @api.post("/systems/{system_id}/refresh", response_model=RefreshOut)
    async def refresh_system_route(system_id: int, session: Session) -> dict[str, object]:
        """Read the status of all instances of the system once. Creates no activity."""
        await load_system(session, system_id)
        warnings = await refresh_system(session, system_id, clients)
        await session.commit()
        return {"system": await load_system(session, system_id), "warnings": warnings}

    @api.post("/systems", response_model=SystemOut, status_code=status.HTTP_201_CREATED)
    async def create_system_route(body: SystemCreate, session: Session) -> System:
        """Create a system from unassigned instances, which may belong to several SIDs."""
        created: list[System] = []

        async def create() -> None:
            created.append(
                await create_system(
                    session,
                    body.name,
                    body.instance_ids,
                    pool_id=body.pool_id,
                    description=body.description,
                )
            )

        await change(session, create())
        return await load_system(session, created[0].id)

    @api.get("/systems/suggestion")
    async def system_suggestion(
        session: Session,
        instance_ids: Annotated[list[int], Query(max_length=200)] = [],  # noqa: B006
    ) -> dict[str, str]:
        """Name proposal for a new system from these instances (the SID of the
        application instances)."""
        rows = list(
            await session.scalars(
                select(Instance)
                .where(Instance.id.in_(instance_ids))
                .options(selectinload(Instance.sid))
            )
        )
        return {"name": suggest_name(rows) if rows else ""}

    @api.get("/systems/{system_id}", response_model=SystemOut)
    async def get_system(system_id: int, session: Session) -> System:
        return await load_system(session, system_id)

    @api.patch("/systems/{system_id}", response_model=SystemOut)
    async def update_system_route(system_id: int, body: SystemUpdate, session: Session) -> System:
        stage = body.stage if "stage" in body.model_fields_set else ...
        await change(session, update_system(session, system_id, body.name, body.description, stage))
        return await load_system(session, system_id)

    @api.delete("/systems/{system_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_system_route(system_id: int, session: Session) -> Response:
        """Delete a system. Its instances stay in the inventory, unassigned."""
        await change(session, delete_system(session, system_id))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @api.post("/systems/{system_id}/instances", response_model=SystemOut)
    async def assign_instances_route(system_id: int, body: InstanceIds, session: Session) -> System:
        await change(session, assign_instances(session, system_id, body.instance_ids))
        return await load_system(session, system_id)

    @api.delete(
        "/systems/{system_id}/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT
    )
    async def unassign_instance_route(
        system_id: int, instance_id: int, session: Session
    ) -> Response:
        await change(session, unassign_instance(session, system_id, instance_id))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @api.put("/systems/{system_id}/dependencies", response_model=SystemOut)
    async def set_system_dependencies(
        system_id: int, body: DependenciesIn, session: Session
    ) -> System:
        """Replace the systems this system depends on, e.g. its database system."""
        if await session.get(System, system_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "System not found")
        try:
            await set_dependencies(session, system_id, set(body.depends_on))
        except DependencyError as exc:
            raise HTTPException(422, str(exc)) from exc
        await session.commit()
        return await load_system(session, system_id)

    SystemOperationName = Literal["start", "stop", "restart"]
    # Instances also: the instance agent (sapstartsrv) through the host agent.
    OperationName = Literal["start", "stop", "restart", "register", "unregister", "reregister"]

    @api.get("/pools", response_model=list[PoolOut])
    async def list_pools(session: Session) -> list[Pool]:
        query = select(Pool).order_by(Pool.name).options(selectinload(Pool.systems))
        return list(await session.scalars(query))

    @api.post("/pools", response_model=PoolOut, status_code=status.HTTP_201_CREATED)
    async def create_pool(body: PoolCreate, session: Session) -> Pool:
        pool = Pool(name=body.name.strip(), description=body.description, systems=[])
        session.add(pool)
        try:
            await session.commit()
        except IntegrityError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Pool '{body.name}' already exists"
            ) from exc
        return pool

    async def load_pool(session: AsyncSession, pool_id: int) -> Pool:
        pool = await session.scalar(
            select(Pool).where(Pool.id == pool_id).options(selectinload(Pool.systems))
        )
        if pool is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Pool not found")
        return pool

    @api.get("/pools/{pool_id}", response_model=PoolOut)
    async def get_pool(pool_id: int, session: Session) -> Pool:
        return await load_pool(session, pool_id)

    @api.patch("/pools/{pool_id}", response_model=PoolOut)
    async def update_pool(pool_id: int, body: PoolUpdate, session: Session) -> Pool:
        """Rename a pool or change its description; its systems stay."""
        pool = await load_pool(session, pool_id)
        if body.name is not None:
            name = body.name.strip()
            if not name:
                raise HTTPException(422, "The name must not be empty")
            taken = await session.scalar(
                select(Pool.id).where(Pool.name == name, Pool.id != pool_id)
            )
            if taken is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Pool '{name}' already exists")
            pool.name = name
        if "description" in body.model_fields_set:
            pool.description = (body.description or "").strip() or None
        await session.commit()
        return await load_pool(session, pool_id)

    @api.delete("/pools/{pool_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_pool(pool_id: int, session: Session) -> Response:
        pool = await session.get(Pool, pool_id)
        if pool is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Pool not found")
        await session.delete(pool)
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    def certificate_fields(info: CertificateInfo) -> dict[str, object]:
        return {
            "subject": info.subject,
            "issuer": info.issuer,
            "fingerprint": info.fingerprint,
            "not_before": info.not_before,
            "not_after": info.not_after,
            "self_signed": info.self_signed,
            "expired": info.expired(),
        }

    def trusted_out(cert: TrustedCertificate) -> dict[str, object]:
        info = CertificateInfo(
            pem=cert.pem,
            subject=cert.subject,
            issuer=cert.issuer,
            fingerprint=cert.fingerprint,
            not_before=_aware(cert.not_before),
            not_after=_aware(cert.not_after),
        )
        return {
            **certificate_fields(info),
            "id": cert.id,
            "name": cert.name,
            "pem": cert.pem,
            "created_at": cert.created_at,
            "created_by": cert.created_by,
        }

    @api.get("/trusted-certificates", response_model=list[TrustedCertificateOut])
    async def list_trusted_certificates(session: Session) -> list[dict[str, object]]:
        certs = await session.scalars(
            select(TrustedCertificate).order_by(TrustedCertificate.name, TrustedCertificate.id)
        )
        return [trusted_out(cert) for cert in certs]

    @api.post("/trusted-certificates/check", response_model=CertificateOut)
    async def check_trusted_certificate(body: TrustedCertificateIn) -> dict[str, object]:
        """Show what a PEM text contains before it is added."""
        try:
            return certificate_fields(parse_pem(body.pem))
        except CertificateError as exc:
            raise HTTPException(422, str(exc)) from exc

    @api.post(
        "/trusted-certificates",
        response_model=TrustedCertificateOut,
        status_code=status.HTTP_201_CREATED,
    )
    async def add_trusted_certificate(
        body: TrustedCertificateIn, session: Session, user: CurrentUser
    ) -> dict[str, object]:
        try:
            info = parse_pem(body.pem)
        except CertificateError as exc:
            raise HTTPException(422, str(exc)) from exc
        existing = await session.scalar(
            select(TrustedCertificate).where(TrustedCertificate.fingerprint == info.fingerprint)
        )
        if existing is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This certificate is already trusted as '{existing.name}'",
            )
        cert = TrustedCertificate(
            name=body.name.strip(),
            pem=info.pem,
            subject=info.subject,
            issuer=info.issuer,
            fingerprint=info.fingerprint,
            not_before=info.not_before,
            not_after=info.not_after,
            created_at=datetime.now(UTC),
            created_by=user.username,
        )
        session.add(cert)
        await session.commit()
        await clients.load_trusted(session)
        return trusted_out(cert)

    @api.delete("/trusted-certificates/{cert_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_trusted_certificate(cert_id: int, session: Session) -> Response:
        cert = await session.get(TrustedCertificate, cert_id)
        if cert is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Certificate not found")
        await session.delete(cert)
        await session.commit()
        await clients.load_trusted(session)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @api.put("/systems/{system_id}/pool", response_model=SystemOut)
    async def set_system_pool(system_id: int, body: PoolAssignment, session: Session) -> System:
        """Put a system into a pool; ``null`` takes it out."""
        if await session.get(System, system_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "System not found")
        try:
            await assign_pool(session, system_id, body.pool_id)
        except UnknownPoolError as exc:
            raise HTTPException(422, str(exc)) from exc
        await session.commit()
        return await load_system(session, system_id)

    Timeout = Annotated[
        int,
        Query(ge=10, le=7200, description="Seconds to wait for the target state"),
    ]

    async def submit(submission: Awaitable[Activity]) -> Activity:
        try:
            return await submission
        except TargetNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except (OperationConflictError, NotAssignedError) as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    @api.post(
        "/instances/{instance_id}/{operation}",
        response_model=ActivityOut,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def operate_instance(
        instance_id: int,
        operation: OperationName,
        session: Session,
        user: CurrentUser,
        timeout: Timeout = DEFAULT_TIMEOUT_SECONDS,
    ) -> Activity:
        """Start, stop or restart one instance through the host agent."""
        kind = OperationKind(operation.upper())
        return await submit(
            runner.submit_instance(session, instance_id, kind, timeout, user.username)
        )

    @api.post(
        "/systems/{system_id}/{operation}",
        response_model=ActivityOut,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def operate_system(
        system_id: int,
        operation: SystemOperationName,
        session: Session,
        user: CurrentUser,
        timeout: Timeout = DEFAULT_TIMEOUT_SECONDS,
    ) -> Activity:
        """Start, stop or restart a whole system in the order of the start priorities."""
        kind = OperationKind(operation.upper())
        return await submit(runner.submit_system(session, system_id, kind, timeout, user.username))

    @api.get("/activities", response_model=list[ActivityOut])
    async def list_activities(
        session: Session,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        system_id: int | None = None,
        instance_id: int | None = None,
        host_id: int | None = None,
    ) -> list[Activity]:
        """Newest first. ``system_id``: activities that touched the system, also through
        dependencies or as part of a mass operation; ``instance_id``: those of the instance
        and of its system; ``host_id``: host operations of the host."""
        query = select(Activity).order_by(Activity.id.desc()).limit(limit)
        if instance_id is not None:
            instance = await session.get(Instance, instance_id)
            if instance is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Instance not found")
            touched = Activity.instance_id == instance_id
            if instance.system_id is not None:
                touched = touched | _touches_system(instance.system_id, whole_system=True)
            query = query.where(touched)
        if system_id is not None:
            query = query.where(_touches_system(system_id))
        if host_id is not None:
            query = query.where(Activity.host_id == host_id)
        return list(await session.scalars(query))

    @api.get("/steps", response_model=list[StepOut])
    async def list_steps(
        session: Session,
        limit: Annotated[int, Query(ge=1, le=1000)] = 300,
        activity_id: int | None = None,
    ) -> list[dict[str, object]]:
        """The activities that do the work themselves, newest first: a single operation is one
        step, a mass operation or an operation template has one per target and step. Their
        parents, which only coordinate, are not listed. ``activity_id``: only the steps of
        that (top-level) activity. Each step names its top-level activity (``activity_id``)."""
        containers = Activity.target_type.in_([TargetType.MASS, TargetType.TEMPLATE]) | (
            Activity.kind == OperationKind.TEMPLATE
        )
        parents = dict((await session.execute(select(Activity.id, Activity.parent_id))).all())

        def root(activity_id: int) -> int:
            seen: set[int] = set()
            while parents.get(activity_id) is not None and activity_id not in seen:
                seen.add(activity_id)
                activity_id = parents[activity_id]  # type: ignore[assignment]
            return activity_id

        query = select(Activity).where(~containers).order_by(Activity.id.desc())
        if activity_id is not None:
            if activity_id not in parents:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Activity not found")
            members = [i for i in parents if root(i) == activity_id]
            query = query.where(Activity.id.in_(members))
        rows = list(await session.scalars(query.limit(limit)))
        return [
            {
                "id": a.id,
                "activity_id": root(a.id),
                "kind": a.kind,
                "target_type": a.target_type,
                "target_label": a.target_label,
                "status": a.status,
                "requested_at": a.requested_at,
                "started_at": a.started_at,
                "finished_at": a.finished_at,
            }
            for a in rows
        ]

    # --- import and export (Administration → Import/Export) ---------------------------------

    @api.post("/export")
    async def export(body: ExportIn, session: Session) -> Response:
        """The chosen parts of the configuration as a JSON file (admin)."""
        try:
            data = await export_configuration(
                session, secret_box, body.parts, password=body.password
            )
        except TransferError as exc:
            raise HTTPException(422, {"code": exc.code, "message": str(exc)}) from exc
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
        return Response(
            json.dumps(data, indent=2, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="oslo-export-{stamp}.json"'},
        )

    @api.post("/import", response_model=ImportReportOut)
    async def import_(body: ImportIn, session: Session, user: CurrentUser) -> dict[str, object]:
        """Import an export (admin). Without ``apply`` it is a preview that keeps nothing."""
        try:
            report = await import_configuration(
                session,
                secret_box,
                catalog,
                user,
                body.data,
                mode=body.mode,
                password=body.password,
                zone=scheduler.zone,
                now=scheduler.now(),
            )
        except TransferError as exc:
            await session.rollback()
            raise HTTPException(422, {"code": exc.code, "message": str(exc)}) from exc
        if body.apply:
            counts = {k: v for k, v in report.counts().items() if v}
            config_log.record(
                session,
                "import",
                None,
                "Import",
                {k: [None, v] for k, v in counts.items()},
                action="imported",
            )
            await session.commit()
        else:
            await session.rollback()
        # The catalog and the trusted certificates follow what is in the database now.
        await catalog.reload(session)
        await clients.load_trusted(session)
        return {"applied": body.apply, "counts": report.counts(), "items": report.items}

    # --- OSLO operations bundle (Administration → OSLO operations) ---------------------------

    def bundle_out(row: OperationBundle) -> dict[str, object]:
        return {
            "id": row.id,
            "version": row.version,
            "sha256": row.sha256,
            "active": row.active,
            "uploaded_at": row.uploaded_at,
            "uploaded_by": row.uploaded_by,
            "files": sorted(json.loads(row.files)),
        }

    @api.get("/bundle-status")
    async def bundle_status() -> dict[str, object]:
        """The version of the active bundle, to compare the hosts with (every role)."""
        return {"active_version": bundle_store.version}

    @api.get("/bundles")
    async def list_bundles(session: Session) -> dict[str, object]:
        """Settings, the active and the earlier bundles (admin)."""
        rows = await session.scalars(select(OperationBundle).order_by(OperationBundle.id.desc()))
        return {
            "settings": await load_bundle_settings(session),
            "bundles": [bundle_out(row) for row in rows],
        }

    @api.put("/bundles/settings")
    async def put_bundle_settings(body: BundleSettingsIn, session: Session) -> dict[str, str]:
        """Public key of the bundle signature, address of OSLO for the hosts (admin)."""
        try:
            saved = await save_bundle_settings(
                session, body.public_key, body.base_url, body.ca_path
            )
        except BundleError as exc:
            raise HTTPException(422, str(exc)) from exc
        await session.commit()
        await bundle_store.load(session)
        return saved

    @api.post("/bundles", status_code=status.HTTP_201_CREATED)
    async def upload_bundle(
        body: BundleUploadIn, session: Session, user: CurrentUser
    ) -> dict[str, object]:
        """Upload a signed bundle (base64) and make it the active one (admin)."""
        try:
            data = base64.b64decode(body.data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(422, "The file is not base64") from exc
        try:
            row, _ = await save_bundle(session, data, user.username)
        except BundleError as exc:
            await session.rollback()
            raise HTTPException(422, str(exc)) from exc
        await session.commit()
        await bundle_store.load(session)
        return bundle_out(row)

    @api.post("/bundles/{bundle_id}/activate")
    async def activate_bundle(bundle_id: int, session: Session) -> dict[str, object]:
        """Offer an earlier bundle again, e.g. to go back (admin)."""
        row = await session.get(OperationBundle, bundle_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Bundle not found")
        await activate_stored_bundle(session, row)
        await session.commit()
        await bundle_store.load(session)
        return bundle_out(row)

    @api.get("/bundles/bootstrap")
    async def bootstrap(session: Session) -> Response:
        """The package for the first installation on a host (admin)."""
        settings_ = await load_bundle_settings(session)
        active = bundle_store.active
        if active is None:
            raise HTTPException(409, "Upload a bundle first")
        if not settings_["public_key"] or not settings_["base_url"]:
            raise HTTPException(409, "Enter the public key and the address of OSLO first")
        data = bootstrap_archive(
            active.payload,
            active.signature,
            settings_["public_key"],
            settings_["base_url"],
            settings_["ca_path"],
        )
        name = f"oslo-bootstrap-{active.version}.tar.gz"
        return Response(
            data,
            media_type="application/gzip",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    # --- configuration log (Activities → Configuration) -------------------------------------

    @api.get("/config-changes", response_model=list[ConfigChangeOut])
    async def config_changes(
        session: Session,
        user: CurrentUser,
        limit: Annotated[int, Query(ge=1, le=1000)] = 300,
        object_type: str | None = None,
        object_id: int | None = None,
        username: str | None = None,
        days: Annotated[int | None, Query(ge=1)] = None,
    ) -> list[ConfigChange]:
        """The newest entries of the configuration log. Changes of users only for admins."""
        query = select(ConfigChange).order_by(ConfigChange.id.desc()).limit(limit)
        if object_type:
            query = query.where(ConfigChange.object_type == object_type)
        if object_id is not None:
            query = query.where(ConfigChange.object_id == object_id)
        if username:
            query = query.where(ConfigChange.username == username)
        if days is not None:
            query = query.where(ConfigChange.changed_at >= datetime.now(UTC) - timedelta(days=days))
        if not has_role(user, Role.ADMIN):
            query = query.where(ConfigChange.object_type != "user")
        return list(await session.scalars(query))

    @api.get("/config-log-settings", response_model=ConfigLogSettings)
    async def get_config_log_settings(session: Session) -> dict[str, int]:
        return {"retention_days": await config_log.retention_days(session)}

    @api.put("/config-log-settings", response_model=ConfigLogSettings)
    async def put_config_log_settings(body: ConfigLogSettings, session: Session) -> dict[str, int]:
        """How long the configuration log keeps its entries (admin)."""
        row = await session.get(PlatformSetting, config_log.RETENTION_KEY)
        if row is None:
            session.add(
                PlatformSetting(key=config_log.RETENTION_KEY, value=str(body.retention_days))
            )
        else:
            row.value = str(body.retention_days)
        await session.commit()
        return {"retention_days": body.retention_days}

    @api.get("/server-time")
    async def server_time() -> dict[str, object]:
        """Time of the server and the time zone of schedules, as Operations → Schedules
        shows them."""
        return {"now": scheduler.now(), "timezone": settings.timezone}

    @api.get("/platform")
    async def platform() -> dict[str, object]:
        """Version and settings of the platform (admin)."""
        return {
            "version": __version__,
            "database": settings.database_url.split(":", 1)[0],
            "session_hours": SESSION_LIFETIME_SECONDS // 3600,
            "timezone": settings.timezone,
        }

    @api.get("/activities/{activity_id}", response_model=ActivityDetail)
    async def get_activity(activity_id: int, session: Session) -> Activity:
        activity = await session.scalar(
            select(Activity)
            .where(Activity.id == activity_id)
            .options(selectinload(Activity.entries), selectinload(Activity.children))
        )
        if activity is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Activity not found")
        return activity

    # --- operation templates --------------------------------------------------------------

    async def template_out(session: AsyncSession, template: OperationTemplate) -> dict:
        known = {op.key: op for op in catalog.steps()}
        steps = []
        for step in template.steps:
            target_type = step.target_type
            ids = json.loads(step.targets or "[]")
            labels = await target_labels(session, target_type, ids) if ids else {}
            steps.append(
                {
                    "position": step.position,
                    "operation": step.operation,
                    "name": (known[step.operation].name or step.operation)
                    if step.operation in known
                    else None,
                    "target_type": target_type,
                    "targets": ids,
                    "target_labels": [{"id": i, "label": labels.get(i)} for i in ids],
                    "after": json.loads(step.after or "[]"),
                    "parameters": json.loads(step.parameters or "{}"),
                    "ask": json.loads(step.ask or "[]"),
                    "on_error": step.on_error,
                }
            )
        return {
            "id": template.id,
            "key": template.key,
            "name": template.name,
            "description": template.description,
            "selection": template.target or None,
            "role": template.role,
            "valid": catalog.get(template.key) is not None,
            "steps": steps,
        }

    async def target_labels(session: AsyncSession, target_type: str, ids: list[int]) -> dict:
        if target_type == "SYSTEM":
            rows = await session.execute(select(System.id, System.name).where(System.id.in_(ids)))
            return dict(rows.all())
        if target_type == "HOST":
            rows = await session.execute(select(Host.id, Host.name).where(Host.id.in_(ids)))
            return dict(rows.all())
        instances = await session.scalars(
            select(Instance)
            .where(Instance.id.in_(ids))
            .options(selectinload(Instance.sid), selectinload(Instance.host))
        )
        return {i.id: f"{i.label} ({i.host.name})" for i in instances}

    async def load_template(session: AsyncSession, template_id: int) -> OperationTemplate:
        template = await session.get(OperationTemplate, template_id)
        if template is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
        return template

    async def save_template_body(
        session: AsyncSession, template: OperationTemplate | None, body: TemplateIn
    ) -> dict[str, object]:
        try:
            template = await save_template(
                session,
                catalog,
                template,
                key=body.key,
                name=body.name,
                description=body.description,
                role=body.role,
                steps=[step.model_dump() for step in body.steps],
            )
        except TemplateError as exc:
            await session.rollback()
            code = 409 if exc.code == "template_key_taken" else 422
            raise HTTPException(code, {"code": exc.code, "message": str(exc)}) from exc
        await session.commit()
        await catalog.reload(session)
        return await template_out(session, template)

    @api.get("/templates", response_model=list[TemplateOut])
    async def list_templates(session: Session) -> list[dict[str, object]]:
        rows = await session.scalars(select(OperationTemplate).order_by(OperationTemplate.name))
        return [await template_out(session, t) for t in rows]

    @api.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
    async def create_template(body: TemplateIn, session: Session) -> dict[str, object]:
        """Define an operation template (admin): a chain of operations run one after another."""
        return await save_template_body(session, None, body)

    @api.get("/templates/{template_id}", response_model=TemplateOut)
    async def get_template(template_id: int, session: Session) -> dict[str, object]:
        return await template_out(session, await load_template(session, template_id))

    @api.put("/templates/{template_id}", response_model=TemplateOut)
    async def update_template(
        template_id: int, body: TemplateIn, session: Session
    ) -> dict[str, object]:
        return await save_template_body(session, await load_template(session, template_id), body)

    @api.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_template(template_id: int, session: Session) -> Response:
        template = await load_template(session, template_id)
        planned = await session.scalar(
            select(Schedule.id).where(Schedule.operation == template.key).limit(1)
        )
        if planned is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "The template is still scheduled")
        await session.delete(template)
        await session.commit()
        await catalog.reload(session)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @api.post(
        "/templates/{template_id}/run",
        response_model=ActivityOut,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def run_template(
        template_id: int, body: TemplateRunIn, session: Session, user: CurrentUser
    ) -> Activity:
        """Start a template: one with fixed targets as it is, a dialog template on
        ``target_ids`` (its selection)."""
        template = await load_template(session, template_id)
        definition = catalog.get(template.key)
        if definition is None or definition.template is None:
            raise HTTPException(422, "A step uses an operation that no longer exists")
        if not has_role(user, definition.role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires the role {definition.role}")
        return await start_template(session, user, definition, body.target_ids, body.parameters)

    async def start_template(
        session: AsyncSession,
        user: User,
        definition: OperationDef,
        target_ids: list[int],
        parameters: dict[str, str | int | bool],
    ) -> Activity:
        assert definition.template is not None
        try:
            values = template_values(definition.template, parameters)
        except ParameterError as exc:
            raise HTTPException(422, str(exc)) from exc
        try:
            return await submit(
                runner.submit_template(
                    session, definition.template, target_ids, values, user.username
                )
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @api.get("/templates-blocks", response_model=BuildingBlocksOut)
    async def building_blocks(session: Session, user: CurrentUser) -> dict[str, list]:
        """For the template editor: every operation a step may use, the 5 used most in the
        last 90 days (by all users) and the user's favorites."""
        since = datetime.now(UTC) - timedelta(days=90)
        rows = await session.execute(
            select(Activity.kind, Activity.options)
            .where(Activity.requested_at >= since, Activity.target_type != TargetType.MASS)
            .order_by(Activity.id.desc())
            .limit(20000)
        )
        by_id = {op.custom.id: op.key for op in catalog.steps() if op.custom}
        counts: dict[str, int] = {}
        for kind, options in rows:
            if kind == OperationKind.TEMPLATE:
                continue
            key = kind.lower()
            if kind == OperationKind.CUSTOM:
                custom = json.loads(options or "{}").get("custom") or {}
                key = by_id.get(custom.get("id"))
            if key and catalog.get(key) is not None:
                counts[key] = counts.get(key, 0) + 1
        top = sorted(counts, key=lambda k: (-counts[k], k))[:5]
        favorites = (await get_setting(session, user, FAVORITES) or "").split(",")
        return {
            "top": top,
            "favorites": [f for f in favorites if f],
            "operations": [operation_row(op) for op in catalog.steps()],
        }

    @api.get("/me/preferences", response_model=PreferencesOut)
    async def get_my_preferences(session: Session, user: CurrentUser) -> dict[str, str]:
        return await get_preferences(session, user)

    @api.put("/me/preferences", response_model=PreferencesOut)
    async def set_my_preferences(
        body: PreferencesIn, session: Session, user: CurrentUser
    ) -> dict[str, str]:
        """Language and color scheme of the interface ("My account")."""
        await set_preferences(
            session, user, language=body.language, theme=body.theme, time=body.time
        )
        await session.commit()
        return await get_preferences(session, user)

    @api.put("/me/favorites", response_model=BuildingBlocksOut)
    async def save_favorites(
        body: FavoritesIn, session: Session, user: CurrentUser
    ) -> dict[str, list]:
        """Operations the user marked as favorites in the template editor."""
        known = [k for k in dict.fromkeys(body.operations) if catalog.get(k) is not None]
        await set_setting(session, user, FAVORITES, ",".join(known))
        await session.commit()
        return await building_blocks(session, user)

    # --- schedules ------------------------------------------------------------------------

    def schedule_out(schedule: Schedule, last_status: str | None = None) -> dict[str, object]:
        return {
            "id": schedule.id,
            "name": schedule.name,
            "operation": schedule.operation,
            "target_type": schedule.target_type,
            "target_ids": json.loads(schedule.target_ids),
            "parameters": json.loads(schedule.parameters or "{}"),
            "recurrence": schedule.recurrence,
            "run_at": _aware(schedule.run_at) if schedule.run_at else None,
            "time_of_day": schedule.time_of_day,
            "weekdays": schedule.weekdays,
            "interval_minutes": schedule.interval_minutes,
            "enabled": schedule.enabled,
            "created_by": schedule.created_by,
            "created_at": _aware(schedule.created_at),
            "next_run_at": _aware(schedule.next_run_at) if schedule.next_run_at else None,
            "last_run_at": _aware(schedule.last_run_at) if schedule.last_run_at else None,
            "last_activity_id": schedule.last_activity_id,
            "last_status": last_status,
            "last_error": schedule.last_error,
        }

    async def last_statuses(session: AsyncSession, schedules: list[Schedule]) -> dict[int, str]:
        """Status of the last run of each schedule, by activity id."""
        ids = {s.last_activity_id for s in schedules if s.last_activity_id}
        if not ids:
            return {}
        rows = await session.execute(
            select(Activity.id, Activity.status).where(Activity.id.in_(ids))
        )
        return {activity_id: str(state) for activity_id, state in rows}

    async def save_schedule_body(
        session: AsyncSession, schedule: Schedule | None, body: ScheduleIn, user: User
    ) -> dict[str, object]:
        try:
            schedule = await save_schedule(
                session,
                catalog,
                schedule,
                user,
                scheduler.zone,
                now=scheduler.now(),
                **body.model_dump(),
            )
        except ScheduleError as exc:
            await session.rollback()
            code = 403 if exc.code == "forbidden" else 422
            raise HTTPException(code, {"code": exc.code, "message": str(exc)}) from exc
        await session.commit()
        return schedule_out(schedule)

    async def load_schedule(session: AsyncSession, schedule_id: int, user: User) -> Schedule:
        schedule = await session.get(Schedule, schedule_id)
        if schedule is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
        return schedule

    @api.get("/schedules", response_model=list[ScheduleOut])
    async def list_schedules(
        session: Session, operation: str | None = None
    ) -> list[dict[str, object]]:
        """Planned operations, next due first; ``operation`` limits them to one operation."""
        query = select(Schedule).order_by(Schedule.next_run_at.is_(None), Schedule.next_run_at)
        if operation:
            query = query.where(Schedule.operation == operation)
        schedules = list(await session.scalars(query))
        statuses = await last_statuses(session, schedules)
        return [schedule_out(s, statuses.get(s.last_activity_id or 0)) for s in schedules]

    @api.get("/schedules/{schedule_id}", response_model=ScheduleOut)
    async def get_schedule(
        schedule_id: int, session: Session, user: CurrentUser
    ) -> dict[str, object]:
        schedule = await load_schedule(session, schedule_id, user)
        statuses = await last_statuses(session, [schedule])
        return schedule_out(schedule, statuses.get(schedule.last_activity_id or 0))

    @api.post("/schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
    async def create_schedule(
        body: ScheduleIn, session: Session, user: CurrentUser
    ) -> dict[str, object]:
        """Plan an operation once, daily or every N minutes; it runs with the creator's
        rights, checked again when it is due."""
        return await save_schedule_body(session, None, body, user)

    @api.put("/schedules/{schedule_id}", response_model=ScheduleOut)
    async def update_schedule(
        schedule_id: int, body: ScheduleIn, session: Session, user: CurrentUser
    ) -> dict[str, object]:
        schedule = await load_schedule(session, schedule_id, user)
        return await save_schedule_body(session, schedule, body, user)

    @api.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_schedule(schedule_id: int, session: Session, user: CurrentUser) -> Response:
        await session.delete(await load_schedule(session, schedule_id, user))
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # --- browser interface ----------------------------------------------------------------

    @api.get("/landscape")
    async def get_landscape(session: Session, user: CurrentUser) -> dict[str, object]:
        """Systems with instances, hosts, pools and the operations this user may run, as the
        landscape page shows them."""
        return await landscape_snapshot(session, catalog, user)

    @api.get("/overview")
    async def get_overview(session: Session, user: CurrentUser) -> dict[str, object]:
        """The overview: key figures, systems as a matrix of pools and stages, and what
        needs attention by the rules and this user's exceptions."""
        return await overview_snapshot(session, catalog, user)

    @api.get("/attention-rules")
    async def get_attention_rules(session: Session, user: CurrentUser) -> dict[str, object]:
        """The rules of "needs attention", the same for everyone."""
        return {"rules": await load_rules(session), "defaults": DEFAULT_RULES}

    @api.put("/attention-rules")
    async def put_attention_rules(body: AttentionRulesIn, session: Session) -> dict[str, object]:
        """Change the rules (admin)."""
        try:
            rules = await save_rules(session, body.rules)
        except RuleError as exc:
            raise HTTPException(422, str(exc)) from exc
        await session.commit()
        return {"rules": rules, "defaults": DEFAULT_RULES}

    @api.get("/me/attention")
    async def get_my_attention(session: Session, user: CurrentUser) -> dict[str, object]:
        """The user's exceptions: rules switched off, systems and pools hidden."""
        return (await load_exceptions(session, user)).to_dict()

    @api.put("/me/attention")
    async def put_my_attention(
        body: AttentionExceptionsIn, session: Session, user: CurrentUser
    ) -> dict[str, object]:
        try:
            await save_exceptions(session, user, Exceptions(**body.model_dump()))
        except RuleError as exc:
            raise HTTPException(422, str(exc)) from exc
        await session.commit()
        return (await load_exceptions(session, user)).to_dict()

    @api.get("/instances/{instance_id}/processes")
    async def get_processes(instance_id: int, session: Session) -> dict[str, object]:
        """Processes of an instance, read now from GetProcessList of its sapstartsrv; the
        stored status of the instance is updated."""
        instance = await session.scalar(
            select(Instance)
            .where(Instance.id == instance_id)
            .options(selectinload(Instance.host), selectinload(Instance.sid))
        )
        if instance is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Instance not found")
        return await read_processes(session, instance, clients)

    @api.get("/events")
    async def events(request: Request, user: CurrentUser) -> StreamingResponse:
        """Server-Sent Events: "hello" at once, then "change" whenever activities, status or
        inventory change. The interface reloads what it shows."""
        stream = change_events(
            session_factory,
            app.state.events_sleep,
            interval=app.state.events_interval,
            disconnected=request.is_disconnected,
            limit=app.state.events_limit,
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @api.get("/i18n")
    async def texts(request: Request, session: Session, user: CurrentUser) -> dict[str, object]:
        """All texts of the interface in the user's language."""
        chosen = (await get_preferences(session, user))["language"]
        language = pick_language(
            chosen or request.cookies.get(LANGUAGE_COOKIE),
            request.headers.get("accept-language"),
        )
        return {"language": language, "texts": all_texts(language)}

    @api.get("/operations", response_model=list[OperationOut])
    async def list_operations(user: CurrentUser) -> list[dict[str, object]]:
        """The operations of the catalog this user may run, custom ones with parameters."""
        return [
            {
                "key": operation.key,
                "name": operation.name,
                "targets": sorted(operation.targets),
                "role": operation.role.value,
                "mass": operation.mass,
                "custom": operation.custom is not None,
                "locks": operation.custom.locks if operation.custom else True,
                "standalone": operation.standalone,
                "parameters": [p.__dict__ for p in operation.custom.parameters]
                if operation.custom
                else [],
            }
            for operation in catalog.all()
            if has_role(user, operation.role)
        ]

    # --- custom operations ----------------------------------------------------------------

    def custom_out(operation: CustomOperation) -> dict[str, object]:
        return {
            "id": operation.id,
            "key": operation.key,
            "name": operation.name,
            "description": operation.description,
            "agent_operation": operation.agent_operation,
            "target": operation.target,
            "instance_types": [t for t in operation.instance_types.split(",") if t],
            "ordering": operation.ordering,
            "role": operation.role,
            "mass": operation.mass,
            "locks": operation.locks,
            "standalone": operation.standalone,
            "timeout_seconds": operation.timeout_seconds,
            "parameters": [
                {
                    "name": p.name,
                    "label": p.label,
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                    "pattern": p.pattern,
                    "help": p.help,
                }
                for p in operation.parameters
            ],
        }

    async def save_custom(
        session: AsyncSession, operation: CustomOperation | None, body: CustomOperationIn
    ) -> CustomOperation:
        try:
            operation = await save_operation(
                session,
                operation,
                key=body.key,
                name=body.name,
                description=body.description,
                agent_operation=body.agent_operation,
                target=body.target,
                instance_types=body.instance_types,
                ordering=body.ordering,
                role=body.role,
                mass=body.mass,
                timeout_seconds=body.timeout_seconds,
                locks=body.locks,
                standalone=body.standalone,
            )
            # The parameters are replaced as a whole, in the given order.
            operation.parameters.clear()
            await session.flush()
            for parameter in body.parameters:
                await save_parameter(session, operation, None, **parameter.model_dump())
        except CustomOperationError as exc:
            await session.rollback()
            code = 409 if exc.code == "operation_key_taken" else 422
            raise HTTPException(code, str(exc)) from exc
        await session.commit()
        await catalog.reload(session)
        return operation

    async def load_custom(session: AsyncSession, operation_id: int) -> CustomOperation:
        operation = await session.get(CustomOperation, operation_id)
        if operation is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Custom operation not found")
        return operation

    @api.get("/custom-operations", response_model=list[CustomOperationOut])
    async def list_custom_operations(session: Session) -> list[dict[str, object]]:
        rows = await session.scalars(select(CustomOperation).order_by(CustomOperation.key))
        return [custom_out(op) for op in rows]

    @api.post(
        "/custom-operations",
        response_model=CustomOperationOut,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_custom_operation(
        body: CustomOperationIn, session: Session
    ) -> dict[str, object]:
        """Define a custom operation (admin). It runs the script configured under
        ``agent_operation`` in operations.d of the host agent."""
        return custom_out(await save_custom(session, None, body))

    @api.get("/custom-operations/{operation_id}", response_model=CustomOperationOut)
    async def get_custom_operation(operation_id: int, session: Session) -> dict[str, object]:
        return custom_out(await load_custom(session, operation_id))

    @api.put("/custom-operations/{operation_id}", response_model=CustomOperationOut)
    async def update_custom_operation(
        operation_id: int, body: CustomOperationIn, session: Session
    ) -> dict[str, object]:
        operation = await load_custom(session, operation_id)
        return custom_out(await save_custom(session, operation, body))

    @api.delete("/custom-operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_custom_operation(operation_id: int, session: Session) -> Response:
        operation = await load_custom(session, operation_id)
        if used := await steps_using(session, operation.key):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Used by the templates " + ", ".join(used)
            )
        await session.delete(operation)
        await session.commit()
        await catalog.reload(session)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    async def run_custom(
        session: AsyncSession,
        user: User,
        target_type: TargetType,
        target_id: int,
        key: str,
        body: RunIn,
        timeout: int | None,
    ) -> Activity:
        definition = catalog.get(key)
        if (
            definition is None
            or (definition.custom is None and definition.template is None)
            or not definition.standalone
            or target_type not in definition.targets
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No custom operation {key} here")
        if not has_role(user, definition.role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires the role {definition.role}")
        if definition.template is not None:
            return await start_template(session, user, definition, [target_id], body.parameters)
        if target_type == TargetType.INSTANCE:
            instance = await session.scalar(select(Instance).where(Instance.id == target_id))
            if instance is not None and not definition.applies_to(instance):
                raise HTTPException(
                    422, f"{definition.custom.name} does not apply to this instance"
                )
        try:
            values = parameter_values(definition.custom, body.parameters)
        except ParameterError as exc:
            raise HTTPException(422, str(exc)) from exc
        return await submit(
            runner.submit_custom(
                session,
                definition.custom,
                target_type,
                target_id,
                values,
                timeout,
                user.username,
            )
        )

    CustomTimeout = Annotated[int | None, Query(ge=10, le=86400)]

    @api.post(
        "/instances/{instance_id}/operations/{key}",
        response_model=ActivityOut,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def run_on_instance(
        instance_id: int,
        key: str,
        session: Session,
        user: CurrentUser,
        body: RunIn = RunIn(),  # noqa: B008
        timeout: CustomTimeout = None,
    ) -> Activity:
        """Run a custom operation on an instance."""
        return await run_custom(session, user, TargetType.INSTANCE, instance_id, key, body, timeout)

    @api.post(
        "/systems/{system_id}/operations/{key}",
        response_model=ActivityOut,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def run_on_system(
        system_id: int,
        key: str,
        session: Session,
        user: CurrentUser,
        body: RunIn = RunIn(),  # noqa: B008
        timeout: CustomTimeout = None,
    ) -> Activity:
        """Run a custom operation on the matching instances of a system."""
        return await run_custom(session, user, TargetType.SYSTEM, system_id, key, body, timeout)

    @api.post(
        "/hosts/{host_id}/operations/{key}",
        response_model=ActivityOut,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def run_on_host(
        host_id: int,
        key: str,
        session: Session,
        user: CurrentUser,
        body: RunIn = RunIn(),  # noqa: B008
        timeout: CustomTimeout = None,
    ) -> Activity:
        """Run a custom operation on a host."""
        return await run_custom(session, user, TargetType.HOST, host_id, key, body, timeout)

    @api.post("/activities/{activity_id}/cancel", response_model=ActivityDetail)
    async def cancel_activity(activity_id: int, session: Session, user: CurrentUser) -> Activity:
        """Cancel a running activity. Start and stop only stop waiting; custom operations are
        cancelled on the host agent; a mass operation cancels its running children."""
        try:
            await runner.cancel(session, activity_id, user.username)
            return await get_activity(activity_id, session)
        except TargetNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except NotActiveError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    @api.post("/mass-operations", response_model=ActivityOut, status_code=status.HTTP_202_ACCEPTED)
    async def create_mass_operation(
        body: MassOperationIn,
        session: Session,
        user: CurrentUser,
        timeout: CustomTimeout = None,
    ) -> Activity:
        """Run an operation on many targets; returns the parent activity with the children."""
        definition = catalog.get(body.operation)
        target_type = TargetType(body.target_type)
        if (
            definition is None
            or target_type not in definition.targets
            or not definition.mass
            or not definition.standalone
        ):
            raise HTTPException(422, f"No mass operation {body.operation} on {target_type}")
        if not has_role(user, definition.role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires the role {definition.role}")
        if definition.template is not None:
            # A template runs once with all selected targets as its selection.
            return await start_template(session, user, definition, body.target_ids, body.parameters)
        values = None
        try:
            if definition.custom is not None:
                values = parameter_values(definition.custom, body.parameters)
        except ParameterError as exc:
            raise HTTPException(422, str(exc)) from exc
        default_timeout = (
            definition.custom.timeout_seconds if definition.custom else DEFAULT_TIMEOUT_SECONDS
        )
        try:
            return await runner.submit_mass(
                session,
                definition.kind,
                target_type,
                body.target_ids,
                parallel=body.parallel,
                stop_on_error=body.stop_on_error,
                timeout_seconds=timeout or default_timeout,
                requested_by=user.username,
                custom=definition.custom,
                parameters=values,
            )
        except TargetNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    # --- own account and users ------------------------------------------------------------

    def user_error(exc: UserError) -> HTTPException:
        code = {"username_taken": 409, "last_admin": 409}.get(exc.code, 422)
        return HTTPException(code, str(exc))

    async def load_user(session: AsyncSession, user_id: int) -> User:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        return user

    @api.get("/me", response_model=UserOut)
    async def me(user: CurrentUser) -> User:
        return user

    @api.get("/me/tokens", response_model=list[TokenOut])
    async def my_tokens(user: CurrentUser, session: Session) -> list[ApiToken]:
        query = select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.id)
        return list(await session.scalars(query))

    @api.post("/me/tokens", response_model=NewTokenOut, status_code=status.HTTP_201_CREATED)
    async def create_my_token(
        body: TokenCreate, user: CurrentUser, session: Session
    ) -> dict[str, object]:
        """Create a token; its value is returned only in this response."""
        try:
            token, plain = await create_token(session, user, body.name, body.expires_at)
        except UserError as exc:
            raise user_error(exc) from exc
        await session.commit()
        return {"token": plain, "info": token}

    @api.delete("/me/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_my_token(token_id: int, user: CurrentUser, session: Session) -> Response:
        token = await session.get(ApiToken, token_id)
        if token is None or token.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
        await session.delete(token)
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @api.get("/users", response_model=list[UserOut])
    async def list_users(session: Session) -> list[User]:
        return list(await session.scalars(select(User).order_by(User.username)))

    @api.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
    async def create_user_route(body: UserCreate, session: Session) -> User:
        """Create a user with a start password that must be changed at the first sign-in."""
        try:
            user = await create_user(
                session,
                body.username,
                body.password,
                body.role,
                display_name=body.display_name,
                must_change_password=True,
            )
        except UserError as exc:
            raise user_error(exc) from exc
        await session.commit()
        return user

    @api.patch("/users/{user_id}", response_model=UserOut)
    async def update_user_route(user_id: int, body: UserUpdate, session: Session) -> User:
        user = await load_user(session, user_id)
        try:
            await update_user(
                session,
                user,
                role=body.role,
                active=body.active,
                display_name=body.display_name,
            )
        except UserError as exc:
            await session.rollback()
            raise user_error(exc) from exc
        await session.commit()
        return user

    @api.put("/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
    async def reset_password(user_id: int, body: PasswordReset, session: Session) -> Response:
        """Set a start password; the user must change it at the next sign-in."""
        user = await load_user(session, user_id)
        try:
            set_password(user, body.password, must_change=True)
        except UserError as exc:
            raise user_error(exc) from exc
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    app.state.runner = runner
    app.state.scheduler = scheduler
    # Tests drive the scheduler with tick(); the server lets it run on its own.
    app.state.run_scheduler = run_scheduler
    # Event stream: how often the database is checked for changes; limit only for tests.
    app.state.events_interval = 2.0
    app.state.events_sleep = asyncio.sleep
    app.state.events_limit = None

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        # Everything comes from this server; no inline scripts or styles, no frames.
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    app.state.catalog = catalog
    app.state.clients = clients
    # Replaced in tests; reads the certificate a host shows (tls.fetch_certificate).
    app.state.fetch_certificate = fetch_certificate
    app.state.setup_code = None
    app.state.session_factory = session_factory
    # Downloads of the hosts (oslo_update.sh): no sign-in, the bundle is signed and holds no
    # secrets.
    @app.get("/bundle/{name}", include_in_schema=False)
    async def bundle_file(name: str) -> Response:
        active = bundle_store.active
        files = {"payload.tar.gz": "payload", "payload.sig": "signature"}
        if active is None or name not in files:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No bundle")
        return Response(
            getattr(active, files[name]),
            media_type="application/octet-stream",
            headers={"X-OSLO-Bundle-Version": active.version, "Cache-Control": "no-store"},
        )

    app.state.bundles = bundle_store
    app.mount("/api", api)
    register_web(app, AppContext(settings, secret_box, clients, session_factory, runner, catalog))
    return app

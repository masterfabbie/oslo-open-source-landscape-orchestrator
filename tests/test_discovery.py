from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from oslo.clients import HostAgentClient, SoapFaultError
from oslo.clients.sapcontrol import OSProcess, StateColor
from oslo.connections import ClientFactory
from oslo.crypto import SecretBox, generate_secret_key
from oslo.db import create_engine, create_session_factory, upgrade_database
from oslo.discovery import DiscoveryError, discover_host, instance_status
from oslo.mock.transport import MockLandscapeTransport
from oslo.models import Database, Host, Instance, Sid, System

pytestmark = pytest.mark.anyio


@pytest.fixture
def secret_box() -> SecretBox:
    return SecretBox(generate_secret_key())


@pytest.fixture
def transport(landscape) -> MockLandscapeTransport:
    return MockLandscapeTransport(landscape)


@pytest.fixture
def clients(secret_box, transport) -> ClientFactory:
    return ClientFactory(secret_box, transport=transport)


@pytest.fixture
async def session(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(url)
    await upgrade_database(engine, url)
    async with create_session_factory(engine)() as session:
        yield session
    await engine.dispose()


def make_host(secret_box: SecretBox, name: str, offset: int = 0) -> Host:
    return Host(
        name=name,
        address="127.0.0.1",
        hostagent_port=1128 + offset,
        sapcontrol_port_offset=offset,
        username="devadm",
        password_encrypted=secret_box.encrypt("mock"),
    )


async def instances_of(session, host: Host) -> dict[str, Instance]:
    rows = await session.scalars(
        select(Instance).where(Instance.host_id == host.id).options(selectinload(Instance.sid))
    )
    return {instance.number: instance for instance in rows}


def process(color: StateColor) -> OSProcess:
    return OSProcess("p", "", color, "", "", "", 1)


def test_instance_status_aggregation():
    assert instance_status([]) == "GRAY"
    assert instance_status([process(StateColor.GRAY)] * 2) == "GRAY"
    assert instance_status([process(StateColor.GREEN)] * 2) == "GREEN"
    assert instance_status([process(StateColor.GREEN), process(StateColor.GRAY)]) == "YELLOW"
    assert instance_status([process(StateColor.GREEN), process(StateColor.YELLOW)]) == "YELLOW"
    assert instance_status([process(StateColor.GREEN), process(StateColor.RED)]) == "RED"


async def test_discovery_stores_host_and_unassigned_instances(session, secret_box, clients):
    host = make_host(secret_box, "sapapp1")
    session.add(host)
    await session.flush()

    result = await discover_host(session, host, clients)
    await session.commit()

    assert result.instances_added == ["DEV/01", "DEV/00"]
    assert result.warnings == []
    assert (host.reachable, host.last_error) == (True, None)
    assert (host.os_name, host.cpu_count, host.memory_kb) == ("Linux", 4, 16777216)

    instances = await instances_of(session, host)
    dialog = instances["00"]
    assert dialog.sid.name == "DEV"
    assert dialog.system_id is None
    assert dialog.hostname == "sapapp1"
    assert dialog.features == "ABAP|GATEWAY|ICMAN|IGS"
    assert dialog.start_priority == "3"
    assert dialog.last_status == "GRAY"
    assert instances["01"].features == "MESSAGESERVER|ENQUE"
    assert [sid.name for sid in await session.scalars(select(Sid))] == ["DEV"]
    # Systems are created by the user, never by discovery.
    assert list(await session.scalars(select(System))) == []


async def test_discovery_is_repeatable_and_refreshes_status(
    session, secret_box, clients, landscape, clock
):
    host = make_host(secret_box, "sapapp1")
    session.add(host)
    await session.flush()
    await discover_host(session, host, clients)

    landscape.start_instance(landscape.host("sapapp1").instance(0))
    result = await discover_host(session, host, clients)
    assert result.instances_added == []
    assert result.instances_updated == ["DEV/01", "DEV/00"]
    assert (await instances_of(session, host))["00"].last_status == "YELLOW"

    clock.advance(3)
    await discover_host(session, host, clients)
    instances = await instances_of(session, host)
    assert instances["00"].last_status == "GREEN"
    assert len(instances) == 2


async def test_discovery_of_database_host(session, secret_box, clients):
    host = make_host(secret_box, "sapdb1", offset=10000)
    session.add(host)
    await session.flush()

    result = await discover_host(session, host, clients)
    assert result.instances_added == ["HDV/02"]
    assert result.databases_added == ["SYSTEMDB@HDV", "HDV@HDV"]

    databases = list(await session.scalars(select(Database).order_by(Database.name)))
    assert [(d.name, d.type, d.instance_name, d.last_status) for d in databases] == [
        ("HDV@HDV", "hdb", "HDB02", "STOPPED"),
        ("SYSTEMDB@HDV", "hdb", "HDB02", "STOPPED"),
    ]
    assert (await instances_of(session, host))["02"].features == "HDB|HDB_WORKER"


async def test_database_has_its_own_sid(session, secret_box, clients):
    app_host = make_host(secret_box, "sapapp1")
    db_host = make_host(secret_box, "sapdb1", offset=10000)
    session.add_all([app_host, db_host])
    await session.flush()
    await discover_host(session, app_host, clients)
    await discover_host(session, db_host, clients)

    sids = await session.scalars(
        select(Sid).order_by(Sid.name).options(selectinload(Sid.instances))
    )
    assert {s.name: sorted(i.number for i in s.instances) for s in sids} == {
        "DEV": ["00", "01"],
        "HDV": ["02"],
    }


async def test_unreachable_sapstartsrv_gives_warning(session, secret_box, clients, transport):
    transport.remove_port(50013)
    host = make_host(secret_box, "sapapp1")
    session.add(host)
    await session.flush()

    result = await discover_host(session, host, clients)

    assert len(result.warnings) == 1
    assert result.warnings[0].startswith("DEV/00: sapstartsrv could not be queried")
    instances = await instances_of(session, host)
    assert instances["00"].last_status == "UNKNOWN"
    assert instances["00"].features is None
    assert instances["01"].last_status == "GRAY"


async def test_unreachable_host_agent_raises_and_marks_host(session, secret_box, clients):
    host = make_host(secret_box, "ghost")
    host.hostagent_port = 4711
    session.add(host)
    await session.flush()

    with pytest.raises(DiscoveryError, match="Connection refused"):
        await discover_host(session, host, clients)

    assert host.reachable is False
    assert "Connection refused" in host.last_error
    assert await instances_of(session, host) == {}


async def test_missing_instances_are_reported_but_kept(session, secret_box, clients):
    host = make_host(secret_box, "sapapp1")
    sid = Sid(name="OLD")
    session.add_all([host, sid])
    await session.flush()
    session.add(Instance(host=host, sid=sid, number="42", hostname="sapapp1"))
    await session.flush()

    result = await discover_host(session, host, clients)

    assert result.instances_missing == ["OLD/42"]
    assert "42" in await instances_of(session, host)


async def test_sid_credentials_take_precedence(session, secret_box, transport):
    """Protected sapstartsrv calls use the credentials of the SID when it has any."""
    host = make_host(secret_box, "sapapp1")
    host.password_encrypted = secret_box.encrypt("wrong")
    sid = Sid(name="DEV", username="devadm", password_encrypted=secret_box.encrypt("mock"))
    factory = ClientFactory(secret_box, transport=transport)

    async with factory.sapcontrol(host, 0, sid) as sapcontrol:
        await sapcontrol.start()
    async with factory.sapcontrol(host, 0) as sapcontrol:
        with pytest.raises(Exception, match="Invalid Credentials"):
            await sapcontrol.stop()


async def test_discovery_stores_host_agent_version(session, secret_box, clients):
    host = make_host(secret_box, "sapapp1")
    session.add(host)
    await session.flush()

    result = await discover_host(session, host, clients)

    assert result.warnings == []
    assert host.agent_info.release == "722"
    assert host.agent_info.patch == "72"
    assert host.hostagent_version == "7.22 PL72"
    assert host.agent_info.details.startswith("722 (EXT), patch 1611")


async def test_unreadable_version_gives_warning_and_keeps_old(
    session, secret_box, clients, monkeypatch
):
    host = make_host(secret_box, "sapapp1")
    session.add(host)
    await session.flush()
    await discover_host(session, host, clients)

    async def refuse(self):
        raise SoapFaultError("Permission denied")

    monkeypatch.setattr(HostAgentClient, "get_version", refuse)
    result = await discover_host(session, host, clients)

    assert result.warnings == ["Host agent version could not be read (Permission denied)"]
    assert host.hostagent_version == "7.22 PL72"
    assert result.instances_updated == ["DEV/01", "DEV/00"]

from __future__ import annotations

import httpx
import pytest

from conftest import AUTH
from oslo.clients import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    SapControlClient,
    SoapFaultError,
)
from oslo.clients.sapcontrol import (
    StartStopOption,
    StateColor,
    sapcontrol_port,
)
from oslo.mock.apps import create_sapcontrol_app

pytestmark = pytest.mark.anyio


def make_client(landscape, auth=AUTH) -> SapControlClient:
    transport = httpx.ASGITransport(app=create_sapcontrol_app(landscape, "sapapp1", 0))
    return SapControlClient("sapapp1", 0, auth=auth, transport=transport)


def test_default_ports():
    assert sapcontrol_port(0) == 50013
    assert sapcontrol_port(11) == 51113
    assert sapcontrol_port(11, https=True) == 51114
    with pytest.raises(ValueError):
        sapcontrol_port(100)


def test_base_url_uses_instance_port():
    assert SapControlClient("host1", 7).base_url == "http://host1:50713"
    assert SapControlClient("host1", 7, https=True).base_url == "https://host1:50714"
    assert SapControlClient("host1", 7, port=60013).base_url == "http://host1:60013"


async def test_start_and_process_list(landscape, clock):
    async with make_client(landscape) as client:
        processes = await client.get_process_list()
        assert [p.name for p in processes] == ["disp+work", "igswd_mt", "gwrd", "icman"]
        assert {p.dispstatus for p in processes} == {StateColor.GRAY}
        assert processes[0].pid == -1

        await client.start()
        assert (await client.get_process_list())[0].dispstatus is StateColor.YELLOW

        clock.advance(3)
        first = (await client.get_process_list())[0]
        assert first.dispstatus is StateColor.GREEN
        assert first.textstatus == "Running"
        assert first.description == "Dispatcher"
        assert first.pid > 0


async def test_stop_and_restart(landscape, clock):
    async with make_client(landscape) as client:
        await client.start()
        clock.advance(3)

        await client.restart_instance()
        assert (await client.get_process_list())[0].textstatus == "Stopping"
        clock.advance(5)
        assert (await client.get_process_list())[0].dispstatus is StateColor.GREEN

        await client.stop(softtimeout=60)
        clock.advance(2)
        assert (await client.get_process_list())[0].dispstatus is StateColor.GRAY


async def test_system_instance_list(single_sid_landscape):
    landscape = single_sid_landscape
    async with make_client(landscape) as client:
        instances = {i.hostname: i for i in await client.get_system_instance_list()}
    hdb = instances["sapdb1"]
    assert hdb.instance_nr == 2
    assert hdb.features == ("HDB", "HDB_WORKER")
    assert hdb.start_priority == "0.3"
    assert (hdb.http_port, hdb.https_port) == (60213, 60214)
    assert hdb.dispstatus is StateColor.GRAY


async def test_start_and_stop_system(single_sid_landscape, clock):
    landscape = single_sid_landscape

    async def colors(client: SapControlClient) -> dict[int, StateColor]:
        return {i.instance_nr: i.dispstatus for i in await client.get_system_instance_list()}

    async with make_client(landscape) as client:
        await client.start_system()
        assert await colors(client) == {
            0: StateColor.GRAY,
            1: StateColor.GRAY,
            2: StateColor.YELLOW,
        }
        clock.advance(9)
        assert set((await colors(client)).values()) == {StateColor.GREEN}

        await client.stop_system(StartStopOption.ALLNOHDB)
        clock.advance(4)
        assert await colors(client) == {
            0: StateColor.GRAY,
            1: StateColor.GRAY,
            2: StateColor.GREEN,
        }

        await client.restart_system(StartStopOption.HDB)
        clock.advance(5)
        assert (await colors(client))[2] is StateColor.GREEN


async def test_unsupported_option_raises_fault(landscape):
    async with make_client(landscape) as client:
        with pytest.raises(SoapFaultError, match="not supported"):
            await client.start_system(StartStopOption.PRIORITY_LEVEL, prioritylevel="2")


async def test_protected_method_without_credentials(landscape):
    async with make_client(landscape, auth=None) as client:
        assert await client.get_process_list()
        with pytest.raises(AuthenticationRequiredError) as error:
            await client.start()
        assert error.value.http_status == 401


async def test_protected_method_with_wrong_password(landscape):
    async with make_client(landscape, auth=("devadm", "wrong")) as client:
        with pytest.raises(InvalidCredentialsError):
            await client.start()
        assert (await client.get_process_list())[0].dispstatus is StateColor.GRAY

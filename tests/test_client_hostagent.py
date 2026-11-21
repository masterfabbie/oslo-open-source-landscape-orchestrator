from __future__ import annotations

import httpx
import pytest

from conftest import AUTH, stopped_config
from landscape_orchestrator.clients import (
    AuthenticationRequiredError,
    HostAgentClient,
    SoapFaultError,
)
from landscape_orchestrator.clients.hostagent import (
    DatabaseStatus,
    InstanceStatus,
    LogMessage,
    OperationResult,
    parse_version_info,
)
from landscape_orchestrator.mock.apps import create_hostagent_app
from landscape_orchestrator.mock.landscape import MockLandscape

pytestmark = pytest.mark.anyio


def make_client(landscape, host: str = "sapapp1", auth=AUTH) -> HostAgentClient:
    transport = httpx.ASGITransport(app=create_hostagent_app(landscape, host))
    return HostAgentClient(host, auth=auth, transport=transport)


def test_base_url():
    assert HostAgentClient("host1").base_url == "http://host1:1128"
    assert HostAgentClient("host1", https=True).base_url == "https://host1:1129"
    assert HostAgentClient("host1", port=11128).base_url == "http://host1:11128"


async def test_list_instances(landscape):
    async with make_client(landscape) as client:
        instances = await client.list_instances()
    assert sorted(i.system_number for i in instances) == ["00", "01"]
    first = instances[0]
    assert (first.sid, first.hostname) == ("DEV", "sapapp1")
    assert first.sap_version_info.startswith("753")


async def test_start_and_stop_instance(landscape, clock):
    async with make_client(landscape) as client:
        assert await client.list_instances(InstanceStatus.RUNNING) == []

        result = await client.start_instance("DEV", 0)
        assert "Start of instance DEV/00" in result.messages["description"]
        clock.advance(3)
        running = await client.list_instances(InstanceStatus.RUNNING)
        assert [i.system_number for i in running] == ["00"]

        await client.stop_instance("DEV", "00", soft_timeout=30)
        clock.advance(2)
        stopped = await client.list_instances(InstanceStatus.STOPPED)
        assert sorted(i.system_number for i in stopped) == ["00", "01"]


async def test_list_instances_by_hostname(landscape):
    async with make_client(landscape) as client:
        assert len(await client.list_instances(hostname="sapapp1")) == 2
        assert await client.list_instances(hostname="elsewhere") == []


async def test_start_unknown_instance_raises_fault(landscape):
    async with make_client(landscape) as client:
        with pytest.raises(SoapFaultError, match="not found"):
            await client.start_instance("DEV", 77)


async def test_start_instance_without_credentials(landscape):
    async with make_client(landscape, auth=None) as client:
        with pytest.raises(AuthenticationRequiredError):
            await client.start_instance("DEV", 0)


async def test_databases(landscape, clock):
    async with make_client(landscape, host="sapdb1") as client:
        system_db, database = await client.list_databases()
        assert system_db.name == "SYSTEMDB@HDV"
        assert (database.name, database.type) == ("HDV@HDV", "hdb")
        assert database.status is DatabaseStatus.STOPPED
        assert database.properties["Database/InstanceName"] == "HDB02"
        assert [c.name for c in database.components] == [
            "hdbdaemon",
            "hdbnameserver",
            "hdbindexserver",
        ]

        await client.start_instance("HDV", 2)
        state = await client.get_database_status("HDV@HDV", "hdb")
        assert state.status is DatabaseStatus.STARTING

        clock.advance(3)
        state = await client.get_database_status("HDV@HDV", "hdb", host="sapdb1")
        assert state.status is DatabaseStatus.RUNNING
        component = state.components[0]
        assert component.description == "HDB Daemon"
        assert component.status is DatabaseStatus.RUNNING
        assert component.status_description == "Running"


async def test_host_without_databases(landscape):
    async with make_client(landscape) as client:
        assert await client.list_databases() == []


async def test_unknown_database_raises_fault(landscape):
    async with make_client(landscape) as client:
        with pytest.raises(SoapFaultError, match="not found"):
            await client.get_database_status("XXX", "hdb")


async def test_computer_system(landscape):
    async with make_client(landscape) as client:
        system = await client.get_computer_system()
    assert system.class_name == "ITSAMComputerSystem"
    assert system.value("Name") == "sapapp1"
    assert system.properties["Hostnames"].type == "String[] sep=;"
    assert system.value("Missing", "fallback") == "fallback"

    (operating_system,) = system.find("ITSAMOperatingSystem")
    assert operating_system.value("Name") == "Linux"
    assert operating_system.properties["CPU Count"].type == "uint16"
    assert len(system.find("ITSAMFileSystem")) == 1
    assert system.find("ITSAMComputerSystem") == [system]


async def test_version_info(landscape):
    async with make_client(landscape) as client:
        result = await client.execute_operation("versioninfo")
        version = await client.get_version()
    assert result.operation_id == "MOCKOPERATION"
    assert len(result.entries) > 5
    assert (version.release, version.patch) == ("722", "72")
    assert version.display == "7.22 PL72"
    assert version.details.startswith("722 (EXT), patch 1611")


async def test_unknown_operation_and_missing_credentials(landscape):
    async with make_client(landscape) as client:
        with pytest.raises(SoapFaultError, match="not found"):
            await client.execute_operation("nosuchoperation")
    async with make_client(landscape, auth=None) as client:
        with pytest.raises(AuthenticationRequiredError):
            await client.get_version()


def test_parse_version_info_from_log_lines():
    """Lines as a real host agent printed them; keys are not relied upon."""
    lines = [
        "Retrieve version info: /usr/sap/hostctrl/exe/saphostexec: 722 (EXT), patch 1611, "
        "changelist 2315890, linuxx86_64, opt (EXT) (Oct 13 2026, 09:26:37)",
        "Retrieve version info: /usr/sap/hostctrl/exe/sapstartsrv: 722 (EXT), patch 1611",
        "Retrieve version info: kernel release                722",
        "Retrieve version info: patch number                  72",
    ]
    for key in ("Info", "", "message"):
        result = OperationResult("", {}, [(key, line) for line in lines])
        version = parse_version_info(result)
        assert (version.release, version.patch) == ("722", "72")
        assert version.details.endswith("(Oct 13 2026, 09:26:37)")
    assert parse_version_info(OperationResult("", {}, [("Info", "something else")])) is None


async def test_instance_with_virtual_hostname_needs_hostname(clock):
    """A real host agent did not find an instance with a virtual hostname without it."""
    config = stopped_config()
    config["hosts"][0]["instances"][1]["hostname"] = "sapdevci"  # DEV/00
    virtual = MockLandscape.from_dict(config, clock=clock)
    async with make_client(virtual) as client:
        with pytest.raises(SoapFaultError, match="SAP Instance not found!"):
            await client.start_instance("DEV", 0)
        with pytest.raises(SoapFaultError, match="SAP Instance not found!"):
            await client.start_instance("DEV", 0, hostname="sapapp1")
        await client.start_instance("DEV", 0, hostname="sapdevci")
        await client.start_instance("DEV", 1, hostname="sapapp1")
        clock.advance(3)
        running = await client.list_instances(InstanceStatus.RUNNING)
    assert sorted(i.hostname for i in running) == ["sapapp1", "sapdevci"]


async def test_asynchronous_custom_operation(landscape, clock):
    """As seen on a real host agent: results while running are fault 255 with the lines so
    far, a failed script is fault 127, a cancelled operation is forgotten (fault -20)."""
    from landscape_orchestrator.clients.hostagent import (
        FAULT_COMMAND_FAILED,
        FAULT_TIMEOUT,
        FAULT_UNKNOWN_OPERATION,
        OperationFault,
    )

    async with make_client(landscape) as client:
        arguments = {"SAPSYSTEMNAME": "DEV", "PARAM-SLEEP": "5", "PARAM-RC": "3"}
        operation_id = (await client.execute_async("LO_TEST", arguments)).operation_id
        assert operation_id and not await client.is_operation_finished(operation_id)
        with pytest.raises(OperationFault) as running:
            await client.get_operation_results(operation_id)
        assert running.value.code == FAULT_TIMEOUT
        assert running.value.result.log[-1].display.startswith("saphostcontrol: Executing")
        clock.advance(5)
        assert await client.is_operation_finished(operation_id)
        with pytest.raises(OperationFault) as failed:
            await client.get_operation_results(operation_id)
        assert failed.value.code == FAULT_COMMAND_FAILED
        assert failed.value.result.log[-1] == LogMessage(
            "Error", "saphostcontrol", "Test operation hook failed (exit code = 3)"
        )

        started = await client.execute_async("LO_TEST", {"PARAM-SLEEP": "60", "PARAM-RC": "0"})
        other = started.operation_id
        result = await client.cancel_operation(other)
        assert result.log[-1].text.endswith("hook failed (exit code = 15)")
        with pytest.raises(OperationFault) as gone:
            await client.get_operation_results(other)
        assert gone.value.code == FAULT_UNKNOWN_OPERATION


def test_log_messages_are_grouped():
    """A real host agent sends each line as LogMsg/TimeStamp, /Severity, /Source, /Text."""
    from landscape_orchestrator.clients.hostagent import log_messages

    def line(severity, source, text):
        return [
            ("LogMsg/TimeStamp", ""),
            ("LogMsg/Severity", severity),
            ("LogMsg/Source", source),
            ("LogMsg/Text", text),
        ]

    entries = [
        *line("Info", "Sync", "BEGIN"),
        *line("Warning", "Sync", "careful"),
        ("Info", "a line without LogMsg"),
        ("LogMsg/Severity", "Info"),  # a line without time stamp
        ("LogMsg/Source", "saphostcontrol"),
        ("LogMsg/Text", "Sync hook successfully executed"),
    ]
    lines = log_messages(entries)
    assert [line.text for line in lines] == [
        "BEGIN",
        "careful",
        "a line without LogMsg",
        "Sync hook successfully executed",
    ]
    assert lines[1].severity == "Warning"
    assert lines[3].display == "saphostcontrol: Sync hook successfully executed"


async def test_get_operation_results_answers_get_operation_response(landscape):
    """The WSDL and a real host agent name the response GetOperationResponse."""
    from landscape_orchestrator.mock.soap import build_response

    body = build_response("SAPHostControl", "urn:SAPHostControl", "GetOperationResults", {})
    assert b"GetOperationResponse" in body and b"GetOperationResultsResponse" not in body


async def test_register_and_unregister_instance_service(landscape):
    instance = landscape.host("sapapp1").instance(0)
    async with make_client(landscape) as client:
        result = await client.unregister_instance_service("DEV", 0, hostname="sapapp1")
        assert not instance.service_running
        # Lines as a real host agent returned them (four LogMsg/* messages per line).
        assert [(m.severity, m.source, m.text) for m in result.log][-1] == (
            "Info",
            "saphostcontrol",
            "'sapstartsrv -unreg' successfully executed",
        )
        result = await client.register_instance_service("DEV", "00", hostname="sapapp1")
        assert instance.service_running
        assert "Executing 'sapstartsrv -reg'" in [m.text for m in result.log]
    async with make_client(landscape, auth=None) as anonymous:
        with pytest.raises(AuthenticationRequiredError):
            await anonymous.register_instance_service("DEV", 0)

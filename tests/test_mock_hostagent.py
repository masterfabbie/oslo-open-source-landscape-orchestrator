from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import AUTH, soap_call
from oslo.mock.apps import create_hostagent_app

NS = "urn:SAPHostControl"
INSTANCE_00 = "<aInstance><mSid>DEV</mSid><mSystemNumber>00</mSystemNumber></aInstance>"


@pytest.fixture
def client(landscape) -> TestClient:
    return TestClient(create_hostagent_app(landscape, "sapapp1"))


def listed(client: TestClient, selector: str | None = None) -> list[str]:
    params = (
        f"<aSelector><aInstanceStatus>{selector}</aInstanceStatus></aSelector>" if selector else ""
    )
    status, result = soap_call(client, NS, "ListInstances", params)
    assert status == 200
    return sorted(item.findtext("mSystemNumber") for item in result.find("aInstances"))


def test_list_instances(client):
    status, result = soap_call(client, NS, "ListInstances")
    assert status == 200
    first = result.find("aInstances")[0]
    assert first.findtext("mSid") == "DEV"
    assert first.findtext("mHostname") == "sapapp1"
    assert listed(client) == ["00", "01"]


def test_list_instances_filters_by_status(client, clock):
    assert listed(client, "S-RUNNING") == []
    assert listed(client, "S-STOPPED") == ["00", "01"]

    status, result = soap_call(client, NS, "StartInstance", INSTANCE_00, auth=AUTH)
    assert status == 200
    message = result.find("response/mOperationResults")[0]
    assert "Start of instance DEV/00" in message.findtext("mMessageValue")
    clock.advance(3)
    assert listed(client, "S-RUNNING") == ["00"]
    assert listed(client, "S-STOPPED") == ["01"]

    soap_call(client, NS, "StopInstance", INSTANCE_00, auth=AUTH)
    clock.advance(2)
    assert listed(client, "S-RUNNING") == []


def test_start_instance_requires_credentials(client):
    status, _ = soap_call(client, NS, "StartInstance", INSTANCE_00)
    assert status == 401
    assert listed(client, "S-RUNNING") == []


def test_start_unknown_instance_returns_fault(client):
    params = "<aInstance><mSid>DEV</mSid><mSystemNumber>77</mSystemNumber></aInstance>"
    status, fault = soap_call(client, NS, "StartInstance", params, auth=AUTH)
    assert status == 500
    assert "not found" in fault.findtext("faultstring")


def test_get_computer_system(client):
    _, result = soap_call(client, NS, "GetComputerSystem")

    def attributes(cim_object) -> dict[str, str]:
        return {p.findtext("mName"): p.findtext("mValue") for p in cim_object.find("mProperties")}

    system = attributes(result.find("result"))
    assert system["CreationClassName"] == "ITSAMComputerSystem"
    assert system["Name"] == "sapapp1"
    assert system["Hostnames"] == "sapapp1;"
    members = [attributes(member) for member in result.find("result/mMembers")]
    assert [m["CreationClassName"] for m in members] == [
        "ITSAMOperatingSystem",
        "ITSAMFileSystem",
    ]


def test_databases_on_database_host(landscape, clock):
    client = TestClient(create_hostagent_app(landscape, "sapdb1"))

    _, result = soap_call(client, NS, "ListDatabases")
    assert len(result.find("result")) == 2
    database = result.find("result")[1]
    properties = {p.findtext("mKey"): p.findtext("mValue") for p in database.find("mDatabase")}
    assert properties["Database/Name"] == "HDV@HDV"
    assert properties["Database/Type"] == "hdb"
    assert properties["Database/InstanceName"] == "HDB02"
    assert properties["Database/Host"] == "sapdb1"
    assert database.findtext("mStatus") == "SAPHostControl-DB-STOPPED"
    assert len(database.find("mComponents")) == 3

    hdb = "<aInstance><mSid>HDV</mSid><mSystemNumber>02</mSystemNumber></aInstance>"
    soap_call(client, NS, "StartInstance", hdb, auth=AUTH)
    arguments = (
        "<aArguments><item><mKey>Database/Name</mKey><mValue>HDV@HDV</mValue></item></aArguments>"
    )
    _, result = soap_call(client, NS, "GetDatabaseStatus", arguments)
    assert result.findtext("status") == "SAPHostControl-DB-STARTING"
    clock.advance(3)
    _, result = soap_call(client, NS, "GetDatabaseStatus", arguments)
    assert result.findtext("status") == "SAPHostControl-DB-RUNNING"
    component = result.find("result")[0]
    assert component.findtext("mStatus") == "SAPHostControl-DB-RUNNING"
    details = {p.findtext("mKey"): p.findtext("mValue") for p in component.find("mProperties")}
    assert details == {
        "Database/ComponentName": "hdbdaemon",
        "Database/ComponentDescription": "HDB Daemon",
        "Database/ComponentStatusDescription": "Running",
    }


def test_host_without_databases_returns_empty_list(client):
    status, result = soap_call(client, NS, "ListDatabases")
    assert status == 200
    assert len(result.find("result")) == 0


def test_unknown_database_returns_fault(client):
    arguments = (
        "<aArguments><item><mKey>Database/Name</mKey><mValue>XXX</mValue></item></aArguments>"
    )
    status, fault = soap_call(client, NS, "GetDatabaseStatus", arguments)
    assert status == 500
    assert "not found" in fault.findtext("faultstring")


def test_list_instances_rejects_unknown_status(client):
    params = "<aSelector><aInstanceStatus>S-INSTANCE-ALL</aInstanceStatus></aSelector>"
    status, fault = soap_call(client, NS, "ListInstances", params)
    assert status == 500
    assert "Invalid instance status" in fault.findtext("faultstring")


def test_list_instances_filters_by_hostname(client):
    params = (
        "<aSelector><aInstanceStatus>S-INSTALLED</aInstanceStatus>"
        "<aHostname>otherhost</aHostname></aSelector>"
    )
    _, result = soap_call(client, NS, "ListInstances", params)
    assert len(result.find("aInstances")) == 0

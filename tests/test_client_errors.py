from __future__ import annotations

import httpx
import pytest

from oslo.clients import (
    AuthenticationRequiredError,
    PermissionDeniedError,
    SapControlClient,
    SoapConnectionError,
    SoapFaultError,
    SoapProtocolError,
)

pytestmark = pytest.mark.anyio

ENVELOPE = (
    '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" '
    'xmlns:SAPControl="urn:SAPControl"><SOAP-ENV:Body>{body}</SOAP-ENV:Body></SOAP-ENV:Envelope>'
)


def client_answering(status: int, content: str) -> SapControlClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=content.encode())

    return SapControlClient("host1", 0, transport=httpx.MockTransport(handler))


def fault(faultstring: str) -> str:
    body = (
        "<SOAP-ENV:Fault><faultcode>SOAP-ENV:Server</faultcode>"
        f"<faultstring>{faultstring}</faultstring></SOAP-ENV:Fault>"
    )
    return ENVELOPE.format(body=body)


async def test_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with SapControlClient("host1", 0, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SoapConnectionError, match="connection refused"):
            await client.get_process_list()


async def test_timeout_is_a_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow")

    async with SapControlClient("host1", 0, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SoapConnectionError, match="timeout calling GetProcessList"):
            await client.get_process_list()


async def test_non_xml_answer_is_a_protocol_error():
    async with client_answering(200, "<html>proxy login page") as client:
        with pytest.raises(SoapProtocolError, match="HTTP 200"):
            await client.get_process_list()


async def test_plain_401_without_soap_body():
    async with client_answering(401, "Unauthorized") as client:
        with pytest.raises(AuthenticationRequiredError):
            await client.start()


async def test_response_for_another_method_is_a_protocol_error():
    answer = ENVELOPE.format(body="<SAPControl:StopResponse/>")
    async with client_answering(200, answer) as client:
        with pytest.raises(SoapProtocolError, match="expected StartResponse"):
            await client.start()


async def test_permission_denied_fault():
    async with client_answering(500, fault("Permission denied")) as client:
        with pytest.raises(PermissionDeniedError):
            await client.start()


async def test_generic_fault_keeps_details():
    async with client_answering(500, fault("DpIPCInit failed")) as client:
        with pytest.raises(SoapFaultError) as error:
            await client.get_process_list()
    assert error.value.faultstring == "DpIPCInit failed"
    assert error.value.faultcode == "SOAP-ENV:Server"
    assert error.value.http_status == 500


async def test_unknown_state_color_is_a_protocol_error():
    process = (
        "<SAPControl:GetProcessListResponse><process><item><name>x</name>"
        "<dispstatus>SAPControl-PURPLE</dispstatus><pid>1</pid></item></process>"
        "</SAPControl:GetProcessListResponse>"
    )
    async with client_answering(200, ENVELOPE.format(body=process)) as client:
        with pytest.raises(SoapProtocolError, match="Unknown state color"):
            await client.get_process_list()


async def test_xml_with_entity_expansion_is_rejected():
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;">]><a>&lol2;</a>'
    )
    async with client_answering(200, bomb) as client:
        with pytest.raises(SoapProtocolError):
            await client.get_process_list()


async def test_request_format():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        seen["soapaction"] = request.headers["SOAPAction"]
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, content=ENVELOPE.format(body="<SAPControl:StopResponse/>"))

    transport = httpx.MockTransport(handler)
    async with SapControlClient("host1", 0, auth=("u", "p"), transport=transport) as client:
        await client.stop(softtimeout=30)

    assert seen["url"] == "http://host1:50013/"
    assert seen["soapaction"] == '""'
    assert seen["authorization"] == "Basic dTpw"
    assert 'xmlns:SAPControl="urn:SAPControl"' in seen["body"]
    assert "<SAPControl:Stop><softtimeout>30</softtimeout></SAPControl:Stop>" in seen["body"]

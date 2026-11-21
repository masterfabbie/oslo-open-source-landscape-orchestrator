"""SOAP request parsing and response building for the mock services."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from ..soapxml import (
    SOAP_ENV,
    XmlError,
    build_element,
    envelope,
    items,
    local,
    parse_envelope,
    response_name,
    to_value,
)

__all__ = ["SoapFault", "build_fault", "build_response", "items", "parse_request"]


class SoapFault(Exception):
    def __init__(
        self,
        faultstring: str,
        faultcode: str = "SOAP-ENV:Server",
        http_status: int = 500,
        detail: tuple[str, str, dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(faultstring)
        self.faultstring = faultstring
        self.faultcode = faultcode
        self.http_status = http_status
        # (namespace, element name, content) of the fault detail, e.g. OperationException.
        self.detail = detail


def parse_request(body: bytes) -> tuple[str, dict[str, Any]]:
    """Return (method name, parameters) of a SOAP request."""
    try:
        call = parse_envelope(body)
    except XmlError as exc:
        raise SoapFault("Invalid SOAP request", "SOAP-ENV:Client") from exc
    params = to_value(call)
    return local(call.tag), params if isinstance(params, dict) else {}


def build_response(prefix: str, namespace: str, method: str, payload: dict[str, Any]) -> bytes:
    ET.register_namespace(prefix, namespace)
    return envelope(build_element(namespace, response_name(method), payload))


def build_fault(fault: SoapFault) -> bytes:
    element = ET.Element(f"{{{SOAP_ENV}}}Fault")
    ET.SubElement(element, "faultcode").text = fault.faultcode
    ET.SubElement(element, "faultstring").text = fault.faultstring
    if fault.detail is not None:
        namespace, name, content = fault.detail
        ET.SubElement(element, "detail").append(build_element(namespace, name, content))
    return envelope(element)

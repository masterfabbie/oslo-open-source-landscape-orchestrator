"""SOAP 1.1 envelope handling shared by the clients and the mock services.

Values map to XML as used by the gSOAP services of SAP: a dict becomes nested elements,
a list becomes a sequence of ``<item>`` elements, ``None`` omits the element.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
SAPCONTROL_NS = "urn:SAPControl"
SAPHOSTCONTROL_NS = "urn:SAPHostControl"

# Fixed prefixes keep the generated XML stable and match what the SAP tools send.
ET.register_namespace("SOAP-ENV", SOAP_ENV)
ET.register_namespace("SAPControl", SAPCONTROL_NS)
ET.register_namespace("SAPHostControl", SAPHOSTCONTROL_NS)


class XmlError(ValueError):
    """The data is not a usable SOAP envelope."""


# Response elements whose name is not "<method>Response" (from the WSDL of the host agent:
# GetOperationResults answers with GetOperationResponse, confirmed with a real host agent).
RESPONSE_ELEMENTS = {"GetOperationResults": "GetOperationResponse"}


def response_name(method: str) -> str:
    return RESPONSE_ELEMENTS.get(method, f"{method}Response")


def local(tag: str) -> str:
    """Element name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def to_value(element: ET.Element) -> Any:
    """Convert an element to a string (leaf) or dict; repeated child tags become lists."""
    if len(element) == 0:
        return (element.text or "").strip()
    result: dict[str, Any] = {}
    for child in element:
        key, value = local(child.tag), to_value(child)
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value
    return result


def items(value: Any) -> list[Any]:
    """Normalize a SOAP array (``<x><item>..</item><item>..</item></x>``) to a list."""
    if not isinstance(value, dict) or "item" not in value:
        return []
    item = value["item"]
    return item if isinstance(item, list) else [item]


def append_value(parent: ET.Element, name: str, value: Any) -> None:
    if value is None:
        return
    element = ET.SubElement(parent, name)
    if isinstance(value, dict):
        for key, child in value.items():
            append_value(element, key, child)
    elif isinstance(value, list | tuple):
        for child in value:
            append_value(element, "item", child)
    elif isinstance(value, bool):
        element.text = "true" if value else "false"
    else:
        element.text = str(value)


def build_element(namespace: str, name: str, payload: dict[str, Any] | None) -> ET.Element:
    """Namespace-qualified element with unqualified children built from ``payload``."""
    element = ET.Element(f"{{{namespace}}}{name}")
    for key, value in (payload or {}).items():
        append_value(element, key, value)
    return element


def envelope(body_child: ET.Element) -> bytes:
    root = ET.Element(f"{{{SOAP_ENV}}}Envelope")
    ET.SubElement(root, f"{{{SOAP_ENV}}}Body").append(body_child)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def parse_envelope(data: bytes) -> ET.Element:
    """Return the first child of the SOAP body."""
    try:
        root = SafeET.fromstring(data)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise XmlError("Not well-formed XML") from exc
    body = root.find(f"{{{SOAP_ENV}}}Body")
    if body is None or len(body) == 0:
        raise XmlError("SOAP body is missing or empty")
    return body[0]

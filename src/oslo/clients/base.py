"""Common SOAP transport and error handling for the SAP web service clients."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import httpx

from ..soapxml import (
    SOAP_ENV,
    XmlError,
    build_element,
    envelope,
    local,
    parse_envelope,
    response_name,
    to_value,
)


class SoapError(Exception):
    """Base class for all errors raised by the clients."""


class SoapConnectionError(SoapError):
    """The service could not be reached or did not answer in time."""


class SoapProtocolError(SoapError):
    """The service answered with something that is not a valid response."""


class SoapFaultError(SoapError):
    """The service reported an error as a SOAP fault."""

    def __init__(
        self,
        faultstring: str,
        faultcode: str = "",
        http_status: int = 500,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(faultstring)
        self.faultstring = faultstring
        self.faultcode = faultcode
        self.http_status = http_status
        # Content of the first element of <detail>, e.g. the OperationException of the host
        # agent with mFaultCode, mMessage, mOperationID and mResponseMessages.
        self.detail = detail or {}


class AuthenticationRequiredError(SoapFaultError):
    """A protected method was called without credentials (HTTP 401)."""


class InvalidCredentialsError(SoapFaultError):
    """User or password were rejected."""


class PermissionDeniedError(SoapFaultError):
    """The user is known but not authorized for the method."""


_FAULT_CLASSES = {
    "invalid credentials": InvalidCredentialsError,
    "permission denied": PermissionDeniedError,
}


class SoapClient:
    """Calls methods of one SOAP endpoint. Use as an async context manager."""

    namespace: str
    path: str = "/"

    def __init__(
        self,
        base_url: str,
        *,
        auth: tuple[str, str] | None = None,
        verify: bool | str = True,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url
        self._http = httpx.AsyncClient(
            base_url=base_url,
            auth=auth,
            verify=verify,
            timeout=timeout,
            transport=transport,
            trust_env=False,  # managed hosts are addressed directly, never through a proxy
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call ``method`` and return the content of its response element as a dict."""
        request = envelope(build_element(self.namespace, method, params))
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'}
        try:
            response = await self._http.post(self.path, content=request, headers=headers)
        except httpx.TimeoutException as exc:
            raise SoapConnectionError(f"{self.base_url}: timeout calling {method}") from exc
        except httpx.TransportError as exc:
            raise SoapConnectionError(f"{self.base_url}: {exc}") from exc

        try:
            result = parse_envelope(response.content)
        except XmlError as exc:
            if response.status_code == 401:
                raise AuthenticationRequiredError("Unauthorized", http_status=401) from exc
            raise SoapProtocolError(
                f"{self.base_url}: HTTP {response.status_code} without SOAP content for {method}"
            ) from exc

        if result.tag == f"{{{SOAP_ENV}}}Fault":
            raise self._fault(result, response.status_code)
        expected = response_name(method)
        if local(result.tag) != expected:
            raise SoapProtocolError(
                f"{self.base_url}: expected {expected}, got {local(result.tag)}"
            )
        value = to_value(result)
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _fault(fault: Any, http_status: int) -> SoapFaultError:
        faultstring = (fault.findtext("faultstring") or "").strip()
        faultcode = (fault.findtext("faultcode") or "").strip()
        if http_status == 401:
            cls: type[SoapFaultError] = AuthenticationRequiredError
        else:
            cls = _FAULT_CLASSES.get(faultstring.lower(), SoapFaultError)
        detail: dict[str, Any] = {}
        container = fault.find("detail")
        if container is not None and len(container):
            value = to_value(container[0])
            detail = value if isinstance(value, dict) else {}
        return cls(faultstring or "Unknown SOAP fault", faultcode, http_status, detail)


def as_dict(value: Any) -> dict[str, Any]:
    """A nested element as dict; an empty or missing element becomes an empty dict."""
    return value if isinstance(value, dict) else {}


def as_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SoapProtocolError(f"Field {field!r} is not a number: {value!r}") from exc

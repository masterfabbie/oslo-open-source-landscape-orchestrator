"""SOAP clients for the SAP Host Agent and sapstartsrv."""

from .base import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    PermissionDeniedError,
    SoapConnectionError,
    SoapError,
    SoapFaultError,
    SoapProtocolError,
)
from .hostagent import HostAgentClient
from .sapcontrol import SapControlClient

__all__ = [
    "AuthenticationRequiredError",
    "HostAgentClient",
    "InvalidCredentialsError",
    "PermissionDeniedError",
    "SapControlClient",
    "SoapConnectionError",
    "SoapError",
    "SoapFaultError",
    "SoapProtocolError",
]

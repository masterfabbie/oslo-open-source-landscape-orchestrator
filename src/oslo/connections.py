"""Builds SOAP clients for inventory entries, including their stored credentials."""

from __future__ import annotations

import httpx

from .clients import HostAgentClient, SapControlClient
from .clients.sapcontrol import sapcontrol_port
from .crypto import SecretBox
from .models import Host, Sid


class ClientFactory:
    def __init__(
        self,
        secrets: SecretBox,
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._secrets = secrets
        self._timeout = timeout
        # Only set in tests and local development, to reach the simulated landscape.
        self._transport = transport

    def _auth(self, *owners: Host | Sid | None) -> tuple[str, str] | None:
        """Credentials of the first owner that has any."""
        for owner in owners:
            if owner is not None and owner.username and owner.password_encrypted:
                return owner.username, self._secrets.decrypt(owner.password_encrypted)
        return None

    def hostagent(self, host: Host) -> HostAgentClient:
        return HostAgentClient(
            host.address,
            port=host.hostagent_port,
            https=host.https,
            verify=host.verify_tls,
            auth=self._auth(host),
            timeout=self._timeout,
            transport=self._transport,
        )

    def sapcontrol(
        self, host: Host, instance_number: int, sid: Sid | None = None
    ) -> SapControlClient:
        port = sapcontrol_port(instance_number, host.https) + host.sapcontrol_port_offset
        return SapControlClient(
            host.address,
            instance_number,
            port=port,
            https=host.https,
            verify=host.verify_tls,
            auth=self._auth(sid, host),
            timeout=self._timeout,
            transport=self._transport,
        )

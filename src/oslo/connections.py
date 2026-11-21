"""Builds SOAP clients for inventory entries, including their stored credentials."""

from __future__ import annotations

import ssl

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .clients import HostAgentClient, SapControlClient
from .clients.sapcontrol import sapcontrol_port
from .crypto import SecretBox
from .models import Host, Sid, TrustedCertificate
from .tls import client_context


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
        # PEM texts of Administration → Certificates; see load_trusted().
        self._trusted: list[str] = []
        self._contexts: dict[bool, ssl.SSLContext] = {}

    async def load_trusted(self, session: AsyncSession) -> None:
        """Read the trusted certificates again, at start and after every change."""
        self.set_trusted(list(await session.scalars(select(TrustedCertificate.pem))))

    @property
    def trusted(self) -> list[str]:
        return list(self._trusted)

    def set_trusted(self, pems: list[str]) -> None:
        self._trusted = pems
        self._contexts.clear()

    def _verify(self, host: Host) -> bool | ssl.SSLContext:
        """False without checking, else a context with the system store and the trusted
        certificates. Built once per hostname setting, since loading the store takes time."""
        if not host.https or not host.verify_tls:
            return False
        check_hostname = host.verify_hostname is not False
        context = self._contexts.get(check_hostname)
        if context is None:
            context = client_context(self._trusted, check_hostname=check_hostname)
            self._contexts[check_hostname] = context
        return context

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
            verify=self._verify(host),
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
            verify=self._verify(host),
            auth=self._auth(sid, host),
            timeout=self._timeout,
            transport=self._transport,
        )

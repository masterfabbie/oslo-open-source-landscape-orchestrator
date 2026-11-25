"""Trusted certificates (Administration → Certificates), checking HTTPS to hosts with them,
and reading the certificate a host shows. Uses real TLS servers on 127.0.0.1."""

from __future__ import annotations

import asyncio
import ssl
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

import test_mass
from conftest import make_user
from oslo.connections import ClientFactory
from oslo.crypto import SecretBox, generate_secret_key
from oslo.models import Host
from oslo.tls import CertificateError, fetch_certificate, parse_pem
from test_mass import client

pytestmark = pytest.mark.anyio

app, transport = test_mass.app, test_mass.transport


def self_signed(name: str = "sapapp1", *, ip: bool = True, days: int = 30) -> tuple[str, str]:
    """A self-signed certificate (PEM) and its key, like the one a host agent may show.
    Without the CA flag; ``ip`` puts 127.0.0.1 into the names of the certificate."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    names: list[x509.GeneralName] = [x509.DNSName(name)]
    if ip:
        names.append(x509.IPAddress(IPv4Address("127.0.0.1")))
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return pem, key_pem


class TlsServer:
    """Answers every request with 200 over HTTPS."""

    def __init__(self, tmp_path: Path, pem: str, key: str) -> None:
        (tmp_path / "cert.pem").write_text(pem)
        (tmp_path / "key.pem").write_text(key)
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(tmp_path / "cert.pem", tmp_path / "key.pem")
        self.server: asyncio.Server | None = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
            await writer.drain()
        except (OSError, asyncio.IncompleteReadError, ssl.SSLError):
            pass
        finally:
            writer.close()

    async def __aenter__(self) -> int:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0, ssl=self.context)
        return self.server.sockets[0].getsockname()[1]

    async def __aexit__(self, *exc: object) -> None:
        assert self.server is not None
        self.server.close()


async def get(verify: bool | ssl.SSLContext, url: str) -> int:
    async with httpx.AsyncClient(verify=verify, trust_env=False) as http:
        return (await http.get(url)).status_code


def test_parse_pem():
    pem, key = self_signed()
    info = parse_pem(pem)
    assert info.subject == "CN=sapapp1" and info.self_signed and not info.expired()
    assert len(info.fingerprint) == 95 and info.fingerprint.count(":") == 31
    for text, message in (
        (pem + key, "private key"),
        ("not a certificate", "PEM"),
        (pem + self_signed("sapdb1")[0], "one certificate"),
    ):
        with pytest.raises(CertificateError, match=message):
            parse_pem(text)


async def test_trusted_certificates_make_https_checks_pass(tmp_path):
    pem, key = self_signed()
    factory = ClientFactory(SecretBox(generate_secret_key()))
    host = Host(name="sapapp1", address="127.0.0.1", https=True, verify_tls=True)
    host.verify_hostname = True
    async with TlsServer(tmp_path, pem, key) as port:
        url = f"https://127.0.0.1:{port}/"
        # Only the system's store: the self-signed certificate is refused.
        with pytest.raises(httpx.ConnectError, match="CERTIFICATE_VERIFY_FAILED"):
            await get(factory._verify(host), url)
        factory.set_trusted([pem])
        assert await get(factory._verify(host), url) == 200
        # Without the check, any certificate goes.
        host.verify_tls = False
        assert factory._verify(host) is False
        assert await get(factory._verify(host), url) == 200


async def test_host_name_check_can_be_switched_off(tmp_path):
    pem, key = self_signed(ip=False)  # names only "sapapp1", the host is reached by IP
    factory = ClientFactory(SecretBox(generate_secret_key()))
    factory.set_trusted([pem])
    host = Host(name="sapapp1", address="127.0.0.1", https=True, verify_tls=True)
    host.verify_hostname = True
    async with TlsServer(tmp_path, pem, key) as port:
        url = f"https://127.0.0.1:{port}/"
        with pytest.raises(httpx.ConnectError, match="CERTIFICATE_VERIFY_FAILED"):
            await get(factory._verify(host), url)
        host.verify_hostname = False
        assert await get(factory._verify(host), url) == 200
    # Plain HTTP never gets a context.
    host.https = False
    assert factory._verify(host) is False


async def test_fetch_certificate(tmp_path):
    pem, key = self_signed()
    async with TlsServer(tmp_path, pem, key) as port:
        info = await fetch_certificate("127.0.0.1", port)
    assert info.fingerprint == parse_pem(pem).fingerprint and info.subject == "CN=sapapp1"
    with pytest.raises(CertificateError, match="No TLS connection"):
        await fetch_certificate("127.0.0.1", port, timeout=2)


async def test_certificates_in_the_api(app, tmp_path):
    pem, key = self_signed()
    async with client(app, await make_user(app)) as admin:
        check = await admin.post("/api/trusted-certificates/check", json={"name": "x", "pem": pem})
        assert check.status_code == 200 and check.json()["self_signed"] is True
        bad = await admin.post("/api/trusted-certificates", json={"name": "x", "pem": pem + key})
        assert bad.status_code == 422 and "private key" in bad.text

        added = await admin.post(
            "/api/trusted-certificates", json={"name": " Host agent sapapp1 ", "pem": pem}
        )
        assert added.status_code == 201, added.text
        cert = added.json()
        assert cert["name"] == "Host agent sapapp1" and cert["created_by"] == "admin"
        assert cert["subject"] == "CN=sapapp1" and cert["expired"] is False
        again = await admin.post("/api/trusted-certificates", json={"name": "y", "pem": pem})
        assert again.status_code == 409 and "Host agent sapapp1" in again.text
        listed = (await admin.get("/api/trusted-certificates")).json()
        assert [c["fingerprint"] for c in listed] == [cert["fingerprint"]]
        # The client factory uses it right away.
        assert pem.strip() in "".join(app.state.clients.trusted)

        # The certificate a host shows, and whether it is trusted already.
        async with TlsServer(tmp_path, *self_signed("sapdb1")) as port:
            body = {"name": "sapdb1", "address": "127.0.0.1", "hostagent_port": port}
            host = (await admin.post("/api/hosts", json=body | {"https": True})).json()
            assert host["verify_hostname"] is True
            shown = await admin.post(f"/api/hosts/{host['id']}/certificate")
            assert shown.status_code == 200, shown.text
            assert shown.json()["subject"] == "CN=sapdb1" and shown.json()["trusted_id"] is None
        async with TlsServer(tmp_path, pem, key) as port:
            await admin.patch(f"/api/hosts/{host['id']}", json={"hostagent_port": port})
            shown = (await admin.post(f"/api/hosts/{host['id']}/certificate")).json()
            assert shown["trusted_id"] == cert["id"]
        unreachable = await admin.post(f"/api/hosts/{host['id']}/certificate")
        assert unreachable.status_code == 502

        changed = await admin.patch(f"/api/hosts/{host['id']}", json={"verify_hostname": False})
        assert changed.status_code == 200 and changed.json()["verify_hostname"] is False

        assert (await admin.delete(f"/api/trusted-certificates/{cert['id']}")).status_code == 204
        assert (await admin.get("/api/trusted-certificates")).json() == []
        assert app.state.clients.trusted == []
        missing = await admin.delete(f"/api/trusted-certificates/{cert['id']}")
        assert missing.status_code == 404

    # Only admins manage them; a configurator may read the certificate of a host.
    async with client(app, await make_user(app, "conf", "configurator")) as conf:
        assert (await conf.get("/api/trusted-certificates")).status_code == 403
        denied = await conf.post("/api/trusted-certificates", json={"name": "x", "pem": pem})
        assert denied.status_code == 403
        assert (await conf.post(f"/api/hosts/{host['id']}/certificate")).status_code == 502
    async with client(app, await make_user(app, "op", "operator")) as op:
        assert (await op.post(f"/api/hosts/{host['id']}/certificate")).status_code == 403


async def test_trusted_certificates_are_loaded_at_start(tmp_path, landscape, clock):
    from oslo.api import create_app
    from oslo.settings import Settings

    pem, _ = self_signed()
    settings = Settings(
        secret_key=generate_secret_key(), database_url=f"sqlite+aiosqlite:///{tmp_path / 'c.db'}"
    )
    first = create_app(settings)
    async with first.router.lifespan_context(first):
        async with client(first, await make_user(first)) as admin:
            await admin.post("/api/trusted-certificates", json={"name": "a", "pem": pem})
    second = create_app(settings)
    async with second.router.lifespan_context(second):
        assert [p.strip() for p in second.state.clients.trusted] == [pem.strip()]


def test_https_of_a_host_is_for_the_host_agent_only():
    factory = ClientFactory(SecretBox(generate_secret_key()))
    host = Host(name="sapapp1", address="sapapp1", https=True, verify_tls=True)
    host.sapcontrol_port_offset = 0
    host.verify_hostname = True
    assert factory.hostagent(host).base_url.startswith("https://sapapp1:1129")
    assert factory.sapcontrol(host, 1).base_url == "http://sapapp1:50113"

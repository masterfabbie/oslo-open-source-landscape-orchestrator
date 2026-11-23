"""HTTPS for OSLO itself: certificates created on the server (self-signed or by a CSR for an
own CA), Administration → HTTPS, the start options of oslo-server and the rule for an
expiring certificate."""

from __future__ import annotations

import argparse
import asyncio
import ssl
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

import test_mass
from conftest import make_user
from oslo import servertls
from oslo.crypto import SecretBox, generate_secret_key
from oslo.server import tls_files
from oslo.servertls import TlsError
from oslo.settings import Settings
from test_mass import client

pytestmark = pytest.mark.anyio

app, api, transport = test_mass.app, test_mass.api, test_mass.transport


class OwnCa:
    """A CA that signs requests, like the CA of a customer."""

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
        now = datetime.now(UTC)
        self.cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(self.key, hashes.SHA256())
        )

    def sign(self, csr_pem: str, days: int = 20) -> str:
        csr = x509.load_pem_x509_csr(csr_pem.encode())
        now = datetime.now(UTC)
        alt = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        cert = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(self.cert.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=days))
            .add_extension(alt, critical=False)
            .sign(self.key, hashes.SHA256())
        )
        return (cert.public_bytes(serialization.Encoding.PEM) + self.pem.encode()).decode()

    @property
    def pem(self) -> str:
        return self.cert.public_bytes(serialization.Encoding.PEM).decode()


def test_self_signed_certificate():
    key, cert = servertls.self_signed(["oslo.example", "*.oslo.example"], ["127.0.0.1"], days=10)
    state = servertls.describe(cert)
    assert state.names == ["oslo.example", "*.oslo.example", "127.0.0.1"]
    assert state.self_signed and not state.expires_within(5) and state.expires_within(11)
    assert servertls.matching_chain(cert, key)
    for names, ips, days, message in (
        (["bad name!"], [], 10, "host name"),
        ([], ["300.1.1.1"], 10, "IP address"),
        ([" "], [""], 10, "at least one"),
        (["oslo"], [], 0, "validity"),
    ):
        with pytest.raises(TlsError, match=message):
            servertls.self_signed(names, ips, days)
    other_key, _ = servertls.self_signed(["other"], [])
    with pytest.raises(TlsError, match="does not belong"):
        servertls.matching_chain(cert, other_key)
    with pytest.raises(TlsError, match="private key"):
        servertls.matching_chain(cert + key, key)


async def test_https_page_in_the_api(app, api):
    status = (await api.get("/api/tls")).json()
    assert status == {"https": False, "certificate": None, "csr": None}

    # Self-signed: created and stored, used after a restart with --tls.
    created = await api.post(
        "/api/tls/self-signed", json={"names": ["oslo.example"], "ips": ["127.0.0.1"]}
    )
    assert created.status_code == 200, created.text
    first = created.json()["certificate"]
    assert first["self_signed"] and first["names"] == ["oslo.example", "127.0.0.1"]
    assert "PRIVATE" not in created.text
    bad = await api.post("/api/tls/self-signed", json={"names": ["bad name!"]})
    assert bad.status_code == 422

    # Own CA: request, signed certificate with the CA in the chain.
    ca = OwnCa()
    nothing = await api.post("/api/tls/certificate", json={"pem": ca.pem})
    assert nothing.status_code == 422 and "no open" in nothing.text
    request = (await api.post("/api/tls/request", json={"names": ["oslo.example"]})).json()
    assert request["csr"].startswith("-----BEGIN CERTIFICATE REQUEST-----")
    assert request["certificate"]["pem"] == first["pem"]  # the old one stays until then
    wrong = await api.post("/api/tls/certificate", json={"pem": first["pem"]})
    assert wrong.status_code == 422 and "does not belong" in wrong.text
    signed = await api.post("/api/tls/certificate", json={"pem": ca.sign(request["csr"])})
    assert signed.status_code == 200, signed.text
    now = signed.json()
    assert now["csr"] is None and not now["certificate"]["self_signed"]
    assert "Test CA" in now["certificate"]["issuer"]

    # Discarding a request keeps the certificate.
    await api.post("/api/tls/request", json={"ips": ["127.0.0.1"]})
    dropped = (await api.delete("/api/tls/request")).json()
    assert (
        dropped["csr"] is None and dropped["certificate"]["issuer"] == now["certificate"]["issuer"]
    )

    # The certificate expires within 20 days: the rule (30 days) warns.
    attention = (await api.get("/api/overview")).json()["attention"]
    assert [i["key"] for i in attention if i["rule"] == "tls_expiry"] == ["att.tls_expiring"]

    async with client(app, await make_user(app, "conf", "configurator")) as conf:
        assert (await conf.get("/api/tls")).status_code == 403
        assert (await conf.post("/api/tls/self-signed", json={"names": ["x"]})).status_code == 403


async def test_hsts_only_over_https(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://oslo.example"
    ) as secure:
        assert "strict-transport-security" in (await secure.get("/login")).headers
    async with client(app) as plain:
        assert "strict-transport-security" not in (await plain.get("/login")).headers


def options(**values) -> argparse.Namespace:
    return argparse.Namespace(
        tls=values.get("tls", False),
        ssl_certfile=values.get("certfile"),
        ssl_keyfile=values.get("keyfile"),
    )


async def serve_and_get(certfile: str, keyfile: str, ca: str) -> int:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile, keyfile)

    async def handle(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=context)
    port = server.sockets[0].getsockname()[1]
    try:
        verify = ssl.create_default_context(cadata=ca)
        async with httpx.AsyncClient(verify=verify, trust_env=False) as http:
            return (await http.get(f"https://127.0.0.1:{port}/")).status_code
    finally:
        server.close()


def test_server_start_options(tmp_path, monkeypatch):
    settings = Settings(
        secret_key=generate_secret_key(), database_url=f"sqlite+aiosqlite:///{tmp_path / 'o.db'}"
    )
    monkeypatch.setenv("OSLO_SECRET_KEY", settings.secret_key)
    monkeypatch.setenv("OSLO_DATABASE_URL", settings.database_url)
    assert tls_files(options(), settings, {}) == (None, None)  # plain HTTP
    with pytest.raises(TlsError, match="No certificate is stored"):
        tls_files(options(tls=True), settings, {})

    # oslo-tls-cert stores a certificate; --tls (or OSLO_TLS=1) serves it.
    servertls.main(["--ip", "127.0.0.1", "--out", str(tmp_path / "oslo.pem")])
    certfile, keyfile = tls_files(options(), settings, {"OSLO_TLS": "1"})
    assert stat.S_IMODE(Path(keyfile).stat().st_mode) == 0o600
    assert stat.S_IMODE(Path(keyfile).parent.stat().st_mode) == 0o700
    ca = (tmp_path / "oslo.pem").read_text()
    assert asyncio.run(serve_and_get(certfile, keyfile, ca)) == 200
    # Once read, the written files are removed; files of the administrator stay.
    own = tmp_path / "own.pem"
    own.write_text("x")
    servertls.remove_private_files(str(own))
    assert own.exists()
    servertls.remove_private_files(certfile)
    assert not Path(certfile).parent.exists()
    certfile, keyfile = tls_files(options(tls=True), settings, {})

    # Files given on the command line win; both are needed.
    assert tls_files(options(tls=True, certfile=certfile, keyfile=keyfile), settings, {}) == (
        certfile,
        keyfile,
    )
    with pytest.raises(TlsError, match="both"):
        tls_files(options(certfile=certfile), settings, {})
    with pytest.raises(TlsError, match="does not exist"):
        tls_files(options(certfile="/nonexistent", keyfile=keyfile), settings, {})

    # Another secret key cannot read the stored key.
    other = Settings(secret_key=generate_secret_key(), database_url=settings.database_url)
    with pytest.raises(TlsError, match="OSLO_SECRET_KEY"):
        tls_files(options(tls=True), other, {})


def test_stored_key_is_encrypted(tmp_path):
    async def run():
        from oslo.db import create_engine, create_session_factory, upgrade_database
        from oslo.models import PlatformSetting

        url = f"sqlite+aiosqlite:///{tmp_path / 'k.db'}"
        engine = create_engine(url)
        await upgrade_database(engine, url)
        box = SecretBox(generate_secret_key())
        async with create_session_factory(engine)() as session:
            await servertls.store_self_signed(session, box, ["oslo"], [], 30)
            await session.commit()
            stored = (await session.get(PlatformSetting, servertls.KEY_SETTING)).value
            key, chain = await servertls.load_key_and_chain(session, box)
        await engine.dispose()
        return stored, key, chain

    stored, key, chain = asyncio.run(run())
    assert "PRIVATE KEY" not in stored and "PRIVATE KEY" in key
    assert servertls.describe(chain).names == ["oslo"]

"""HTTPS for OSLO itself (Administration → HTTPS, ``oslo-server --tls``).

The private key is always created here and never uploaded: either with a self-signed
certificate, or with a certificate signing request (CSR) that the customer's CA signs; then
only the signed certificate is uploaded. Key and certificate are stored in
``platform_settings``, the key encrypted with ``OSLO_SECRET_KEY`` like the passwords of the
hosts. ``oslo-server --tls`` writes them to a private temporary directory for uvicorn, which
only reads files. Key files that already exist elsewhere are given with ``--ssl-certfile`` and
``--ssl-keyfile`` instead.
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import ipaddress
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from sqlalchemy.ext.asyncio import AsyncSession

from .crypto import SecretBox, SecretError
from .models import PlatformSetting

KEY_SETTING = "tls.key"  # encrypted private key (PEM)
CERT_SETTING = "tls.cert"  # certificate chain (PEM), leaf first
PENDING_KEY_SETTING = "tls.pending_key"  # key of an open CSR, encrypted
CSR_SETTING = "tls.csr"
DEFAULT_DAYS = 730
MAX_DAYS = 3650
_LABEL = r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
# A host name, optionally with "*." in front (wildcard certificate).
_NAME = re.compile(rf"^(?=.{{1,253}}$)(\*\.)?{_LABEL}(\.{_LABEL})*$")
MAX_CHAIN = 64_000


class TlsError(ValueError):
    """Names, certificate or key are not usable."""


@dataclass(frozen=True)
class CertificateState:
    subject: str
    issuer: str
    names: list[str]
    not_before: datetime
    not_after: datetime
    self_signed: bool
    pem: str

    def expires_within(self, days: int, now: datetime | None = None) -> bool:
        return self.not_after < (now or datetime.now(UTC)) + timedelta(days=days)


def _subject_alt_names(names: list[str], ips: list[str]) -> list[x509.GeneralName]:
    result: list[x509.GeneralName] = []
    for name in names:
        name = name.strip()
        if not name:
            continue
        if not _NAME.match(name):
            raise TlsError(f"Not a host name: {name}")
        result.append(x509.DNSName(name))
    for ip in ips:
        ip = ip.strip()
        if not ip:
            continue
        try:
            result.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError as exc:
            raise TlsError(f"Not an IP address: {ip}") from exc
    if not result:
        raise TlsError("Give at least one host name or IP address")
    return result


def _key_pem(key: ec.EllipticCurvePrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _common_name(names: list[str], ips: list[str]) -> str:
    return next((n.strip() for n in [*names, *ips] if n.strip()), "oslo")[:64]


def self_signed(
    names: list[str], ips: list[str], days: int = DEFAULT_DAYS, now: datetime | None = None
) -> tuple[str, str]:
    """A new key (P-256) and a self-signed server certificate: (key PEM, certificate PEM)."""
    if not 1 <= days <= MAX_DAYS:
        raise TlsError(f"The validity must be 1 to {MAX_DAYS} days")
    alt = _subject_alt_names(names, ips)
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _common_name(names, ips))])
    now = now or datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return _key_pem(key), cert.public_bytes(serialization.Encoding.PEM).decode()


def signing_request(names: list[str], ips: list[str]) -> tuple[str, str]:
    """A new key and a certificate signing request for it: (key PEM, CSR PEM)."""
    alt = _subject_alt_names(names, ips)
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _common_name(names, ips))])
        )
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .sign(key, hashes.SHA256())
    )
    return _key_pem(key), csr.public_bytes(serialization.Encoding.PEM).decode()


def _load_chain(pem: str) -> list[x509.Certificate]:
    if len(pem) > MAX_CHAIN:
        raise TlsError("The text is too long for a certificate chain")
    if "PRIVATE KEY" in pem:
        raise TlsError("The text contains a private key; upload only the certificate")
    try:
        chain = x509.load_pem_x509_certificates(pem.strip().encode())
    except ValueError as exc:
        raise TlsError("The text is not a certificate in PEM format") from exc
    return chain


def describe(pem: str) -> CertificateState:
    leaf = _load_chain(pem)[0]
    try:
        alt = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = [str(v) for v in alt.get_values_for_type(x509.DNSName)] + [
            str(v) for v in alt.get_values_for_type(x509.IPAddress)
        ]
    except x509.ExtensionNotFound:
        names = []
    return CertificateState(
        subject=leaf.subject.rfc4514_string(),
        issuer=leaf.issuer.rfc4514_string(),
        names=names,
        not_before=leaf.not_valid_before_utc,
        not_after=leaf.not_valid_after_utc,
        self_signed=leaf.subject == leaf.issuer,
        pem=pem,
    )


def matching_chain(chain_pem: str, key_pem: str) -> str:
    """The chain normalized, if its first certificate belongs to the key; else TlsError."""
    chain = _load_chain(chain_pem)
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    raw = serialization.PublicFormat.SubjectPublicKeyInfo
    mine = key.public_key().public_bytes(serialization.Encoding.DER, raw)
    if chain[0].public_key().public_bytes(serialization.Encoding.DER, raw) != mine:
        raise TlsError("The certificate does not belong to the key of the request")
    if chain[0].not_valid_after_utc < datetime.now(UTC):
        raise TlsError("The certificate has expired")
    return "".join(c.public_bytes(serialization.Encoding.PEM).decode() for c in chain)


# --- storage ---------------------------------------------------------------------------------


async def _get(session: AsyncSession, key: str) -> str:
    row = await session.get(PlatformSetting, key)
    return row.value if row else ""


async def _set(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(PlatformSetting, key)
    if not value:
        if row is not None:
            await session.delete(row)
    elif row is None:
        session.add(PlatformSetting(key=key, value=value))
    else:
        row.value = value


async def store_self_signed(
    session: AsyncSession, box: SecretBox, names: list[str], ips: list[str], days: int
) -> CertificateState:
    """Create and store a self-signed certificate; an open CSR is dropped. Caller commits."""
    key, cert = self_signed(names, ips, days)
    await _set(session, KEY_SETTING, box.encrypt(key))
    await _set(session, CERT_SETTING, cert)
    await _set(session, PENDING_KEY_SETTING, "")
    await _set(session, CSR_SETTING, "")
    return describe(cert)


async def store_request(
    session: AsyncSession, box: SecretBox, names: list[str], ips: list[str]
) -> str:
    """Create a key and a CSR; the current certificate stays in use until the signed one is
    uploaded. Caller commits."""
    key, csr = signing_request(names, ips)
    await _set(session, PENDING_KEY_SETTING, box.encrypt(key))
    await _set(session, CSR_SETTING, csr)
    return csr


async def store_signed(session: AsyncSession, box: SecretBox, chain_pem: str) -> CertificateState:
    """Take the certificate the CA signed for the open CSR. Caller commits."""
    pending = await _get(session, PENDING_KEY_SETTING)
    if not pending:
        raise TlsError("There is no open certificate signing request")
    try:
        key = box.decrypt(pending)
    except SecretError as exc:
        raise TlsError("The key of the request cannot be read; create a new request") from exc
    chain = matching_chain(chain_pem, key)
    await _set(session, KEY_SETTING, pending)
    await _set(session, CERT_SETTING, chain)
    await _set(session, PENDING_KEY_SETTING, "")
    await _set(session, CSR_SETTING, "")
    return describe(chain)


async def cancel_request(session: AsyncSession) -> None:
    await _set(session, PENDING_KEY_SETTING, "")
    await _set(session, CSR_SETTING, "")


async def current(session: AsyncSession) -> CertificateState | None:
    cert = await _get(session, CERT_SETTING)
    return describe(cert) if cert else None


async def open_request(session: AsyncSession) -> str:
    return await _get(session, CSR_SETTING)


async def load_key_and_chain(session: AsyncSession, box: SecretBox) -> tuple[str, str] | None:
    cert = await _get(session, CERT_SETTING)
    key = await _get(session, KEY_SETTING)
    if not cert or not key:
        return None
    try:
        return box.decrypt(key), cert
    except SecretError as exc:
        raise TlsError("The stored key cannot be decrypted; was OSLO_SECRET_KEY changed?") from exc


def write_private_files(key_pem: str, chain_pem: str) -> tuple[str, str]:
    """Key and chain as files only this process can read, removed when it ends:
    (certificate file, key file) for uvicorn."""
    directory = tempfile.mkdtemp(prefix="oslo-tls-")
    os.chmod(directory, 0o700)
    atexit.register(shutil.rmtree, directory, ignore_errors=True)
    paths = []
    for name, content in (("cert.pem", chain_pem), ("key.pem", key_pem)):
        path = Path(directory) / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
        paths.append(str(path))
    return paths[0], paths[1]


def remove_private_files(certfile: str) -> None:
    """Remove the files of write_private_files once the server has read them; files given by
    the administrator (not in an oslo-tls- directory) stay."""
    directory = Path(certfile).parent
    if directory.name.startswith("oslo-tls-") and directory.parent == Path(tempfile.gettempdir()):
        shutil.rmtree(directory, ignore_errors=True)


# --- command line: oslo-tls-cert --------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    from .db import create_engine, create_session_factory, upgrade_database
    from .settings import Settings, SettingsError

    parser = argparse.ArgumentParser(
        prog="oslo-tls-cert",
        description="Create a self-signed certificate for OSLO and store it in its database "
        "(used by oslo-server --tls).",
    )
    parser.add_argument("--name", action="append", default=[], help="host name (repeatable)")
    parser.add_argument("--ip", action="append", default=[], help="IP address (repeatable)")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--out", type=Path, help="also write the certificate to this file")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
    except SettingsError as exc:
        sys.exit(f"Configuration error: {exc}")

    async def run() -> CertificateState:
        engine = create_engine(settings.database_url)
        try:
            await upgrade_database(engine, settings.database_url)
            async with create_session_factory(engine)() as session:
                state = await store_self_signed(
                    session, SecretBox(settings.secret_key), args.name, args.ip, args.days
                )
                await session.commit()
                return state
        finally:
            await engine.dispose()

    try:
        state = asyncio.run(run())
    except TlsError as exc:
        sys.exit(f"Error: {exc}")
    if args.out:
        args.out.write_text(state.pem)
    print(f"Certificate for {', '.join(state.names)} valid until {state.not_after:%Y-%m-%d}.")
    print("Start the server with: oslo-server --tls")

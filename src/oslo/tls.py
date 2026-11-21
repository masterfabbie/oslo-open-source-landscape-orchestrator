"""Trusted certificates for HTTPS to managed hosts, and reading the certificate a host shows.

With "verify certificate" on, a host must show a certificate that chains up to a trust
anchor: the operating system's store or one of the certificates admins added under
Administration → Certificates. A self-signed certificate can be added directly; OpenSSL then
treats it as its own issuer.
"""

from __future__ import annotations

import asyncio
import hashlib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

MAX_PEM_LENGTH = 64_000


class CertificateError(ValueError):
    """The text is not a usable certificate, or the host could not be reached."""


@dataclass(frozen=True)
class CertificateInfo:
    pem: str
    subject: str
    issuer: str
    fingerprint: str  # SHA-256 of the DER encoding, hex with colons
    not_before: datetime
    not_after: datetime

    @property
    def self_signed(self) -> bool:
        return self.subject == self.issuer

    def expired(self, now: datetime | None = None) -> bool:
        return self.not_after < (now or datetime.now(UTC))


def _info(cert: x509.Certificate) -> CertificateInfo:
    der = cert.public_bytes(Encoding.DER)
    digest = hashlib.sha256(der).hexdigest().upper()
    return CertificateInfo(
        pem=cert.public_bytes(Encoding.PEM).decode(),
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        fingerprint=":".join(digest[i : i + 2] for i in range(0, len(digest), 2)),
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
    )


def parse_pem(text: str) -> CertificateInfo:
    """Exactly one certificate in PEM format (no private key)."""
    if len(text) > MAX_PEM_LENGTH:
        raise CertificateError("The text is too long for a certificate")
    if "PRIVATE KEY" in text:
        raise CertificateError("The text contains a private key; add only the certificate")
    try:
        certs = x509.load_pem_x509_certificates(text.strip().encode())
    except ValueError as exc:
        raise CertificateError("The text is not a certificate in PEM format") from exc
    if len(certs) != 1:
        raise CertificateError("Add one certificate at a time")
    return _info(certs[0])


def info_from_der(der: bytes) -> CertificateInfo:
    return _info(x509.load_der_x509_certificate(der))


def client_context(trusted_pems: list[str], *, check_hostname: bool) -> ssl.SSLContext:
    """Context for HTTPS to a host: the system's trust store plus ``trusted_pems``."""
    context = ssl.create_default_context()
    if trusted_pems:
        context.load_verify_locations(cadata="\n".join(trusted_pems))
    context.check_hostname = check_hostname
    return context


async def fetch_certificate(address: str, port: int, *, timeout: float = 10.0) -> CertificateInfo:
    """The certificate a host shows on ``port``, read without checking it.

    Only the host's own certificate is read, not the rest of its chain (Python 3.11 cannot
    read the chain of an unverified connection).
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(address, port, ssl=context, server_hostname=address),
            timeout,
        )
    except (OSError, TimeoutError, ssl.SSLError) as exc:
        raise CertificateError(
            f"No TLS connection to {address}:{port}: {exc or type(exc).__name__}"
        ) from exc
    try:
        ssl_object = writer.get_extra_info("ssl_object")
        der = ssl_object.getpeercert(binary_form=True) if ssl_object else None
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, ssl.SSLError):
            pass
    if not der:
        raise CertificateError(f"{address}:{port} did not show a certificate")
    return info_from_der(der)

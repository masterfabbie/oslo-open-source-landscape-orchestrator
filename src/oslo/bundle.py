"""The OSLO operations bundle: files OSLO installs into operations.d of the host agents.

The host agent cannot receive files from OSLO (``DeployConfiguration`` was refused on a real
host with "Remote deployment not permitted", also locally as root), so hosts fetch the
bundle themselves:

- The first installation is done once per host by hand or by the customer's own tools
  (e.g. Ansible) from the bootstrap package (``bootstrap_archive``). It installs the
  operations, the public key of the bundle signature and ``oslo.cfg`` with the address of
  OSLO.
- New versions are uploaded to OSLO (Administration → OSLO operations) as a signed bundle
  file. The operation ``oslo_update`` on the host downloads ``/bundle/payload.tar.gz`` and
  ``/bundle/payload.sig`` over HTTPS, checks the signature with the installed key and
  installs the files (``bundle_files/oslo/oslo_update.sh``).
- ``oslo_version`` reports the installed version and whether the files are unchanged; OSLO
  reads it at every discovery.

Bundles are signed with Ed25519 by whoever builds releases (``oslo-bundle build``); the
private key never belongs on the OSLO server. OSLO only checks uploads against the public
key configured by an admin, so a self-made archive is refused by OSLO and by the hosts.

A bundle file is an uncompressed tar with ``payload.tar.gz`` and ``payload.sig``. The
payload holds ``oslo_*.conf`` and the directory ``oslo/`` with the scripts, ``VERSION`` and
``SHA256SUMS``.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import re
import sys
import tarfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

MAX_BUNDLE_BYTES = 5_000_000
VERSION_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,31}$")
# The same rule as in oslo_update.sh: only names of OSLO.
_MEMBER = re.compile(r"^(oslo_[A-Za-z0-9_-]+\.conf|oslo|oslo/[A-Za-z0-9_.-]+)$")
# Not part of a bundle: they come with the bootstrap package and stay on updates.
HOST_ONLY = ("oslo/bundle_key.pem", "oslo/oslo.cfg")
_OUTPUT = re.compile(r"oslo_bundle (version|integrity|installed)=(\S+)")


class BundleError(ValueError):
    """Not a valid or not a trusted bundle."""


@dataclass(frozen=True)
class Manifest:
    version: str
    files: dict[str, str]  # path in operations.d → SHA-256 (hex)


def source_dir() -> Path:
    """The files of the bundle as they are in this version of OSLO."""
    return Path(str(resources.files("oslo") / "bundle_files"))


def _add(archive: tarfile.TarFile, name: str, data: bytes, mode: int) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    archive.addfile(info, io.BytesIO(data))


def _add_dir(archive: tarfile.TarFile, name: str) -> None:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE
    info.mode = 0o755
    info.mtime = 0
    info.uname = info.gname = "root"
    archive.addfile(info)


def build_payload(version: str, source: Path | None = None) -> bytes:
    """The payload (tar.gz) of a bundle from the source files, always the same bytes for the
    same files and version."""
    if not VERSION_PATTERN.match(version):
        raise BundleError("A version consists of letters, digits, '.', '_' and '-'")
    source = source or source_dir()
    files: dict[str, bytes] = {}
    for path in sorted(source.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            name = path.relative_to(source).as_posix()
            if name in HOST_ONLY or not _MEMBER.match(name):
                raise BundleError(f"Unexpected file in the bundle sources: {name}")
            files[name] = path.read_bytes()
    files["oslo/VERSION"] = f"{version}\n".encode()
    sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in files.items())
    files["oslo/SHA256SUMS"] = sums.encode()
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as archive:
        _add_dir(archive, "oslo")
        for name in sorted(files):
            _add(archive, name, files[name], 0o755 if name.endswith(".sh") else 0o644)
    # gzip without a timestamp, so that the bytes do not change between builds.
    return gzip.compress(raw.getvalue(), mtime=0)


def generate_key() -> tuple[bytes, bytes]:
    """A new signing key: (private PEM, public PEM)."""
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private, public


def sign(payload: bytes, private_pem: bytes) -> bytes:
    key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise BundleError("The signing key must be an Ed25519 key")
    return key.sign(payload)


def public_key(pem: str) -> Ed25519PublicKey:
    """The public key from PEM text; only Ed25519."""
    try:
        key = serialization.load_pem_public_key(pem.strip().encode())
    except ValueError as exc:
        raise BundleError("The key is not a public key in PEM format") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise BundleError("The key must be an Ed25519 public key")
    return key


def normalized_key(pem: str) -> str:
    return (
        public_key(pem)
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )


def verify(payload: bytes, signature: bytes, public_pem: str) -> None:
    try:
        public_key(public_pem).verify(signature, payload)
    except InvalidSignature as exc:
        raise BundleError("The signature does not match the configured key") from exc


def pack(payload: bytes, signature: bytes) -> bytes:
    """The bundle file to upload: payload and signature in one tar."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as archive:
        _add(archive, "payload.tar.gz", payload, 0o644)
        _add(archive, "payload.sig", signature, 0o644)
    return raw.getvalue()


def _read(archive: tarfile.TarFile, name: str) -> bytes:
    try:
        member = archive.getmember(name)
    except KeyError as exc:
        raise BundleError(f"{name} is missing in the bundle") from exc
    if not member.isfile():
        raise BundleError(f"{name} is not a file")
    stream = archive.extractfile(member)
    assert stream is not None
    return stream.read()


def unpack(data: bytes) -> tuple[bytes, bytes]:
    """(payload, signature) of a bundle file. Nothing is written to disk."""
    if len(data) > MAX_BUNDLE_BYTES:
        raise BundleError("The bundle is too large")
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            return _read(archive, "payload.tar.gz"), _read(archive, "payload.sig")
    except tarfile.TarError as exc:
        raise BundleError("The file is not an OSLO operations bundle") from exc


def read_manifest(payload: bytes) -> Manifest:
    """Version and files of a payload, checked like oslo_update.sh does on the host."""
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            contents: dict[str, bytes] = {}
            for member in archive.getmembers():
                name = member.name.rstrip("/")
                if not _MEMBER.match(name) or ".." in name:
                    raise BundleError(f"Unexpected file in the bundle: {member.name}")
                if member.isdir():
                    continue
                if not member.isfile():
                    raise BundleError(f"The bundle contains a link or special file: {name}")
                stream = archive.extractfile(member)
                assert stream is not None
                contents[name] = stream.read()
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise BundleError("The payload of the bundle is not a valid tar.gz") from exc
    try:
        version = contents["oslo/VERSION"].decode().splitlines()[0].strip()
        sums = contents["oslo/SHA256SUMS"].decode()
    except (KeyError, IndexError, UnicodeDecodeError) as exc:
        raise BundleError("VERSION or SHA256SUMS is missing in the bundle") from exc
    if not VERSION_PATTERN.match(version):
        raise BundleError(f"Invalid version in the bundle: {version!r}")
    files: dict[str, str] = {}
    for line in sums.splitlines():
        digest, _, name = line.partition("  ")
        if name not in contents or hashlib.sha256(contents[name]).hexdigest() != digest:
            raise BundleError(f"{name or line} does not match SHA256SUMS")
        files[name] = digest
    extra = set(contents) - set(files) - {"oslo/SHA256SUMS"}
    if extra:
        raise BundleError(f"Files without a checksum: {', '.join(sorted(extra))}")
    for needed in ("oslo_version.conf", "oslo_update.conf", "oslo/oslo_update.sh"):
        if needed not in files:
            raise BundleError(f"{needed} is missing in the bundle")
    return Manifest(version, files)


def check_bundle(data: bytes, public_pem: str) -> tuple[bytes, bytes, Manifest]:
    """Payload, signature and manifest of an uploaded bundle, if it is trusted."""
    payload, signature = unpack(data)
    verify(payload, signature, public_pem)
    return payload, signature, read_manifest(payload)


INSTALL_SH = """#!/bin/sh
# First installation of the OSLO operations into operations.d of the SAP host agent.
# Run as root on each host:  sh install.sh [<operations.d>]
# Later versions are installed from OSLO with the operation "Update OSLO operations".
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OPS=${1:-/usr/sap/hostctrl/exe/operations.d}
[ "$(id -u)" = 0 ] || { echo "Run as root" >&2; exit 1; }
[ -d "$(dirname "$OPS")" ] || { echo "$(dirname "$OPS") does not exist" >&2; exit 1; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
tar -xzf "$HERE/payload.tar.gz" -C "$tmp" oslo/oslo_update.sh
sh "$tmp/oslo/oslo_update.sh" --local "$HERE/payload.tar.gz" "$HERE/payload.sig" \\
    "$HERE/bundle_key.pem" "$OPS"
install -m 644 "$HERE/bundle_key.pem" "$OPS/oslo/bundle_key.pem"
install -m 644 "$HERE/oslo.cfg" "$OPS/oslo/oslo.cfg"
echo "Installed. Check it with:"
echo "  /usr/sap/hostctrl/exe/saphostctrl -function ExecuteOperation -name oslo_version"
"""


def bootstrap_archive(
    payload: bytes, signature: bytes, public_pem: str, base_url: str, ca_path: str = ""
) -> bytes:
    """The package for the first installation on a host (tar.gz with install.sh)."""
    config = f"OSLO_URL={base_url.rstrip('/')}\n"
    config += f"OSLO_CA={ca_path}\n" if ca_path else "# OSLO_CA=/path/to/ca.pem\n"
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz", format=tarfile.GNU_FORMAT) as archive:
        _add_dir(archive, "oslo-bootstrap")
        _add(archive, "oslo-bootstrap/install.sh", INSTALL_SH.encode(), 0o755)
        _add(archive, "oslo-bootstrap/payload.tar.gz", payload, 0o644)
        _add(archive, "oslo-bootstrap/payload.sig", signature, 0o644)
        _add(archive, "oslo-bootstrap/bundle_key.pem", normalized_key(public_pem).encode(), 0o644)
        _add(archive, "oslo-bootstrap/oslo.cfg", config.encode(), 0o644)
    return raw.getvalue()


def parse_output(lines: list[str]) -> dict[str, str]:
    """Values the bundle scripts print, e.g. {"version": "1.0.0", "integrity": "ok"}."""
    values: dict[str, str] = {}
    for line in lines:
        match = _OUTPUT.search(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


# --- command line: oslo-bundle ------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="oslo-bundle", description="Build and sign the OSLO operations bundle."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    keygen = commands.add_parser("keygen", help="create a signing key pair")
    keygen.add_argument("--out", type=Path, default=Path("."), help="directory for the keys")
    build = commands.add_parser("build", help="build and sign a bundle")
    build.add_argument("--version", required=True)
    build.add_argument("--key", type=Path, required=True, help="private key (PEM)")
    build.add_argument("--out", type=Path, help="bundle file to write")
    build.add_argument("--source", type=Path, help="bundle sources (default: those of OSLO)")
    check = commands.add_parser("verify", help="check a bundle against a public key")
    check.add_argument("bundle", type=Path)
    check.add_argument("--key", type=Path, required=True, help="public key (PEM)")
    args = parser.parse_args(argv)

    try:
        if args.command == "keygen":
            private, public = generate_key()
            args.out.mkdir(parents=True, exist_ok=True)
            private_path = args.out / "oslo-bundle-private.pem"
            if private_path.exists():
                sys.exit(f"{private_path} exists already")
            private_path.touch(mode=0o600)
            private_path.write_bytes(private)
            (args.out / "oslo-bundle-public.pem").write_bytes(public)
            print(f"Private key: {private_path} (keep it off the OSLO server)")
            print(f"Public key:  {args.out / 'oslo-bundle-public.pem'} (enter it in OSLO)")
        elif args.command == "build":
            payload = build_payload(args.version, args.source)
            signature = sign(payload, args.key.read_bytes())
            out = args.out or Path(f"oslo-operations-{args.version}.oslobundle")
            out.write_bytes(pack(payload, signature))
            print(f"Bundle {args.version}: {out}")
        else:
            _, _, manifest = check_bundle(args.bundle.read_bytes(), args.key.read_text())
            print(f"Valid bundle {manifest.version} with {len(manifest.files)} files")
    except (BundleError, OSError, ValueError) as exc:
        sys.exit(f"Error: {exc}")


if __name__ == "__main__":
    main()

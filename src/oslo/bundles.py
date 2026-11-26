"""OSLO operations bundles on the server: uploads, the active bundle hosts download, the
settings of Administration → OSLO operations, and the state of a host (see bundle.py)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .bundle import (
    BundleError,
    Manifest,
    check_bundle,
    normalized_key,
    parse_output,
    read_manifest,
)
from .clients.base import SoapFaultError
from .clients.hostagent import FAULT_TIMEOUT, HostAgentClient, OperationFault
from .models import Host, OperationBundle, PlatformSetting

# Platform settings (Administration → OSLO operations).
KEY_SETTING = "bundle.public_key"
URL_SETTING = "bundle.base_url"
CA_SETTING = "bundle.ca_path"

# States of a host, shown at the host and used by "needs attention".
UNKNOWN, MISSING, MODIFIED, OUTDATED, CURRENT, INSTALLED = (
    "unknown",  # not read yet
    "missing",  # oslo_version is not configured on the host
    "modified",  # files differ from SHA256SUMS of the installed bundle
    "outdated",  # another version than the active bundle
    "current",
    "installed",  # installed, but OSLO has no active bundle to compare with
)
NEEDS_UPDATE = (MISSING, MODIFIED, OUTDATED)

VERSION_OPERATION = "oslo_version"
UPDATE_OPERATION = "oslo_update"


@dataclass(frozen=True)
class ActiveBundle:
    id: int
    version: str
    payload: bytes
    signature: bytes
    # Entries of oslo/operations.json (bundle.parse_operations), offered in the catalog.
    operations: tuple[dict, ...] = ()


class BundleStore:
    """The active bundle in memory, for the downloads of the hosts."""

    def __init__(self) -> None:
        self.active: ActiveBundle | None = None
        self.public_key = ""

    async def load(self, session: AsyncSession) -> None:
        """Read the active bundle and the key again, after every change."""
        row = await session.scalar(select(OperationBundle).where(OperationBundle.active))
        self.active = None
        if row is not None:
            try:
                operations = read_manifest(row.payload).operations
            except BundleError:
                operations = ()  # stored before operations.json was checked
            self.active = ActiveBundle(row.id, row.version, row.payload, row.signature, operations)
        self.public_key = await get_setting(session, KEY_SETTING)

    def files(self) -> tuple[bytes, bytes] | None:
        """(payload, signature) of the active bundle."""
        return (self.active.payload, self.active.signature) if self.active else None

    @property
    def version(self) -> str | None:
        return self.active.version if self.active else None


async def get_setting(session: AsyncSession, key: str) -> str:
    row = await session.get(PlatformSetting, key)
    return row.value if row else ""


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(PlatformSetting, key)
    if row is None:
        session.add(PlatformSetting(key=key, value=value))
    else:
        row.value = value


async def load_settings(session: AsyncSession) -> dict[str, str]:
    return {
        "public_key": await get_setting(session, KEY_SETTING),
        "base_url": await get_setting(session, URL_SETTING),
        "ca_path": await get_setting(session, CA_SETTING),
    }


async def save_settings(
    session: AsyncSession, public_key: str, base_url: str, ca_path: str
) -> dict[str, str]:
    """Check and store the settings; the caller commits. Raises BundleError."""
    key = normalized_key(public_key) if public_key.strip() else ""
    url = base_url.strip().rstrip("/")
    if url and not url.startswith("https://"):
        raise BundleError("The address of OSLO for the hosts must start with https://")
    if any(c.isspace() for c in url) or any(c.isspace() for c in ca_path.strip()):
        raise BundleError("Addresses and paths must not contain spaces")
    ca = ca_path.strip()
    if ca and not ca.startswith("/"):
        raise BundleError("The path of the CA file on the hosts must be absolute")
    await set_setting(session, KEY_SETTING, key)
    await set_setting(session, URL_SETTING, url)
    await set_setting(session, CA_SETTING, ca)
    return {"public_key": key, "base_url": url, "ca_path": ca}


async def save_bundle(
    session: AsyncSession, data: bytes, username: str | None
) -> tuple[OperationBundle, Manifest]:
    """Check an uploaded bundle against the configured key and make it the active one. An
    upload of a bundle that is stored already activates that one. The caller commits."""
    public = await get_setting(session, KEY_SETTING)
    if not public:
        raise BundleError("Enter the public key of the bundle signature first")
    payload, signature, manifest = check_bundle(data, public)
    digest = hashlib.sha256(payload).hexdigest()
    row = await session.scalar(select(OperationBundle).where(OperationBundle.sha256 == digest))
    if row is None:
        row = OperationBundle(
            version=manifest.version,
            sha256=digest,
            payload=payload,
            signature=signature,
            files=json.dumps(manifest.files),
            uploaded_at=datetime.now(UTC),
            uploaded_by=username,
        )
        session.add(row)
        await session.flush()
    await activate(session, row)
    return row, manifest


async def activate(session: AsyncSession, row: OperationBundle) -> None:
    await session.execute(
        update(OperationBundle).where(OperationBundle.id != row.id).values(active=False)
    )
    row.active = True


def host_state(host: Host, active_version: str | None) -> str:
    if host.bundle_checked_at is None:
        return UNKNOWN
    if not host.bundle_version or host.bundle_version == "none":
        return MISSING
    if host.bundle_integrity != "ok":
        return MODIFIED
    if active_version is None:
        return INSTALLED
    return CURRENT if host.bundle_version == active_version else OUTDATED


async def follow_operation(
    agent: HostAgentClient,
    name: str,
    operation_id: str,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    poll: float = 0.5,
    attempts: int = 60,
) -> list[str]:
    """The texts of the lines of a started operation, once it has ended (like a custom
    operation: GetOperationResults until it answers without fault 255). Raises
    SoapFaultError if it fails or does not end in time."""
    for _ in range(attempts):
        try:
            result = await agent.get_operation_results(operation_id)
        except OperationFault as fault:
            if fault.code != FAULT_TIMEOUT:
                raise
        else:
            # Results without a fault: it ended. The host agent forgets the operation then;
            # IsOperationFinished would answer "Failed to determine operation status".
            return [line.text for line in result.log]
        await sleep(poll)
    raise SoapFaultError(f"{name} did not finish in time")


async def read_host_bundle(
    agent: HostAgentClient, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
) -> tuple[str, str | None]:
    """(version, integrity) of the OSLO operations on a host; ("none", None) if the host agent
    refuses to start oslo_version (not configured in operations.d). Any other error, e.g. in
    reading the results, is raised, so that it is shown and the stored state stays."""
    try:
        started = await agent.execute_async(VERSION_OPERATION)
    except OperationFault:
        raise
    except SoapFaultError:
        return "none", None
    if not started.operation_id:
        raise SoapFaultError(f"{VERSION_OPERATION}: the host agent returned no operation ID")
    lines = await follow_operation(agent, VERSION_OPERATION, started.operation_id, sleep=sleep)
    values = parse_output(lines)
    if "version" not in values:
        raise SoapFaultError(f"{VERSION_OPERATION} printed no version: {' | '.join(lines)[:300]}")
    return values["version"][:32], values.get("integrity")

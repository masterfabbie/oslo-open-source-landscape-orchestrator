"""Export and import of the configuration (Administration → Import/Export) as JSON.

The file holds the parts chosen at the export: hosts, SID credentials, pools, systems, custom
operations, operation templates, schedules, the rules of "needs attention" and trusted
certificates. Activities, logs and users are never part of it.

Things refer to each other by name, not by id, so that a file fits another OSLO: a system by
its name, a host by its name, an instance by host, SID and number. Instances themselves come
from a discovery; an import only assigns instances that are already known.

Passwords of hosts and SIDs are only exported when the export gets a password. They are then
encrypted with a key derived from that password (scrypt, Fernet), never in plain text;
OSLO_SECRET_KEY cannot be used because another OSLO does not know it. Without the password an
import skips them and takes everything else.

An import never deletes anything. Mode "add" creates what is missing and leaves existing
things alone; mode "update" changes existing ones as well. A preview runs the same import and
rolls it back.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .attention import RULES_KEY, RuleError, load_rules, save_rules
from .catalog import Catalog
from .crypto import SecretBox
from .customops import CustomOperationError, save_operation, save_parameter
from .dependencies import DependencyError, set_dependencies
from .hosts import Connection, HostChangeError, update_connection
from .models import (
    CustomOperation,
    Host,
    HostTag,
    Instance,
    OperationTemplate,
    PlatformSetting,
    Pool,
    Schedule,
    Sid,
    System,
    SystemTag,
    TrustedCertificate,
    User,
)
from .pools import assign_pool
from .schedules import ScheduleError, save_schedule
from .systems import SystemChangeError, update_system
from .tags import TagError, parse_tags, replace_tags, tag_texts
from .templates import TemplateError, save_template
from .tls import CertificateError, parse_pem

FORMAT = "oslo-export"
VERSION = 1
PARTS = (
    "hosts",
    "sids",
    "pools",
    "systems",
    "custom_operations",
    "templates",
    "schedules",
    "attention_rules",
    "certificates",
)
MODES = ("add", "update")
# Costs of the key derivation for the export password (scrypt).
_KDF = {"n": 2**15, "r": 8, "p": 1}
_CHECK = "oslo"


class TransferError(ValueError):
    """The file or the request cannot be used at all."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# --- credentials --------------------------------------------------------------------------


def _fernet(password: str, salt: bytes, kdf: Mapping[str, int]) -> Fernet:
    key = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=int(kdf["n"]),
        r=int(kdf["r"]),
        p=int(kdf["p"]),
        maxmem=128 * 1024 * 1024,
        dklen=32,
    )
    return Fernet(base64.urlsafe_b64encode(key))


def _export_cipher(password: str) -> tuple[Fernet, dict[str, Any]]:
    salt = secrets.token_bytes(16)
    fernet = _fernet(password, salt, _KDF)
    header = {
        "kdf": "scrypt",
        **_KDF,
        "salt": base64.b64encode(salt).decode(),
        "check": fernet.encrypt(_CHECK.encode()).decode(),
    }
    return fernet, header


def _import_cipher(header: Any, password: str | None) -> Fernet | None:
    """The key for the passwords in the file; None without password or passwords."""
    if not header or not password:
        return None
    try:
        fernet = _fernet(password, base64.b64decode(header["salt"]), header)
        if fernet.decrypt(header["check"].encode()).decode() != _CHECK:
            raise InvalidToken
    except (InvalidToken, KeyError, TypeError, ValueError) as exc:
        raise TransferError("transfer_password", "The password of the export is wrong") from exc
    return fernet


# --- export -------------------------------------------------------------------------------


def _instance_ref(instance: Instance) -> dict[str, str]:
    return {"host": instance.host.name, "sid": instance.sid.name, "number": instance.number}


async def _target_refs(session: AsyncSession, target_type: str, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    if target_type == "SYSTEM":
        rows = dict(
            (await session.execute(select(System.id, System.name).where(System.id.in_(ids)))).all()
        )
        return [{"system": rows[i]} for i in ids if i in rows]
    if target_type == "HOST":
        rows = dict(
            (await session.execute(select(Host.id, Host.name).where(Host.id.in_(ids)))).all()
        )
        return [{"host": rows[i]} for i in ids if i in rows]
    instances = {
        i.id: i
        for i in await session.scalars(
            select(Instance)
            .where(Instance.id.in_(ids))
            .options(selectinload(Instance.host), selectinload(Instance.sid))
        )
    }
    return [_instance_ref(instances[i]) for i in ids if i in instances]


async def export_configuration(
    session: AsyncSession,
    secret_box: SecretBox,
    parts: list[str],
    *,
    password: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The chosen parts as a JSON-ready dict. With ``password`` the passwords of hosts and SIDs
    are included, encrypted with it."""
    unknown = set(parts) - set(PARTS)
    if unknown or not parts:
        raise TransferError("invalid_input", f"Unknown parts: {sorted(unknown)}")
    fernet, header = _export_cipher(password) if password else (None, None)

    def secret(owner: Host | Sid) -> dict[str, str]:
        out: dict[str, str] = {}
        if owner.username:
            out["username"] = owner.username
        if fernet and owner.password_encrypted:
            out["password"] = fernet.encrypt(
                secret_box.decrypt(owner.password_encrypted).encode()
            ).decode()
        return out

    data: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": (now or datetime.now(UTC)).isoformat(),
        "parts": [p for p in PARTS if p in parts],
        "credentials": header,
    }
    if "hosts" in parts:
        hosts = await session.scalars(
            select(Host).order_by(Host.name).options(selectinload(Host.tags))
        )
        data["hosts"] = [
            {
                "name": h.name,
                "address": h.address,
                "hostagent_port": h.hostagent_port,
                "https": h.https,
                "verify_tls": h.verify_tls,
                "verify_hostname": h.verify_hostname,
                "sapcontrol_port_offset": h.sapcontrol_port_offset,
                "tags": tag_texts(h.tags),
                **secret(h),
            }
            for h in hosts
        ]
    if "sids" in parts:
        sids = await session.scalars(
            select(Sid).where(Sid.username.is_not(None)).order_by(Sid.name)
        )
        data["sids"] = [{"name": s.name, **secret(s)} for s in sids]
    if "pools" in parts:
        pools = await session.scalars(select(Pool).order_by(Pool.name))
        data["pools"] = [{"name": p.name, "description": p.description} for p in pools]
    if "systems" in parts:
        systems = await session.scalars(
            select(System)
            .order_by(func.lower(System.name))
            .options(
                selectinload(System.instances).selectinload(Instance.host),
                selectinload(System.instances).selectinload(Instance.sid),
                selectinload(System.depends_on),
                selectinload(System.pool),
                selectinload(System.tags),
            )
        )
        data["systems"] = [
            {
                "name": s.name,
                "description": s.description,
                "stage": s.stage,
                "pool": s.pool.name if s.pool else None,
                "tags": tag_texts(s.tags),
                "depends_on": sorted(d.name for d in s.depends_on),
                "instances": [_instance_ref(i) for i in s.instances],
            }
            for s in systems
        ]
    if "custom_operations" in parts:
        operations = await session.scalars(
            select(CustomOperation)
            .order_by(CustomOperation.key)
            .options(selectinload(CustomOperation.parameters))
        )
        data["custom_operations"] = [
            {
                "key": o.key,
                "name": o.name,
                "description": o.description,
                "agent_operation": o.agent_operation,
                "target": o.target,
                "instance_types": [t for t in (o.instance_types or "").split(",") if t],
                "ordering": o.ordering,
                "role": o.role,
                "mass": o.mass,
                "locks": o.locks,
                "standalone": o.standalone,
                "timeout_seconds": o.timeout_seconds,
                "parameters": [
                    {
                        "name": p.name,
                        "label": p.label,
                        "type": p.type,
                        "required": p.required,
                        "default": p.default,
                        "pattern": p.pattern,
                        "help": p.help,
                    }
                    for p in sorted(o.parameters, key=lambda p: p.position)
                ],
            }
            for o in operations
        ]
    if "templates" in parts:
        templates = await session.scalars(
            select(OperationTemplate)
            .order_by(OperationTemplate.key)
            .options(selectinload(OperationTemplate.steps))
        )
        data["templates"] = []
        for t in templates:
            steps = []
            for step in sorted(t.steps, key=lambda s: s.position):
                steps.append(
                    {
                        "position": step.position,
                        "operation": step.operation,
                        "target_type": step.target_type,
                        "targets": await _target_refs(
                            session, step.target_type, json.loads(step.targets or "[]")
                        ),
                        "after": json.loads(step.after or "[]"),
                        "parameters": json.loads(step.parameters or "{}"),
                        "ask": json.loads(step.ask or "[]"),
                        "on_error": step.on_error,
                    }
                )
            data["templates"].append(
                {
                    "key": t.key,
                    "name": t.name,
                    "description": t.description,
                    "role": t.role,
                    "steps": steps,
                }
            )
    if "schedules" in parts:
        schedules = await session.scalars(select(Schedule).order_by(Schedule.id))
        data["schedules"] = [
            {
                "name": s.name,
                "operation": s.operation,
                "target_type": s.target_type,
                "targets": await _target_refs(session, s.target_type, json.loads(s.target_ids)),
                "parameters": json.loads(s.parameters or "{}"),
                "recurrence": s.recurrence,
                "run_at": s.run_at.isoformat() if s.run_at else None,
                "time_of_day": s.time_of_day,
                "weekdays": s.weekdays,
                "interval_minutes": s.interval_minutes,
                "enabled": s.enabled,
            }
            for s in schedules
        ]
    if "attention_rules" in parts:
        data["attention_rules"] = await load_rules(session)
    if "certificates" in parts:
        certs = await session.scalars(select(TrustedCertificate).order_by(TrustedCertificate.name))
        data["certificates"] = [{"name": c.name, "pem": c.pem} for c in certs]
    return data


# --- import -------------------------------------------------------------------------------


@dataclass
class Report:
    """What an import did, item by item: created, updated, skipped or failed."""

    items: list[dict[str, str]] = field(default_factory=list)

    def add(self, part: str, name: str, action: str, message: str = "") -> None:
        self.items.append({"part": part, "name": name, "action": action, "message": message})

    def counts(self) -> dict[str, int]:
        result = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "warning": 0}
        for item in self.items:
            result[item["action"]] = result.get(item["action"], 0) + 1
        return result


@dataclass
class _Context:
    session: AsyncSession
    secret_box: SecretBox
    catalog: Catalog
    user: User
    zone: ZoneInfo
    now: datetime
    update: bool
    fernet: Fernet | None
    report: Report


_ITEM_ERRORS = (
    SystemChangeError,
    HostChangeError,
    CustomOperationError,
    TemplateError,
    ScheduleError,
    DependencyError,
    TagError,
    RuleError,
    CertificateError,
    ValueError,
    KeyError,
    TypeError,
)


async def _each(
    ctx: _Context, part: str, items: Any, name_of: Callable[[dict], str], handle: Callable
) -> None:
    """Run ``handle`` for every item in its own savepoint; a failing item is undone alone."""
    if not isinstance(items, list):
        ctx.report.add(part, "", "failed", "Not a list")
        return
    for item in items:
        name = str(name_of(item)) if isinstance(item, dict) else "?"
        try:
            async with ctx.session.begin_nested():
                if not isinstance(item, dict):
                    raise ValueError("Not an object")
                action, message = await handle(ctx, item)
        except _ITEM_ERRORS as exc:
            ctx.report.add(part, name, "failed", str(exc) or type(exc).__name__)
            continue
        ctx.report.add(part, name, action, message)


def _password(ctx: _Context, item: dict) -> str | None:
    """The decrypted password of an item, if the file has one and the import has the key."""
    token = item.get("password")
    if not token or ctx.fernet is None:
        return None
    try:
        return ctx.fernet.decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("The password in the file cannot be decrypted") from exc


def _set_credentials(ctx: _Context, owner: Host | Sid, item: dict) -> str:
    """Take over user and password; returns a note when the password was left out."""
    password = _password(ctx, item)
    if password is not None and item.get("username"):
        owner.username = item["username"]
        owner.password_encrypted = ctx.secret_box.encrypt(password)
        return ""
    if item.get("password") and ctx.fernet is None:
        return "password skipped (no export password given)"
    return ""


async def _host(ctx: _Context, item: dict) -> tuple[str, str]:
    name = str(item["name"]).strip()
    host = await ctx.session.scalar(
        select(Host).where(func.lower(Host.name) == name.lower()).options(selectinload(Host.tags))
    )
    if host is not None and not ctx.update:
        return "skipped", "exists"
    created = host is None
    if created:
        if not name or len(name) > 255:
            raise ValueError("The name must have 1 to 255 characters")
        host = Host(name=name, address=str(item.get("address") or name))
        host.tags = []
        host.agent_info = None
        ctx.session.add(host)
        host.hostagent_port = item.get("hostagent_port")
        host.https = bool(item.get("https", False))
        host.verify_tls = bool(item.get("verify_tls", True))
        host.verify_hostname = bool(item.get("verify_hostname", True))
        host.sapcontrol_port_offset = int(item.get("sapcontrol_port_offset") or 0)
        await ctx.session.flush()
    else:
        await update_connection(
            ctx.session,
            host,
            Connection(
                name=name,
                address=item.get("address"),
                hostagent_port=item.get("hostagent_port") or 0,
                https=item.get("https"),
                verify_tls=item.get("verify_tls"),
                verify_hostname=item.get("verify_hostname"),
                sapcontrol_port_offset=item.get("sapcontrol_port_offset"),
            ),
        )
    replace_tags(host.tags, HostTag, parse_tags(item.get("tags") or []))
    note = _set_credentials(ctx, host, item)
    await ctx.session.flush()
    return ("created" if created else "updated"), note


async def _sid(ctx: _Context, item: dict) -> tuple[str, str]:
    name = str(item["name"]).strip().upper()
    sid = await ctx.session.scalar(select(Sid).where(Sid.name == name))
    if sid is not None and sid.username and not ctx.update:
        return "skipped", "has credentials"
    created = sid is None
    if sid is None:
        # Known from a discovery later; the credentials are kept for it.
        if not 1 <= len(name) <= 8:
            raise ValueError("A SID has 1 to 8 characters")
        sid = Sid(name=name)
        ctx.session.add(sid)
    note = _set_credentials(ctx, sid, item)
    if not item.get("password") and item.get("username") and not sid.username:
        note = "no password in the file"
    await ctx.session.flush()
    return ("created" if created else "updated"), note


async def _pool(ctx: _Context, item: dict) -> tuple[str, str]:
    name = str(item["name"]).strip()
    if not name or len(name) > 64:
        raise ValueError("A pool name has 1 to 64 characters")
    pool = await ctx.session.scalar(select(Pool).where(Pool.name == name))
    if pool is not None:
        if not ctx.update:
            return "skipped", "exists"
        pool.description = (item.get("description") or "").strip() or None
        await ctx.session.flush()
        return "updated", ""
    ctx.session.add(
        Pool(name=name, description=(item.get("description") or "").strip() or None, systems=[])
    )
    await ctx.session.flush()
    return "created", ""


async def _find_instance(session: AsyncSession, ref: Mapping[str, Any]) -> Instance | None:
    return await session.scalar(
        select(Instance)
        .join(Host, Instance.host_id == Host.id)
        .join(Sid, Instance.sid_id == Sid.id)
        .where(
            func.lower(Host.name) == str(ref["host"]).lower(),
            Sid.name == str(ref["sid"]).upper(),
            Instance.number == str(ref["number"]).zfill(2),
        )
    )


async def _system(ctx: _Context, item: dict) -> tuple[str, str]:
    name = str(item["name"]).strip()
    system = await ctx.session.scalar(
        select(System)
        .where(func.lower(System.name) == name.lower())
        .options(selectinload(System.tags))
    )
    if system is not None and not ctx.update:
        return "skipped", "exists"
    found: list[Instance] = []
    missing: list[str] = []
    taken: list[str] = []
    for ref in item.get("instances") or []:
        instance = await _find_instance(ctx.session, ref)
        label = f"{str(ref['sid']).upper()}/{str(ref['number']).zfill(2)} ({ref['host']})"
        if instance is None:
            missing.append(label)
        elif instance.system_id is not None and (system is None or instance.system_id != system.id):
            taken.append(label)
        else:
            found.append(instance)
    created = system is None
    if created:
        if not found:
            raise ValueError(
                "None of its instances is known; run a discovery of its hosts, then import again"
            )
        system = System(name=name)
        system.tags = []
        ctx.session.add(system)
        await ctx.session.flush()
    await update_system(
        ctx.session, system.id, name, item.get("description"), item.get("stage") or None
    )
    for instance in found:
        instance.system_id = system.id
    pool_name = item.get("pool")
    pool = (
        await ctx.session.scalar(select(Pool).where(Pool.name == pool_name)) if pool_name else None
    )
    if pool_name and pool is None:
        missing.append(f"pool {pool_name}")
    await assign_pool(ctx.session, system.id, pool.id if pool else None)
    replace_tags(system.tags, SystemTag, parse_tags(item.get("tags") or []))
    await ctx.session.flush()
    notes = []
    if missing:
        notes.append("not found: " + ", ".join(missing))
    if taken:
        notes.append("in another system: " + ", ".join(taken))
    return ("created" if created else "updated"), "; ".join(notes)


async def _dependencies(ctx: _Context, item: dict) -> tuple[str, str]:
    """Second pass over the systems, once all of them exist."""
    system = await ctx.session.scalar(
        select(System).where(func.lower(System.name) == str(item["name"]).strip().lower())
    )
    if system is None:
        return "skipped", "system not imported"
    ids, missing = set(), []
    for other in item.get("depends_on") or []:
        found = await ctx.session.scalar(
            select(System.id).where(func.lower(System.name) == str(other).lower())
        )
        if found is None:
            missing.append(str(other))
        else:
            ids.add(found)
    await set_dependencies(ctx.session, system.id, ids)
    return "updated", ("not found: " + ", ".join(missing)) if missing else ""


async def _custom_operation(ctx: _Context, item: dict) -> tuple[str, str]:
    key = str(item["key"]).strip()
    operation = await ctx.session.scalar(
        select(CustomOperation)
        .where(CustomOperation.key == key)
        .options(selectinload(CustomOperation.parameters))
    )
    if operation is not None and not ctx.update:
        return "skipped", "exists"
    created = operation is None
    operation = await save_operation(
        ctx.session,
        operation,
        key=key,
        name=str(item["name"]),
        description=item.get("description"),
        agent_operation=str(item["agent_operation"]),
        target=str(item["target"]),
        instance_types=list(item.get("instance_types") or []),
        ordering=str(item.get("ordering") or "parallel"),
        role=str(item.get("role") or "configurator"),
        mass=bool(item.get("mass", True)),
        timeout_seconds=int(item.get("timeout_seconds") or 3600),
        locks=bool(item.get("locks", True)),
        standalone=bool(item.get("standalone", True)),
    )
    if created:
        await ctx.session.refresh(operation, ["parameters"])
    existing = {p.name: p for p in operation.parameters}
    for parameter in item.get("parameters") or []:
        await save_parameter(
            ctx.session,
            operation,
            existing.get(str(parameter["name"]).strip().upper()),
            name=str(parameter["name"]),
            label=str(parameter["label"]),
            type=str(parameter.get("type") or "STRING"),
            required=bool(parameter.get("required", False)),
            default=parameter.get("default"),
            pattern=parameter.get("pattern"),
            help=parameter.get("help"),
        )
    await ctx.catalog.reload(ctx.session)
    return ("created" if created else "updated"), ""


async def _target_ids(
    session: AsyncSession, target_type: str, refs: Any
) -> tuple[list[int], list[str]]:
    ids, missing = [], []
    for ref in refs or []:
        if target_type == "SYSTEM":
            found = await session.scalar(
                select(System.id).where(func.lower(System.name) == str(ref["system"]).lower())
            )
            label = str(ref["system"])
        elif target_type == "HOST":
            found = await session.scalar(
                select(Host.id).where(func.lower(Host.name) == str(ref["host"]).lower())
            )
            label = str(ref["host"])
        else:
            instance = await _find_instance(session, ref)
            found = instance.id if instance else None
            label = f"{ref['sid']}/{ref['number']} ({ref['host']})"
        if found is None:
            missing.append(label)
        else:
            ids.append(found)
    return ids, missing


async def _template(ctx: _Context, item: dict) -> tuple[str, str]:
    key = str(item["key"]).strip()
    template = await ctx.session.scalar(
        select(OperationTemplate).where(OperationTemplate.key == key)
    )
    if template is not None and not ctx.update:
        return "skipped", "exists"
    steps, missing = [], []
    for step in item.get("steps") or []:
        target_type = str(step.get("target_type") or "")
        ids, lost = await _target_ids(ctx.session, target_type, step.get("targets"))
        if step.get("targets") and lost:
            missing.extend(lost)
        steps.append(
            {
                "position": int(step["position"]),
                "operation": str(step["operation"]),
                "target_type": target_type,
                "targets": ids,
                "after": [int(a) for a in step.get("after") or []],
                "parameters": dict(step.get("parameters") or {}),
                "ask": list(step.get("ask") or []),
                "on_error": str(step.get("on_error") or "stop"),
            }
        )
    if missing:
        # A step with fixed targets must not silently fall back to the selection.
        raise ValueError("Targets not found: " + ", ".join(missing))
    created = template is None
    await save_template(
        ctx.session,
        ctx.catalog,
        template,
        key=key,
        name=str(item["name"]),
        description=item.get("description"),
        role=str(item.get("role") or "operator"),
        steps=steps,
    )
    await ctx.catalog.reload(ctx.session)
    return ("created" if created else "updated"), ""


async def _schedule(ctx: _Context, item: dict) -> tuple[str, str]:
    target_type = str(item.get("target_type") or "")
    ids, missing = await _target_ids(ctx.session, target_type, item.get("targets"))
    if missing:
        raise ValueError("Targets not found: " + ", ".join(missing))
    run_at = datetime.fromisoformat(item["run_at"]) if item.get("run_at") else None
    fields = {
        "name": item.get("name"),
        "operation": str(item["operation"]),
        "target_type": target_type,
        "target_ids": ids,
        "parameters": dict(item.get("parameters") or {}),
        "recurrence": str(item["recurrence"]),
        "run_at": run_at,
        "time_of_day": item.get("time_of_day"),
        "weekdays": str(item.get("weekdays") or "1234567"),
        "interval_minutes": item.get("interval_minutes"),
        "enabled": bool(item.get("enabled", True)),
    }
    # The same schedule: by name, or without name by what it plans.
    existing = None
    for schedule in await ctx.session.scalars(
        select(Schedule).where(Schedule.operation == fields["operation"])
    ):
        if (fields["name"] and schedule.name == fields["name"]) or (
            not fields["name"]
            and not schedule.name
            and schedule.target_type == target_type
            and json.loads(schedule.target_ids) == ids
            and schedule.recurrence == fields["recurrence"]
            and schedule.time_of_day == fields["time_of_day"]
            and schedule.interval_minutes == fields["interval_minutes"]
            and (schedule.run_at == run_at)
        ):
            existing = schedule
            break
    if existing is not None and not ctx.update:
        return "skipped", "exists"
    await save_schedule(
        ctx.session, ctx.catalog, existing, ctx.user, ctx.zone, now=ctx.now, **fields
    )
    note = "" if existing is not None else f"runs with the rights of {ctx.user.username}"
    return ("updated" if existing is not None else "created"), note


async def _attention_rules(ctx: _Context, rules: Any) -> None:
    if not isinstance(rules, dict):
        ctx.report.add("attention_rules", "", "failed", "Not an object")
        return
    stored = await ctx.session.get(PlatformSetting, RULES_KEY)
    if stored is not None and not ctx.update:
        ctx.report.add("attention_rules", "", "skipped", "exists")
        return
    try:
        async with ctx.session.begin_nested():
            await save_rules(ctx.session, rules)
    except _ITEM_ERRORS as exc:
        ctx.report.add("attention_rules", "", "failed", str(exc))
        return
    ctx.report.add("attention_rules", "", "updated" if stored else "created")


async def _certificate(ctx: _Context, item: dict) -> tuple[str, str]:
    info = parse_pem(str(item["pem"]))
    cert = await ctx.session.scalar(
        select(TrustedCertificate).where(TrustedCertificate.fingerprint == info.fingerprint)
    )
    name = str(item.get("name") or info.subject).strip()[:255]
    if cert is not None:
        if not ctx.update or cert.name == name:
            return "skipped", "exists"
        cert.name = name
        return "updated", ""
    ctx.session.add(
        TrustedCertificate(
            name=name,
            pem=info.pem,
            subject=info.subject,
            issuer=info.issuer,
            fingerprint=info.fingerprint,
            not_before=info.not_before,
            not_after=info.not_after,
            created_at=ctx.now,
            created_by=ctx.user.username,
        )
    )
    await ctx.session.flush()
    return "created", ""


async def _begin(session: AsyncSession) -> None:
    """Start the transaction explicitly. The SQLite driver only begins one before a write, so a
    savepoint opened before would commit on release, and a preview could not be rolled back."""
    if session.bind is not None and session.bind.dialect.name != "sqlite":
        return
    connection = await session.connection()
    try:
        await connection.exec_driver_sql("BEGIN")
    except OperationalError:
        pass  # a transaction is open already


def check_file(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise TransferError("transfer_format", "This is not an export of OSLO")
    if not isinstance(data.get("version"), int) or data["version"] > VERSION:
        raise TransferError(
            "transfer_version", f"Export version {data.get('version')} is newer than this OSLO"
        )
    return data


async def import_configuration(
    session: AsyncSession,
    secret_box: SecretBox,
    catalog: Catalog,
    user: User,
    data: Any,
    *,
    mode: str,
    password: str | None,
    zone: ZoneInfo,
    now: datetime,
) -> Report:
    """Import the parts of an export into the session. The caller commits, or rolls back for a
    preview (and reloads the catalog then)."""
    data = check_file(data)
    if mode not in MODES:
        raise TransferError("invalid_input", "Mode: add or update")
    await _begin(session)
    ctx = _Context(
        session,
        secret_box,
        catalog,
        user,
        zone,
        now,
        mode == "update",
        _import_cipher(data.get("credentials"), password),
        Report(),
    )
    if data.get("credentials") and not password:
        ctx.report.add(
            "credentials", "", "warning", "No export password given; passwords are skipped"
        )
    # Order matters: what is referred to comes first.
    if "hosts" in data:
        await _each(ctx, "hosts", data["hosts"], lambda i: i.get("name", "?"), _host)
    if "sids" in data:
        await _each(ctx, "sids", data["sids"], lambda i: i.get("name", "?"), _sid)
    if "pools" in data:
        await _each(ctx, "pools", data["pools"], lambda i: i.get("name", "?"), _pool)
    if "systems" in data:
        await _each(ctx, "systems", data["systems"], lambda i: i.get("name", "?"), _system)
        dependencies = [s for s in data["systems"] if isinstance(s, dict) and s.get("depends_on")]
        await _each(ctx, "dependencies", dependencies, lambda i: i.get("name", "?"), _dependencies)
    if "custom_operations" in data:
        await _each(
            ctx,
            "custom_operations",
            data["custom_operations"],
            lambda i: i.get("key", "?"),
            _custom_operation,
        )
    if "templates" in data:
        await _each(ctx, "templates", data["templates"], lambda i: i.get("key", "?"), _template)
    if "schedules" in data:
        await _each(
            ctx,
            "schedules",
            data["schedules"],
            lambda i: i.get("name") or i.get("operation", "?"),
            _schedule,
        )
    if "attention_rules" in data:
        await _attention_rules(ctx, data["attention_rules"])
    if "certificates" in data:
        await _each(
            ctx, "certificates", data["certificates"], lambda i: i.get("name", "?"), _certificate
        )
    return ctx.report

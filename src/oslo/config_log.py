"""The configuration log: who changed what in the configuration, and when.

Changes are recorded automatically when a session flushes (``before_flush``), for the models
and fields listed in ``SPECS``: what a person configures, not what discoveries, activities or
schedules write (status, versions, next runs). Only changes made in the name of a user are
recorded; the API and the web pages set the user (``set_actor``) when they check the sign-in.
Changes that bypass the ORM (pool membership, dependencies) are recorded by their code with
``record``. Secrets are never stored, only that they changed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, event, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .models import (
    ConfigChange,
    CustomOperation,
    CustomOperationParameter,
    Host,
    HostTag,
    Instance,
    OperationBundle,
    OperationTemplate,
    PlatformSetting,
    Pool,
    Schedule,
    Sid,
    System,
    SystemTag,
    TemplateStep,
    TrustedCertificate,
    User,
)

CREATED, UPDATED, DELETED = "created", "updated", "deleted"
# Stands for a secret, or for a value too long to show, whose change is recorded.
CHANGED = "(changed)"
MAX_VALUE = 120

# Platform setting with the number of days the log is kept.
RETENTION_KEY = "config_log.retention_days"
DEFAULT_RETENTION_DAYS = 365

_ACTOR: ContextVar[str | None] = ContextVar("config_actor", default=None)


def set_actor(username: str | None) -> None:
    """The user in whose name the current request changes things."""
    _ACTOR.set(username)


def actor() -> str | None:
    return _ACTOR.get()


@dataclass(frozen=True)
class Spec:
    object_type: str
    fields: tuple[str, ...]
    name: Callable[[Any], str]
    secrets: tuple[str, ...] = ()
    # Whether creating and deleting are recorded (SIDs are created by discoveries).
    lifecycle: bool = True
    # Values shown as "(changed)" only, e.g. JSON or certificates.
    opaque: tuple[str, ...] = field(default=())


SPECS: dict[type, Spec] = {
    Host: Spec(
        "host",
        (
            "name",
            "address",
            "hostagent_port",
            "https",
            "verify_tls",
            "verify_hostname",
            "sapcontrol_port_offset",
            "username",
            "password_encrypted",
            "stage",
        ),
        lambda o: o.name,
        secrets=("password_encrypted",),
    ),
    Sid: Spec(
        "sid",
        ("username", "password_encrypted"),
        lambda o: o.name,
        secrets=("password_encrypted",),
        lifecycle=False,
    ),
    System: Spec("system", ("name", "description", "stage"), lambda o: o.name),
    Pool: Spec("pool", ("name", "description"), lambda o: o.name),
    CustomOperation: Spec(
        "custom_operation",
        (
            "key",
            "name",
            "description",
            "agent_operation",
            "target",
            "instance_types",
            "ordering",
            "role",
            "locks",
            "standalone",
            "timeout_seconds",
            "category",
        ),
        lambda o: o.name,
    ),
    OperationTemplate: Spec(
        "template",
        ("key", "name", "description", "target", "role", "category"),
        lambda o: o.name,
    ),
    Schedule: Spec(
        "schedule",
        (
            "name",
            "operation",
            "target_type",
            "target_ids",
            "parameters",
            "recurrence",
            "run_at",
            "time_of_day",
            "weekdays",
            "interval_minutes",
            "enabled",
        ),
        lambda o: o.name or o.operation,
    ),
    TrustedCertificate: Spec("certificate", ("name",), lambda o: o.name),
    OperationBundle: Spec("bundle", ("version", "active"), lambda o: o.version),
    User: Spec(
        "user",
        ("username", "display_name", "role", "active", "must_change_password", "password_hash"),
        lambda o: o.username,
        secrets=("password_hash",),
    ),
    PlatformSetting: Spec("platform", ("value",), lambda o: o.key),
}

# Rows that belong to another object: (object type, parent class, parent id attribute,
# field of the parent, text of the row or None for "(changed)").
CHILDREN: dict[type, tuple[type, str, str, Callable[[Any], str] | None]] = {
    HostTag: (Host, "host_id", "tags", lambda o: o.text),
    SystemTag: (System, "system_id", "tags", lambda o: o.text),
    CustomOperationParameter: (CustomOperation, "operation_id", "parameters", None),
    TemplateStep: (OperationTemplate, "template_id", "steps", None),
}


def _show(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and len(value) > MAX_VALUE:
        return CHANGED
    return value


def _old_and_new(obj: object, name: str) -> tuple[bool, object, object]:
    history = inspect(obj).attrs[name].history
    if not history.has_changes():
        return False, None, None
    old = history.deleted[0] if history.deleted else None
    new = history.added[0] if history.added else None
    return old != new, old, new


class _Collector:
    """Changes of one flush, merged per object."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, object], dict[str, Any]] = {}

    def row(
        self, object_type: str, obj: object, object_id: int | None, name: str, action: str
    ) -> dict:
        # New objects have no id before the flush: keep them apart by identity.
        key = (object_type, object_id if object_id is not None else f"new-{id(obj)}")
        row = self.rows.get(key)
        if row is None:
            row = {
                "type": object_type,
                "id": object_id,
                "name": name,
                "action": action,
                "changes": {},
                "object": obj,
            }
            self.rows[key] = row
        elif action != UPDATED:
            row["action"] = action
        return row

    def change(self, row: dict, field_name: str, old: object, new: object) -> None:
        current = row["changes"].get(field_name)
        if current is None:
            row["changes"][field_name] = [old, new]
        else:  # e.g. several tags: list them together
            for index, value in ((0, old), (1, new)):
                if value is None:
                    continue
                if current[index] in (None, CHANGED):
                    current[index] = value
                elif value != CHANGED and str(value) not in str(current[index]).split(", "):
                    # Sorted: the order in which a flush lists its objects is random.
                    items = str(current[index]).split(", ") + [str(value)]
                    current[index] = ", ".join(sorted(items))


def _platform_type(key: str) -> str:
    return "attention_rules" if key.startswith("attention.") else "platform"


def _collect(session: Session) -> _Collector:
    collector = _Collector()
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        kind = type(obj)
        if obj in session.new:
            action = CREATED
        elif obj in session.deleted:
            action = DELETED
        else:
            action = UPDATED
        if kind is Instance:
            _instance(session, collector, obj, action)
            continue
        if kind in CHILDREN:
            _child(session, collector, obj, action)
            continue
        spec = SPECS.get(kind)
        if spec is None:
            continue
        object_type = spec.object_type
        if kind is PlatformSetting:
            object_type = _platform_type(obj.key)
        if action != UPDATED and not spec.lifecycle:
            continue
        object_id = getattr(obj, "id", None)
        if action == UPDATED:
            _removed_children(collector, obj, spec, object_type)
            changed = []
            for name in spec.fields:
                differs, old, new = _old_and_new(obj, name)
                if differs:
                    changed.append((name, old, new))
            if not changed:
                continue
            row = collector.row(object_type, obj, object_id, spec.name(obj), action)
            for name, old, new in changed:
                if name in spec.secrets or name in spec.opaque:
                    old, new = None, CHANGED
                collector.change(row, name, _show(old), _show(new))
        else:
            row = collector.row(object_type, obj, object_id, spec.name(obj), action)
            if action == CREATED:
                for name in spec.fields:
                    value = getattr(obj, name, None)
                    if value in (None, "", []):
                        continue
                    if name in spec.secrets or name in spec.opaque:
                        value = CHANGED
                    collector.change(row, name, None, _show(value))
    return collector


def _removed_children(collector: _Collector, obj: object, spec: Spec, object_type: str) -> None:
    """Rows taken out of a parent's list are deleted only during the flush (as orphans), so
    they are found in the history of the list."""
    for child_cls, (parent_cls, _id_attr, field_name, text) in CHILDREN.items():
        if parent_cls is not type(obj) or text is None:
            continue
        for child in inspect(obj).attrs[field_name].history.deleted:
            if isinstance(child, child_cls):
                row = collector.row(object_type, obj, obj.id, spec.name(obj), UPDATED)
                collector.change(row, field_name, text(child), None)


def _parent(session: Session, cls: type, parent_id: int | None) -> object | None:
    if parent_id is None:
        return None
    with session.no_autoflush:
        return session.get(cls, parent_id)


def _child(session: Session, collector: _Collector, obj: object, action: str) -> None:
    parent_cls, id_attr, field_name, text = CHILDREN[type(obj)]
    parent = getattr(obj, id_attr, None)
    parent_obj = _parent(session, parent_cls, parent)
    if parent_obj is None:
        # A row just added to its parent's list has no parent id before the flush.
        parent_obj = next(
            (
                p
                for p in list(session.new) + list(session.dirty)
                if isinstance(p, parent_cls) and obj in getattr(p, field_name)
            ),
            None,
        )
        parent = getattr(parent_obj, "id", None)
    if parent_obj is None or parent_obj in session.new or parent_obj in session.deleted:
        # A new parent lists its rows itself; a deleted one takes them along.
        if parent_obj is not None and parent_obj in session.new and text is not None:
            spec = SPECS[parent_cls]
            row = collector.row(spec.object_type, parent_obj, None, spec.name(parent_obj), CREATED)
            collector.change(row, field_name, None, text(obj))
        return
    spec = SPECS[parent_cls]
    row = collector.row(spec.object_type, parent_obj, parent, spec.name(parent_obj), UPDATED)
    if text is None:
        collector.change(row, field_name, None, CHANGED)
        return
    if action == CREATED:
        collector.change(row, field_name, None, text(obj))
    elif action == DELETED:
        collector.change(row, field_name, text(obj), None)
    else:
        differs, old, new = _old_and_new(obj, "value")
        if differs:
            key = obj.key  # type: ignore[attr-defined]
            collector.change(
                row, field_name, f"{key}={old}" if old else key, f"{key}={new}" if new else key
            )


def _instance_text(session: Session, instance: Instance) -> str:
    with session.no_autoflush:
        sid = session.get(Sid, instance.sid_id)
        host = session.get(Host, instance.host_id)
    return f"{sid.name if sid else '?'}/{instance.number} ({host.name if host else '?'})"


def _instance(session: Session, collector: _Collector, instance: Instance, action: str) -> None:
    """Assigning an instance to a system, or taking it out, changes the systems."""
    if action != UPDATED:
        return
    differs, old, new = _old_and_new(instance, "system_id")
    if not differs:
        return
    text = _instance_text(session, instance)
    for system_id, removed in ((old, True), (new, False)):
        system = _parent(session, System, system_id)  # type: ignore[arg-type]
        if system is None or system in session.deleted:
            continue
        row = collector.row("system", system, system.id, system.name, UPDATED)
        collector.change(row, "instances", text if removed else None, None if removed else text)


def _entry(row: dict, username: str | None, now: datetime) -> ConfigChange:
    return ConfigChange(
        changed_at=now,
        username=username,
        object_type=row["type"],
        object_id=row["id"],
        object_name=str(row["name"])[:255],
        action=row["action"],
        changes=json.dumps(row["changes"], ensure_ascii=False, default=str),
    )


def _after_flush(session: Session, _context: object) -> None:
    """New objects get their id only in the flush; fill it into their entries. Runs after
    the flush has finished (``after_flush_postexec``), so the change is flushed in turn."""
    pending = session.info.pop("config_new", None)
    if not pending:
        return
    for entry, obj in pending:
        entry.object_id = getattr(obj, "id", None)


def _before_flush(session: Session, _context: object, _instances: object) -> None:
    username = actor()
    if username is None:
        return
    collector = _collect(session)
    now = datetime.now(UTC)
    pending = session.info.setdefault("config_new", [])
    for row in collector.rows.values():
        entry = _entry(row, username, now)
        session.add(entry)
        if row["id"] is None:
            pending.append((entry, row["object"]))


def install() -> None:
    """Record changes in every session (once per process)."""
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
        event.listen(Session, "after_flush_postexec", _after_flush)


def record(
    session: AsyncSession | Session,
    object_type: str,
    object_id: int | None,
    name: str,
    changes: dict[str, list[object]],
    action: str = UPDATED,
) -> None:
    """Record a change made without the ORM (pool membership, dependencies, imports)."""
    username = actor()
    if username is None or not changes:
        return
    row = {"type": object_type, "id": object_id, "name": name, "action": action, "changes": changes}
    session.add(_entry(row, username, datetime.now(UTC)))


async def retention_days(session: AsyncSession) -> int:
    row = await session.get(PlatformSetting, RETENTION_KEY)
    try:
        return int(row.value) if row else DEFAULT_RETENTION_DAYS
    except ValueError:
        return DEFAULT_RETENTION_DAYS


async def purge(session: AsyncSession, now: datetime | None = None) -> int:
    """Delete entries older than the retention; returns how many. The caller commits."""
    days = await retention_days(session)
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    result = await session.execute(delete(ConfigChange).where(ConfigChange.changed_at < cutoff))
    return result.rowcount or 0

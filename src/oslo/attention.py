"""The "needs attention" list of the overview, built from rules.

Admins configure the rules for everyone (platform setting "attention.rules"): which kinds of
problems are shown, from when on (e.g. a run longer than 60 minutes) and what stays hidden
(e.g. failures of operations scheduled every hour, or of certain operations). Each user can
switch rules off and hide systems or pools for themselves (user setting "attention.user").

Each item names a translation key and its values, so the interface shows it in its language.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .catalog import Catalog
from .models import STAGES, Activity, Host, PlatformSetting, Schedule, System, User
from .operations import ACTIVE_STATUSES, ActivityStatus, OperationKind
from .users import get_setting, set_setting

RULES_KEY = "attention.rules"
USER_KEY = "attention.user"

# Rule -> its settings with the defaults; "enabled" switches a rule on or off.
DEFAULT_RULES: dict[str, dict[str, Any]] = {
    # Failed or partly failed activities of the last hours.
    "failed_activities": {
        "enabled": True,
        "hours": 24,
        # Hide failures of schedules repeating at least this often (interval schedules of at
        # most this many minutes; 0: hide none), e.g. operations planned every hour.
        "hide_scheduled_every_minutes": 60,
        # Keys of operations whose failures are not shown.
        "hide_operations": [],
        # Hide a failure once a later run of the same operation on the same target succeeded.
        "hide_when_succeeded_later": True,
        # Only systems of these stages; empty: all (activities without a system always).
        "stages": [],
    },
    # Systems with a status in "statuses" (not while an activity runs on them).
    "system_status": {"enabled": True, "statuses": ["RED", "YELLOW"], "stages": []},
    # Stopped systems of these stages, e.g. production.
    "stopped_systems": {"enabled": True, "stages": ["production"]},
    # Activities running longer than this.
    "long_running": {"enabled": True, "minutes": 60},
    # Hosts whose host agent could not be reached at the last discovery.
    "host_unreachable": {"enabled": True},
    # Schedules whose last run could not start.
    "schedule_errors": {"enabled": True},
    # Hosts without a discovery for this many days.
    "stale_discovery": {"enabled": False, "days": 7},
}
SYSTEM_STATUSES = ("RED", "YELLOW", "GRAY", "UNKNOWN")
_SCHEDULED = re.compile(r"\(schedule (\d+)\)$")


class RuleError(ValueError):
    pass


def check_rules(rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Complete and check rules given by an admin; unknown rules or settings are refused."""
    if unknown := set(rules) - set(DEFAULT_RULES):
        raise RuleError(f"Unknown rules: {sorted(unknown)}")
    result: dict[str, dict[str, Any]] = {}
    for name, defaults in DEFAULT_RULES.items():
        given = dict(rules.get(name) or {})
        if unknown := set(given) - set(defaults):
            raise RuleError(f"{name}: unknown settings {sorted(unknown)}")
        rule = defaults | given
        for key, default in defaults.items():
            value = rule[key]
            if isinstance(default, bool):
                if not isinstance(value, bool):
                    raise RuleError(f"{name}.{key}: true or false")
            elif isinstance(default, int):
                number = isinstance(value, int) and not isinstance(value, bool)
                if not number or not 0 <= value <= 100000:
                    raise RuleError(f"{name}.{key}: a number from 0 to 100000")
            elif isinstance(default, list):
                if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                    raise RuleError(f"{name}.{key}: a list of texts")
                allowed = {"stages": STAGES, "statuses": SYSTEM_STATUSES}.get(key)
                if allowed is not None and (bad := set(value) - set(allowed)):
                    raise RuleError(f"{name}.{key}: unknown values {sorted(bad)}")
                rule[key] = list(dict.fromkeys(value))
        result[name] = rule
    return result


async def load_rules(session: AsyncSession) -> dict[str, dict[str, Any]]:
    row = await session.get(PlatformSetting, RULES_KEY)
    stored = json.loads(row.value) if row else {}
    try:
        return check_rules({k: v for k, v in stored.items() if k in DEFAULT_RULES})
    except RuleError:
        return check_rules({})


async def save_rules(session: AsyncSession, rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checked = check_rules(rules)
    row = await session.get(PlatformSetting, RULES_KEY)
    if row is None:
        session.add(PlatformSetting(key=RULES_KEY, value=json.dumps(checked)))
    else:
        row.value = json.dumps(checked)
    await session.flush()
    return checked


@dataclass
class Exceptions:
    """What one user does not want to see."""

    disabled_rules: list[str] = field(default_factory=list)
    hidden_systems: list[int] = field(default_factory=list)
    hidden_pools: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, list]:
        return self.__dict__.copy()


async def load_exceptions(session: AsyncSession, user: User) -> Exceptions:
    raw = await get_setting(session, user, USER_KEY)
    try:
        data = json.loads(raw) if raw else {}
        return Exceptions(
            disabled_rules=[r for r in data.get("disabled_rules", []) if r in DEFAULT_RULES],
            hidden_systems=[int(i) for i in data.get("hidden_systems", [])],
            hidden_pools=[int(i) for i in data.get("hidden_pools", [])],
        )
    except (ValueError, TypeError, AttributeError):
        return Exceptions()


async def save_exceptions(session: AsyncSession, user: User, exceptions: Exceptions) -> None:
    if unknown := set(exceptions.disabled_rules) - set(DEFAULT_RULES):
        raise RuleError(f"Unknown rules: {sorted(unknown)}")
    clean = Exceptions(
        disabled_rules=list(dict.fromkeys(exceptions.disabled_rules)),
        hidden_systems=list(dict.fromkeys(exceptions.hidden_systems)),
        hidden_pools=list(dict.fromkeys(exceptions.hidden_pools)),
    )
    await set_setting(session, user, USER_KEY, json.dumps(clean.to_dict()))


def operation_key(activity: Activity, catalog: Catalog) -> str | None:
    """Catalog key of the operation an activity ran, e.g. "stop" or "copy_kernel"."""
    options = json.loads(activity.options or "{}") if activity.options else {}
    if activity.kind == OperationKind.TEMPLATE:
        return (options.get("template") or {}).get("key")
    if activity.kind == OperationKind.CUSTOM:
        custom_id = (options.get("custom") or {}).get("id")
        return next(
            (op.key for op in catalog.steps() if op.custom and op.custom.id == custom_id), None
        )
    return activity.kind.lower()


def _target(activity: Activity) -> tuple[str, int | None]:
    if activity.instance_id is not None:
        return "INSTANCE", activity.instance_id
    if activity.host_id is not None and activity.system_id is None:
        return "HOST", activity.host_id
    return activity.target_type, activity.system_id


@dataclass
class Item:
    rule: str
    severity: str  # error or warning
    key: str  # translation key
    values: dict[str, str | int]
    link: str
    at: datetime | None = None
    system_id: int | None = None
    host_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def attention_items(
    session: AsyncSession,
    catalog: Catalog,
    systems: Iterable[System],
    hosts: Iterable[Host],
    statuses: dict[int, str],
    running_systems: set[int],
    rules: dict[str, dict[str, Any]],
    exceptions: Exceptions,
    now: datetime | None = None,
) -> list[Item]:
    """Everything the rules show for this user, errors first, newest first."""
    now = now or datetime.now(UTC)
    on = {name for name, rule in rules.items() if rule["enabled"]} - set(exceptions.disabled_rules)
    systems = list(systems)
    stage_of = {s.id: s.stage for s in systems}
    pool_of = {s.id: s.pool.id if s.pool else None for s in systems}

    def hidden(system_id: int | None) -> bool:
        if system_id is None:
            return False
        return system_id in exceptions.hidden_systems or pool_of.get(system_id) in set(
            exceptions.hidden_pools
        )

    def in_stages(system_id: int | None, stages: list[str]) -> bool:
        return not stages or system_id is None or stage_of.get(system_id) in stages

    items: list[Item] = []
    if "system_status" in on or "stopped_systems" in on:
        for system in systems:
            if hidden(system.id) or system.id in running_systems:
                continue
            status = statuses.get(system.id, "UNKNOWN")
            values = {"system": system.name, "status": status}
            link = f"/landscape?system={system.id}"
            rule = rules["system_status"]
            if (
                "system_status" in on
                and status in rule["statuses"]
                and in_stages(system.id, rule["stages"])
            ):
                severity = "error" if status == "RED" else "warning"
                items.append(
                    Item(
                        "system_status",
                        severity,
                        "att.system_status",
                        values,
                        link,
                        system_id=system.id,
                    )
                )
            elif (
                "stopped_systems" in on
                and status == "GRAY"
                and system.stage in rules["stopped_systems"]["stages"]
            ):
                items.append(
                    Item("stopped_systems", "warning", "att.stopped", values, link, None, system.id)
                )

    if "failed_activities" in on:
        rule = rules["failed_activities"]
        since = now - timedelta(hours=rule["hours"])
        recent = list(
            await session.scalars(
                select(Activity)
                .where(Activity.requested_at >= since, Activity.parent_id.is_(None))
                .order_by(Activity.id.desc())
                .limit(2000)
            )
        )
        frequent = set()
        if rule["hide_scheduled_every_minutes"]:
            frequent = set(
                await session.scalars(
                    select(Schedule.id).where(
                        Schedule.recurrence == "interval",
                        Schedule.interval_minutes <= rule["hide_scheduled_every_minutes"],
                    )
                )
            )
        succeeded: set[tuple[str | None, str, int | None]] = set()
        for activity in recent:  # newest first
            key = operation_key(activity, catalog)
            target = _target(activity)
            if activity.status == ActivityStatus.SUCCEEDED:
                succeeded.add((key, *target))
                continue
            if activity.status not in (ActivityStatus.FAILED, ActivityStatus.PARTIAL):
                continue
            if key in rule["hide_operations"] or hidden(activity.system_id):
                continue
            if not in_stages(activity.system_id, rule["stages"]):
                continue
            if rule["hide_when_succeeded_later"] and (key, *target) in succeeded:
                continue
            match = _SCHEDULED.search(activity.requested_by or "")
            if match and int(match.group(1)) in frequent:
                continue
            items.append(
                Item(
                    "failed_activities",
                    "error" if activity.status == ActivityStatus.FAILED else "warning",
                    "att.failed",
                    {
                        "id": activity.id,
                        "kind": activity.kind,
                        "target": activity.target_label,
                        "error": (activity.error or "")[:200],
                    },
                    f"/activities/{activity.id}",
                    _utc(activity.finished_at or activity.requested_at),
                    activity.system_id,
                    activity.host_id,
                )
            )

    if "long_running" in on:
        limit = now - timedelta(minutes=rules["long_running"]["minutes"])
        rows = await session.scalars(
            select(Activity).where(
                Activity.status.in_(ACTIVE_STATUSES),
                Activity.parent_id.is_(None),
                Activity.requested_at <= limit,
            )
        )
        for activity in rows:
            if hidden(activity.system_id):
                continue
            started = _utc(activity.started_at or activity.requested_at)
            minutes = int((now - started).total_seconds() // 60) if started else 0
            items.append(
                Item(
                    "long_running",
                    "warning",
                    "att.long_running",
                    {"id": activity.id, "target": activity.target_label, "minutes": minutes},
                    f"/activities/{activity.id}",
                    started,
                    activity.system_id,
                )
            )

    for host in hosts:
        link = f"/landscape?tab=hosts&host={host.id}"
        if "host_unreachable" in on and host.reachable is False:
            items.append(
                Item(
                    "host_unreachable",
                    "error",
                    "att.host_unreachable",
                    {"host": host.name, "error": (host.last_error or "")[:200]},
                    link,
                    _utc(host.last_discovery_at),
                    None,
                    host.id,
                )
            )
        if "stale_discovery" in on:
            last = _utc(host.last_discovery_at)
            days = rules["stale_discovery"]["days"]
            if last is None or last < now - timedelta(days=days):
                items.append(
                    Item(
                        "stale_discovery",
                        "warning",
                        "att.stale_discovery",
                        {"host": host.name, "days": days},
                        link,
                        last,
                        None,
                        host.id,
                    )
                )

    if "schedule_errors" in on:
        rows = await session.scalars(
            select(Schedule).where(Schedule.last_error.is_not(None), Schedule.enabled.is_(True))
        )
        for schedule in rows:
            items.append(
                Item(
                    "schedule_errors",
                    "warning",
                    "att.schedule_error",
                    {"operation": schedule.operation, "error": schedule.last_error or ""},
                    "/operations/templates",
                    _utc(schedule.last_run_at),
                )
            )

    order = {"error": 0, "warning": 1}
    minimum = datetime.min.replace(tzinfo=UTC)
    items.sort(key=lambda i: (order[i.severity], -(i.at or minimum).timestamp()))
    return items


def overview_columns(systems: Iterable[System]) -> list[str]:
    """Stages shown as columns: development, quality and production always, sandbox and
    preprod if a system has them; "" for systems without a stage, if there are any."""
    used = {s.stage for s in systems}
    columns = [s for s in STAGES if s in ("development", "quality", "production") or s in used]
    if None in used or "" in used:
        columns.append("")
    return columns

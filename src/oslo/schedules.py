"""Planned operations: once at a time, daily at a time of day, or every N minutes.

A schedule names an operation of the catalog (built-in, custom or template), its targets
and parameter values. When it is due, the scheduler starts it with the rights of the user
who created it, checked again at that moment. Several targets run as a mass operation.
Times of day are local time in the time zone of the settings (OSLO_TIMEZONE).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .catalog import Catalog, OperationDef
from .customops import ParameterError, parameter_values
from .models import Activity, Schedule, User
from .operations import (
    DEFAULT_TIMEOUT_SECONDS,
    NotAssignedError,
    OperationConflictError,
    OperationRunner,
    TargetNotFoundError,
    TargetType,
)
from .templates import template_values
from .users import has_role

logger = logging.getLogger(__name__)

RECURRENCES = ("once", "daily", "interval")
MIN_INTERVAL_MINUTES = 5
TIME_PATTERN = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


class ScheduleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def next_run(schedule: Schedule, after: datetime, zone: ZoneInfo) -> datetime | None:
    """The next time the schedule is due after ``after`` (UTC); None when it is used up."""
    if schedule.recurrence == "once":
        if schedule.run_at is None or schedule.last_run_at is not None:
            return None
        return _utc(schedule.run_at)
    if schedule.recurrence == "interval":
        minutes = schedule.interval_minutes or MIN_INTERVAL_MINUTES
        if schedule.last_run_at is None:
            return after
        return max(_utc(schedule.last_run_at) + timedelta(minutes=minutes), after)
    # daily: the next local time_of_day on one of the weekdays (1 = Monday)
    hour, minute = (int(x) for x in (schedule.time_of_day or "00:00").split(":"))
    local = after.astimezone(zone)
    for day in range(8):
        candidate = (local + timedelta(days=day)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate > local and str(candidate.isoweekday()) in schedule.weekdays:
            return candidate.astimezone(UTC)
    return None


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def check_values(
    definition: OperationDef, given: Mapping[str, str | int | bool]
) -> dict[str, dict[str, str]] | dict[str, str] | None:
    """Checked parameter values for a run of ``definition`` (None for built-ins)."""
    if definition.template is not None:
        return template_values(definition.template, given)
    if definition.custom is not None:
        return parameter_values(definition.custom, given)
    return None


async def save_schedule(
    session: AsyncSession,
    catalog: Catalog,
    schedule: Schedule | None,
    user: User,
    zone: ZoneInfo,
    *,
    operation: str,
    name: str | None = None,
    target_type: str,
    target_ids: Sequence[int],
    parameters: Mapping[str, str | int | bool],
    recurrence: str,
    run_at: datetime | None,
    time_of_day: str | None,
    weekdays: str,
    interval_minutes: int | None,
    enabled: bool,
    now: datetime,
) -> Schedule:
    """Create or change a schedule; the operation's role and parameters are checked now
    and again when it runs. The caller commits."""
    definition = catalog.get(operation)
    if definition is None or not definition.standalone:
        raise ScheduleError("schedule_operation", f"No operation {operation}")
    ids = list(dict.fromkeys(int(i) for i in target_ids))
    fixed = definition.template is not None and not definition.template.selection
    if fixed:
        # A template with fixed targets only runs as it is.
        if target_type or ids:
            raise ScheduleError("schedule_targets", f"{operation} has fixed targets")
        kind = None
    else:
        try:
            kind = TargetType(target_type)
        except ValueError as exc:
            raise ScheduleError("invalid_input", "Unknown target type") from exc
        if kind not in definition.targets:
            raise ScheduleError("schedule_operation", f"{operation} does not run on {target_type}")
        if not ids:
            raise ScheduleError("schedule_targets", "Choose at least one target")
    if len(ids) > 1 and not definition.mass:
        raise ScheduleError("schedule_targets", f"{operation} allows no mass operation")
    if not has_role(user, definition.role):
        raise ScheduleError("forbidden", f"Requires the role {definition.role.value}")
    try:
        check_values(definition, parameters)
    except ParameterError as exc:
        raise ScheduleError("parameter_values", str(exc)) from exc
    if recurrence not in RECURRENCES:
        raise ScheduleError("invalid_input", "Unknown recurrence")
    if recurrence == "once" and run_at is None:
        raise ScheduleError("schedule_time", "A one-time schedule needs a date and time")
    if recurrence == "daily":
        if not time_of_day or not TIME_PATTERN.fullmatch(time_of_day):
            raise ScheduleError("schedule_time", "Time of day as HH:MM")
        if not weekdays or set(weekdays) - set("1234567"):
            raise ScheduleError("schedule_time", "Choose at least one weekday")
    if recurrence == "interval" and (interval_minutes or 0) < MIN_INTERVAL_MINUTES:
        raise ScheduleError(
            "schedule_time", f"An interval of at least {MIN_INTERVAL_MINUTES} minutes"
        )

    if schedule is None:
        schedule = Schedule(created_at=now, created_by=user.username)
        session.add(schedule)
    schedule.operation = operation
    schedule.name = (name or "").strip() or None
    schedule.target_type = kind.value if kind else ""
    schedule.target_ids = json.dumps(ids)
    schedule.parameters = json.dumps(dict(parameters))
    schedule.recurrence = recurrence
    schedule.run_at = run_at.astimezone(UTC) if run_at else None
    schedule.time_of_day = time_of_day if recurrence == "daily" else None
    schedule.weekdays = "".join(sorted(set(weekdays))) if recurrence == "daily" else "1234567"
    schedule.interval_minutes = interval_minutes if recurrence == "interval" else None
    schedule.enabled = enabled
    schedule.last_run_at = None if recurrence == "once" else schedule.last_run_at
    schedule.next_run_at = next_run(schedule, now, zone) if enabled else None
    await session.flush()
    return schedule


async def start_operation(
    session: AsyncSession,
    runner: OperationRunner,
    definition: OperationDef,
    target_type: TargetType | None,
    target_ids: list[int],
    parameters: Mapping[str, str | int | bool],
    requested_by: str,
) -> Activity:
    """Start an operation of the catalog on one or more targets, as the landscape does. A
    template runs once on all targets (its selection)."""
    values = check_values(definition, parameters)
    if definition.template is not None:
        return await runner.submit_template(
            session, definition.template, target_ids, values, requested_by
        )
    assert target_type is not None
    if len(target_ids) > 1:
        return await runner.submit_mass(
            session,
            definition.kind,
            target_type,
            target_ids,
            requested_by=requested_by,
            timeout_seconds=(
                definition.custom.timeout_seconds if definition.custom else DEFAULT_TIMEOUT_SECONDS
            ),
            custom=definition.custom,
            parameters=values if definition.custom else None,
        )
    [target] = target_ids
    if definition.custom is not None:
        return await runner.submit_custom(
            session, definition.custom, target_type, target, values, requested_by=requested_by
        )
    if target_type == TargetType.HOST:
        return await runner.submit_host(session, target, definition.kind, requested_by=requested_by)
    if target_type == TargetType.INSTANCE:
        return await runner.submit_instance(
            session, target, definition.kind, requested_by=requested_by
        )
    return await runner.submit_system(session, target, definition.kind, requested_by=requested_by)


class Scheduler:
    """Starts due schedules. ``tick`` checks once; ``run`` checks every ``interval``."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        runner: OperationRunner,
        catalog: Catalog,
        zone: ZoneInfo,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        interval: float = 30.0,
    ) -> None:
        self._session_factory = session_factory
        self._runner = runner
        self._catalog = catalog
        self.zone = zone
        self.now = now
        self._sleep = sleep
        self.interval = interval

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 - the scheduler must keep running
                logger.exception("Scheduler tick failed")
            await self._sleep(self.interval)

    async def tick(self) -> list[int]:
        """Start every due schedule once; returns the ids of the activities started."""
        now = self.now()
        started: list[int] = []
        async with self._session_factory() as session:
            due = list(
                await session.scalars(
                    select(Schedule).where(Schedule.enabled.is_(True), Schedule.next_run_at <= now)
                )
            )
            for schedule in due:
                activity_id = await self._fire(session, schedule)
                schedule.last_run_at = now
                schedule.next_run_at = next_run(schedule, now + timedelta(seconds=1), self.zone)
                if schedule.next_run_at is None:
                    schedule.enabled = False
                await session.commit()
                if activity_id is not None:
                    started.append(activity_id)
        return started

    async def _fire(self, session: AsyncSession, schedule: Schedule) -> int | None:
        """Start the schedule's operation; problems are recorded in ``last_error``."""
        user = await session.scalar(select(User).where(User.username == schedule.created_by))
        definition = self._catalog.get(schedule.operation)
        schedule.last_error = None
        if user is None or not user.active:
            schedule.last_error = f"User {schedule.created_by} no longer exists or is disabled"
        elif definition is None:
            schedule.last_error = f"Operation {schedule.operation} no longer exists"
        elif not has_role(user, definition.role):
            schedule.last_error = f"{user.username} no longer has the role {definition.role.value}"
        if schedule.last_error:
            return None
        assert definition is not None
        try:
            activity = await start_operation(
                session,
                self._runner,
                definition,
                TargetType(schedule.target_type) if schedule.target_type else None,
                json.loads(schedule.target_ids),
                json.loads(schedule.parameters or "{}"),
                f"{schedule.created_by} (schedule {schedule.id})",
            )
        except (
            ParameterError,
            TargetNotFoundError,
            NotAssignedError,
            OperationConflictError,
            ValueError,
        ) as exc:
            schedule.last_error = str(exc)
            return None
        schedule.last_activity_id = activity.id
        return activity.id

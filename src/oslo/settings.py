"""Configuration from environment variables."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./landscape.db"


class SettingsError(Exception):
    """The configuration is missing or invalid."""


_warned: set[str] = set()


def env_value(env: Mapping[str, str], name: str, default: str = "") -> str:
    """``OSLO_<name>``, or the old ``LO_<name>`` from before the rename, with a warning."""
    value = env.get(f"OSLO_{name}")
    if value is not None:
        return value
    old = env.get(f"LO_{name}")
    if old is None:
        return default
    if name not in _warned:
        _warned.add(name)
        print(f"LO_{name} is deprecated; rename it to OSLO_{name}.", file=sys.stderr)
    return old


DEFAULT_TIMEZONE = "Europe/Berlin"


def _timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise SettingsError(f"OSLO_TIMEZONE {name!r} is not a known time zone") from exc
    return name


@dataclass(frozen=True)
class Settings:
    secret_key: str
    database_url: str = DEFAULT_DATABASE_URL
    # Time zone for times of day in schedules (IANA name). Assumption: the owner's landscape
    # runs in Central Europe; set OSLO_TIMEZONE otherwise.
    timezone: str = DEFAULT_TIMEZONE

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        secret_key = env_value(env, "SECRET_KEY")
        if not secret_key:
            raise SettingsError("OSLO_SECRET_KEY is not set. Create one with: oslo-keygen")
        return cls(
            secret_key=secret_key,
            database_url=env_value(env, "DATABASE_URL", DEFAULT_DATABASE_URL),
            timezone=_timezone(env_value(env, "TIMEZONE", DEFAULT_TIMEZONE)),
        )

"""Users, roles, passwords, browser sessions and personal API tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ApiToken, User, UserSetting

# Cookie of the signed-in browser session; read by the web pages and the API.
SESSION_COOKIE = "oslo_session"
# Header the browser interface sends with every API call that changes something. Other
# sites cannot send it without a CORS preflight, which the server does not allow.
API_REQUEST_HEADER = "x-oslo-request"

MIN_PASSWORD_LENGTH = 12
MAX_FAILED_LOGINS = 5
LOCK_SECONDS = 60
SESSION_LIFETIME_SECONDS = 8 * 3600
USERNAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
TOKEN_PREFIX = "oslo_"

# scrypt parameters (memory about 16 MB per hash).
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


class Role(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    CONFIGURATOR = "configurator"
    ADMIN = "admin"


ROLE_ORDER = (Role.VIEWER, Role.OPERATOR, Role.CONFIGURATOR, Role.ADMIN)


def has_role(user: User, required: Role) -> bool:
    """Roles build on each other: an admin may do everything a configurator may, etc."""
    try:
        return ROLE_ORDER.index(Role(user.role)) >= ROLE_ORDER.index(required)
    except ValueError:
        return False


class UserError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    # SQLite returns naive datetimes; they are stored in UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


# --- passwords ----------------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    encode = base64.b64encode
    return (
        f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}$"
        f"{encode(salt).decode()}${encode(digest).decode()}"
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise UserError(
            "password_short", f"The password needs at least {MIN_PASSWORD_LENGTH} characters"
        )


# --- users --------------------------------------------------------------------------------


def normalize_username(username: str) -> str:
    name = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(name):
        raise UserError(
            "username_invalid",
            "User names consist of lowercase letters, digits, '.', '-' and '_'",
        )
    return name


async def user_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count(User.id))) or 0


async def create_user(
    session: AsyncSession,
    username: str,
    password: str,
    role: Role | str,
    *,
    display_name: str | None = None,
    must_change_password: bool = False,
) -> User:
    """Create a user. The caller commits."""
    name = normalize_username(username)
    check_password(password)
    if await session.scalar(select(User.id).where(User.username == name)) is not None:
        raise UserError("username_taken", f"The user {name} already exists")
    user = User(
        username=name,
        display_name=(display_name or "").strip() or None,
        password_hash=hash_password(password),
        role=Role(role).value,
        active=True,
        must_change_password=must_change_password,
        session_epoch=0,
        failed_logins=0,
        created_at=_now(),
    )
    session.add(user)
    await session.flush()
    return user


async def _active_admins(session: AsyncSession) -> int:
    return (
        await session.scalar(
            select(func.count(User.id)).where(User.role == Role.ADMIN, User.active.is_(True))
        )
        or 0
    )


async def update_user(
    session: AsyncSession,
    user: User,
    *,
    role: Role | str | None = None,
    active: bool | None = None,
    display_name: str | None = None,
) -> None:
    """Change role, active flag or display name. The caller commits.

    The last active admin can be neither demoted nor deactivated. A change of role or of
    the active flag ends the user's browser sessions.
    """
    new_role = Role(role).value if role is not None else user.role
    new_active = user.active if active is None else active
    was_admin = user.role == Role.ADMIN and user.active
    if was_admin and not (new_role == Role.ADMIN and new_active):
        if await _active_admins(session) <= 1:
            raise UserError("last_admin", "The last active admin must stay an active admin")
    if new_role != user.role or new_active != user.active:
        user.session_epoch += 1
    user.role = new_role
    user.active = new_active
    if display_name is not None:
        user.display_name = display_name.strip() or None


def set_password(user: User, password: str, *, must_change: bool = False) -> None:
    """Set a new password and end all browser sessions of the user. The caller commits."""
    check_password(password)
    user.password_hash = hash_password(password)
    user.must_change_password = must_change
    user.session_epoch += 1
    user.failed_logins = 0
    user.locked_until = None


async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
    """The user if name and password match, the account is active and not locked.

    Counts failed attempts; after MAX_FAILED_LOGINS the account is locked for LOCK_SECONDS.
    The caller commits, also on failure, so the counter is kept.
    """
    try:
        name = normalize_username(username)
    except UserError:
        return None
    user = await session.scalar(select(User).where(User.username == name))
    if user is None:
        verify_password(password, _DUMMY_HASH)  # same effort as for a real user
        return None
    now = _now()
    locked_until = _aware(user.locked_until)
    if locked_until is not None and locked_until > now:
        return None
    if not verify_password(password, user.password_hash) or not user.active:
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(seconds=LOCK_SECONDS)
            user.failed_logins = 0
        return None
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    return user


_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


# --- browser sessions ---------------------------------------------------------------------


def _session_key(secret_key: str) -> bytes:
    return hmac.new(secret_key.encode(), b"oslo-session-key", hashlib.sha256).digest()


def _session_signature(secret_key: str, payload: str) -> str:
    return hmac.new(_session_key(secret_key), payload.encode(), hashlib.sha256).hexdigest()


def create_session(secret_key: str, user: User, now: float | None = None) -> str:
    """Cookie value: user id, session epoch, expiry and signature."""
    expires = int((time.time() if now is None else now) + SESSION_LIFETIME_SECONDS)
    payload = f"{user.id}.{user.session_epoch}.{expires}"
    return f"{payload}.{_session_signature(secret_key, payload)}"


def parse_session(
    secret_key: str, value: str | None, now: float | None = None
) -> tuple[int, int] | None:
    """(user id, session epoch) of a valid, unexpired cookie value."""
    parts = (value or "").split(".")
    if len(parts) != 4 or not all(part.isdigit() for part in parts[:3]):
        return None
    user_id, epoch, expires, signature = parts
    if int(expires) < (time.time() if now is None else now):
        return None
    expected = _session_signature(secret_key, f"{user_id}.{epoch}.{expires}")
    if not hmac.compare_digest(signature, expected):
        return None
    return int(user_id), int(epoch)


async def session_user(
    session: AsyncSession, secret_key: str, value: str | None
) -> User | None:
    parsed = parse_session(secret_key, value)
    if parsed is None:
        return None
    user = await session.get(User, parsed[0])
    if user is None or not user.active or user.session_epoch != parsed[1]:
        return None
    return user


# --- API tokens ---------------------------------------------------------------------------


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_token(
    session: AsyncSession, user: User, name: str, expires_at: datetime | None = None
) -> tuple[ApiToken, str]:
    """A new token for ``user``; the plain text is returned only here. The caller commits."""
    name = name.strip()
    if not name or len(name) > 64:
        raise UserError("token_name", "The token needs a name of at most 64 characters")
    plain = TOKEN_PREFIX + secrets.token_urlsafe(32)
    token = ApiToken(
        user_id=user.id,
        name=name,
        token_hash=_token_hash(plain),
        prefix=plain[:10],
        created_at=_now(),
        expires_at=expires_at,
    )
    session.add(token)
    await session.flush()
    return token, plain


async def token_user(session: AsyncSession, plain: str) -> User | None:
    """The active user of a valid, unexpired token; records its use. The caller commits."""
    if not plain:
        return None
    token = await session.scalar(select(ApiToken).where(ApiToken.token_hash == _token_hash(plain)))
    if token is None:
        return None
    now = _now()
    expires_at = _aware(token.expires_at)
    if expires_at is not None and expires_at <= now:
        return None
    user = await session.get(User, token.user_id)
    if user is None or not user.active:
        return None
    token.last_used_at = now
    return user


# --- settings -----------------------------------------------------------------------------


async def get_setting(session: AsyncSession, user: User, key: str) -> str | None:
    setting = await session.get(UserSetting, (user.id, key))
    return setting.value if setting else None


async def set_setting(session: AsyncSession, user: User, key: str, value: str) -> None:
    setting = await session.get(UserSetting, (user.id, key))
    if setting is None:
        session.add(UserSetting(user_id=user.id, key=key, value=value))
    else:
        setting.value = value


# Display preferences of a user ("Mein Konto"): language ("" follows the browser), color
# scheme ("system" follows the operating system) and the zone times are shown in ("browser":
# the browser's local time, "utc"). Times are always stored and sent in UTC.
PREFERENCE_LANGUAGE = "ui.language"
PREFERENCE_THEME = "ui.theme"
PREFERENCE_TIME = "ui.time"
PREFERENCE_LANGUAGES = ("", "en", "de")
THEMES = ("system", "light", "dark")
TIME_DISPLAYS = ("browser", "utc")


async def get_preferences(session: AsyncSession, user: User) -> dict[str, str]:
    language = await get_setting(session, user, PREFERENCE_LANGUAGE) or ""
    theme = await get_setting(session, user, PREFERENCE_THEME) or "system"
    time = await get_setting(session, user, PREFERENCE_TIME) or "browser"
    return {
        "language": language if language in PREFERENCE_LANGUAGES else "",
        "theme": theme if theme in THEMES else "system",
        "time": time if time in TIME_DISPLAYS else "browser",
    }


async def set_preferences(
    session: AsyncSession,
    user: User,
    *,
    language: str | None = None,
    theme: str | None = None,
    time: str | None = None,
) -> None:
    """Change the given preferences; the caller commits. Raises ValueError for unknown ones."""
    if language is not None:
        if language not in PREFERENCE_LANGUAGES:
            raise ValueError(f"Unknown language {language!r}")
        await set_setting(session, user, PREFERENCE_LANGUAGE, language)
    if theme is not None:
        if theme not in THEMES:
            raise ValueError(f"Unknown color scheme {theme!r}")
        await set_setting(session, user, PREFERENCE_THEME, theme)
    if time is not None:
        if time not in TIME_DISPLAYS:
            raise ValueError(f"Unknown time display {time!r}")
        await set_setting(session, user, PREFERENCE_TIME, time)

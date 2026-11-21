"""``oslo-user``: manage users from the command line, e.g. when no admin can sign in."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy import select

from .db import SchemaError, create_engine, create_session_factory, upgrade_database
from .models import User
from .settings import DEFAULT_DATABASE_URL, env_value
from .users import ROLE_ORDER, UserError, create_user, normalize_username, set_password


def _read_password(prompt: str = "Password: ") -> str:
    password = getpass.getpass(prompt)
    if password != getpass.getpass("Repeat password: "):
        raise UserError("password_mismatch", "The passwords do not match")
    return password


async def _run(args: argparse.Namespace, database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        await upgrade_database(engine, database_url)
        async with create_session_factory(engine)() as session:
            if args.action == "list":
                for user in await session.scalars(select(User).order_by(User.username)):
                    state = "active" if user.active else "inactive"
                    print(f"{user.username:<24} {user.role:<13} {state}")
                return
            if args.action == "add":
                password = _read_password()
                await create_user(
                    session,
                    args.username,
                    password,
                    args.role,
                    display_name=args.display_name,
                    must_change_password=args.must_change,
                )
                await session.commit()
                print(f"User {normalize_username(args.username)} created ({args.role})")
                return
            # passwd: set a new password, unlock and activate the account
            name = normalize_username(args.username)
            user = await session.scalar(select(User).where(User.username == name))
            if user is None:
                raise UserError("unknown_user", f"No user {name}")
            set_password(user, _read_password("New password: "), must_change=args.must_change)
            user.active = True
            await session.commit()
            print(f"Password of {name} set; the account is active and unlocked")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="OSLO users")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("list", help="list users")
    add = commands.add_parser("add", help="create a user (asks for the password)")
    add.add_argument("username")
    add.add_argument("--role", choices=[r.value for r in ROLE_ORDER], default="viewer")
    add.add_argument("--display-name")
    add.add_argument("--must-change", action="store_true", help="password must be changed")
    passwd = commands.add_parser("passwd", help="set a password, unlock and activate")
    passwd.add_argument("username")
    passwd.add_argument("--must-change", action="store_true", help="password must be changed")
    args = parser.parse_args()

    database_url = env_value(os.environ, "DATABASE_URL", DEFAULT_DATABASE_URL)
    try:
        asyncio.run(_run(args, database_url))
    except (UserError, SchemaError) as exc:
        sys.exit(f"Error: {exc}")

from __future__ import annotations

import pytest

from oslo.crypto import (
    SecretBox,
    SecretError,
    generate_secret_key,
)
from oslo.settings import DEFAULT_DATABASE_URL, Settings, SettingsError


def test_encrypt_roundtrip():
    box = SecretBox(generate_secret_key())
    token = box.encrypt("s3cret-pässword")
    assert "s3cret" not in token
    assert box.decrypt(token) == "s3cret-pässword"


def test_same_password_encrypts_differently():
    box = SecretBox(generate_secret_key())
    assert box.encrypt("x") != box.encrypt("x")


def test_decrypt_with_other_key_fails():
    token = SecretBox(generate_secret_key()).encrypt("x")
    with pytest.raises(SecretError, match="secret key changed"):
        SecretBox(generate_secret_key()).decrypt(token)


def test_invalid_key_is_rejected():
    with pytest.raises(SecretError, match="not a valid Fernet key"):
        SecretBox("too-short")


def test_settings_from_env():
    env = {"OSLO_SECRET_KEY": generate_secret_key()}
    settings = Settings.from_env(env)
    assert settings.database_url == DEFAULT_DATABASE_URL
    assert Settings.from_env(env | {"OSLO_DATABASE_URL": "sqlite+aiosqlite:///x.db"}).database_url


def test_settings_require_secret_key():
    with pytest.raises(SettingsError, match="OSLO_SECRET_KEY"):
        Settings.from_env({})
    # LO_API_TOKEN is no longer used.
    assert Settings.from_env({"OSLO_SECRET_KEY": "k", "LO_API_TOKEN": "x"}).secret_key == "k"


def test_old_variable_names_still_work(capsys):
    settings = Settings.from_env({"LO_SECRET_KEY": "old", "LO_TIMEZONE": "UTC"})
    assert settings.secret_key == "old" and settings.timezone == "UTC"
    assert "rename it to OSLO_" in capsys.readouterr().err
    # The new name wins over the old one.
    assert Settings.from_env({"OSLO_SECRET_KEY": "new", "LO_SECRET_KEY": "old"}).secret_key == "new"

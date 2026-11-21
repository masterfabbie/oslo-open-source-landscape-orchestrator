"""Encryption of stored credentials."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class SecretError(Exception):
    """A secret could not be encrypted or decrypted."""


class SecretBox:
    """Encrypts passwords for storage in the database (Fernet: AES-128-CBC with HMAC)."""

    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode())
        except (ValueError, TypeError) as exc:
            raise SecretError("The secret key is not a valid Fernet key") from exc

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise SecretError(
                "Stored credential cannot be decrypted. Was the secret key changed?"
            ) from exc


def generate_secret_key() -> str:
    return Fernet.generate_key().decode()


def keygen() -> None:
    """Entry point of ``oslo-keygen``: print a fresh value for OSLO_SECRET_KEY."""
    print(f"OSLO_SECRET_KEY={generate_secret_key()}")

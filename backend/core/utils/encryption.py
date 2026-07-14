from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


class SymmetricEncryptor:
    """Symmetric encryptor for application secrets."""

    def __init__(self, key: str) -> None:
        if not key:
            raise ValueError("Encryption key must not be empty")

        self._fernet = Fernet(key.encode("utf-8"))

    def encrypt(self, value: str) -> str:
        if value is None:
            raise ValueError("Cannot encrypt None")

        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, encrypted_value: str) -> str:
        if encrypted_value is None:
            raise ValueError("Cannot decrypt None")

        try:
            return self._fernet.decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Invalid encryption token or key") from exc


def encrypt_secret(value: str, key: str) -> str:
    return SymmetricEncryptor(key).encrypt(value)


def decrypt_secret(encrypted_value: str, key: str) -> str:
    return SymmetricEncryptor(key).decrypt(encrypted_value)


def get_secret_encryption_key() -> str:
    key = os.getenv("SECRET_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("SECRET_ENCRYPTION_KEY must be set")
    return key

import pytest
from cryptography.fernet import Fernet

from core.utils.encryption import (
    SymmetricEncryptor,
    decrypt_secret,
    encrypt_secret,
)


def generate_encryption_key() -> str:
    return Fernet.generate_key().decode("utf-8")


def test_encrypt_decrypt_round_trip() -> None:
    key = generate_encryption_key()
    encryptor = SymmetricEncryptor(key)

    encrypted = encryptor.encrypt("super-secret-value")

    assert encrypted != "super-secret-value"
    assert encryptor.decrypt(encrypted) == "super-secret-value"


def test_convenience_functions_round_trip() -> None:
    key = generate_encryption_key()

    encrypted = encrypt_secret("mongodb-instance-secret", key)

    assert decrypt_secret(encrypted, key) == "mongodb-instance-secret"


def test_generate_encryption_key_returns_valid_fernet_key() -> None:
    key = generate_encryption_key()

    encrypted = Fernet(key.encode("utf-8")).encrypt(b"value")

    assert Fernet(key.encode("utf-8")).decrypt(encrypted) == b"value"


def test_decrypt_with_wrong_key_raises_value_error() -> None:
    encrypted = encrypt_secret("secret", generate_encryption_key())

    with pytest.raises(ValueError, match="Invalid encryption token or key"):
        decrypt_secret(encrypted, generate_encryption_key())


def test_empty_key_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Encryption key must not be empty"):
        SymmetricEncryptor("")

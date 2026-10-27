"""
Signs time-limited links for storage services that run next to the data (POSIX file services).

The backend decides access; the file service only checks that a link was signed here, names its
namespace, path and operation, and hasn't expired.
"""
import base64
import os
import time
import uuid
from functools import lru_cache
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ALGORITHM = "RS256"
ISSUER = "inn-portal"
KEY_FILE_ENV = "STORAGE_LINK_SIGNING_KEY_FILE"
OPERATIONS = {"read", "write", "stat", "delete"}


class LinkSigner:
    """Signs and publishes the public key for storage link tokens."""

    def __init__(self, private_key: rsa.RSAPrivateKey, key_id: str = "storage-links-1"):
        """
        :param private_key: RSA private key used to sign tokens.
        :param key_id: Key identifier published with the public key.
        """
        self._private_key = private_key
        self.key_id = key_id

    @classmethod
    def from_pem_file(cls, path: str) -> "LinkSigner":
        """Load the signing key from a PEM file."""
        with open(path, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise TypeError("Storage link signing key must be an RSA private key")
        return cls(key)

    def sign(self, namespace: str, path: str, operation: str, ttl: int, subject: str | None = None,
             grant: str | None = None) -> str:
        """
        Sign a token for one operation on one path.

        :param namespace: The storage instance's namespace (token audience).
        :param path: The resource, ``namespace/key``.
        :param operation: One of ``read``, ``write``, ``stat``, ``delete``.
        :param ttl: Lifetime in seconds.
        :param subject: The portal user the link is issued to (``sub``), so the file service can record
            which person each link, and its temporary user ID, served.
        :param grant: The approval the link belongs to (``grant``). Links of one approval share it, so
            the file service gives them one temporary user ID instead of one per link.
        :return: The signed token.
        """
        if operation not in OPERATIONS:
            raise ValueError(f"Unsupported operation {operation!r}")
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "aud": namespace,
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": now + ttl,
            "op": operation,
            "path": path,
        }
        if subject is not None:
            claims["sub"] = subject
        if grant is not None:
            claims["grant"] = grant
        return jwt.encode(claims, self._private_key, algorithm=ALGORITHM, headers={"kid": self.key_id})

    def jwks(self) -> dict[str, Any]:
        """Return the public key as a JSON Web Key Set."""
        numbers = self._private_key.public_key().public_numbers()
        return {"keys": [{
            "kty": "RSA",
            "use": "sig",
            "alg": ALGORITHM,
            "kid": self.key_id,
            "n": _b64url_uint(numbers.n),
            "e": _b64url_uint(numbers.e),
        }]}


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@lru_cache(maxsize=1)
def get_link_signer() -> LinkSigner:
    """
    Return the process-wide signer, loading the key named by ``STORAGE_LINK_SIGNING_KEY_FILE``.

    :raises RuntimeError: If the key file isn't configured or can't be read.
    """
    path = os.getenv(KEY_FILE_ENV)
    if not path:
        raise RuntimeError(f"{KEY_FILE_ENV} is not set; POSIX storage links can't be signed")
    try:
        return LinkSigner.from_pem_file(path)
    except (OSError, ValueError, TypeError) as e:
        raise RuntimeError(f"Unable to load the storage link signing key from {path}") from e

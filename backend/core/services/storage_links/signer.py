"""
Signs time-limited links for storage services that run next to the data (POSIX file services).

The backend decides access; the file service only checks that a link was signed here, names its
namespace, path and operation, and hasn't expired.
"""
import base64
import hashlib
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
KEY_ENV = "STORAGE_LINK_SIGNING_KEY"            # the PEM itself, as deployments pass secrets
KEY_FILE_ENV = "STORAGE_LINK_SIGNING_KEY_FILE"  # or a path to it (local stacks)
PREVIOUS_KEY_ENV = "STORAGE_LINK_SIGNING_KEY_PREVIOUS"  # during a rotation: the old key's PEM, still published
OPERATIONS = {"read", "write", "stat", "delete", "bundle"}


class LinkSigner:
    """Signs and publishes the public key for storage link tokens."""

    def __init__(self, private_key: rsa.RSAPrivateKey, previous: list[rsa.RSAPublicKey] = ()):
        """
        :param private_key: RSA private key used to sign tokens.
        :param previous: Public keys from before a rotation, still published (and accepted) so links
            signed with them keep working until they expire.
        """
        self._private_key = private_key
        self._public = {_key_id(k): k for k in [private_key.public_key(), *previous]}
        self.key_id = _key_id(private_key.public_key())

    @classmethod
    def from_pem(cls, pem: bytes, previous: list[rsa.RSAPublicKey] = ()) -> "LinkSigner":
        """Load the signing key from PEM text."""
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise TypeError("Storage link signing key must be an RSA private key")
        return cls(key, previous)

    @classmethod
    def from_pem_file(cls, path: str, previous: list[rsa.RSAPublicKey] = ()) -> "LinkSigner":
        """Load the signing key from a PEM file."""
        with open(path, "rb") as f:
            return cls.from_pem(f.read(), previous)

    def sign(self, namespace: str, path: str, operation: str, ttl: int, subject: str | None = None,
             grant: str | None = None, listing: str | None = None) -> str:
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
        :param listing: For a ``bundle`` link, the SHA-256 of the file list the portal serves for it
            (``list``), so the file service can't be given a different list.
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
        if listing is not None:
            claims["list"] = listing
        return jwt.encode(claims, self._private_key, algorithm=ALGORITHM, headers={"kid": self.key_id})

    def verify(self, token: str) -> dict[str, Any]:
        """Check a token this signer issued (with the current or a published previous key), whatever its
        namespace; return its claims."""
        key = self._public.get(jwt.get_unverified_header(token).get("kid"))
        if key is None:
            raise jwt.InvalidKeyError("Unknown signing key")
        return jwt.decode(token, key, algorithms=[ALGORITHM], issuer=ISSUER,
                          options={"verify_aud": False, "require": ["exp", "jti", "op"]})

    def jwks(self) -> dict[str, Any]:
        """Return the public keys (current first) as a JSON Web Key Set."""
        return {"keys": [{
            "kty": "RSA",
            "use": "sig",
            "alg": ALGORITHM,
            "kid": kid,
            "n": _b64url_uint(key.public_numbers().n),
            "e": _b64url_uint(key.public_numbers().e),
        } for kid, key in self._public.items()]}


def _key_id(key: rsa.RSAPublicKey) -> str:
    """A key's ID: its fingerprint, so a new key never shares an ID with the one it replaces."""
    der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()[:16]


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@lru_cache(maxsize=1)
def get_link_signer() -> LinkSigner:
    """
    Return the process-wide signer. The key comes from ``STORAGE_LINK_SIGNING_KEY`` (the PEM
    itself) or, if that isn't set, from the file named by ``STORAGE_LINK_SIGNING_KEY_FILE``.

    :raises RuntimeError: If neither is configured, or the key can't be read.
    """
    previous = []
    if os.getenv(PREVIOUS_KEY_ENV):
        try:
            previous = [serialization.load_pem_private_key(os.environ[PREVIOUS_KEY_ENV].encode(), password=None).public_key()]
        except (ValueError, TypeError) as e:
            raise RuntimeError(f"Unable to load the previous signing key from {PREVIOUS_KEY_ENV}") from e
    pem = os.getenv(KEY_ENV)
    if pem:
        try:
            return LinkSigner.from_pem(pem.encode(), previous)
        except (ValueError, TypeError) as e:
            raise RuntimeError(f"Unable to load the storage link signing key from {KEY_ENV}") from e
    path = os.getenv(KEY_FILE_ENV)
    if not path:
        raise RuntimeError(f"Neither {KEY_ENV} nor {KEY_FILE_ENV} is set; POSIX storage links can't be signed")
    try:
        return LinkSigner.from_pem_file(path, previous)
    except (OSError, ValueError, TypeError) as e:
        raise RuntimeError(f"Unable to load the storage link signing key from {path}") from e

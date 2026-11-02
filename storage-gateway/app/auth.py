"""
Check the portal's signed links.

The portal decides access. This service only accepts a token that the portal signed, that names
this service's namespace, the exact path requested and the operation being performed, and that
hasn't expired.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

import jwt
from fastapi import HTTPException, Request, status

ALGORITHMS = ["RS256"]
REQUIRED_CLAIMS = ["exp", "iat", "jti", "op", "path"]  # plus iss and aud, always checked

# GET downloads, PUT uploads, HEAD reads metadata, DELETE removes.
OPERATION_BY_METHOD = {"GET": "read", "PUT": "write", "HEAD": "stat", "DELETE": "delete"}

KeyResolver = Callable[[str], Any]


def jwks_key_resolver(jwks_url: str) -> KeyResolver:
    """Resolve a token's signing key from the portal's published key set (cached)."""
    client = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300)
    return lambda token: client.get_signing_key_from_jwt(token).key


def token_from_request(request: Request) -> str:
    """Take the token from ``?token=`` (links) or an ``Authorization: Bearer`` header (portal calls)."""
    token = request.query_params.get("token")
    if token:
        return token
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value:
        return value
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")


def check_token(
    token: str,
    resolve_key: KeyResolver,
    *,
    namespace: str,
    issuer: str,
    path: str,
    method: str,
    operation: str | None = None,
) -> dict[str, Any]:
    """
    Verify a token for one request and return its claims.

    ``path`` is the resource requested, ``namespace/key``. ``method`` is the HTTP method, which must
    match the token's operation, unless ``operation`` names the one required instead (``bundle``).
    Raise ``HTTPException`` 401 for an invalid or expired token, 403 if it names a different path or
    operation.
    """
    try:
        key = resolve_key(token)
        claims = jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            audience=namespace,
            issuer=issuer,
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from e

    required = operation or OPERATION_BY_METHOD.get(method)
    if claims["path"] != path or claims["op"] != required:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token doesn't allow this request")
    return claims


def bundle_listing(claims: dict[str, Any], body: str) -> dict[str, Any]:
    """
    Return the file list of a ``bundle`` link as the portal served it: ``folder_name`` and ``paths``.

    Raise ``HTTPException`` 403 if the list isn't the one the link was signed for.
    """
    if hashlib.sha256(body.encode()).hexdigest() != claims.get("list"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="File list doesn't match the link")
    return json.loads(body)

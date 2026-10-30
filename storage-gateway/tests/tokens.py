"""Links signed the way the portal signs them, for the file service's tests."""
import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

NS = "inn-posix"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def sign(path, op, *, ttl=60, key=KEY, drop=(), **claims):
    """A token for ``op`` on ``path``. ``claims`` add or replace claims (``grant``, ``sub``, ``list``,
    ``aud``...); ``None`` values are left out, and ``drop`` removes standard ones."""
    now = int(time.time())
    body = {"iss": "inn-portal", "aud": NS, "jti": uuid.uuid4().hex, "iat": now, "exp": now + ttl, "op": op,
            "path": path} | {name: value for name, value in claims.items() if value is not None}
    for name in drop:
        body.pop(name)
    return jwt.encode(body, key, algorithm="RS256")

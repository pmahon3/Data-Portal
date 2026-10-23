"""
API fuzzing with Schemathesis (TESTING-STRATEGY.md, layer 6).

Requests are generated from the file service's OpenAPI schema and sent in-process. Each one is
given a valid token for whatever path was generated, so the fuzzer gets past the token check and
exercises the path handling behind it. Every response must be a deliberate answer, never a
server error, and nothing outside the root may come back.
"""
import atexit
import shutil
import tempfile
import time
import uuid
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

schemathesis = pytest.importorskip("schemathesis")
from hypothesis import HealthCheck, settings  # noqa: E402

from app.auth import OPERATION_BY_METHOD  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

NS = "inn-posix"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
BASE = Path(tempfile.mkdtemp(prefix="fuzz-"))
atexit.register(shutil.rmtree, BASE, True)
ROOT = BASE / "root"
(ROOT / "study").mkdir(parents=True)
(ROOT / "study" / "scan.nii.gz").write_bytes(b"inside")
(BASE / "secret.txt").write_bytes(b"SECRET OUTSIDE")
(ROOT / "link").symlink_to(BASE / "secret.txt")

app = create_app(Settings(root=ROOT, namespace=NS, jwks_url="unused"), resolve_key=lambda t: KEY.public_key())
schema = schemathesis.openapi.from_asgi("/openapi.json", app)


@schema.parametrize()
@settings(max_examples=150, deadline=None, suppress_health_check=list(HealthCheck))
def test_no_server_errors_and_nothing_from_outside_the_root(case):
    resource = (case.path_parameters or {}).get("resource")
    if resource is not None:
        op = OPERATION_BY_METHOD.get(case.method.upper())
        if op:
            now = int(time.time())
            token = jwt.encode({"iss": "inn-portal", "aud": NS, "jti": uuid.uuid4().hex, "iat": now,
                                "exp": now + 60, "op": op, "path": resource}, KEY, algorithm="RS256")
            case.query = (case.query or {}) | {"token": token}
    response = case.call()
    assert response.status_code < 500, (case.method, case.path_parameters, response.status_code)
    assert b"SECRET OUTSIDE" not in response.content

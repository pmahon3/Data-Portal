"""
API fuzzing with Schemathesis (TESTING-STRATEGY.md, layer 6).

Requests are generated from the file service's OpenAPI schema and sent in-process. Each one is
given a valid token for whatever path was generated, so the fuzzer gets past the token check and
exercises the path handling behind it. Every response must be a deliberate answer, never a
server error, and nothing outside the root may come back.

Verifies: AC-3.
"""
import atexit
import shutil
import tempfile
from pathlib import Path

import pytest

schemathesis = pytest.importorskip("schemathesis")
from hypothesis import HealthCheck, settings  # noqa: E402

from app.auth import OPERATION_BY_METHOD  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.tokens import KEY, NS, sign  # noqa: E402

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
            case.query = (case.query or {}) | {"token": sign(resource, op)}
    response = case.call()
    assert response.status_code < 500, (case.method, case.path_parameters, response.status_code)
    assert b"SECRET OUTSIDE" not in response.content

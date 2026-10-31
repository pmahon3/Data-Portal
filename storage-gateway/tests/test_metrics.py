"""
Request and error counters on the file service, in the Prometheus text format, so it can be watched
the way the bundler is. Requests are counted by route, never by path: a path names a user's file.

Verifies: PX-1.
"""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.tokens import KEY, NS
from tests.tokens import sign as token

FILE = f"{NS}/study/scan.nii.gz"


@pytest.fixture
def client(tmp_path):
    (tmp_path / "study").mkdir()
    (tmp_path / "study" / "scan.nii.gz").write_bytes(b"x" * 10)
    settings = Settings(root=tmp_path, namespace=NS, jwks_url="unused")
    return TestClient(create_app(settings, resolve_key=lambda t: KEY.public_key()), raise_server_exceptions=False)


def counters(client) -> dict[str, float]:
    r = client.get("/v1/metrics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    samples = [line.rsplit(" ", 1) for line in r.text.splitlines() if line and not line.startswith("#")]
    return {name: float(value) for name, value in samples}


def requests(method, route, code):
    return f'posix_file_service_requests_total{{method="{method}",route="{route}",code="{code}"}}'


def test_requests_are_counted_by_route_and_status(client):
    client.get(f"/v1/files/{FILE}", params={"token": token(FILE, "read")})
    client.get(f"/v1/files/{FILE}", params={"token": token(FILE, "read")})
    client.get(f"/v1/files/{FILE}")  # no token
    seen = counters(client)
    assert seen[requests("GET", "/v1/files/{resource:path}", 200)] == 2
    assert seen[requests("GET", "/v1/files/{resource:path}", 401)] == 1


def test_paths_and_tokens_never_appear(client):
    client.get(f"/v1/files/{FILE}", params={"token": token(FILE, "read")})
    client.get("/v1/no-such-route/secret-name")
    text = client.get("/v1/metrics").text
    assert "scan.nii.gz" not in text and "secret-name" not in text and "token" not in text
    assert counters(client)[requests("GET", "unmatched", 404)] == 1


def test_an_unhandled_error_is_counted(client, monkeypatch):
    monkeypatch.setattr("os.open", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk gone")))
    assert client.get(f"/v1/files/{FILE}", params={"token": token(FILE, "read")}).status_code == 500
    seen = counters(client)
    assert seen[requests("GET", "/v1/files/{resource:path}", 500)] == 1
    assert seen["posix_file_service_errors_total"] == 1

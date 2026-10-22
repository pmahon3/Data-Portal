"""
POSIX file service against the link contract (STREAMING-SPEC.md, "File service contract").

Tokens are signed here the way the portal signs them, so these tests pin the contract from the
file service's side without importing backend code.
"""
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

NS = "inn-posix"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(path, op, *, ttl=60, aud=NS, iss="inn-portal", key=KEY, drop=()):
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "jti": uuid.uuid4().hex, "iat": now, "exp": now + ttl, "op": op, "path": path}
    for name in drop:
        claims.pop(name)
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def root(tmp_path):
    (tmp_path / "study").mkdir()
    (tmp_path / "study" / "scan.nii.gz").write_bytes(bytes(range(256)) * 4)  # 1024 bytes
    return tmp_path


@pytest.fixture
def client(root):
    settings = Settings(root=root, namespace=NS, jwks_url="unused", chunk_size=100)
    return TestClient(create_app(settings, resolve_key=lambda t: KEY.public_key()))


def get(client, path, op="read", headers=None, **kw):
    return client.get(f"/v1/files/{path}", params={"token": token(path, op, **kw)}, headers=headers or {})


FILE = f"{NS}/study/scan.nii.gz"


def test_health(client):
    assert client.get("/v1/health").json() == {"status": "ok", "namespace": NS}


def test_download_whole_file(client, root):
    r = get(client, FILE)
    assert r.status_code == 200
    assert r.content == (root / "study" / "scan.nii.gz").read_bytes()
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-length"] == "1024"
    assert r.headers["etag"]


@pytest.mark.parametrize("header,start,end", [
    ("bytes=0-99", 0, 99),
    ("bytes=1000-", 1000, 1023),
    ("bytes=-24", 1000, 1023),
    ("bytes=1000-5000", 1000, 1023),
])
def test_byte_ranges_resume_a_download(client, root, header, start, end):
    r = get(client, FILE, headers={"Range": header})
    assert r.status_code == 206
    assert r.content == (root / "study" / "scan.nii.gz").read_bytes()[start:end + 1]
    assert r.headers["content-range"] == f"bytes {start}-{end}/1024"
    assert r.headers["content-length"] == str(end - start + 1)


@pytest.mark.parametrize("header", ["bytes=1024-", "bytes=50-10", "bytes=-0", "items=0-1", "bytes=a-b"])
def test_unsatisfiable_ranges(client, header):
    r = get(client, FILE, headers={"Range": header})
    assert r.status_code == 416
    assert r.headers["content-range"] == "bytes */1024"


def test_if_range_restarts_when_the_file_changed(client, root):
    first = get(client, FILE)
    unchanged = get(client, FILE, headers={"Range": "bytes=0-9", "If-Range": first.headers["etag"]})
    assert unchanged.status_code == 206

    (root / "study" / "scan.nii.gz").write_bytes(b"changed")
    changed = get(client, FILE, headers={"Range": "bytes=0-9", "If-Range": first.headers["etag"]})
    assert changed.status_code == 200
    assert changed.content == b"changed"


def test_metadata_with_a_bearer_token(client):
    r = client.head(f"/v1/files/{FILE}", headers={"Authorization": f"Bearer {token(FILE, 'stat')}"})
    assert r.status_code == 200
    assert r.headers["content-length"] == "1024"
    assert {"etag", "last-modified", "content-type"} <= set(r.headers)


def test_upload_then_download(client, root):
    path = f"{NS}/new/deep/result.csv"
    r = client.put(f"/v1/files/{path}", params={"token": token(path, "write")}, content=b"a,b\n1,2\n")
    assert r.status_code == 201
    assert (root / "new" / "deep" / "result.csv").read_bytes() == b"a,b\n1,2\n"
    assert not [p for p in (root / "new" / "deep").iterdir() if p.name.startswith(".upload-")]

    again = client.put(f"/v1/files/{path}", params={"token": token(path, "write")}, content=b"x")
    assert again.status_code == 200
    assert get(client, path).content == b"x"


def test_delete(client, root):
    r = client.delete(f"/v1/files/{FILE}", headers={"Authorization": f"Bearer {token(FILE, 'delete')}"})
    assert r.status_code == 204
    assert not (root / "study" / "scan.nii.gz").exists()
    gone = client.delete(f"/v1/files/{FILE}", headers={"Authorization": f"Bearer {token(FILE, 'delete')}"})
    assert gone.status_code == 404


# --- Refusals: every way a token can fail to fit the request ---

def test_no_token(client):
    assert client.get(f"/v1/files/{FILE}").status_code == 401


@pytest.mark.parametrize("kw", [
    {"ttl": -10},                       # expired
    {"aud": "other-namespace"},         # minted for another file service
    {"iss": "someone-else"},            # not signed by the portal
    {"key": OTHER_KEY},                 # wrong signature
    {"drop": ("jti",)},                 # missing link id
])
def test_invalid_tokens_are_refused(client, kw):
    assert get(client, FILE, **kw).status_code == 401


def test_a_token_for_one_file_doesnt_open_another(client):
    r = client.get(f"/v1/files/{FILE}", params={"token": token(f"{NS}/study/other.nii.gz", "read")})
    assert r.status_code == 403


def test_a_token_for_a_folder_doesnt_open_its_files(client):
    r = client.get(f"/v1/files/{FILE}", params={"token": token(f"{NS}/study", "read")})
    assert r.status_code == 403


@pytest.mark.parametrize("method,op", [("get", "write"), ("get", "delete"), ("put", "read"), ("delete", "read")])
def test_the_operation_must_match_the_method(client, method, op):
    t = token(FILE, op)
    if method == "get":
        r = client.get(f"/v1/files/{FILE}", params={"token": t})
    elif method == "put":
        r = client.put(f"/v1/files/{FILE}", params={"token": t}, content=b"x")
    else:
        r = client.delete(f"/v1/files/{FILE}", headers={"Authorization": f"Bearer {t}"})
    assert r.status_code == 403


@pytest.mark.parametrize("path", [
    "other-namespace/study/scan.nii.gz",
    f"{NS}/study/../study/scan.nii.gz",
    f"{NS}/study//scan.nii.gz",
    f"{NS}/./study/scan.nii.gz",
])
def test_unsafe_paths_are_refused_even_with_a_matching_token(client, path):
    # HTTP clients may normalise "." and ".." before sending, which turns this into a token mismatch
    # (403) rather than a bad path (400). Either way the request is refused.
    r = client.get(f"/v1/files/{path}", params={"token": token(path, "read")})
    assert r.status_code in (400, 403)


@pytest.mark.parametrize("key", ["study/../study/scan.nii.gz", "./study/scan.nii.gz", "study//scan.nii.gz", "", "../x"])
def test_raw_unsafe_keys_never_resolve(root, key):
    from app.files import BadPath, resolve

    with pytest.raises(BadPath):
        resolve(root, NS, f"{NS}/{key}")


def test_symlinks_cant_escape_the_root(client, root, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.txt"
    outside.write_text("secret")
    (root / "study" / "link.txt").symlink_to(outside)
    path = f"{NS}/study/link.txt"
    assert get(client, path).status_code == 400


def test_folders_and_missing_files_are_not_found(client):
    assert get(client, f"{NS}/study").status_code == 404
    assert get(client, f"{NS}/study/missing.nii.gz").status_code == 404


def test_refusal_comes_before_existence(client):
    # A bad token on a missing file says "unauthorized", not "not found": no probing for files.
    r = client.get(f"/v1/files/{NS}/study/missing.nii.gz", params={"token": token(FILE, "read")})
    assert r.status_code == 403

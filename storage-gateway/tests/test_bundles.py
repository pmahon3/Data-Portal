"""
Several files streamed as one ZIP (GET /v1/bundles/{namespace}/{grant}): the archive holds exactly
the approved list, resumes by byte range, and refuses a list the link wasn't signed for.

Verifies: PX-13.
"""
import hashlib
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.tokens import KEY, NS, sign

FILES = {"study/a.nii": b"a" * 3000, "study/sub/b.csv": b"b,c\n" * 500}
LIST = json.dumps({"folder_name": "my study", "paths": [f"{NS}/{k}" for k in FILES]}, separators=(",", ":"))
BUNDLE = f"{NS}/g1"


def bundle_token(listing=LIST, op="bundle", path=BUNDLE):
    return sign(path, op, grant="g1", list=hashlib.sha256(listing.encode()).hexdigest())


@pytest.fixture
def root(tmp_path):
    for key, data in FILES.items():
        (tmp_path / key).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / key).write_bytes(data)
    return tmp_path


@pytest.fixture
def served():
    return {"g1": LIST}


@pytest.fixture
def client(root, served):
    settings = Settings(root=root, namespace=NS, jwks_url="unused", chunk_size=100)
    return TestClient(create_app(settings, resolve_key=lambda t: KEY.public_key(),
                                 fetch_list=lambda grant, token: served[grant]))


def get(client, token=None, headers=None):
    return client.get(f"/v1/bundles/{BUNDLE}", params={"token": token or bundle_token()}, headers=headers or {})


def test_the_archive_holds_exactly_the_approved_files(client):
    r = get(client)
    assert r.status_code == 200
    assert r.headers["content-length"] == str(len(r.content))
    assert r.headers["content-disposition"] == 'attachment; filename="my_study.zip"'
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert z.testzip() is None
        assert {n: z.read(n) for n in z.namelist()} == {f"my study/{NS}/{k}": v for k, v in FILES.items()}


def test_a_broken_download_resumes_where_it_stopped(client):
    """PX-5."""
    whole = get(client)
    r = get(client, headers={"Range": "bytes=2500-", "If-Range": whole.headers["etag"]})
    assert r.status_code == 206
    assert r.content == whole.content[2500:]


def test_a_resume_after_a_file_changed_starts_again(client, root):
    """PX-5."""
    whole = get(client)
    (root / "study" / "a.nii").write_bytes(b"x" * 3000)
    r = get(client, headers={"Range": "bytes=2500-", "If-Range": whole.headers["etag"]})
    assert r.status_code == 200 and r.headers["etag"] != whole.headers["etag"]


def test_a_list_other_than_the_signed_one_is_refused(client, served):
    """AC-3. The portal's list is checked against the digest in the link."""
    served["g1"] = json.dumps({"folder_name": "", "paths": [f"{NS}/study/a.nii", f"{NS}/secret.txt"]})
    assert get(client).status_code == 403


@pytest.mark.parametrize("kwargs", [{"op": "read"}, {"path": f"{NS}/g2"}])
def test_only_a_bundle_link_for_this_bundle_opens_it(client, kwargs):
    """AC-3."""
    assert get(client, bundle_token(**kwargs)).status_code == 403

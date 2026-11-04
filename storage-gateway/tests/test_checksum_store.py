"""
Checksums of files already sent in a multi-file download, kept so that resuming after the file
service restarts doesn't re-read every file before the resume point (STREAMING-SPEC: checksums that
survive a restart). Kept on disk when ``state_dir`` is set, in memory otherwise.

Verifies: PX-5.
"""
import io
import zipfile

from fastapi.testclient import TestClient

from app import file_access
from app.checksums import ChecksumStore
from app.config import Settings
from app.main import create_app
from tests.test_bundles import FILES, LIST, get
from tests.tokens import KEY, NS


def test_checksums_survive_reopening(tmp_path):
    ChecksumStore(tmp_path).put_many([("ns/a", '"e1"', 123), ("ns/b", '"e2"', 456)])
    store = ChecksumStore(tmp_path)
    assert store.get("ns/a", '"e1"') == 123 and store.get("ns/b", '"e2"') == 456
    assert store.get("ns/a", '"other"') is None  # a changed file has a new ETag


def test_without_a_state_dir_they_are_kept_in_memory():
    store = ChecksumStore(None)
    store.put_many([("ns/a", '"e1"', 1)])
    assert store.get("ns/a", '"e1"') == 1


def serve(root, state_dir):
    settings = Settings(root=root, namespace=NS, jwks_url="unused", chunk_size=100, state_dir=state_dir)
    return TestClient(create_app(settings, resolve_key=lambda t: KEY.public_key(), fetch_list=lambda g, t: LIST))


def test_a_resume_after_a_restart_reads_only_what_is_left(tmp_path, monkeypatch):
    root, state = tmp_path / "data", tmp_path / "state"
    for key, data in FILES.items():
        (root / key).parent.mkdir(parents=True, exist_ok=True)
        (root / key).write_bytes(data)
    state.mkdir()
    whole = get(serve(root, state))  # sent once: checksums recorded

    opened = []
    real_open = file_access.BatchOpener.open
    monkeypatch.setattr(file_access.BatchOpener, "open", lambda self, path: opened.append(path) or real_open(self, path))
    restarted = serve(root, state)
    with zipfile.ZipFile(io.BytesIO(whole.content)) as z:
        tail = z.getinfo(f"my study/{NS}/study/sub/b.csv").header_offset + 100  # inside the last file
    r = get(restarted, headers={"Range": f"bytes={tail}-", "If-Range": whole.headers["etag"]})
    assert r.status_code == 206 and r.content == whole.content[tail:]
    assert opened == [f"{NS}/study/sub/b.csv"]  # the first file's checksum came from the store


def test_without_the_store_a_resume_after_a_restart_rereads_earlier_files(tmp_path, monkeypatch):
    """The case the store is for: the same resume with nothing kept reads the first file again."""
    for key, data in FILES.items():
        (tmp_path / key).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / key).write_bytes(data)
    whole = get(serve(tmp_path, None))
    opened = []
    real_open = file_access.BatchOpener.open
    monkeypatch.setattr(file_access.BatchOpener, "open", lambda self, path: opened.append(path) or real_open(self, path))
    with zipfile.ZipFile(io.BytesIO(whole.content)) as z:
        tail = z.getinfo(f"my study/{NS}/study/sub/b.csv").header_offset + 100
    get(serve(tmp_path, None), headers={"Range": f"bytes={tail}-", "If-Range": whole.headers["etag"]})
    assert f"{NS}/study/a.nii" in opened

"""
Limits on multi-file downloads (STREAMING-SPEC.md, "Downloads at once" and "Request limits"): at
most ``max_downloads`` stream at once and extra ones wait for a slot (then 503 with Retry-After),
and a download may list at most ``max_bundle_files`` files. A slot is given back however the
download ends.

Verifies: PX-14.
"""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import DownloadSlots, create_app
from tests.test_bundles import BUNDLE, FILES, LIST, bundle_token, get
from tests.tokens import KEY, NS


@pytest.fixture
def root(tmp_path):
    for key, data in FILES.items():
        (tmp_path / key).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / key).write_bytes(data)
    return tmp_path


def make(root, **limits):
    settings = Settings(root=root, namespace=NS, jwks_url="unused", chunk_size=100, **limits)
    app = create_app(settings, resolve_key=lambda t: KEY.public_key(), fetch_list=lambda grant, token: LIST)
    return app, TestClient(app)


def test_a_download_waits_for_a_free_slot_then_gives_up_with_retry_after(root):
    app, client = make(root, max_downloads=1, download_wait_seconds=0)
    assert app.state.download_slots.acquire(timeout=0)  # another download is streaming
    r = get(client)
    assert r.status_code == 503 and int(r.headers["retry-after"]) > 0


def test_a_finished_download_gives_its_slot_back(root):
    app, client = make(root, max_downloads=1, download_wait_seconds=0)
    for _ in range(3):
        assert get(client).status_code == 200
    assert app.state.download_slots.free == 1


@pytest.mark.parametrize("request_kw,status", [
    ({"headers": {"Range": "bytes=999999-"}}, 416),        # range can't be met
    ({"token": bundle_token(listing='{"x":1}')}, 403),     # list the link wasn't signed for
])
def test_a_refused_download_gives_its_slot_back(root, request_kw, status):
    app, client = make(root, max_downloads=1, download_wait_seconds=0)
    assert get(client, **request_kw).status_code == status
    assert app.state.download_slots.free == 1


def test_a_download_listing_too_many_files_is_refused(root):
    app, client = make(root, max_bundle_files=1)
    r = get(client)
    assert r.status_code == 413
    assert app.state.download_slots.free == app.state.download_slots.size


def test_waiting_downloads_go_in_turn():
    slots = DownloadSlots(1)
    first = slots.acquire(timeout=0)
    got = []
    waiter = threading.Thread(target=lambda: got.append(slots.acquire(timeout=5)))
    waiter.start()
    time.sleep(0.2)
    assert got == []          # still waiting
    slots.release(first)
    waiter.join()
    assert got and got[0] and slots.free == 0


def test_releasing_twice_frees_one_slot():
    slots = DownloadSlots(2)
    token = slots.acquire(timeout=0)
    slots.release(token)
    slots.release(token)      # the stream's end and the response's background task both release
    assert slots.free == 2

"""
Fault injection (TESTING-STRATEGY.md, layer 8): connections cut partway, slow links, and files that
change between attempts. Toxiproxy sits between the client and the file service (:9101 -> :9100).
Setup: see conftest.py; Toxiproxy is part of local/docker-compose.posix.yaml.
"""
import hashlib
import os
import time
from urllib.parse import urlparse

import pytest
import requests

from portal import TIMEOUT, data_exists, data_overwrite, delete_file, download_url, upload, upload_leftovers, unique_name

TOXIPROXY = os.getenv("E2E_TOXIPROXY_URL", "http://localhost:8474")
PROXIED = os.getenv("E2E_PROXIED_GATEWAY", "http://localhost:9101")
SIZE = 6 * 1024 * 1024


@pytest.fixture(scope="module")
def proxy():
    try:
        requests.get(f"{TOXIPROXY}/version", timeout=3).raise_for_status()
    except requests.RequestException:
        pytest.skip("Toxiproxy not running")
    requests.delete(f"{TOXIPROXY}/proxies/posix-gateway", timeout=TIMEOUT)
    r = requests.post(f"{TOXIPROXY}/proxies", timeout=TIMEOUT, json={
        "name": "posix-gateway", "listen": "0.0.0.0:9101", "upstream": "posix-gateway:9100",
    })
    assert r.status_code in (200, 201), r.text
    yield "posix-gateway"
    requests.delete(f"{TOXIPROXY}/proxies/posix-gateway", timeout=TIMEOUT)


@pytest.fixture
def toxic(proxy):
    """Add a toxic for the duration of a block; removed afterwards."""
    added = []

    def add(kind, stream="downstream", **attributes):
        name = f"{kind}-{stream}-{len(added)}"
        r = requests.post(f"{TOXIPROXY}/proxies/{proxy}/toxics", timeout=TIMEOUT,
                          json={"name": name, "type": kind, "stream": stream, "attributes": attributes})
        assert r.status_code in (200, 201), r.text
        added.append(name)
        return name

    def remove(name):
        requests.delete(f"{TOXIPROXY}/proxies/{proxy}/toxics/{name}", timeout=TIMEOUT)
        added.remove(name)

    add.remove = remove
    yield add
    for name in list(added):
        remove(name)


def via_proxy(url):
    """The same signed link, sent through the proxy (the file service checks the path, not the host)."""
    parsed, proxied = urlparse(url), urlparse(PROXIED)
    return parsed._replace(scheme=proxied.scheme, netloc=proxied.netloc).geturl()


def partial_get(url, headers=None):
    """GET that keeps whatever arrived before the connection broke."""
    received = bytearray()
    try:
        with requests.get(url, headers=headers or {}, stream=True, timeout=TIMEOUT) as r:
            status, response_headers = r.status_code, r.headers
            for chunk in r.iter_content(64 * 1024):
                received += chunk
    except requests.RequestException:
        pass
    return status, response_headers, bytes(received)


@pytest.fixture
def big_file(admin, instance):
    content = os.urandom(SIZE)
    file_id, key = upload(admin, instance, unique_name(), content)
    yield file_id, key, content
    delete_file(admin, instance, file_id)


def test_a_cut_download_resumes_to_identical_bytes(admin, instance, big_file, toxic):
    file_id, _, content = big_file
    url = via_proxy(download_url(admin, instance, file_id).json()["url"])

    cut = toxic("limit_data", bytes=2 * 1024 * 1024)
    status, headers, first = partial_get(url)
    assert status == 200 and 0 < len(first) < SIZE
    toxic.remove(cut)

    status, _, rest = partial_get(url, {"Range": f"bytes={len(first)}-", "If-Range": headers["etag"]})
    assert status == 206
    assert hashlib.sha256(first + rest).hexdigest() == hashlib.sha256(content).hexdigest()


def test_a_file_changed_between_attempts_restarts_instead_of_mixing(admin, instance, big_file, toxic):
    file_id, key, _ = big_file
    url = via_proxy(download_url(admin, instance, file_id).json()["url"])

    cut = toxic("limit_data", bytes=1024 * 1024)
    _, headers, first = partial_get(url)
    toxic.remove(cut)
    replacement = os.urandom(SIZE)
    data_overwrite(key, replacement)  # rewritten in place, same size, by a process on the machine

    status, _, body = partial_get(url, {"Range": f"bytes={len(first)}-", "If-Range": headers["etag"]})
    assert status == 200  # whole new file, not the rest of the old one
    assert body == replacement


def test_a_cut_upload_leaves_no_partial_file(admin, instance, toxic):
    from portal import BACKEND, NAMESPACE, root_id

    name = unique_name()
    init = requests.post(f"{BACKEND}/api/tree/files/upload/init", headers=admin, timeout=TIMEOUT, json={
        "instance_name": instance, "bucket": NAMESPACE, "folder_id": root_id(admin, instance),
        "filename": name, "content_type": "application/octet-stream"}).json()
    cut = toxic("limit_data", stream="upstream", bytes=1024 * 1024)
    with pytest.raises(requests.RequestException):
        requests.put(via_proxy(init["url"]), data=os.urandom(SIZE), timeout=TIMEOUT)
    toxic.remove(cut)

    deadline = time.time() + 10
    while time.time() < deadline and upload_leftovers():
        time.sleep(0.2)
    assert not data_exists(init["key"])
    assert not upload_leftovers()
    delete_file(admin, instance, init["file_id"])


def test_a_slow_connection_still_delivers_identical_bytes(admin, instance, big_file, toxic):
    file_id, _, content = big_file
    url = via_proxy(download_url(admin, instance, file_id).json()["url"])
    toxic("latency", latency=200, jitter=100)
    toxic("bandwidth", rate=8192)  # KB/s
    r = requests.get(url, timeout=60)
    assert r.status_code == 200 and r.content == content

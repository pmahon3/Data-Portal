"""End to end through the portal API and the POSIX file service. Setup: see conftest.py."""
import io
import os
import zipfile
from urllib.parse import urlparse

import pytest
import requests

from portal import BACKEND, GATEWAY, NAMESPACE, TIMEOUT, data_exists, data_read, delete_file, download_url, root_id, unique_name, upload


@pytest.fixture(scope="module")
def uploaded(admin, instance):
    content = os.urandom(300_000)
    name = unique_name()
    file_id, key = upload(admin, instance, name, content)
    return {"id": file_id, "key": key, "content": content}


def test_upload_lands_on_the_posix_machine(uploaded):
    """PX-1."""
    assert data_read(uploaded["key"]) == uploaded["content"]


def test_uploaded_file_is_listed(admin, instance, uploaded):
    """PX-1."""
    r = requests.get(f"{BACKEND}/api/tree/{root_id(admin, instance)}", headers=admin, timeout=TIMEOUT,
                     params={"instance_name": instance, "bucket": NAMESPACE})
    assert r.status_code == 200, r.text
    assert uploaded["id"] in [f["id"] for f in r.json()["files"]]


def test_download_and_resume(admin, instance, uploaded):
    """PX-5."""
    url = download_url(admin, instance, uploaded["id"]).json()["url"]
    assert requests.get(url, timeout=TIMEOUT).content == uploaded["content"]
    tail = requests.get(url, headers={"Range": "bytes=200000-"}, timeout=TIMEOUT)
    assert tail.status_code == 206
    assert tail.content == uploaded["content"][200000:]


def test_a_user_without_access_gets_no_link(u1, instance, uploaded):
    """AC-3."""
    assert download_url(u1, instance, uploaded["id"]).status_code == 403


def test_a_link_for_one_file_doesnt_open_another(admin, instance, uploaded):
    """AC-3."""
    url = urlparse(download_url(admin, instance, uploaded["id"]).json()["url"])
    other = url._replace(path=f"/v1/files/{NAMESPACE}/study/seed.csv").geturl()
    assert requests.get(other, timeout=TIMEOUT).status_code == 403


def test_several_files_download_as_one_zip_from_the_machine(admin, instance, uploaded):
    """PX-13, PX-7, PX-14. One link, straight to the file service, with nothing to wait for or keep;
    the archive holds both files and resumes by byte range."""
    second_id, second_key = upload(admin, instance, unique_name(), b"second")
    try:
        r = requests.post(f"{BACKEND}/api/tree/bundle/zip", headers=admin, timeout=TIMEOUT,
                          json={"instance_name": instance, "file_ids": [uploaded["id"], second_id]})
        assert r.status_code == 200 and r.json()["status"] == "completed", r.text
        url = r.json()["single_file_url"]
        assert urlparse(url).netloc == urlparse(GATEWAY).netloc
        whole = requests.get(url, timeout=TIMEOUT)
        with zipfile.ZipFile(io.BytesIO(whole.content)) as z:
            assert {n: z.read(n) for n in z.namelist()} == {
                f"{NAMESPACE}/{uploaded['key']}": uploaded["content"], f"{NAMESPACE}/{second_key}": b"second"}
        tail = requests.get(url, headers={"Range": "bytes=200000-", "If-Range": whole.headers["etag"]}, timeout=TIMEOUT)
        assert tail.status_code == 206 and tail.content == whole.content[200000:]
    finally:
        delete_file(admin, instance, second_id)


def test_delete_through_the_portal(admin, instance, uploaded):
    """PX-2."""
    r = delete_file(admin, instance, uploaded["id"])
    assert r.status_code == 200, r.text
    assert not data_exists(uploaded["key"])

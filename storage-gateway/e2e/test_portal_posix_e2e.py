"""End to end through the portal API and the POSIX file service. Setup: see conftest.py."""
import os
from urllib.parse import urlparse

import pytest
import requests

from portal import BACKEND, DATA, NAMESPACE, TIMEOUT, delete_file, download_url, root_id, unique_name, upload


@pytest.fixture(scope="module")
def uploaded(admin, instance):
    content = os.urandom(300_000)
    name = unique_name()
    file_id, key = upload(admin, instance, name, content)
    return {"id": file_id, "key": key, "content": content, "path": DATA / key}


def test_upload_lands_on_the_posix_machine(uploaded):
    assert uploaded["path"].read_bytes() == uploaded["content"]


def test_uploaded_file_is_listed(admin, instance, uploaded):
    r = requests.get(f"{BACKEND}/api/tree/{root_id(admin, instance)}", headers=admin, timeout=TIMEOUT,
                     params={"instance_name": instance, "bucket": NAMESPACE})
    assert r.status_code == 200, r.text
    assert uploaded["id"] in [f["id"] for f in r.json()["files"]]


def test_download_and_resume(admin, instance, uploaded):
    url = download_url(admin, instance, uploaded["id"]).json()["url"]
    assert requests.get(url, timeout=TIMEOUT).content == uploaded["content"]
    tail = requests.get(url, headers={"Range": "bytes=200000-"}, timeout=TIMEOUT)
    assert tail.status_code == 206
    assert tail.content == uploaded["content"][200000:]


def test_a_user_without_access_gets_no_link(u1, instance, uploaded):
    assert download_url(u1, instance, uploaded["id"]).status_code == 403


def test_a_link_for_one_file_doesnt_open_another(admin, instance, uploaded):
    url = urlparse(download_url(admin, instance, uploaded["id"]).json()["url"])
    other = url._replace(path=f"/v1/files/{NAMESPACE}/study/seed.csv").geturl()
    assert requests.get(other, timeout=TIMEOUT).status_code == 403


def test_multi_file_downloads_are_refused(admin, instance, uploaded):
    second_id, _ = upload(admin, instance, unique_name(), b"second")
    r = requests.post(f"{BACKEND}/api/tree/bundle/zip", headers=admin, timeout=TIMEOUT,
                      json={"instance_name": instance, "file_ids": [uploaded["id"], second_id]})
    delete_file(admin, instance, second_id)
    assert r.status_code == 501, r.text


def test_delete_through_the_portal(admin, instance, uploaded):
    r = delete_file(admin, instance, uploaded["id"])
    assert r.status_code == 200, r.text
    assert not uploaded["path"].exists()

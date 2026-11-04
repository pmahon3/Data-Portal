"""
Through the portal to a file service running without administrator access (GATEWAY_ACCESS=shared-account,
the posix-gateway-shared container): the same flows as the user-per-approval mode, with no root anywhere.

Verifies: PX-8.
"""
import io
import os
import subprocess
import uuid
import zipfile

import pytest
import requests

from portal import BACKEND, TIMEOUT, delete_file, download_url, unique_name, upload

GATEWAY = os.getenv("E2E_GATEWAY_SHARED_URL", "http://posix-gateway-shared.localhost:9102")
CONTAINER = os.getenv("E2E_GATEWAY_SHARED_CONTAINER", "posix-gateway-shared")
NAMESPACE = "inn-posix-shared"


@pytest.fixture(scope="module")
def account_instance(admin):
    try:
        requests.get(f"{GATEWAY}/v1/health", timeout=TIMEOUT).raise_for_status()
    except requests.RequestException:
        pytest.skip("shared-account file service not running")
    name = f"posix-shared-e2e-{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{BACKEND}/api/instances/", headers=admin, timeout=TIMEOUT, json={
        "flavour": "posix", "instance_name": name, "instance_url": GATEWAY, "namespace": NAMESPACE,
        "project_names": []})
    assert r.status_code == 201, r.text
    grant = requests.post(f"{BACKEND}/api/policies/", headers=admin, timeout=TIMEOUT, json={
        "username": "qa-authz-admin", "instance_name": name, "resource": "*", "action": "*"})
    assert grant.status_code in (200, 201), grant.text
    yield name
    requests.delete(f"{BACKEND}/api/instances/{r.json()['instance']['uuid']}", headers=admin, timeout=TIMEOUT)


def test_no_process_in_the_file_service_runs_as_root():
    users = subprocess.run(["docker", "exec", CONTAINER, "sh", "-c", "cat /proc/[0-9]*/status"],
                           capture_output=True, text=True, timeout=30)
    uids = {line.split()[1] for line in users.stdout.splitlines() if line.startswith("Uid:")}
    assert users.returncode == 0 and "0" not in uids and uids


def test_upload_download_resume_and_delete(admin, account_instance):
    content = os.urandom(200_000)
    file_id, key = upload(admin, account_instance, unique_name(), content, bucket=NAMESPACE)
    url = download_url(admin, account_instance, file_id).json()["url"]
    assert requests.get(url, timeout=TIMEOUT).content == content
    tail = requests.get(url, headers={"Range": "bytes=150000-"}, timeout=TIMEOUT)
    assert tail.status_code == 206 and tail.content == content[150000:]
    assert delete_file(admin, account_instance, file_id).status_code in (200, 204)


def test_a_user_without_access_gets_no_link(admin, u1, account_instance):
    """AC-3."""
    file_id, _ = upload(admin, account_instance, unique_name(), b"private", bucket=NAMESPACE)
    try:
        assert download_url(u1, account_instance, file_id).status_code in (403, 404)
    finally:
        delete_file(admin, account_instance, file_id)


def test_several_files_stream_as_one_zip(admin, account_instance):
    """PX-13."""
    ids = [upload(admin, account_instance, unique_name(), body, bucket=NAMESPACE) for body in (b"one", b"two")]
    try:
        r = requests.post(f"{BACKEND}/api/tree/bundle/zip", headers=admin, timeout=TIMEOUT,
                          json={"instance_name": account_instance, "file_ids": [i for i, _ in ids]})
        archive = requests.get(r.json()["single_file_url"], timeout=TIMEOUT).content
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            assert sorted(z.read(n) for n in z.namelist()) == [b"one", b"two"]
    finally:
        for i, _ in ids:
            delete_file(admin, account_instance, i)

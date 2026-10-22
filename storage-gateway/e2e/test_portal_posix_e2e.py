"""
End to end through the portal API and the POSIX file service (local stack only).

Needs the main stack plus `docker compose -p ams-posix -f local/docker-compose.posix.yaml up -d`,
and the throwaway local test users qa-authz-admin and qa-authz-u1 (password "<username>-pw").
Creates its own POSIX instance and removes it afterwards.

    uv run --no-project --with pytest --with requests pytest storage-gateway/e2e -q
"""
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest
import requests

BACKEND = os.getenv("E2E_BACKEND_URL", "http://localhost:8001")
KEYCLOAK = os.getenv("E2E_KEYCLOAK_URL", "http://localhost:8080")
GATEWAY = os.getenv("E2E_GATEWAY_URL", "http://posix-gateway.localhost:9100")
DATA = Path(os.getenv("E2E_GATEWAY_DATA", Path(__file__).resolve().parents[1] / "data"))
NAMESPACE = "inn-posix"
INSTANCE = f"posix-e2e-{uuid.uuid4().hex[:6]}"
TIMEOUT = 15


def login(user):
    r = requests.post(
        f"{KEYCLOAK}/realms/ams-portal/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "ams-portal-ui", "username": user, "password": f"{user}-pw"},
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        pytest.skip(f"no token for {user}: {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin():
    return login("qa-authz-admin")


@pytest.fixture(scope="module")
def u1():
    return login("qa-authz-u1")


@pytest.fixture(scope="module")
def instance(admin):
    try:
        requests.get(f"{GATEWAY}/v1/health", timeout=TIMEOUT).raise_for_status()
    except requests.RequestException:
        pytest.skip("POSIX file service not running")
    r = requests.post(f"{BACKEND}/api/instances/", headers=admin, timeout=TIMEOUT, json={
        "flavour": "posix", "instance_name": INSTANCE,
        "instance_url": GATEWAY, "namespace": NAMESPACE, "project_names": [],
    })
    assert r.status_code == 201, r.text
    instance_uuid = r.json()["instance"]["uuid"]
    # The creator's automatic "admin" grant gives no file access (nothing checks that action), so
    # grant the admin everything on the instance, as an administrator would through the policy page.
    grant = requests.post(f"{BACKEND}/api/policies/", headers=admin, timeout=TIMEOUT, json={
        "username": "qa-authz-admin", "instance_name": INSTANCE, "resource": "*", "action": "*",
    })
    assert grant.status_code in (200, 201), grant.text
    yield INSTANCE
    requests.delete(f"{BACKEND}/api/instances/{instance_uuid}", headers=admin, timeout=TIMEOUT)


def root_id(headers, instance):
    r = requests.get(f"{BACKEND}/api/tree/root", headers=headers, timeout=TIMEOUT,
                     params={"instance_name": instance, "bucket": NAMESPACE})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def upload(headers, instance, filename, content):
    """Upload through the portal: init (signed link) -> PUT to the file service -> complete."""
    init = requests.post(f"{BACKEND}/api/tree/files/upload/init", headers=headers, timeout=TIMEOUT, json={
        "instance_name": instance, "bucket": NAMESPACE, "folder_id": root_id(headers, instance),
        "filename": filename, "content_type": "application/octet-stream",
    })
    assert init.status_code == 200, init.text
    put = requests.put(init.json()["url"], data=content, timeout=TIMEOUT)
    assert put.status_code in (200, 201), put.text
    done = requests.post(f"{BACKEND}/api/tree/files/upload/complete", headers=headers, timeout=TIMEOUT,
                         json={"instance_name": instance, "file_id": init.json()["file_id"]})
    assert done.status_code == 200, done.text
    return init.json()["file_id"], init.json()["key"]


def download_url(headers, instance, file_id):
    return requests.get(f"{BACKEND}/api/tree/files/{file_id}/download-url", headers=headers,
                        timeout=TIMEOUT, params={"instance_name": instance})


@pytest.fixture(scope="module")
def uploaded(admin, instance):
    content = os.urandom(300_000)
    name = f"e2e-{uuid.uuid4().hex[:8]}.bin"
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
    second_id, _ = upload(admin, instance, f"e2e-{uuid.uuid4().hex[:8]}.bin", b"second")
    r = requests.post(f"{BACKEND}/api/tree/bundle/zip", headers=admin, timeout=TIMEOUT,
                      json={"instance_name": instance, "file_ids": [uploaded["id"], second_id]})
    requests.delete(f"{BACKEND}/api/tree/files/{second_id}", headers=admin, timeout=TIMEOUT,
                    params={"instance_name": instance})
    assert r.status_code == 501, r.text


def test_delete_through_the_portal(admin, instance, uploaded):
    r = requests.delete(f"{BACKEND}/api/tree/files/{uploaded['id']}", headers=admin, timeout=TIMEOUT,
                        params={"instance_name": instance})
    assert r.status_code == 200, r.text
    assert not uploaded["path"].exists()

"""Helpers for driving the portal API and the POSIX file service in end-to-end tests."""
import os
import subprocess
import uuid

import pytest
import requests

BACKEND = os.getenv("E2E_BACKEND_URL", "http://localhost:8001")
KEYCLOAK = os.getenv("E2E_KEYCLOAK_URL", "http://localhost:8080")
GATEWAY = os.getenv("E2E_GATEWAY_URL", "http://posix-gateway.localhost:9100")
GATEWAY_CONTAINER = os.getenv("E2E_GATEWAY_CONTAINER", "posix-gateway")
DATA_ROOT = "/srv/posix/data"
NAMESPACE = "inn-posix"
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


def delete_file(headers, instance, file_id):
    return requests.delete(f"{BACKEND}/api/tree/files/{file_id}", headers=headers, timeout=TIMEOUT,
                           params={"instance_name": instance})


def unique_name(suffix=".bin"):
    return f"e2e-{uuid.uuid4().hex[:8]}{suffix}"


# The data lives on a Docker volume (the file service's Linux permissions and ACLs need a real Linux
# filesystem), so tests look at it through the container, as root.

def _in_gateway(*command, stdin=None):
    return subprocess.run(["docker", "exec", "-i", GATEWAY_CONTAINER, *command], input=stdin, capture_output=True)


def data_read(key):
    r = _in_gateway("cat", f"{DATA_ROOT}/{key}")
    return r.stdout if r.returncode == 0 else None


def data_exists(key):
    return _in_gateway("test", "-e", f"{DATA_ROOT}/{key}").returncode == 0


def data_overwrite(key, content):
    """Rewrite a file in place (same inode, owner and mode), as a process on the machine would."""
    assert _in_gateway("sh", "-c", f"cat > '{DATA_ROOT}/{key}'", stdin=content).returncode == 0


def upload_leftovers():
    r = _in_gateway("find", "/srv/posix", "-name", ".upload-*")
    return [line for line in r.stdout.decode().splitlines() if line]

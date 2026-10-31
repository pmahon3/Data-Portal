"""Helpers for driving the portal API and the POSIX file service in end-to-end tests."""
import os
import uuid
from pathlib import Path

import pytest
import requests

BACKEND = os.getenv("E2E_BACKEND_URL", "http://localhost:8001")
KEYCLOAK = os.getenv("E2E_KEYCLOAK_URL", "http://localhost:8080")
GATEWAY = os.getenv("E2E_GATEWAY_URL", "http://posix-gateway.localhost:9100")
DATA = Path(os.getenv("E2E_GATEWAY_DATA", Path(__file__).resolve().parents[1] / "data"))
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

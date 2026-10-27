"""
Fixtures for end-to-end tests (local stack only).

Needs the main stack plus `docker compose -p ams-posix -f local/docker-compose.posix.yaml up -d`,
and the throwaway local test users qa-authz-admin and qa-authz-u1 (password "<username>-pw").
A POSIX instance is created for the session and removed afterwards.

    uv run --no-project --with pytest --with requests pytest storage-gateway/e2e -q
"""
import uuid

import pytest
import requests

from portal import BACKEND, GATEWAY, NAMESPACE, TIMEOUT, login


@pytest.fixture(scope="session")
def admin():
    return login("qa-authz-admin")


@pytest.fixture(scope="session")
def u1():
    return login("qa-authz-u1")


@pytest.fixture(scope="session")
def instance(admin):
    try:
        requests.get(f"{GATEWAY}/v1/health", timeout=TIMEOUT).raise_for_status()
    except requests.RequestException:
        pytest.skip("POSIX file service not running")
    name = f"posix-e2e-{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{BACKEND}/api/instances/", headers=admin, timeout=TIMEOUT, json={
        "flavour": "posix", "instance_name": name,
        "instance_url": GATEWAY, "namespace": NAMESPACE, "project_names": [],
    })
    assert r.status_code == 201, r.text
    instance_uuid = r.json()["instance"]["uuid"]
    # The creator's automatic "admin" grant gives no file access (nothing checks that action), so
    # grant the admin everything on the instance, as an administrator would through the policy page.
    grant = requests.post(f"{BACKEND}/api/policies/", headers=admin, timeout=TIMEOUT, json={
        "username": "qa-authz-admin", "instance_name": name, "resource": "*", "action": "*",
    })
    assert grant.status_code in (200, 201), grant.text
    yield name
    requests.delete(f"{BACKEND}/api/instances/{instance_uuid}", headers=admin, timeout=TIMEOUT)

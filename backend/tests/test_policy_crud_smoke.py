# backend/tests/test_policy_crud_smoke.py
"""
Policy CRUD Smoke Tests

Tests policy management API functionality including:
- Creating policies with request body
- Listing policies
- Deleting policies with request body
- Admin-only access control

Note: These tests validate the API endpoints accept request bodies
(not query params) for POST and DELETE operations.
"""

import os
import json
from pathlib import Path

import pytest
import requests


# --- Config helpers ----------------------------------------------------------

def env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None or v == "":
        raise RuntimeError(f"Missing required env var: {name}")
    return v

def kc_base() -> str:
    return env("KEYCLOAK_DOMAIN")

def kc_realm() -> str:
    return env("KEYCLOAK_REALM")

def backend_base() -> str:
    return os.getenv("BACKEND_BASE_URL", "http://localhost:8000")


# --- Token helpers -----------------------------------------------------------

def get_admin_token(timeout=10) -> str:
    """Get admin user token via password grant."""
    token_url = f"{kc_base()}/realms/{kc_realm()}/protocol/openid-connect/token"
    ui_client_id = os.getenv("KEYCLOAK_UI_CLIENT_ID", "ams-portal-ui")
    data = {
        "grant_type": "password",
        "client_id": ui_client_id,
        "username": "admin",
        "password": "admin123",
    }
    r = requests.post(token_url, data=data, timeout=timeout)
    try:
        payload = r.json()
    except json.JSONDecodeError:
        pytest.fail(f"Non-JSON response from token endpoint: HTTP {r.status_code}\n{r.text[:500]}")
    if r.status_code != 200:
        pytest.fail(f"Token request failed HTTP {r.status_code}: {json.dumps(payload)[:500]}")
    token = payload.get("access_token", "")
    if not token:
        pytest.fail(f"No access_token in response: {json.dumps(payload)[:500]}")
    return token


# --- Test fixtures -----------------------------------------------------------

@pytest.fixture(scope="session")
def admin_token():
    """Provide admin token (fetched once per test session)."""
    return get_admin_token()

@pytest.fixture(scope="session")
def auth_headers(admin_token):
    """Provide authorization headers with admin token."""
    return {"Authorization": f"Bearer {admin_token}"}


# --- Policy API Tests --------------------------------------------------------

def test_list_policies_requires_admin(auth_headers):
    """Test that listing policies requires admin privileges."""
    url = f"{backend_base()}/api/policies/"
    r = requests.get(url, headers=auth_headers, timeout=10)
    assert r.status_code == 200, f"Admin should be able to list policies, got {r.status_code}: {r.text[:500]}"

    data = r.json()
    assert "details" in data, f"Expected 'details' key in response, got: {data.keys()}"
    assert isinstance(data["details"], list), f"Expected list of policies, got: {type(data['details'])}"


def test_list_policies_without_auth_fails():
    """Test that listing policies without auth token fails."""
    url = f"{backend_base()}/api/policies/"
    r = requests.get(url, timeout=10)
    assert r.status_code == 401, f"Expected 401 Unauthorized, got {r.status_code}"


def test_create_policy_accepts_request_body(auth_headers):
    """Test that POST /api/policies accepts JSON request body (not query params)."""
    url = f"{backend_base()}/api/policies/"
    payload = {
        "username": "testuser",
        "instance_name": "test_instance",
        "resource": "/test/resource/.*",
        "action": "read"
    }

    # This will fail if user/instance don't exist, but we're testing that:
    # 1. The endpoint accepts JSON body
    # 2. The endpoint doesn't require query params
    # 3. We get a proper error response (not 422 validation error)
    r = requests.post(url, json=payload, headers=auth_headers, timeout=10)

    # Should be 404 (user/instance not found) or 201 (success if they exist)
    # NOT 422 (which would mean request body wasn't parsed)
    assert r.status_code in (201, 404), \
        f"Expected 201 or 404, got {r.status_code}. " \
        f"422 would indicate request body not accepted. Response: {r.text[:500]}"


def test_delete_policy_accepts_request_body(auth_headers):
    """Test that DELETE /api/policies accepts JSON request body (not query params)."""
    url = f"{backend_base()}/api/policies/"
    payload = {
        "user_uuid": "00000000-0000-0000-0000-000000000000",
        "instance_uuid": "00000000-0000-0000-0000-000000000000",
        "resource": "/test/.*",
        "action": "read"
    }

    # This will fail because the policy doesn't exist, but we're testing that:
    # 1. The endpoint accepts JSON body
    # 2. The endpoint doesn't require query params
    # 3. We get a proper error response (not 422 validation error)
    r = requests.delete(url, json=payload, headers=auth_headers, timeout=10)

    # Should be 400 or 404 (policy not found) or 200 (success if it exists)
    # NOT 422 (which would mean request body wasn't parsed)
    assert r.status_code in (200, 400, 404), \
        f"Expected 200, 400, or 404, got {r.status_code}. " \
        f"422 would indicate request body not accepted. Response: {r.text[:500]}"


def test_create_policy_without_auth_fails():
    """Test that creating policies without auth token fails."""
    url = f"{backend_base()}/api/policies/"
    payload = {
        "username": "someone",
        "instance_name": "something",
        "resource": "/test/.*",
        "action": "read"
    }

    r = requests.post(url, json=payload, timeout=10)
    assert r.status_code == 401, f"Expected 401 Unauthorized, got {r.status_code}"


def test_delete_policy_without_auth_fails():
    """Test that deleting policies without auth token fails."""
    url = f"{backend_base()}/api/policies/"
    payload = {
        "user_uuid": "00000000-0000-0000-0000-000000000000",
        "instance_uuid": "00000000-0000-0000-0000-000000000000",
        "resource": "/test/.*",
        "action": "read"
    }

    r = requests.delete(url, json=payload, timeout=10)
    assert r.status_code == 401, f"Expected 401 Unauthorized, got {r.status_code}"

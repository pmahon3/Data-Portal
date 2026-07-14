# backend/tests/test_auth_smoke.py
import os
import json
import time
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
    return env("KEYCLOAK_DOMAIN")  # e.g. http://keycloak:8080

def kc_realm() -> str:
    return env("KEYCLOAK_REALM")   # e.g. ams-portal

def kc_admin_client_id() -> str:
    return env("KEYCLOAK_ADMIN_CLIENT_ID")  # e.g. ams-portal-admin

def kc_issuer() -> str:
    # external issuer (must match token 'iss')
    # Use KEYCLOAK_EXTERNAL_ISSUER if set, otherwise derive from KEYCLOAK_DOMAIN
    external = os.getenv("KEYCLOAK_EXTERNAL_ISSUER")
    if external:
        return external
    return f"{kc_base()}/realms/{kc_realm()}"

def backend_base() -> str:
    # when running *inside* the backend container, localhost:8000 hits the app directly
    return os.getenv("BACKEND_BASE_URL", "http://localhost:8000")


# --- Token helpers -----------------------------------------------------------

def read_admin_client_secret() -> str:
    # Prefer the mounted Docker secret file
    p = Path(os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET_FILE", "/run/secrets/kc_admin_client_secret"))
    if not p.is_file():
        raise RuntimeError(f"Client secret file not found at {p}")
    secret = p.read_text().strip()
    if not secret:
        raise RuntimeError("Client secret file is empty")
    return secret

def get_client_credentials_token(timeout=10) -> str:
    token_url = f"{kc_base()}/realms/{kc_realm()}/protocol/openid-connect/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": kc_admin_client_id(),
        "client_secret": env("KEYCLOAK_ADMIN_CLIENT_SECRET"),
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

def get_user_password_token(username: str, password: str, timeout=10) -> str:
    """Obtain token via password grant (direct access grants)."""
    token_url = f"{kc_base()}/realms/{kc_realm()}/protocol/openid-connect/token"
    # Use the UI client which has directAccessGrantsEnabled=true
    ui_client_id = os.getenv("KEYCLOAK_UI_CLIENT_ID", "ams-portal-ui")
    data = {
        "grant_type": "password",
        "client_id": ui_client_id,
        "username": username,
        "password": password,
    }
    r = requests.post(token_url, data=data, timeout=timeout)
    try:
        payload = r.json()
    except json.JSONDecodeError:
        pytest.fail(f"Non-JSON response from token endpoint: HTTP {r.status_code}\n{r.text[:500]}")
    if r.status_code != 200:
        pytest.fail(f"Password grant failed HTTP {r.status_code}: {json.dumps(payload)[:500]}")
    token = payload.get("access_token", "")
    if not token:
        pytest.fail(f"No access_token in response: {json.dumps(payload)[:500]}")
    return token


# --- Tests -------------------------------------------------------------------

def test_health_ready():
    url = f"{backend_base()}/api/health/ready"
    r = requests.get(url, timeout=5)
    assert r.status_code == 200, f"/api/health/ready returned {r.status_code}: {r.text[:200]}"

def test_validate_token_unauthorized():
    url = f"{backend_base()}/api/auth/validate"
    r = requests.get(url, timeout=5)  # no Authorization header
    assert r.status_code == 401, f"Expected 401 without token, got {r.status_code}: {r.text[:200]}"

def test_validate_token_authorized():
    # 1) obtain a client_credentials token for ams-portal-admin
    token = get_client_credentials_token()

    # 2) call backend /api/auth/validate
    url = f"{backend_base()}/api/auth/validate"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)

    # Helpful logging on failure
    assert r.status_code == 200, f"/api/auth/validate returned {r.status_code}: {r.text[:500]}"
    data = r.json()
    assert data.get("valid") is True, f"Unexpected payload: {data}"

    user = data.get("user") or {}
    # issuer must match external issuer configured in compose (and in KC tokens)
    iss = user.get("iss", "")
    assert iss == kc_issuer(), f"issuer mismatch: got {iss!r}, expected {kc_issuer()!r}"

    # sanity: azp should be our admin client id
    azp = user.get("azp", "")
    assert azp == kc_admin_client_id(), f"azp mismatch: got {azp!r}, expected {kc_admin_client_id()!r}"

    # optional: token still valid (exp > now)
    exp = user.get("exp", 0)
    assert exp and exp > int(time.time()), "Token appears expired"


def test_validate_token_with_garbage_token():
    url = f"{backend_base()}/api/auth/validate"
    r = requests.get(url, headers={"Authorization": "Bearer not.a.real.token"}, timeout=5)
    assert r.status_code == 401, f"Expected 401 with garbage token, got {r.status_code}: {r.text[:200]}"


# --- Keycloak Integration Tests (User Authentication) -----------------------

def test_user_password_authentication():
    """Test user authentication with username/password flow."""
    # Use the admin user from keycloak-realm-export.json
    token = get_user_password_token("admin", "admin123")

    # Verify we got a valid token
    assert token, "Should receive a token from password grant"
    assert len(token) > 50, "Token should be a valid JWT"

    # Verify the token works with our backend
    url = f"{backend_base()}/api/auth/validate"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200, f"Token validation failed: {r.status_code}: {r.text[:500]}"

    data = r.json()
    assert data.get("valid") is True, f"Token should be valid: {data}"

    user = data.get("user", {})
    assert user.get("preferred_username") == "admin", f"Username mismatch: {user}"


def test_admin_role_detection():
    """Test that admin role is correctly detected from token."""
    # Get admin user token
    admin_token = get_user_password_token("admin", "admin123")

    # Call validate endpoint
    url = f"{backend_base()}/api/auth/validate"
    r = requests.get(url, headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
    assert r.status_code == 200, f"Token validation failed: {r.status_code}"

    data = r.json()
    user = data.get("user", {})

    # Check that admin role is present in realm_access
    realm_access = user.get("realm_access", {})
    roles = realm_access.get("roles", [])
    assert "admin" in roles, f"Admin role not found in token. Roles: {roles}"


# --- Core API Endpoint Tests ------------------------------------------------

def test_health_live():
    """Test liveness probe endpoint."""
    url = f"{backend_base()}/api/health/live"
    r = requests.get(url, timeout=5)
    assert r.status_code == 200, f"/api/health/live returned {r.status_code}: {r.text[:200]}"
    data = r.json()
    assert data.get("status") == "alive", f"Expected alive status: {data}"


def test_protected_endpoint_requires_auth():
    """Test that protected endpoints reject requests without auth."""
    # Try to access users list without token
    url = f"{backend_base()}/api/users/"
    r = requests.get(url, timeout=5)
    assert r.status_code == 401, f"Expected 401 without auth, got {r.status_code}: {r.text[:200]}"


def test_protected_endpoint_with_valid_token():
    """Test that protected endpoints accept valid tokens."""
    # Get a valid admin token
    token = get_user_password_token("admin", "admin123")

    # Access users list with token (admin-only endpoint)
    url = f"{backend_base()}/api/users/"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200, f"Expected 200 with valid admin token, got {r.status_code}: {r.text[:500]}"

    # Should return a list
    data = r.json()
    assert isinstance(data, list), f"Expected list of users, got: {type(data)}"


def test_admin_only_endpoint_enforcement():
    """Test that admin-only endpoints properly enforce admin role requirement."""
    # This test verifies admin-only enforcement by testing with admin user
    # (we don't have a non-admin user in the realm export yet)
    admin_token = get_user_password_token("admin", "admin123")

    # Admin should be able to access admin-only endpoint
    url = f"{backend_base()}/api/users/"
    r = requests.get(url, headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
    assert r.status_code == 200, f"Admin should access /api/users/, got {r.status_code}: {r.text[:500]}"

    # TODO: Add test with non-admin user when one is configured in realm export

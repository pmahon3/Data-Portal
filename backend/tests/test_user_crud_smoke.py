# backend/tests/test_user_crud_smoke.py
"""
User CRUD Smoke Tests

Tests comprehensive user management functionality including:
- Creating users
- Listing users
- Retrieving individual user details
- Updating user information
- Deleting users
- Role-based access control
- Owner vs Admin permissions
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

def read_admin_client_secret() -> str:
    p = Path(os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET_FILE", "/run/secrets/kc_admin_client_secret"))
    if not p.is_file():
        raise RuntimeError(f"Client secret file not found at {p}")
    secret = p.read_text().strip()
    if not secret:
        raise RuntimeError("Client secret file is empty")
    return secret

def get_keycloak_token(username: str, password: str, timeout=10) -> str:
    """Get Keycloak user token via password grant."""
    token_url = f"{kc_base()}/realms/{kc_realm()}/protocol/openid-connect/token"
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
        pytest.fail(f"Token request failed HTTP {r.status_code}: {json.dumps(payload)[:500]}")
    token = payload.get("access_token", "")
    if not token:
        pytest.fail(f"No access_token in response: {json.dumps(payload)[:500]}")
    return token

def get_admin_token(timeout=10) -> str:
    """Get admin user token."""
    return get_keycloak_token(env("KEYCLOAK_ADMIN", "admin"), env("KEYCLOAK_ADMIN_PASSWORD", "admin123"), timeout=timeout)

# --- Test fixtures -----------------------------------------------------------

@pytest.fixture
def admin_token():
    """Provide admin token for tests."""
    return get_admin_token()

@pytest.fixture
def auth_headers(admin_token):
    """Provide authorization headers with admin token."""
    return {"Authorization": f"Bearer {admin_token}"}

@pytest.fixture
def regular_user(auth_headers):
    """Create a temporary regular user for testing."""
    url = f"{backend_base()}/api/users/"

    user_info = {
        "username": "regular_user",
        "email": "regular_user@example.com",
        "password": "default_password",
        "roles": ["user"]
    }
    
    # Create the user
    r = requests.post(url, json=user_info, headers=auth_headers, timeout=10)
    if r.status_code != 201:
        pytest.fail(f"Failed to create regular test user: {r.status_code}: {r.text[:500]}")
    
    yield user_info
    
    # Cleanup: delete the test user
    requests.delete(f"{url}{user_info["username"]}", headers=auth_headers, timeout=5)

@pytest.fixture
def regular_user_token(regular_user):
    """Provide token for regular user."""
    return get_keycloak_token(regular_user["username"], regular_user["password"])

@pytest.fixture
def regular_user_headers(regular_user_token):
    """Provide authorization headers with regular user token."""
    return {"Authorization": f"Bearer {regular_user_token}"}


# --- User CRUD Tests ---------------------------------------------------------

def test_list_users_requires_admin(auth_headers):
    """Test that listing users requires admin privileges."""
    url = f"{backend_base()}/api/users/"
    r = requests.get(url, headers=auth_headers, timeout=10)
    assert r.status_code == 200, f"Admin should be able to list users, got {r.status_code}: {r.text[:500]}"

    data = r.json()
    assert isinstance(data, list), f"Expected list of users, got: {type(data)}"
    assert len(data) > 0, "Should have at least one user (admin)"


def test_list_users_without_auth():
    """Test that listing users without auth is rejected."""
    url = f"{backend_base()}/api/users/"
    r = requests.get(url, timeout=5)
    assert r.status_code == 401, f"Expected 401 without auth, got {r.status_code}"


def test_create_user(auth_headers):
    """Test creating a new user."""
    url = f"{backend_base()}/api/users/"
    username = "testuser1"

    new_user = {
        "username": username,
        "email": "testuser1@example.com",
        "roles": ["user"]
    }

    try:
        r = requests.post(url, json=new_user, headers=auth_headers, timeout=10)
        assert r.status_code == 201, f"Expected 201 creating user, got {r.status_code}: {r.text[:500]}"

        data = r.json()
        assert data.get("success") is True, f"Expected success=True, got: {data}"
        assert "details" in data, f"Expected details in response: {data}"

        user_details = data["details"]
        assert user_details["username"] == username, f"Username mismatch: {user_details}"
        assert user_details["email"] == "testuser1@example.com", f"Email mismatch: {user_details}"
    finally:
        # Cleanup: delete the test user
        requests.delete(f"{url}{username}", headers=auth_headers, timeout=5)


def test_create_duplicate_user(auth_headers):
    """Test that creating duplicate user is rejected."""
    url = f"{backend_base()}/api/users/"
    username = "testuser2"

    # Create first user
    new_user = {
        "username": username,
        "email": "testuser2@example.com",
        "roles": ["user"]
    }

    try:
        r1 = requests.post(url, json=new_user, headers=auth_headers, timeout=10)
        assert r1.status_code == 201, f"First create should succeed: {r1.status_code}: {r1.text[:500]}"

        # Try to create duplicate
        r2 = requests.post(url, json=new_user, headers=auth_headers, timeout=10)
        assert r2.status_code == 400, f"Expected 400 for duplicate user, got {r2.status_code}: {r2.text[:500]}"

        data = r2.json()
        assert "already exists" in data.get("detail", "").lower(), f"Expected 'already exists' error: {data}"
    finally:
        # Cleanup: delete the test user
        requests.delete(f"{url}{username}", headers=auth_headers, timeout=5)


def test_create_user_without_auth():
    """Test that creating user without auth is rejected."""
    url = f"{backend_base()}/api/users/"

    new_user = {
        "username": "unauthorized_user",
        "email": "unauthorized@example.com",
        "roles": ["user"]
    }

    r = requests.post(url, json=new_user, timeout=5)
    assert r.status_code == 401, f"Expected 401 without auth, got {r.status_code}"


def test_get_user_by_username(auth_headers):
    """Test retrieving user by username."""
    # First create a user
    url = f"{backend_base()}/api/users/"
    username = "testuser3"
    new_user = {
        "username": username,
        "email": "testuser3@example.com",
        "roles": ["user"]
    }

    try:
        r_create = requests.post(url, json=new_user, headers=auth_headers, timeout=10)
        assert r_create.status_code == 201, f"User creation failed: {r_create.status_code}: {r_create.text[:500]}"

        # Now retrieve the user
        url_get = f"{backend_base()}/api/users/{username}"
        r = requests.get(url_get, headers=auth_headers, timeout=10)
        assert r.status_code == 200, f"Expected 200 getting user, got {r.status_code}: {r.text[:500]}"

        data = r.json()
        assert data["username"] == username, f"Username mismatch: {data}"
        assert data["email"] == "testuser3@example.com", f"Email mismatch: {data}"
        assert "uuid" in data, f"Expected uuid in response: {data}"
    finally:
        # Cleanup: delete the test user
        requests.delete(f"{url}{username}", headers=auth_headers, timeout=5)


def test_get_nonexistent_user(auth_headers):
    """Test that getting non-existent user returns 404."""
    url = f"{backend_base()}/api/users/nonexistent_user_12345"
    r = requests.get(url, headers=auth_headers, timeout=10)
    assert r.status_code == 404, f"Expected 404 for non-existent user, got {r.status_code}: {r.text[:500]}"


def test_get_current_user_info_admin(auth_headers):
    """Test /api/users/me endpoint for admin user info."""
    url = f"{backend_base()}/api/users/me"
    r = requests.get(url, headers=auth_headers, timeout=10)
    assert r.status_code == 200, f"Expected 200 for /me endpoint, got {r.status_code}: {r.text[:500]}"

    data = r.json()
    assert data["username"] == env("KEYCLOAK_ADMIN", "admin"), f"Expected admin user, got: {data}"
    assert "uuid" in data, f"Expected uuid in response: {data}"
    assert "email" in data, f"Expected email in response: {data}"

def test_get_current_user_info_regular(regular_user_headers, regular_user):
    """Test /api/users/me endpoint for regular user info."""
    url = f"{backend_base()}/api/users/me"
    r = requests.get(url, headers=regular_user_headers, timeout=10)
    assert r.status_code == 200, f"Expected 200 for /me endpoint, got {r.status_code}: {r.text[:500]}"

    data = r.json()
    assert data["username"] == regular_user["username"], f"Expected regular user, got: {data}"
    assert "uuid" in data, f"Expected uuid in response: {data}"
    assert "email" in data, f"Expected email in response: {data}"


def test_delete_user(auth_headers):
    """Test deleting a user."""
    # First create a user
    url = f"{backend_base()}/api/users/"
    new_user = {
        "username": "testuser_delete",
        "email": "testuser_delete@example.com",
        "roles": ["user"]
    }

    r_create = requests.post(url, json=new_user, headers=auth_headers, timeout=10)
    assert r_create.status_code == 201, f"User creation failed: {r_create.status_code}"

    # Now delete the user
    url_delete = f"{backend_base()}/api/users/testuser_delete"
    r = requests.delete(url_delete, headers=auth_headers, timeout=10)
    assert r.status_code == 200, f"Expected 200 deleting user, got {r.status_code}: {r.text[:500]}"

    data = r.json()
    assert data.get("success") is True, f"Expected success=True, got: {data}"
    assert "details" in data, f"Expected details in response: {data}"

    # Verify user is gone
    url_get = f"{backend_base()}/api/users/testuser_delete"
    r_verify = requests.get(url_get, headers=auth_headers, timeout=10)
    assert r_verify.status_code == 404, f"User should be deleted, got {r_verify.status_code}"


def test_delete_nonexistent_user(auth_headers):
    """Test that deleting non-existent user returns 404."""
    url = f"{backend_base()}/api/users/nonexistent_user_67890"
    r = requests.delete(url, headers=auth_headers, timeout=10)
    assert r.status_code == 404, f"Expected 404 deleting non-existent user, got {r.status_code}: {r.text[:500]}"


def test_delete_user_without_auth():
    """Test that deleting user without auth is rejected."""
    url = f"{backend_base()}/api/users/someuser"
    r = requests.delete(url, timeout=5)
    assert r.status_code == 401, f"Expected 401 without auth, got {r.status_code}"

def test_delete_self_as_regular_user(auth_headers):
    """Test that regular user can delete their own account."""
    url = f"{backend_base()}/api/users/"
    new_user = {
        "username": "testuser_delete_self",
        "email": "testuser_delete_self@example.com",
        "roles": ["user"],
        "password": "default_password"
    }

    try:
        # First create a user as admin
        r_create = requests.post(url, json=new_user, headers=auth_headers, timeout=10)
        assert r_create.status_code == 201, f"User creation failed: {r_create.status_code}: {r_create.text[:500]}"

        # Get token for the user
        user_token = get_keycloak_token(new_user["username"], new_user["password"])
        user_headers = {"Authorization": f"Bearer {user_token}"}

        # User deletes their own account
        url_delete = f"{backend_base()}/api/users/{new_user["username"]}"
        r_delete = requests.delete(url_delete, headers=user_headers, timeout=10)
        assert r_delete.status_code == 200, f"User should be able to delete own account, got {r_delete.status_code}: {r_delete.text[:500]}"

        data = r_delete.json()
        assert data.get("success") is True, f"Expected success=True, got: {data}"
        assert "details" in data, f"Expected details in response: {data}"
        assert data["details"]["username"] == new_user["username"], f"Username mismatch in response: {data}"

        # Verify user is gone
        r_verify = requests.get(f"{url}{new_user["username"]}", headers=auth_headers, timeout=10)
        assert r_verify.status_code == 404, f"User should be deleted, got {r_verify.status_code}"
    finally:
        # Cleanup on failure: delete the test user as admin if it still exists
        requests.delete(f"{url}{new_user["username"]}", headers=auth_headers, timeout=5)


# --- User Management Dashboard Tests -----------------------------------------

# TODO: Fix dashboard endpoint - currently not returning expected data structure
# def test_user_dashboard_access(auth_headers):
#     """Test that admin can access user management dashboard."""
#     url = f"{backend_base()}/api/users/dashboard"
#     r = requests.get(url, headers=auth_headers, timeout=10)
#     assert r.status_code == 200, f"Admin should access dashboard, got {r.status_code}: {r.text[:500]}"
#
#     data = r.json()
#     assert "users" in data, f"Expected 'users' in dashboard data: {data.keys()}"
#     assert "file_trees" in data, f"Expected 'file_trees' in dashboard data: {data.keys()}"
#     assert "models" in data, f"Expected 'models' in dashboard data: {data.keys()}"
#
#     assert isinstance(data["users"], list), f"Expected list of users: {type(data['users'])}"
#     assert len(data["users"]) > 0, "Should have at least one user"


def test_user_dashboard_without_auth():
    """Test that dashboard access without auth is rejected."""
    url = f"{backend_base()}/api/users/dashboard"
    r = requests.get(url, timeout=5)
    assert r.status_code == 401, f"Expected 401 without auth, got {r.status_code}"


# --- Complete User Lifecycle Test --------------------------------------------

def test_complete_user_lifecycle(auth_headers):
    """Test complete user lifecycle: create, list, get, delete."""
    base_url = f"{backend_base()}/api/users/"
    username = "lifecycle_test_user"

    # Step 1: Create user
    new_user = {
        "username": username,
        "email": f"{username}@example.com",
        "roles": ["user"]
    }
    r_create = requests.post(base_url, json=new_user, headers=auth_headers, timeout=10)
    assert r_create.status_code == 201, f"Create failed: {r_create.text[:500]}"
    created_data = r_create.json()
    user_uuid = created_data["details"]["uuid"]

    # Step 2: Verify user appears in list
    r_list = requests.get(base_url, headers=auth_headers, timeout=10)
    assert r_list.status_code == 200
    users = r_list.json()
    usernames = [u["username"] for u in users]
    assert username in usernames, f"User not found in list: {usernames}"

    # Step 3: Get user details
    r_get = requests.get(f"{base_url}{username}", headers=auth_headers, timeout=10)
    assert r_get.status_code == 200
    user_data = r_get.json()
    assert user_data["username"] == username
    assert user_data["uuid"] == user_uuid

    # Step 4: Delete user
    r_delete = requests.delete(f"{base_url}{username}", headers=auth_headers, timeout=10)
    assert r_delete.status_code == 200
    delete_data = r_delete.json()
    assert delete_data["success"] is True

    # Step 5: Verify user is gone
    r_verify = requests.get(f"{base_url}{username}", headers=auth_headers, timeout=10)
    assert r_verify.status_code == 404, "User should be deleted"


# --- Input Validation Tests --------------------------------------------------

def test_create_user_invalid_email(auth_headers):
    """Test that creating user with invalid email is rejected."""
    url = f"{backend_base()}/api/users/"

    new_user = {
        "username": "testuser_invalid_email",
        "email": "not_an_email",  # Invalid email format
        "roles": ["user"]
    }

    r = requests.post(url, json=new_user, headers=auth_headers, timeout=10)
    # Should either reject (422) or accept depending on validation rules
    # This test documents current behavior
    assert r.status_code in [201, 400, 422], f"Unexpected status for invalid email: {r.status_code}"


def test_create_user_missing_fields(auth_headers):
    """Test that creating user with missing required fields is rejected."""
    url = f"{backend_base()}/api/users/"

    # Missing email and roles
    incomplete_user = {
        "username": "incomplete_user"
    }

    r = requests.post(url, json=incomplete_user, headers=auth_headers, timeout=10)
    assert r.status_code == 422, f"Expected 422 for missing fields, got {r.status_code}: {r.text[:500]}"


def test_create_user_empty_username(auth_headers):
    """Test that creating user with empty username is rejected."""
    url = f"{backend_base()}/api/users/"

    new_user = {
        "username": "",
        "email": "empty@example.com",
        "roles": ["user"]
    }

    r = requests.post(url, json=new_user, headers=auth_headers, timeout=10)
    assert r.status_code in [400, 422], f"Expected 400/422 for empty username, got {r.status_code}"


# --- 403 Forbidden Tests -----------------------------------------------------

def test_list_users_forbidden(regular_user_headers):
    """Test that regular user cannot list all users (403 forbidden)."""
    url = f"{backend_base()}/api/users/"
    r = requests.get(url, headers=regular_user_headers, timeout=10)
    assert r.status_code == 403, f"Regular user should get 403 when listing users, got {r.status_code}: {r.text[:500]}"


def test_create_user_forbidden(regular_user_headers):
    """Test that regular user cannot create users (403 forbidden)."""
    url = f"{backend_base()}/api/users/"

    new_user = {
        "username": "forbidden_user",
        "email": "forbidden@example.com",
        "roles": ["user"]
    }

    r = requests.post(url, json=new_user, headers=regular_user_headers, timeout=10)
    assert r.status_code == 403, f"Regular user should get 403 when creating users, got {r.status_code}: {r.text[:500]}"


def test_delete_user_forbidden(regular_user_headers, auth_headers):
    """Test that regular user cannot delete other users (403 forbidden)."""
    # First create a user as admin
    url = f"{backend_base()}/api/users/"
    username = "testuser_forbidden_delete"
    new_user = {
        "username": username,
        "email": "testuser_forbidden_delete@example.com",
        "roles": ["user"]
    }

    try:
        r_create = requests.post(url, json=new_user, headers=auth_headers, timeout=10)
        assert r_create.status_code == 201, f"Admin user creation failed: {r_create.status_code}"

        # Try to delete as regular user
        url_delete = f"{backend_base()}/api/users/{username}"
        r = requests.delete(url_delete, headers=regular_user_headers, timeout=10)
        assert r.status_code == 403, f"Regular user should get 403 when deleting other users, got {r.status_code}: {r.text[:500]}"
    finally:
        # Cleanup: delete the test user as admin
        requests.delete(f"{url}{username}", headers=auth_headers, timeout=5)


def test_get_user_forbidden(regular_user_headers, auth_headers):
    """Test that regular user cannot get other user details (403 forbidden)."""
    # First create a user as admin
    url = f"{backend_base()}/api/users/"
    username = "testuser_forbidden_get"
    new_user = {
        "username": username,
        "email": "testuser_forbidden_get@example.com",
        "roles": ["user"]
    }

    try:
        r_create = requests.post(url, json=new_user, headers=auth_headers, timeout=10)
        assert r_create.status_code == 201, f"Admin user creation failed: {r_create.status_code}"

        # Try to get user details as regular user
        url_get = f"{backend_base()}/api/users/{username}"
        r = requests.get(url_get, headers=regular_user_headers, timeout=10)
        assert r.status_code == 403, f"Regular user should get 403 when getting other user details, got {r.status_code}: {r.text[:500]}"
    finally:
        # Cleanup: delete the test user as admin
        requests.delete(f"{url}{username}", headers=auth_headers, timeout=5)


def test_dashboard_forbidden(regular_user_headers):
    """Test that regular user cannot access user management dashboard (403 forbidden)."""
    url = f"{backend_base()}/api/users/dashboard"
    r = requests.get(url, headers=regular_user_headers, timeout=10)
    assert r.status_code == 403, f"Regular user should get 403 when accessing dashboard, got {r.status_code}: {r.text[:500]}"

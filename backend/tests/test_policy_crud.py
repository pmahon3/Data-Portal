# backend/tests/test_policy_crud.py
"""
Policy CRUD Tests

Tests full policy lifecycle with real data:
- Create policies for actual users and instances
- Read/list policies
- Delete policies
- Data validation and error handling
"""

import os
import json

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
        pytest.fail(f"Non-JSON response: HTTP {r.status_code}\n{r.text[:500]}")
    if r.status_code != 200:
        pytest.fail(f"Token request failed: {r.status_code}: {json.dumps(payload)[:500]}")
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
    """Provide auth headers."""
    return {"Authorization": f"Bearer {admin_token}"}


# --- Helper functions --------------------------------------------------------

def create_test_user(auth_headers, username):
    """Create a test user for policy testing."""
    url = f"{backend_base()}/api/users/"
    payload = {
        "username": username,
        "email": f"{username}@test.local",
        "password": "default_password",
        "roles": ["user"],
    }
    r = requests.post(url, json=payload, headers=auth_headers, timeout=10)
    assert r.status_code == 201, \
        f"Failed to create test user '{username}': {r.status_code}: {r.text[:500]}"
    return r.json()["details"]

def delete_test_user(auth_headers, username):
    """Delete a test user."""
    url = f"{backend_base()}/api/users/{username}"
    requests.delete(url, headers=auth_headers, timeout=5)

def create_test_instance(auth_headers, instance_name):
    """Create a test dummy storage instance.

    Uses the 'dummy' flavour which doesn't require real storage connectivity.
    """
    url = f"{backend_base()}/api/instances/"
    payload = {
        "flavour": "dummy",
        "instance_name": instance_name,
        "instance_url": f"dummy://test/{instance_name}"
    }
    r = requests.post(url, json=payload, headers=auth_headers, timeout=10)
    assert r.status_code == 201, \
        f"Failed to create test instance '{instance_name}': {r.status_code}: {r.text[:500]}"
    return r.json().get("instance")

def delete_test_instance(auth_headers, instance_name):
    """Delete a test storage instance by name."""
    # First get the list of instances to find the UUID
    list_url = f"{backend_base()}/api/instances/"
    r = requests.get(list_url, headers=auth_headers, timeout=5)
    if r.status_code != 200:
        return  # Can't list instances, skip deletion

    instances = r.json().get("instances", [])
    instance_uuid = None
    for inst in instances:
        if inst.get("name") == instance_name:
            instance_uuid = inst.get("uuid")
            break

    if instance_uuid:
        delete_url = f"{backend_base()}/api/instances/{instance_uuid}"
        requests.delete(delete_url, headers=auth_headers, timeout=5)


# --- Policy CRUD Tests -------------------------------------------------------

def test_policy_create_read_delete(auth_headers):
    """Test basic policy CRUD: create, read, delete."""
    username = "policy_crud_user"
    instance_name = "policy_crud_instance"

    # Cleanup any existing test fixtures first
    delete_test_user(auth_headers, username)
    delete_test_instance(auth_headers, instance_name)

    try:
        # Setup: Create user and instance
        user = create_test_user(auth_headers, username)
        instance = create_test_instance(auth_headers, instance_name)
        assert user and instance, "Failed to create test fixtures"

        user_uuid = user["uuid"]
        instance_uuid = instance["uuid"]

        # CREATE: Add a policy
        policy_url = f"{backend_base()}/api/policies/"
        create_payload = {
            "username": username,
            "instance_name": instance_name,
            "resource": "/data/.*",
            "action": "read"
        }
        r = requests.post(policy_url, json=create_payload, headers=auth_headers, timeout=10)
        assert r.status_code == 201, f"Policy creation failed: {r.status_code}: {r.text[:500]}"

        created = r.json()
        assert created.get("success") is True, f"Creation unsuccessful: {created}"
        assert len(created.get("details", [])) > 0, "No policy returned"

        # READ: List policies and find ours
        r = requests.get(policy_url, headers=auth_headers, timeout=10)
        assert r.status_code == 200, f"Failed to list policies: {r.status_code}"

        policies = r.json().get("details", [])
        found = any(
            p.get("user_uuid") == user_uuid and
            p.get("instance_uuid") == instance_uuid and
            p.get("resource") == "/data/.*"
            for p in policies
        )
        assert found, f"Created policy not found. User: {user_uuid}, Instance: {instance_uuid}"

        # DELETE: Remove the policy
        delete_payload = {
            "user_uuid": user_uuid,
            "instance_uuid": instance_uuid,
            "resource": "/data/.*",
            "action": "read"
        }
        r = requests.delete(policy_url, json=delete_payload, headers=auth_headers, timeout=10)
        assert r.status_code == 200, f"Policy deletion failed: {r.status_code}: {r.text[:500]}"

        deleted = r.json()
        assert deleted.get("success") is True, f"Deletion unsuccessful: {deleted}"

    finally:
        # Cleanup
        delete_test_user(auth_headers, username)
        delete_test_instance(auth_headers, instance_name)


def test_create_multiple_policies_same_user(auth_headers):
    """Test creating multiple policies for the same user/instance."""
    username = "policy_multi_user"
    instance_name = "policy_multi_instance"

    # Cleanup any existing test fixtures first
    delete_test_user(auth_headers, username)
    delete_test_instance(auth_headers, instance_name)

    try:
        # Setup
        user = create_test_user(auth_headers, username)
        instance = create_test_instance(auth_headers, instance_name)
        assert user and instance, "Failed to create test fixtures"

        user_uuid = user["uuid"]
        instance_uuid = instance["uuid"]

        # Create multiple policies
        policy_url = f"{backend_base()}/api/policies/"
        policies_to_create = [
            {"resource": "/data/.*", "action": "read"},
            {"resource": "/data/.*", "action": "write"},
            {"resource": "/config/.*", "action": "read"},
        ]

        for policy_spec in policies_to_create:
            payload = {
                "username": username,
                "instance_name": instance_name,
                **policy_spec
            }
            r = requests.post(policy_url, json=payload, headers=auth_headers, timeout=10)
            assert r.status_code == 201, f"Failed to create policy {policy_spec}: {r.text[:500]}"

        # Verify all policies exist
        r = requests.get(policy_url, headers=auth_headers, timeout=10)
        all_policies = r.json().get("details", [])
        user_policies = [p for p in all_policies if p.get("user_uuid") == user_uuid]

        assert len(user_policies) >= len(policies_to_create), \
            f"Expected at least {len(policies_to_create)} policies, found {len(user_policies)}"

        # Cleanup policies
        for policy_spec in policies_to_create:
            delete_payload = {
                "user_uuid": user_uuid,
                "instance_uuid": instance_uuid,
                **policy_spec
            }
            requests.delete(policy_url, json=delete_payload, headers=auth_headers, timeout=10)

    finally:
        delete_test_user(auth_headers, username)
        delete_test_instance(auth_headers, instance_name)


def test_create_policy_nonexistent_user(auth_headers):
    """Test that creating a policy for non-existent user fails properly."""
    policy_url = f"{backend_base()}/api/policies/"
    payload = {
        "username": "nonexistent_user_12345",
        "instance_name": "some_instance",
        "resource": "/test/.*",
        "action": "read"
    }
    r = requests.post(policy_url, json=payload, headers=auth_headers, timeout=10)
    assert r.status_code == 404, f"Expected 404 for non-existent user, got {r.status_code}"


def test_create_policy_nonexistent_instance(auth_headers):
    """Test that creating a policy for non-existent instance fails properly."""
    username = "policy_test_user_temp"

    try:
        user = create_test_user(auth_headers, username)
        assert user, "Failed to create test user"

        policy_url = f"{backend_base()}/api/policies/"
        payload = {
            "username": username,
            "instance_name": "nonexistent_instance_12345",
            "resource": "/test/.*",
            "action": "read"
        }
        r = requests.post(policy_url, json=payload, headers=auth_headers, timeout=10)
        assert r.status_code == 404, f"Expected 404 for non-existent instance, got {r.status_code}"

    finally:
        delete_test_user(auth_headers, username)


def test_delete_nonexistent_policy(auth_headers):
    """Test that deleting non-existent policy fails gracefully."""
    policy_url = f"{backend_base()}/api/policies/"
    delete_payload = {
        "user_uuid": "00000000-0000-0000-0000-000000000000",
        "instance_uuid": "00000000-0000-0000-0000-000000000000",
        "resource": "/fake/.*",
        "action": "read"
    }
    r = requests.delete(policy_url, json=delete_payload, headers=auth_headers, timeout=10)
    assert r.status_code in (400, 404), \
        f"Expected 400 or 404 for non-existent policy, got {r.status_code}"


def test_read_policies_filtered_by_user(auth_headers):
    """Test that GET /policies/ with user_uuid filter returns only that user's policies."""
    username = "policy_filter_user"
    instance_name = "policy_filter_instance"

    delete_test_user(auth_headers, username)
    delete_test_instance(auth_headers, instance_name)

    try:
        user = create_test_user(auth_headers, username)
        instance = create_test_instance(auth_headers, instance_name)
        assert user and instance, "Failed to create test fixtures"

        user_uuid = user["uuid"]
        instance_uuid = instance["uuid"]

        # Create a policy for this user
        policy_url = f"{backend_base()}/api/policies/"
        r = requests.post(policy_url, json={
            "username": username,
            "instance_name": instance_name,
            "resource": "/filtered/.*",
            "action": "read"
        }, headers=auth_headers, timeout=10)
        assert r.status_code == 201, f"Policy creation failed: {r.text[:500]}"

        # Filter by user_uuid
        r = requests.get(policy_url, params={"user_uuid": user_uuid}, headers=auth_headers, timeout=10)
        assert r.status_code == 200, f"Filtered GET failed: {r.status_code}"

        policies = r.json().get("details", [])
        assert all(p.get("user_uuid") == user_uuid for p in policies), \
            f"Filter returned policies belonging to other users: {policies}"
        assert len(policies) == 1

        # Cleanup policy
        requests.delete(policy_url, json={
            "user_uuid": user_uuid,
            "instance_uuid": instance_uuid,
            "resource": "/filtered/.*",
            "action": "read"
        }, headers=auth_headers, timeout=10)

    finally:
        delete_test_user(auth_headers, username)
        delete_test_instance(auth_headers, instance_name)


def test_duplicate_policy_creation(auth_headers):
    """Test that creating the same policy twice is handled gracefully (idempotent or 400)."""
    username = "policy_dup_user"
    instance_name = "policy_dup_instance"

    delete_test_user(auth_headers, username)
    delete_test_instance(auth_headers, instance_name)

    try:
        user = create_test_user(auth_headers, username)
        instance = create_test_instance(auth_headers, instance_name)
        assert user and instance, "Failed to create test fixtures"

        user_uuid = user["uuid"]
        instance_uuid = instance["uuid"]
        policy_url = f"{backend_base()}/api/policies/"
        payload = {
            "username": username,
            "instance_name": instance_name,
            "resource": "/dup/.*",
            "action": "read"
        }

        # First creation must succeed
        r = requests.post(policy_url, json=payload, headers=auth_headers, timeout=10)
        assert r.status_code == 201, f"First policy creation failed: {r.text[:500]}"

        # Second creation of the identical policy: accept 201 (idempotent) or 400 (rejected)
        r = requests.post(policy_url, json=payload, headers=auth_headers, timeout=10)
        assert r.status_code in (201, 400, 409), \
            f"Unexpected status for duplicate policy: {r.status_code}: {r.text[:500]}"

        # Cleanup
        requests.delete(policy_url, json={
            "user_uuid": user_uuid,
            "instance_uuid": instance_uuid,
            "resource": "/dup/.*",
            "action": "read"
        }, headers=auth_headers, timeout=10)

    finally:
        delete_test_user(auth_headers, username)
        delete_test_instance(auth_headers, instance_name)


def test_create_and_read_policy_for_multiple_instances(auth_headers):
    """Test that policies for different instances are correctly isolated."""
    username = "policy_multi_inst_user"
    instance_a = "policy_inst_b"
    instance_b = "policy_inst_a"

    delete_test_user(auth_headers, username)
    delete_test_instance(auth_headers, instance_a)
    delete_test_instance(auth_headers, instance_b)

    try:
        user = create_test_user(auth_headers, username)
        inst_a = create_test_instance(auth_headers, instance_a)
        inst_b = create_test_instance(auth_headers, instance_b)
        assert user and inst_a and inst_b, "Failed to create test fixtures"

        user_uuid = user["uuid"]
        uuid_a = inst_a["uuid"]
        uuid_b = inst_b["uuid"]
        policy_url = f"{backend_base()}/api/policies/"

        # Create one policy per instance for the same user
        for inst_name in (instance_a, instance_b):
            r = requests.post(policy_url, json={
                "username": username,
                "instance_name": inst_name,
                "resource": "/shared/.*",
                "action": "read"
            }, headers=auth_headers, timeout=10)
            assert r.status_code == 201, \
                f"Policy creation for instance '{inst_name}' failed: {r.text[:500]}"

        # Read all policies for this user and verify both instances are present
        r = requests.get(policy_url, params={"user_uuid": user_uuid}, headers=auth_headers, timeout=10)
        assert r.status_code == 200
        policies = r.json().get("details", [])

        covered_instances = {p["instance_uuid"] for p in policies}
        assert uuid_a in covered_instances, f"Policy for instance A ({uuid_a}) not found"
        assert uuid_b in covered_instances, f"Policy for instance B ({uuid_b}) not found"

        # Cleanup policies
        for inst_uuid in (uuid_a, uuid_b):
            requests.delete(policy_url, json={
                "user_uuid": user_uuid,
                "instance_uuid": inst_uuid,
                "resource": "/shared/.*",
                "action": "read"
            }, headers=auth_headers, timeout=10)

    finally:
        delete_test_user(auth_headers, username)
        delete_test_instance(auth_headers, instance_a)
        delete_test_instance(auth_headers, instance_b)

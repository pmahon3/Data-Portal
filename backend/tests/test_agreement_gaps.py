# backend/tests/test_agreement_gaps.py
"""
Agreement Gap Characterization Tests

Pin down how the portal behaves today where agreement-bound access would need
something different. Each test asserts CURRENT behaviour. A test that starts
failing means that gap has changed, so check whether it closed on purpose.

Gaps covered:
- Agreement stub: create/remove_agreement are silent no-ops
- Policy model: no time, condition or purpose term (no expiry possible)
- Project removal: a removed member keeps their policies
- Manager scope: a project manager can grant any path on a project instance,
  and loses the ability to revoke once the grantee leaves the project

Unit tests need the backend's dependencies (run them where the backend runs).
Stack tests need the local stack and three existing Keycloak users that can log
in with a password grant (users created through the API get a temporary
password, so they cannot). They skip unless these are set:
  QA_ADMIN_USER / QA_ADMIN_PASSWORD       admin role
  QA_MANAGER_USER / QA_MANAGER_PASSWORD   non-admin, becomes the project manager
  QA_MEMBER_USER / QA_MEMBER_PASSWORD     non-admin, becomes the project member
Each run creates a throwaway project and removes it, plus any policies the run
added, afterwards. Policies the member already had are left alone.
"""

import os
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
import requests


# --- Unit: agreement stub and policy model ----------------------------------

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MODEL_CONF = BACKEND_ROOT / "core/services/policies/casbin/model.conf"


def test_agreement_stub_methods_are_silent_noops():
    """create_agreement/remove_agreement build NotImplementedError but never raise it."""
    pytest.importorskip("sqlalchemy")
    from core.services.policies.casbin.CasbinPolicyManager import CasbinPolicyManager
    from core.services.policies.models import Agreement

    manager = object.__new__(CasbinPolicyManager)  # no enforcer or DB needed
    agreement = Agreement(uuid=uuid.uuid4(), policies=[], lifespan=timedelta(days=30), version=1.0)

    assert manager.create_agreement(agreement) is None
    assert manager.remove_agreement(agreement) is None


def test_agreement_model_has_no_parties_terms_or_status():
    """The stub carries policies, lifespan and version only."""
    pytest.importorskip("pydantic")
    pytest.importorskip("sqlalchemy")
    from core.services.policies.models import Agreement

    assert set(Agreement.model_fields) == {"uuid", "policies", "lifespan", "version"}


def test_policy_has_no_temporal_or_purpose_field():
    """A policy cannot carry an end date, condition or purpose."""
    pytest.importorskip("sqlalchemy")
    from core.services.policies.models import Policy

    assert set(Policy.model_fields) == {
        "user_uuid", "instance_uuid", "resource", "action", "username", "instance_name",
    }


def test_casbin_model_has_no_time_or_condition_term():
    """Request and policy definitions are sub, dom, obj, act; allow-only effect."""
    casbin = pytest.importorskip("casbin")
    model = casbin.Model()
    model.load_model(str(MODEL_CONF))

    assert model["r"]["r"].tokens == ["r_sub", "r_dom", "r_obj", "r_act"]
    assert model["p"]["p"].tokens == ["p_sub", "p_dom", "p_obj", "p_act"]
    assert model["e"]["e"].value == "some(where (p_eft == allow))"


# --- Stack: project membership and manager scope -----------------------------

BACKEND = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
KEYCLOAK = os.getenv("KEYCLOAK_DOMAIN", "http://localhost:8080")
REALM = os.getenv("KEYCLOAK_REALM", "ams-portal")
UI_CLIENT = os.getenv("KEYCLOAK_UI_CLIENT_ID", "ams-portal-ui")
INSTANCE = os.getenv("QA_INSTANCE", "qa-instance")
BUCKET = os.getenv("QA_BUCKET", "qa-authz")
TIMEOUT = 15

PROJECT = f"qa-agr-{uuid.uuid4().hex[:6]}"
NARROW = f"{BUCKET}/study/patient-7/summary.csv"
WHOLE_INSTANCE = ".*"
ADDED = [(WHOLE_INSTANCE, "read"), (NARROW, "read")]


def _creds(role: str) -> tuple[str, str]:
    user, password = os.getenv(f"QA_{role}_USER"), os.getenv(f"QA_{role}_PASSWORD")
    if not (user and password):
        pytest.skip(f"QA_{role}_USER / QA_{role}_PASSWORD not set")
    return user, password


def _token(username: str, password: str) -> dict:
    r = requests.post(
        f"{KEYCLOAK}/realms/{REALM}/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": UI_CLIENT,
              "username": username, "password": password},
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        pytest.skip(f"no token for {username}: {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _my_policies(headers: dict) -> list[dict]:
    r = requests.get(f"{BACKEND}/api/policies/me", headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["details"]


def _has(policies: list[dict], resource: str, action: str) -> bool:
    return any(p["resource"] == resource and p["action"] == action for p in policies)


@pytest.fixture(scope="module")
def stack():
    """Throwaway project on the QA instance with an existing manager and member."""
    admin_creds, manager_creds, member_creds = _creds("ADMIN"), _creds("MANAGER"), _creds("MEMBER")
    try:
        requests.get(f"{BACKEND}/api/health", timeout=5).raise_for_status()
    except requests.RequestException:
        pytest.skip(f"backend not reachable at {BACKEND}")

    admin = _token(*admin_creds)
    member_name = member_creds[0]
    before = _my_policies(_token(*member_creds))
    if any(_has(before, r, a) for r, a in ADDED):
        pytest.skip(f"{member_name} already holds a policy this test would add")

    try:
        steps = [
            ("post", "/api/projects", {"name": PROJECT}),
            ("post", f"/api/projects/{PROJECT}/storage-instances", {"instance_name": INSTANCE}),
            ("post", f"/api/projects/{PROJECT}/managers", {"username": manager_creds[0]}),
            ("post", f"/api/projects/{PROJECT}/users", {"username": member_name}),
        ]
        for method, path, body in steps:
            r = requests.request(method, f"{BACKEND}{path}", headers=admin, json=body, timeout=TIMEOUT)
            assert r.status_code in (200, 201), f"{path}: {r.status_code} {r.text}"

        # Project roles travel in the JWT's `projects` claim, so the manager's
        # token must be issued after they are added to the project.
        yield {
            "admin": admin,
            "manager": _token(*manager_creds),
            "member_name": member_name,
            "member": lambda: _token(*member_creds),
        }
    finally:
        for p in _my_policies(_token(*member_creds)):
            if (p["resource"], p["action"]) in ADDED:
                requests.delete(f"{BACKEND}/api/policies/", headers=admin, timeout=TIMEOUT, json={
                    "user_uuid": p["user_uuid"], "instance_uuid": p["instance_uuid"],
                    "resource": p["resource"], "action": p["action"]})
        requests.delete(f"{BACKEND}/api/projects/{PROJECT}", headers=admin, timeout=TIMEOUT)


def _grant(stack: dict, resource: str, action: str) -> requests.Response:
    return requests.post(f"{BACKEND}/api/policies/", headers=stack["manager"], timeout=TIMEOUT, json={
        "username": stack["member_name"], "instance_name": INSTANCE,
        "resource": resource, "action": action})


def test_manager_can_grant_whole_instance(stack):
    """A project manager (not admin) can grant a member every path on a project instance.

    Nothing checks the grant against an agreement, a steward or the data's owner.
    """
    r = _grant(stack, WHOLE_INSTANCE, "read")
    assert r.status_code == 201, r.text
    assert _has(_my_policies(stack["member"]()), WHOLE_INSTANCE, "read")


def test_removed_member_keeps_access(stack):
    """Removing a member from the project leaves their policies in place."""
    r = _grant(stack, NARROW, "read")
    assert r.status_code == 201, r.text

    r = requests.delete(f"{BACKEND}/api/projects/{PROJECT}/users/{stack['member_name']}",
                        headers=stack["admin"], timeout=TIMEOUT)
    assert r.status_code == 200, r.text

    after = _my_policies(stack["member"]())
    assert _has(after, NARROW, "read")
    assert _has(after, WHOLE_INSTANCE, "read")


def test_manager_cannot_revoke_after_removal(stack):
    """Once the grantee leaves the project, the granting manager can no longer revoke.

    Only an admin can remove the orphaned access. Runs after the removal test.
    """
    member = next(p for p in _my_policies(stack["member"]())
                  if p["resource"] == NARROW and p["action"] == "read")
    r = requests.delete(f"{BACKEND}/api/policies/", headers=stack["manager"], timeout=TIMEOUT, json={
        "user_uuid": member["user_uuid"], "instance_uuid": member["instance_uuid"],
        "resource": NARROW, "action": "read"})
    assert r.status_code == 403, r.text

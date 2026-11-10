# backend/tests/test_policy_leading_slash.py
"""
Saving a policy written as the policy form suggests

The Create Policy form used to suggest "/bucket/prefix/.*", but requests are checked against paths
without a leading "/", so such a policy granted nothing and no error was shown. A leading "/" is now
dropped when a policy is saved, so the policy grants what it names.

Calls the create-policy endpoint directly with stand-in managers: no database, Keycloak or storage
needed.
"""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import casbin
from fastapi import HTTPException

# Read when the endpoints are imported, never used
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:1/test")

from api.v0_1.common.models import AddPolicyRequest
from api.v0_1.endpoints import policies as endpoint

MODEL = Path(__file__).resolve().parents[1] / "core" / "services" / "policies" / "casbin" / "model.conf"
ADMIN = {"realm_access": {"roles": ["admin"]}}
USER, INSTANCE = uuid4(), uuid4()

class Users:
    def get_user_uuid(self, username):
        return USER

    def get_user(self, user_uuid):
        return {"uuid": user_uuid}


class Instances:
    def get_instance_uuid(self, name):
        return INSTANCE

    def get_instance_by_uuid(self, instance_uuid):
        return {"uuid": instance_uuid}


class Policies:
    def __init__(self):
        self.saved = []

    def add_policies(self, policies):
        self.saved += policies


def save(resource: str, monkeypatch) -> str | None:
    """Create a read policy through the endpoint; return the resource as saved, or None if refused."""
    async def no_roots():
        pass
    monkeypatch.setattr(endpoint, "init_db_roots", no_roots)
    policies = Policies()
    request = AddPolicyRequest(username="alice", instance_name="qa", resource=resource, action="read")
    try:
        asyncio.run(endpoint.create_policy(request, ADMIN, Users(), None, policies, Instances()))
    except HTTPException as refused:
        assert refused.status_code == 400
        return None
    return policies.saved[0].resource


def allows(resource: str, path: str) -> bool:
    enforcer = casbin.Enforcer(str(MODEL))
    enforcer.add_policy(str(USER), str(INSTANCE), resource, "read")
    return enforcer.enforce(str(USER), str(INSTANCE), path, "read")


def test_a_policy_written_with_a_leading_slash_grants_access(monkeypatch):
    saved = save("/study/sub-01/*", monkeypatch)
    assert saved is not None and allows(saved, "study/sub-01/scan.nii.gz")


def test_a_policy_without_a_leading_slash_still_grants_access(monkeypatch):
    saved = save("study/sub-01/scan.nii.gz", monkeypatch)
    assert saved is not None and allows(saved, "study/sub-01/scan.nii.gz")

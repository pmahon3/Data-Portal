# backend/tests/test_folder_operation_checks.py
"""
Folder delete and folder upload act only on files the user may act on (INN-293)

Both endpoints check the user's permission once, on the folder, and then act on every file in it.
A user allowed to delete one file can delete its whole folder; a user allowed to write one file can
replace the others with a folder upload. Each request should be refused, or act only on files the
user could delete or write one by one.

Calls the endpoints directly with the real Casbin model and stand-ins for the database and storage:
no database, Keycloak or storage needed.
"""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import casbin
import pytest
from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:1/test")  # read at import, never used

from api.v0_1.endpoints import s3_endpoints as endpoint

MODEL = Path(__file__).resolve().parents[1] / "core" / "services" / "policies" / "casbin" / "model.conf"
USER, INSTANCE, BUCKET = uuid4(), uuid4(), "bucket"

class PolicyManager:
    """The real Casbin model, with the user's policies held in memory."""

    def __init__(self, *policies):
        self.enforcer = casbin.Enforcer(str(MODEL))
        for action, resource in policies:
            self.enforcer.add_policy(str(USER), str(INSTANCE), resource, action)

    def validate_policy(self, policy):
        return self.enforcer.enforce(str(policy.user_uuid), str(policy.instance_uuid), policy.resource, policy.action)


class Agent:
    s3_client = object()

    def __init__(self):
        self.deleted, self.write_links = [], []

    def delete_objects(self, resources):
        self.deleted += resources

    def generate_access_link(self, resource, action, expires):
        self.write_links.append(resource)
        return [f"https://storage/{resource}"], [resource]


class Session:
    """Answers the endpoints' queries: the folder by id, then the files it already holds."""

    def __init__(self, folder_path, existing_keys=()):
        self.folder = SimpleNamespace(id=1, full_path=folder_path, bucket=BUCKET)
        self.existing = [SimpleNamespace(key=key) for key in existing_keys]

    async def execute(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        rows = [self.folder] if entity is endpoint.Folder else self.existing
        if entity is endpoint.Folder and statement.column_descriptions[0]["name"] == "full_path":
            rows = []
        return SimpleNamespace(scalar_one=lambda: rows[0], scalars=lambda: SimpleNamespace(all=lambda: rows))


class Tree:
    def __init__(self, session):
        pass

    async def delete_folder_subtree(self, bucket, folder_id):
        pass

    async def ensure_folder_path(self, bucket, parent_id, path):
        return SimpleNamespace(id=1)


class Files:
    def __init__(self, session):
        pass

    async def create_or_replace_file_row(self, *args, **kwargs):
        return SimpleNamespace(id=1)


@pytest.fixture
def setup(monkeypatch):
    agent = Agent()
    monkeypatch.setattr(endpoint, "TreeService", Tree)
    monkeypatch.setattr(endpoint, "FileService", Files)
    users = SimpleNamespace(get_user_uuid=lambda name: USER)
    instances = SimpleNamespace(get_instance_uuid=lambda name: INSTANCE,
                                get_instance_by_uuid=lambda uuid: SimpleNamespace(agent=agent))
    return agent, users, instances


def refused(call) -> bool:
    try:
        asyncio.run(call)
    except HTTPException as error:
        assert error.status_code == 403
        return True
    return False


def test_delete_on_one_file_does_not_delete_its_folder(setup, monkeypatch):
    agent, users, instances = setup
    monkeypatch.setattr(endpoint, "list_keys_under_prefix", lambda s3, bucket, prefix: ["del/one.nii", "del/two.nii"])
    policies = PolicyManager(("delete", "bucket/del/one.nii"))
    call = endpoint.delete_folder(1, "qa", BUCKET, {"preferred_username": "alice"}, Session("/del/"), users, policies, instances)
    assert refused(call) or agent.deleted == ["bucket/del/one.nii"]
    assert "bucket/del/two.nii" not in agent.deleted


def test_write_on_one_file_does_not_allow_replacing_others_by_folder_upload(setup):
    agent, users, instances = setup
    policies = PolicyManager(("write", "bucket/over/mine.csv"))
    payload = endpoint.FolderUploadInitIn(instance_name="qa", bucket=BUCKET, parent_id=1, on_conflict="replace",
                                          files=[{"relative_path": "theirs.csv"}, {"relative_path": "sub/other.csv"}])
    session = Session("/over/", existing_keys=["over/theirs.csv", "over/sub/other.csv"])
    call = endpoint.folder_upload_init(payload, {"preferred_username": "alice"}, session, users, policies, instances)
    assert refused(call) or agent.write_links == []


def test_delete_on_a_folder_deletes_everything_in_it(setup, monkeypatch):
    agent, users, instances = setup
    monkeypatch.setattr(endpoint, "list_keys_under_prefix", lambda s3, bucket, prefix: ["del/one.nii", "del/two.nii"])
    policies = PolicyManager(("delete", "bucket/del/.*"))
    asyncio.run(endpoint.delete_folder(1, "qa", BUCKET, {"preferred_username": "alice"}, Session("/del/"), users, policies, instances))
    assert sorted(agent.deleted) == ["bucket/del/one.nii", "bucket/del/two.nii"]

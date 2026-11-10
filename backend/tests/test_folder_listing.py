# backend/tests/test_folder_listing.py
"""
A folder listing shows only what the user may see

The folder listing API checks read once, on the folder, and then returns every file and subfolder
in it. A user who may read one file sees the names of every file beside it, and of every folder
above it. A listing should show the files the user may read, and only the folders on the path to
something they hold.

Calls the endpoint directly with the real Casbin model and stand-ins for the database: no database,
Keycloak or storage needed.
"""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import casbin

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:1/test")  # read at import, never used

from api.v0_1.endpoints import s3_endpoints as endpoint

MODEL = Path(__file__).resolve().parents[1] / "core" / "services" / "policies" / "casbin" / "model.conf"
USER, INSTANCE, BUCKET = uuid4(), uuid4(), "study"
GRANT = ("read", "study/patient-7/summary.csv")

# What the bucket holds: folder path -> (subfolders, files)
TREE = {
    "/": (["/patient-7/", "/patient-8/"], ["protocol.pdf"]),
    "/patient-7/": ([], ["summary.csv", "identifiers-MRN-0047731.csv"]),
}


class PolicyManager:
    """The real Casbin model, with the user's policies held in memory."""

    def __init__(self, *policies):
        self.enforcer = casbin.Enforcer(str(MODEL))
        for action, resource in policies:
            self.enforcer.add_policy(str(USER), str(INSTANCE), resource, action)

    def validate_policy(self, policy):
        return self.enforcer.enforce(str(policy.user_uuid), str(policy.instance_uuid), policy.resource, policy.action)


class Session:
    def __init__(self, path):
        self.folder = SimpleNamespace(id=1, full_path=path, bucket=BUCKET)

    async def execute(self, statement):
        return SimpleNamespace(scalar_one=lambda: self.folder)


def tree_for(path):
    class Tree:
        def __init__(self, session):
            pass

        async def list_children(self, bucket, folder_id):
            folders, files = TREE[path]
            return ([SimpleNamespace(id=i, name=f.strip("/").split("/")[-1], full_path=f) for i, f in enumerate(folders)],
                    [SimpleNamespace(id=i, name=n, key=path.lstrip("/") + n, size=1, last_modified=None, content_type=None)
                     for i, n in enumerate(files)])
    return Tree


def listing(path, monkeypatch):
    """(folder paths, file keys) the user is shown when listing `path`."""
    monkeypatch.setattr(endpoint, "TreeService", tree_for(path))
    users = SimpleNamespace(get_user_uuid=lambda name: USER)
    instances = SimpleNamespace(get_instance_uuid=lambda name: INSTANCE,
                                get_instance_by_uuid=lambda uuid: SimpleNamespace(agent=None))
    query = SimpleNamespace(instance_name="qa", bucket=BUCKET)
    out = asyncio.run(endpoint.list_children(1, query, {"preferred_username": "alice"}, Session(path),
                                             users, PolicyManager(GRANT), instances))
    return {f["full_path"] for f in out["folders"]}, {f["key"] for f in out["files"]}


def test_a_folder_listing_shows_only_files_the_user_may_read(monkeypatch):
    assert listing("/patient-7/", monkeypatch) == (set(), {"patient-7/summary.csv"})


def test_a_listing_above_a_file_shows_only_the_path_to_it(monkeypatch):
    assert listing("/", monkeypatch) == ({"/patient-7/"}, set())

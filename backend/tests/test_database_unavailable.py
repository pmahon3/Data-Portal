"""
Creating a storage instance when PostgreSQL can't be reached

Calls the create-instance endpoint with a real database session pointed at a PostgreSQL that isn't
there, the real instance manager over an in-memory collection, and stand-ins for policies and
projects: no database, Keycloak or storage needed.

A database that can't be reached is reported as unavailable (503), not as an internal error.
Requests succeed again once the database is back through the connection pool's pre-ping, which isn't
tested here.
"""

import asyncio
import os

import pytest
from fastapi import HTTPException

# Read when the endpoints are imported; nothing listens there
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused")

# Imported before the endpoints, as the app does, to avoid an import cycle
import core.services.filetree  # noqa: E402,F401
from sqlalchemy.exc import ProgrammingError  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from api.v0_1.common.models import S3InstanceCreate  # noqa: E402
from api.v0_1.endpoints import instances as endpoint  # noqa: E402
from core.services.instances.InstanceManager import InstanceManager  # noqa: E402

UNREACHABLE = {
    "nothing listening": "postgresql+asyncpg://user:pass@127.0.0.1:1/inn_db",
    # What the deployment rendered when service discovery found no database: no host or port
    "no host in the address": "postgresql+asyncpg://user:pass@/inn_db",
}

DB_OUTAGE_REPORTED_AS_500 = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="an unreachable database is reported as an internal error",
)

ADMIN = {
    "sub": "6f1c2b9e-0d3a-4e5f-8a7b-1c2d3e4f5a6b",
    "preferred_username": "admin",
    "realm_access": {"roles": ["admin"]},
}


class Collection:
    """An in-memory MongoDB collection: no instances yet, and records what is inserted."""

    def __init__(self):
        self.inserted = []

    def find(self, *args, **kwargs):
        return []

    def insert_one(self, document):
        self.inserted.append(document)


class Policies:
    def __init__(self):
        self.added = []

    def add_policy(self, policy):
        self.added.append(policy)
        return True


class Projects:
    def __init__(self):
        self.attached = []

    def add_project_storage_instance(self, project_name, instance_name):
        self.attached.append((project_name, instance_name))


def create_instance(database_url: str):
    """
    Create an S3 storage instance through the endpoint with the database at ``database_url``.
    Return the HTTP status (201 if created) and the stand-ins.
    """
    collection, policies, projects = Collection(), Policies(), Projects()
    config = S3InstanceCreate(
        flavour="s3",
        instance_name="new-instance",
        instance_url="http://storage.invalid",
        aws_access_key_id="key",
        aws_secret_access_key="secret",
    )

    async def run():
        engine = create_async_engine(database_url, pool_pre_ping=True)
        try:
            async with async_sessionmaker(engine, class_=AsyncSession)() as session:
                await endpoint.create_instance(
                    config=config,
                    current_user=ADMIN,
                    instance_manager=InstanceManager(collection=collection),
                    policy_manager=policies,
                    project_manager=projects,
                    session=session,
                )
            return 201
        except HTTPException as refused:
            return refused.status_code
        finally:
            await engine.dispose()

    return asyncio.run(run()), collection, policies, projects


@DB_OUTAGE_REPORTED_AS_500
@pytest.mark.parametrize("database_url", UNREACHABLE.values(), ids=UNREACHABLE.keys())
def test_an_unreachable_database_is_reported_as_unavailable(database_url):
    status, *_ = create_instance(database_url)
    assert status == 503


def test_another_database_error_is_still_an_internal_error(monkeypatch):
    async def no_tables(session):
        raise ProgrammingError(
            "SELECT DISTINCT folders.bucket FROM folders",
            {},
            Exception('relation "folders" does not exist'),
        )

    monkeypatch.setattr(InstanceManager, "get_existing_bucket_names", staticmethod(no_tables))
    status, collection, *_ = create_instance(UNREACHABLE["nothing listening"])
    assert status == 500
    assert collection.inserted == []

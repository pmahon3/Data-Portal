"""
Creating a storage instance when PostgreSQL can't be reached

Calls the create-instance endpoint with a real database session pointed at a PostgreSQL that isn't
there: no database, Keycloak or storage needed. Requests succeed again once the database is back
through the connection pool's pre-ping, which isn't tested here.
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
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from api.v0_1.common.models import S3InstanceCreate  # noqa: E402
from api.v0_1.endpoints import instances as endpoint  # noqa: E402
from core.services.instances.InstanceManager import InstanceManager  # noqa: E402

UNREACHABLE = {
    "nothing listening": "postgresql+asyncpg://user:pass@127.0.0.1:1/inn_db",
    # What the deployment rendered when service discovery found no database
    "no host in the address": "postgresql+asyncpg://user:pass@/inn_db",
}

DB_OUTAGE_REPORTED_AS_500 = pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="an unreachable database is reported as an internal error"
)


def create_instance(database_url: str) -> int:
    """Create an S3 storage instance with the database at ``database_url``; return the HTTP status."""
    config = S3InstanceCreate(
        flavour="s3", instance_name="new-instance", instance_url="http://storage.invalid",
        aws_access_key_id="key", aws_secret_access_key="secret",
    )

    async def run():
        engine = create_async_engine(database_url)
        try:
            async with AsyncSession(engine) as session:
                await endpoint.create_instance(config, {}, InstanceManager(), None, None, session)
            return 201
        except HTTPException as refused:
            return refused.status_code
        finally:
            await engine.dispose()

    return asyncio.run(run())


@DB_OUTAGE_REPORTED_AS_500
@pytest.mark.parametrize("database_url", UNREACHABLE.values(), ids=UNREACHABLE.keys())
def test_an_unreachable_database_is_reported_as_unavailable(database_url):
    assert create_instance(database_url) == 503


def test_another_database_error_is_still_an_internal_error(monkeypatch):
    async def no_tables(session):
        raise ProgrammingError("SELECT ...", {}, Exception('relation "folders" does not exist'))

    monkeypatch.setattr(InstanceManager, "get_existing_bucket_names", staticmethod(no_tables))
    assert create_instance(UNREACHABLE["nothing listening"]) == 500

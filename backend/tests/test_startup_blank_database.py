"""
The backend starts on a blank PostgreSQL database.

Needs a PostgreSQL server: set TEST_DATABASE_URL to postgresql://user:password@host:5432/postgres
for a user that may create databases. Skipped when it isn't set.
"""

import asyncio
import os
import uuid

import pytest

ADMIN_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="needs a PostgreSQL server: set TEST_DATABASE_URL")

# startup.py builds its database engine on import, from DATABASE_URL
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@localhost:5432/unused")


class FakeInstanceManager:
    """One S3-like storage instance with one bucket."""

    class Agent:
        def fetch_all_buckets(self):
            return ["bundle"]

    instances = [type("Instance", (), {"agent": Agent()})()]


def test_startup_on_a_blank_database(monkeypatch):
    """Startup creates the tables on a blank database, and a restart changes nothing."""
    import asyncpg
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    import core.services.filetree  # noqa: F401  (imported before startup, as the app does, to avoid an import cycle)
    from api.v0_1 import startup

    async def run():
        name = f"blank_{uuid.uuid4().hex[:12]}"
        base = ADMIN_URL.rsplit("/", 1)[0]
        admin = await asyncpg.connect(ADMIN_URL)
        await admin.execute(f'CREATE DATABASE "{name}"')
        engine = create_async_engine(f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{name}")
        try:
            monkeypatch.setattr(startup, "engine", engine, raising=False)
            monkeypatch.setattr(startup, "AsyncSessionMaker",
                                async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
            monkeypatch.setattr(startup, "get_instance_manager", lambda: FakeInstanceManager())
            monkeypatch.setattr(startup, "init_mongo_indexes", lambda: None)
            await startup.run_startup_tasks()
            await startup.run_startup_tasks()  # a restart
            async with engine.connect() as conn:
                raw = await conn.get_raw_connection()
                return await raw.driver_connection.fetch("SELECT bucket, full_path FROM folders WHERE full_path = '/'")
        finally:
            await engine.dispose()
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            await admin.close()

    roots = asyncio.run(run())
    assert [(r["bucket"], r["full_path"]) for r in roots] == [("bundle", "/")]

"""
The backend starts on a blank PostgreSQL database (INN-303).

Staging was respun on an empty database and the backend never started: startup reads the
folders table to create each bucket's root folder, and nothing had created the table.

Needs a PostgreSQL server: set TEST_DATABASE_URL to postgresql://user:password@host:5432/postgres
for a user that may create databases. Each test creates a blank database of its own, runs the
startup tasks against it, and drops it. Skipped when TEST_DATABASE_URL isn't set.
"""

import asyncio
import os
import uuid

import pytest
from sqlalchemy.exc import ProgrammingError

ADMIN_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="needs a PostgreSQL server: set TEST_DATABASE_URL")

# startup.py builds its database engine on import, from DATABASE_URL
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@localhost:5432/unused")


class FakeAgent:
    """An S3-like storage agent with one bucket, as staging had."""

    def fetch_all_buckets(self):
        return ["bundle"]


class FakeInstanceManager:
    instances = [type("Instance", (), {"agent": FakeAgent()})()]


async def start_on_blank_database(monkeypatch, starts: int):
    """Create a blank database, run the startup tasks `starts` times, return the root folders."""
    import asyncpg
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    import core.services.filetree  # noqa: F401  (imported before startup, as the app does, to avoid an import cycle)
    from api.v0_1 import startup

    name = f"blank_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(ADMIN_URL)
    await admin.execute(f'CREATE DATABASE "{name}"')
    base = ADMIN_URL.rsplit("/", 1)[0]
    engine = create_async_engine(f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{name}")
    try:
        monkeypatch.setattr(startup, "engine", engine, raising=False)
        monkeypatch.setattr(startup, "AsyncSessionMaker",
                            async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
        monkeypatch.setattr(startup, "get_instance_manager", lambda: FakeInstanceManager())
        monkeypatch.setattr(startup, "init_mongo_indexes", lambda: None)
        for _ in range(starts):
            await startup.run_startup_tasks()
        db = await asyncpg.connect(f"{base}/{name}")
        try:
            return await db.fetch("SELECT bucket, full_path FROM folders WHERE full_path = '/'")
        finally:
            await db.close()
    finally:
        await engine.dispose()
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.close()


@pytest.mark.xfail(strict=True, raises=ProgrammingError, reason="INN-303: startup doesn't create the tables on a blank database")
def test_startup_on_a_blank_database_creates_the_tables(monkeypatch):
    """INN-303: on a blank database, startup creates the tables and each bucket's root folder."""
    roots = asyncio.run(start_on_blank_database(monkeypatch, starts=1))
    assert [(r["bucket"], r["full_path"]) for r in roots] == [("bundle", "/")]


@pytest.mark.xfail(strict=True, raises=ProgrammingError, reason="INN-303: startup doesn't create the tables on a blank database")
def test_restarting_on_the_created_database_changes_nothing(monkeypatch):
    """INN-303: a second start on the same database succeeds and leaves one root folder."""
    roots = asyncio.run(start_on_blank_database(monkeypatch, starts=2))
    assert [(r["bucket"], r["full_path"]) for r in roots] == [("bundle", "/")]

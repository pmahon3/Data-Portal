from __future__ import annotations

import os

from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, String, Table, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy_utils import LtreeType

DATABASE_URL = os.environ["DATABASE_URL"]

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionMaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
metadata = MetaData()

folders = Table(
    "folders",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("bucket", Text, nullable=False),
    Column("parent_id", BigInteger, nullable=True),
    Column("name", String(512), nullable=False),
    Column("path", LtreeType, nullable=False),
    Column("full_path", Text, nullable=False),
    Column("marker_key", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

files = Table(
    "files",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("bucket", Text, nullable=False),
    Column("folder_id", BigInteger, nullable=False),
    Column("name", String(512), nullable=False),
    Column("key", Text, nullable=False),
    Column("size", BigInteger, nullable=True),
    Column("etag", Text, nullable=True),
    Column("last_modified", DateTime(timezone=True), nullable=True),
    Column("content_type", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

storage_events = Table(
    "storage_events",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("event_id", Text, nullable=True),
    Column("bucket", Text, nullable=False),
    Column("object_key", Text, nullable=False),
    Column("event_type", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("size", BigInteger, nullable=True),
    Column("etag", Text, nullable=True),
    Column("event_time", DateTime(timezone=True), nullable=True),
    Column("status", Text, nullable=False, server_default="pending"),
    Column("retry_count", Integer, nullable=False, server_default="0"),
    Column("error_message", Text, nullable=True),
    Column("raw_event", JSONB, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("processed_at", DateTime(timezone=True), nullable=True),
)

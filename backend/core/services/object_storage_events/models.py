from sqlalchemy import BigInteger, Column, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from core.db.postgres.base import Base


class StorageEvent(Base):
    __tablename__ = "storage_events"

    id = Column(BigInteger, primary_key=True)
    event_id = Column(Text, nullable=True)
    bucket = Column(Text, nullable=False)
    object_key = Column(Text, nullable=False)
    event_type = Column(Text, nullable=False)
    action = Column(Text, nullable=False)
    size = Column(BigInteger, nullable=True)
    etag = Column(Text, nullable=True)
    event_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(Text, nullable=False, server_default="pending")
    retry_count = Column(Integer, nullable=False, server_default="0")
    error_message = Column(Text, nullable=True)
    raw_event = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

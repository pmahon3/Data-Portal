from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from core.db.postgres.base import Base


class File(Base):
    __tablename__ = "files"

    id = Column(BigInteger, primary_key=True)
    bucket = Column(Text, nullable=False)
    folder_id = Column(BigInteger, ForeignKey("folders.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(512), nullable=False)

    # object storage key (flat namespace)
    key = Column(Text, nullable=False)

    size = Column(BigInteger, nullable=True)
    etag = Column(Text, nullable=True)
    last_modified = Column(DateTime(timezone=True), nullable=True)
    content_type = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="pending")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # defines many‑to‑one relationship and allows file.folder without manual join
    folder = relationship("Folder")

#the combination (bucket, key) is unique.
    __table_args__ = (
        UniqueConstraint("bucket", "key", name="uq_files_bucket_key"),
    )

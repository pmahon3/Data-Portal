from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from core.db.postgres.base import Base


class Bundle(Base):
    """A bundle request, recorded so redemption can be re-authorized.

    The bundler service is identity-unaware: it holds the archive, not the
    question of who may have it. A bundle id identifies an archive but does
    not grant access to one - every redemption is checked against the
    caller's current policies.

    See docs/bundling-design.md.
    """

    __tablename__ = "bundles"

    # the bundler's job id
    id = Column(Text, primary_key=True)
    instance_uuid = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BundleScope(Base):
    """The distinct folder prefixes a bundle draws from.

    Deduplicated by parent folder rather than recorded per file: policies are
    path-scoped, so files sharing a directory resolve identically. A 10k-file
    bundle spanning 50 directories therefore costs 50 policy checks rather
    than 10,000 (~3ms against ~380ms, measured).
    """

    __tablename__ = "bundle_scopes"

    id = Column(BigInteger, primary_key=True)
    bundle_id = Column(Text, ForeignKey("bundles.id", ondelete="CASCADE"), nullable=False)
    bucket = Column(Text, nullable=False)
    # normalized parent folder path, e.g. "/proj/sub/"
    folder_path = Column(Text, nullable=False)

    __table_args__ = (
        Index("ix_bundle_scopes_bundle_id", "bundle_id"),
        UniqueConstraint("bundle_id", "bucket", "folder_path", name="uq_bundle_scope"),
    )

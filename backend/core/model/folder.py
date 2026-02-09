
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship
from sqlalchemy_utils import LtreeType

from core.model.base import Base


class Folder(Base):
    __tablename__ = "folders"

    id = Column(BigInteger, primary_key=True)
    bucket = Column(Text, nullable=False)

    #Self‑referencing FK to the parent folder.
    parent_id = Column(BigInteger, ForeignKey("folders.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(512), nullable=False)

    # encoded ltree path, e.g. root.projects.inn
    path = Column(LtreeType, nullable=False, index=True)

    # display path, e.g. /projects/inn/
    full_path = Column(Text, nullable=False)

    #s3 marker for the folder like /projects/inn
    marker_key = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    #Self‑relationship.

    '''
    remote side: which column is on the “other side” of this self‑referencing relationship. It disambiguates parent vs child when a table points to itself.
    Parent = the row whose id is referenced by another row’s parent_id.
    Child = the row that has parent_id pointing to its parent.
    
    example:
    
    demo = session.get(Folder, 7)
    demo.parent.id        # returns  1  (root folder)
    demo.children         # returns   [Folder(id=9, ...)]  (sub folder)
    '''
    parent = relationship("Folder", remote_side=[id], backref="children")

    __table_args__ = (
        UniqueConstraint("bucket", "path", name="uq_folders_bucket_path"),
        UniqueConstraint("bucket", "full_path", name="uq_folders_bucket_full_path"),
    )

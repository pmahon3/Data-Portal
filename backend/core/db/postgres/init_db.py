from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_utils import Ltree

from core.services.instances import AbstractInstanceManager
from core.services.filetree.models.folder import Folder


async def ensure_root_for_bucket(session: AsyncSession, bucket: str) -> Folder:
    """
      Purpose: check if a bucket has a root folder row (full_path='/').
      If it already exists, return it; otherwise create it.
    """
    q = select(Folder).where(Folder.bucket == bucket, Folder.full_path == "/")
    res = await session.execute(q)
    root = res.scalar_one_or_none()
    if root:
        return root

    root = Folder(
        bucket=bucket,
        parent_id=None,
        name="/",
        path=Ltree("root"),
        full_path="/",
        status="complete",
    )
    session.add(root)
    await session.commit()
    await session.refresh(root)
    return root


async def ensure_roots_for_instances(
    session: AsyncSession,
    instance_manager: AbstractInstanceManager,
) -> list[Folder]:
    """
        Purpose: for every configured storage instance, create a root folder (if not exists)  for
        each bucket that instance exposes. so,  the DB tree.
        """

    roots: list[Folder] = []

    for instance in instance_manager.instances:
        agent = instance.agent
        # if not s3 like storage skip
        if not hasattr(agent, "fetch_all_buckets"):
            continue

        for bucket in agent.fetch_all_buckets():
            root = await ensure_root_for_bucket(session, bucket)
            roots.append(root)

    return roots

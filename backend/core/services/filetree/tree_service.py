from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_utils import Ltree

from core.db.postgres.init_db import ensure_root_for_bucket
from core.services.filetree.models.file import File
from core.services.filetree.models.folder import Folder
from core.util.paths import (
    build_ltree_path,
    build_object_key,
    join_child_full_path,
    normalize_folder_full_path,
    split_segments,
)


@dataclass(frozen=True)
class TreeService:
    # one session per instance
    session: AsyncSession

    async def get_root(self, bucket: str) -> Folder:
        return await ensure_root_for_bucket(self.session, bucket)

    async def list_children(self, bucket: str, folder_id: int) -> tuple[list[Folder], list[File]]:
        '''
            Return only the immediate child folders/files (not recursive).
        '''


        #check if the folder exists otherwise scalar_one returns error
        folder = (await self.session.execute(
            select(Folder).where(Folder.id == folder_id, Folder.bucket == bucket)
        )).scalar_one()

        # all subfolders folder with id folder_id
        folders_q = (
            select(Folder)
            .where(Folder.bucket == bucket, Folder.parent_id == folder_id)
            .order_by(Folder.name)
        )
        # all files whose their folder has  id folder_id
        files_q = (
            select(File)
            .where(File.bucket == bucket, File.folder_id == folder_id)
            .order_by(File.name)
        )
        folders = list((await self.session.execute(folders_q)).scalars().all())
        files = list((await self.session.execute(files_q)).scalars().all())
        return folders, files


    async def create_folder(self, bucket: str, parent_id: int, name: str) -> Folder:

        #Loads the parent folder for this parent_id. If not found, scalar_one() raises an error
        parent = (await self.session.execute(
            select(Folder).where(Folder.id == parent_id, Folder.bucket == bucket)
        )).scalar_one()

        # normalize the parent folder
        parent_full = normalize_folder_full_path(parent.full_path)

        #Builds the child's full path. For example:  /demo/ + sub ->  /demo/sub/
        child_full = join_child_full_path(parent_full, name)

        #Converts the full path into an ltree label string. For example:  /demo/sub/ -> root.demo.sub
        ltree_path_str = build_ltree_path(split_segments(child_full))

        folder = Folder(
            bucket=bucket,
            parent_id=parent.id,
            name=name,
            path=Ltree(ltree_path_str),
            full_path=child_full,
        )
        self.session.add(folder)
        await self.session.commit()
        await self.session.refresh(folder)
        return folder

    async def delete_folder_subtree(self, bucket: str, folder_id: int) -> None:
        folder = (await self.session.execute(
            select(Folder).where(Folder.id == folder_id, Folder.bucket == bucket)
        )).scalar_one()

        subtree_q = select(Folder.id).where(
            Folder.bucket == bucket,
            Folder.path.op("<@")(folder.path),   #<@ means "is descendant of or equal to"
        )

        #Deletes all files whose folder_id is in the subtree.
        await self.session.execute(delete(File).where(File.folder_id.in_(subtree_q)))

        #Deletes all folders in the subtree (including the root folder itself)
        await self.session.execute(
            delete(Folder).where(
                Folder.bucket == bucket,
                Folder.path.op("<@")(folder.path),
            )
        )
        await self.session.commit()

    async def build_key(self, bucket: str, folder_id: int, filename: str) -> tuple[Folder, str]:
        '''
        finds the folder by folder_id and bucket, normalizes its full_path, then builds the S3 object key using the folder path + filename. It returns both: the Folder object
        the computed key string (e.g., file.txt)
        '''
        folder = (await self.session.execute(
            select(Folder).where(Folder.id == folder_id, Folder.bucket == bucket)
        )).scalar_one()
        folder_full = normalize_folder_full_path(folder.full_path)
        return folder, build_object_key(folder_full, filename)

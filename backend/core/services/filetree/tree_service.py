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

    async def ensure_folder_path(self, bucket: str, parent_id: int, relative_path: str) -> Folder:
        """
        Ensure a nested relative path exists in Postgres under `parent_id`.

        This is the missing piece needed for folder uploads.

        Example:
        - The user selects destination folder `/research/` in the UI.
        - The browser provides a file with webkitRelativePath:
          `StudyA/session1/image1.sample.gz`
        - The frontend sends `relative_path="StudyA/session1"` to this method.
        - We then make sure the following folder rows exist in the DB:
          `/research/StudyA/`
          `/research/StudyA/session1/`
        - The returned Folder is the row for `/research/StudyA/session1/`
        - The existing single-file upload flow then stores `image1.sample.gz`
          inside that folder by generating the object key:
          `research/StudyA/session1/image1.sample.gz`

        Important:
        - This method only ensures folder metadata in PostgreSQL.
        - S3 does not need real folder creation for non-empty folders; the folder
          structure is represented implicitly by object keys when files are
          uploaded.
        - Empty-folder support is a separate concern and is not handled here.

        Returns the final folder. An empty relative path resolves to the parent.
        """
        # Fetch the parent folder row from Postgres and use it as the starting folder.
        folder = (await self.session.execute(
            select(Folder).where(Folder.id == parent_id, Folder.bucket == bucket)
        )).scalar_one()

        # Convert "StudyA/session1" into ["StudyA", "session1"] and ignore
        # accidental repeated slashes or empty segments.
        segments = [segment.strip() for segment in split_segments(relative_path) if segment.strip()]
        if not segments:
            return folder

        for segment in segments:
            # Build the next child path relative to the folder we are currently at.
            child_full = join_child_full_path(folder.full_path, segment)
            existing = (await self.session.execute(
                select(Folder).where(Folder.bucket == bucket, Folder.full_path == child_full)
            )).scalar_one_or_none()
            if existing:
                # Reuse the existing folder row so repeated uploads into the same
                # path remain idempotent at the folder-metadata level.
                folder = existing
                continue

            # Missing segment: create exactly one folder level, then continue
            # walking deeper until the whole relative path exists.
            folder = await self.create_folder(bucket, folder.id, segment)

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

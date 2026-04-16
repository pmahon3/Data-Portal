from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.services.filetree.models.file import File


#makes attributes immutable and cannot be reassigned. We cannot create a new session but the session itself can change and perform DB operations
@dataclass(frozen=True)
class FileService:
    session: AsyncSession

    async def create_file_row(
        self,
        bucket: str,
        folder_id: int,
        name: str,
        key: str,
        content_type: str | None = None,
    ) -> File:
        lookup = select(File).where(File.bucket == bucket, File.key == key)
        result = await self.session.execute(lookup)
        if result.scalar_one_or_none():
            raise ValueError

        file = File(
            bucket=bucket,
            folder_id=folder_id,
            name=name,
            key=key,
            content_type=content_type,
        )
        self.session.add(file)
        await self.session.commit()
        await self.session.refresh(file)
        return file

    async def get_file(self,  file_id: int) -> File | None:
        return (await self.session.execute(
            select(File).where(File.id == file_id)
        )).scalar_one_or_none()

    async def get_files(self, file_ids: list[int]) -> list[File]:
        return list((await self.session.execute(
            select(File).where(File.id.in_(file_ids))
        )).scalars().all())

    async def update_from_head(self, file: File, head: dict) -> None:
        file.size = head.get("ContentLength", file.size)
        file.etag = head.get("ETag", file.etag)
        file.last_modified = head.get("LastModified", file.last_modified)
        file.content_type = head.get("ContentType", file.content_type)
        await self.session.commit()

    async def delete_file_row(self, file: File) -> None:
        await self.session.delete(file)
        await self.session.commit()

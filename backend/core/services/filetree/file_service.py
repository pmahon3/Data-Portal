from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import any_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.services.filetree.models.file import File


@dataclass(frozen=True)
class FileService:
    """Service for managing file records in the database.

    Provides CRUD operations for the ``File`` model, including creating
    pending file rows, looking up completed files, and syncing metadata
    from object-storage HEAD responses.

    The dataclass is frozen so the session reference is immutable;
    the session itself remains mutable and can perform DB operations.
    """

    session: AsyncSession

    async def create_file_row(
        self,
        bucket: str,
        folder_id: int,
        name: str,
        key: str,
        content_type: str | None = None,
    ) -> File:
        """Create a new pending file row, or update an existing pending row.

        Returns:
            The newly created or updated ``File`` instance.

        Raises:
            ValueError: If a completed file row already exists for the same
                bucket + key combination.
        """
        lookup = select(File).where(File.bucket == bucket, File.key == key)
        result = await self.session.execute(lookup)

        # Check if there an existing record
        existing = result.scalar_one_or_none()
        if existing:
            # TODO: File updates are currently unsupported (delete and re-upload required). 
            #       Implementing updates requires refactoring to resolve a race condition 
            #       with object storage notifications.

            # if there is an existing pending record we can overwrite it
            if existing.status == "pending":
                existing.folder_id = folder_id
                existing.name = name
                existing.content_type = content_type
                await self.session.commit()
                await self.session.refresh(existing)
                return existing
            # If there is an existing complete record we fail
            raise ValueError

        file = File(
            bucket=bucket,
            folder_id=folder_id,
            name=name,
            key=key,
            content_type=content_type,
            status="pending",
        )
        self.session.add(file)
        await self.session.commit()
        await self.session.refresh(file)
        return file

    async def get_file(self, file_id: int, include_pending: bool = False) -> File | None:
        """Retrieve a single file record by its ID.

        By default only returns files with ``status == "complete"``.

        Returns:
            The matching ``File`` or ``None`` if not found.
        """
        query = select(File).where(File.id == file_id)
        if not include_pending:
            query = query.where(File.status == "complete")
        return (await self.session.execute(
            query
        )).scalar_one_or_none()

    async def get_files(self, file_ids: list[int]) -> list[File]:
        """Retrieve multiple completed file records by their IDs.

        Returns:
            List of completed ``File`` instances (may be empty).
        """
        return list((await self.session.execute(
            select(File).where(File.id == any_(file_ids), File.status == "complete")
        )).scalars().all())

    async def update_from_head(self, file: File, head: dict) -> None:
        """Update file metadata from an S3/MinIO HEAD-object response.

        Sets size, ETag, last-modified, content-type, and marks the file
        status as ``"complete"``. Keys not present in *head* keep their
        existing values.

        Args:
            file: The ``File`` instance to update (mutated in place).
            head: Dictionary from a HEAD-object call (keys like
                ``ContentLength``, ``ETag``, ``LastModified``,
                ``ContentType``).
        """
        file.size = head.get("ContentLength", file.size)
        file.etag = head.get("ETag", file.etag)
        file.last_modified = head.get("LastModified", file.last_modified)
        file.content_type = head.get("ContentType", file.content_type)
        file.status = "complete"
        await self.session.commit()

    async def delete_file_row(self, file: File) -> None:
        """
        Delete a file record from the database.
        """
        await self.session.delete(file)
        await self.session.commit()

"""S3 / file-tree endpoints.

Handles folder navigation, file upload (presigned URL init + complete),
file download (presigned URL), file/folder deletion, and asset bundling.
"""

import os
import httpx
import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import any_, select
from sqlalchemy.ext.asyncio import AsyncSession

# INN dependencies
from api.v0_1.endpoints.auth import decode_token
from api.v0_1.common.models import BundleCreateRequest, BundleCreateResponse, BundleDownloadUrlResponse
# DB models
from core.db.postgres.session import get_session
from core.services.injectors import get_instance_manager, get_policy_manager, get_user_manager
from core.services.instances import AbstractInstanceManager
from core.services.policies import CasbinPolicyManager
from core.services.policies import Policy
from core.services.policies.rules import Checker
from core.services.users import AbstractUserManager
from core.services.filetree.models.file import File
from core.services.filetree.models.folder import Folder
from core.services.filetree.file_service import FileService
from core.services.filetree.tree_service import TreeService
from core.utils.paths import build_object_key, join_child_full_path, normalize_folder_full_path

router = APIRouter(prefix="/tree", tags=["Tree"])
logger = logging.getLogger("api.endpoints")
BUNDLER_PROVIDER = os.getenv("BUNDLER_PROVIDER", "java").strip().lower()
BUNDLER_URL = os.getenv("BUNDLER_URL", "http://bundler:8082")
PYTHON_BUNDLER_URL = os.getenv("PYTHON_BUNDLER_URL", BUNDLER_URL)
JAVA_BUNDLER_URL = os.getenv("JAVA_BUNDLER_URL", "http://localhost:8888")
BUNDLE_SOURCE_URL_EXPIRATION_SECONDS = int(os.getenv("BUNDLE_SOURCE_URL_EXPIRATION_SECONDS", "7200"))
FOLDER_UPLOAD_PUT_EXPIRATION_SECONDS = int(os.getenv("FOLDER_UPLOAD_PUT_EXPIRATION_SECONDS", "7200"))
FOLDER_UPLOAD_SKIP_HEAD_CHECK = os.getenv("FOLDER_UPLOAD_SKIP_HEAD_CHECK", "false").strip().lower() == "true"

# Global async HTTP client for interacting with the bundler service
bundler_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
KNOWN_BUNDLER_ERROR_STATUSES = {400, 409, 413, 422, 501}

#################################################################################### Pydantic models
class TreeRootQuery(BaseModel):
    instance_name: str
    bucket: str


class CreateFolderIn(BaseModel):
    instance_name: str
    bucket: str
    parent_id: int
    name: str = Field(..., min_length=1, max_length=512)


class EnsureFolderPathIn(BaseModel):
    # `relative_path` is the folder chain relative to the selected destination
    # folder in the UI, e.g. "StudyA/session1".
    instance_name: str
    bucket: str
    parent_id: int
    relative_path: str = Field(..., max_length=4096)


class UploadInitIn(BaseModel):
    instance_name: str
    bucket: str
    folder_id: int
    filename: str = Field(..., min_length=1, max_length=512)
    content_type: str | None = None


class UploadInitOut(BaseModel):
    file_id: int
    key: str
    url: str


class UploadCompleteIn(BaseModel):
    instance_name: str
    file_id: int


# Request to complete many folder-upload files at once.
# Example: file_ids = [691, 692].
class FolderUploadCompleteIn(BaseModel):
    instance_name: str
    file_ids: list[int] = Field(..., min_length=1)


# One file that could not be completed.
class FolderUploadCompleteFailureOut(BaseModel):
    file_id: int
    detail: str


# Batch complete result.
# Example: completed = 2 and failed = [] means all files completed.
class FolderUploadCompleteOut(BaseModel):
    completed: int
    failed: list[FolderUploadCompleteFailureOut]


# One file inside the selected folder.
# `relative_path` keeps the folder path from the user's computer.
class FolderUploadManifestFileIn(BaseModel):
    relative_path: str = Field(..., min_length=1, max_length=4096)
    content_type: str | None = None
    size: int | None = Field(default=None, ge=0)


# Request body for starting a folder upload check.
# Folder upload is separate from single-file upload because it handles many files.
class FolderUploadInitIn(BaseModel):
    instance_name: str
    bucket: str
    parent_id: int
    on_conflict: Literal["error", "replace"] = "error"
    files: list[FolderUploadManifestFileIn] = Field(..., min_length=1)


class FolderUploadConflictOut(BaseModel):
    relative_path: str
    key: str


class FolderUploadPreparedFileOut(BaseModel):
    file_id: int
    relative_path: str
    key: str
    action: Literal["create", "replace"]
    # One PUT URL for this exact file key.
    # Example: the browser PUTs "StudyA/a.txt" to this URL.
    url: str
    expires_in: int


# Response for the folder upload setup.
# It creates DB metadata and returns one PUT URL per file.
class FolderUploadInitOut(BaseModel):
    total_files: int
    total_bytes: int
    common_prefix: str
    folders_to_create: int
    conflicts: list[FolderUploadConflictOut]
    files: list[FolderUploadPreparedFileOut]


class FolderOut(BaseModel):
    id: int
    name: str
    full_path: str


class FileOut(BaseModel):
    id: int
    name: str
    key: str
    size: int | None
    last_modified: datetime | None
    content_type: str | None


class ListChildrenOut(BaseModel):
    folder_id: int
    folders: list[FolderOut]
    files: list[FileOut]


class UploadCompleteOut(BaseModel):
    status: str


class DownloadUrlOut(BaseModel):
    url: str


class DeleteFileOut(BaseModel):
    deleted: bool
    file_id: int


class DeleteFolderOut(BaseModel):
    deleted: bool
    folder_id: int


class BundleStatusOut(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    status: str
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    result_url: str | None = Field(default=None, alias="resultUrl")

#################################################################################### helper functions
def policy_or_403(policy_manager: CasbinPolicyManager, policy: Policy) -> None:
    """Validate a policy and raise 403 if denied."""
    if not policy_manager.validate_policy(policy):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied by policy")


def allowed_or_403(check: Checker, resource: str, action: str) -> None:
    """Raise 403 unless the user may do `action` on `resource`."""
    if not check.allows(resource, action):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied by policy")


def folder_shown_or_403(check: Checker, resource: str) -> None:
    """Raise 403 unless the user can read the folder or something inside it (browsing only)."""
    if not check.shows_folder(resource, "read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied by policy")


def keys_or_403(
    check: Checker,
    bucket: str,
    keys: list[str],
    action: str,
    labels: dict[str, str] | None = None,
) -> None:
    """Check `action` on every key a bulk operation touches; raise 403 if any is denied.

    A permission on a folder doesn't imply the same permission on every file in it, so
    bulk operations (folder upload, folder delete) must check each key before acting on
    any of them. `labels` maps keys to the names shown in the error (e.g. upload paths).
    """
    _allowed, denied = check.split([resource_for_key(bucket, key) for key in keys], action)
    if denied:
        label_by_resource = {resource_for_key(bucket, key): (labels or {}).get(key, key) for key in keys}
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": f"Access denied by policy for {len(denied)} of {len(keys)} file(s).",
                "denied": [label_by_resource[resource] for resource in denied[:20]],
            },
        )


def get_instance_agent(instance_manager: AbstractInstanceManager, instance_name: str):
    """Resolve an instance UUID and its storage agent by name."""
    instance_uuid = instance_manager.get_instance_uuid(instance_name)
    instance = instance_manager.get_instance_by_uuid(instance_uuid)
    return instance_uuid, instance.agent


def resource_for_folder(bucket: str, full_path: str) -> str:
    """Build a Casbin resource string for a folder (e.g. ``bucket/folder/``)."""
    full_path = normalize_folder_full_path(full_path)
    return f"{bucket}{full_path}"


def resource_for_key(bucket: str, key: str) -> str:
    """Build a Casbin resource string for a file key (e.g. ``bucket/path/file.txt``)."""
    return f"{bucket}/{key}"


def normalize_upload_relative_path(relative_path: str) -> str:
    """Normalize a browser folder-upload relative path and reject traversal."""
    # Clean the browser path and block paths that try to go outside the folder.
    normalized = str(relative_path or "").replace("\\", "/").strip("/")
    segments = [segment for segment in normalized.split("/") if segment]

    if not segments:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Folder upload file relative_path must include a filename",
        )

    if any(segment in {".", ".."} for segment in segments):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid folder upload relative_path: {relative_path!r}",
        )

    return "/".join(segments)


def folder_full_paths_for_relative_file(parent_full_path: str, relative_path: str) -> list[str]:
    """Return folder full paths that would be needed for a relative file path."""
    # Find which folder rows would be needed in Postgres for this file path.
    segments = relative_path.split("/")[:-1]
    folder_full_path = normalize_folder_full_path(parent_full_path)
    full_paths: list[str] = []

    for segment in segments:
        folder_full_path = join_child_full_path(folder_full_path, segment)
        full_paths.append(folder_full_path)

    return full_paths

####################################################################################
########################################  ENDPOINTS ################################
####################################################################################

@router.get("/root", response_model=FolderOut)
async def get_root(
    q: TreeRootQuery = Depends(),
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> FolderOut:
    """Return the root folder for a bucket (creating it if needed)."""
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, _agent = get_instance_agent(instance_manager, q.instance_name)
    folder_shown_or_403(policy_manager.checker(user_uuid, instance_uuid), resource_for_folder(q.bucket, "/"))

    tree_svc = TreeService(session)
    root = await tree_svc.get_root(q.bucket)
    return {"id": root.id, "name": root.name, "full_path": root.full_path}

####################################################################################
@router.get("/{folder_id}", response_model=ListChildrenOut)
async def list_children(
    folder_id: int,
    q: TreeRootQuery = Depends(),
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> ListChildrenOut:
    """List immediate child folders and files of a folder (non-recursive)."""
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, _agent = get_instance_agent(instance_manager, q.instance_name)

    folder = (await session.execute(
        select(Folder).where(Folder.id == folder_id, Folder.bucket == q.bucket)
    )).scalar_one()
    check = policy_manager.checker(user_uuid, instance_uuid)
    folder_shown_or_403(check, resource_for_folder(q.bucket, folder.full_path))

    tree_svc = TreeService(session)
    folders, files = await tree_svc.list_children(q.bucket, folder_id)
    # Only list what the user can see: folders on the way to their files, and their files
    folders = [f for f in folders if check.shows_folder(resource_for_folder(q.bucket, f.full_path), "read")]
    files = [x for x in files if check.allows(resource_for_key(q.bucket, x.key), "read")]

    return {
        "folder_id": folder_id,
        "folders": [{"id": f.id, "name": f.name, "full_path": f.full_path} for f in folders],
        "files": [
            {
                "id": x.id,
                "name": x.name,
                "key": x.key,
                "size": x.size,
                "last_modified": x.last_modified,
                "content_type": x.content_type,
            }
            for x in files
        ],
    }
####################################################################################

@router.post("/folders", response_model=FolderOut)
async def create_folder(
    payload: CreateFolderIn,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> FolderOut:
    """Create a new subfolder under an existing parent folder."""
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, _agent = get_instance_agent(instance_manager, payload.instance_name)

    parent = (await session.execute(
        select(Folder).where(Folder.id == payload.parent_id, Folder.bucket == payload.bucket)
    )).scalar_one()
    policy = Policy(user_uuid=user_uuid, instance_uuid=instance_uuid, resource=resource_for_folder(payload.bucket,
                                                                                                   parent.full_path), action="write")
    policy_or_403(policy_manager, policy)

    tree_svc = TreeService(session)
    folder = await tree_svc.create_folder(payload.bucket, payload.parent_id, payload.name)
    return {"id": folder.id, "name": folder.name, "full_path": folder.full_path}

####################################################################################
@router.post("/folders/ensure-path", response_model=FolderOut)
async def ensure_folder_path(
    payload: EnsureFolderPathIn,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> FolderOut:
    """Ensure a nested folder path exists under a parent (idempotent)."""
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, _agent = get_instance_agent(instance_manager, payload.instance_name)

    # Load the folder selected in the write tree. Folder uploads create nested
    # DB folders underneath this starting parent.
    parent = (await session.execute(
        select(Folder).where(Folder.id == payload.parent_id, Folder.bucket == payload.bucket)
    )).scalar_one()

    # Apply the same write-permission check as normal file uploads: the user
    # must have write access on the selected parent folder before nested
    # folders can be created under it.
    policy = Policy(
        user_uuid=user_uuid,
        instance_uuid=instance_uuid,
        resource=resource_for_folder(payload.bucket, parent.full_path),
        action="write",
    )
    policy_or_403(policy_manager, policy)

    tree_svc = TreeService(session)
    # Example:
    # - selected parent folder: /research/
    # - relative_path: StudyA/session1
    # This ensures /research/StudyA/ and /research/StudyA/session1/ exist in
    # Postgres, then returns the final folder row to the frontend.
    folder = await tree_svc.ensure_folder_path(payload.bucket, payload.parent_id, payload.relative_path)
    return {"id": folder.id, "name": folder.name, "full_path": folder.full_path}

####################################################################################
@router.post("/folders/upload/init", response_model=FolderUploadInitOut)
async def folder_upload_init(
    payload: FolderUploadInitIn,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> FolderUploadInitOut:
    """Create folder/file metadata for a folder upload before bytes are uploaded."""
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, agent = get_instance_agent(instance_manager, payload.instance_name)

    # All uploaded files will go under this selected folder.
    parent = (await session.execute(
        select(Folder).where(Folder.id == payload.parent_id, Folder.bucket == payload.bucket)
    )).scalar_one()

    # Check that the user can write to the selected folder.
    check = policy_manager.checker(user_uuid, instance_uuid)
    allowed_or_403(check, resource_for_folder(payload.bucket, parent.full_path), "write")

    parent_full_path = normalize_folder_full_path(parent.full_path)
    planned_files: list[dict[str, str]] = []
    folder_full_paths: set[str] = set()

    # Build the final object key for each file and collect needed folder paths.
    for file_in in payload.files:
        relative_path = normalize_upload_relative_path(file_in.relative_path)
        # Example: parent "/bc/" + "sub/a.txt" becomes key "bc/sub/a.txt".
        key = build_object_key(parent_full_path, relative_path)
        planned_files.append({"relative_path": relative_path, "key": key})
        folder_full_paths.update(folder_full_paths_for_relative_file(parent_full_path, relative_path))

    # We may add duplicate-key checks later before bulk DB inserts.
    # For now, browser folder selections are assumed to be unique.
    relative_path_by_key = {file["key"]: file["relative_path"] for file in planned_files}
    keys = list(relative_path_by_key.keys())

    # The folder check above doesn't cover every file: check write on each target key,
    # including files this upload would replace, before creating anything.
    keys_or_403(check, payload.bucket, keys, "write", labels=relative_path_by_key)

    # Find existing completed files that this upload would conflict with.
    existing_files = list((await session.execute(
        select(File).where(
            File.bucket == payload.bucket,
            File.key == any_(keys),
            File.status == "complete",
        )
    )).scalars().all())
    existing_file_keys = {file.key for file in existing_files}

    conflicts = [
        FolderUploadConflictOut(
            relative_path=relative_path_by_key[key],
            key=key,
        )
        for key in sorted(existing_file_keys)
    ]

    if conflicts and payload.on_conflict == "error":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Folder upload has file conflicts.",
                "conflicts": [conflict.model_dump() for conflict in conflicts],
            },
        )

    common_prefix = parent_full_path.lstrip("/")
    existing_folder_paths: set[str] = set()
    if folder_full_paths:
        # Count missing folder rows before creating them.
        existing_folder_paths = set((await session.execute(
            select(Folder.full_path).where(
                Folder.bucket == payload.bucket,
                Folder.full_path == any_(list(folder_full_paths)),
            )
        )).scalars().all())
    folders_to_create = len(folder_full_paths - existing_folder_paths)

    tree_svc = TreeService(session)
    file_svc = FileService(session)
    prepared_files: list[FolderUploadPreparedFileOut] = []

    for file_in, planned_file in zip(payload.files, planned_files):
        relative_path = planned_file["relative_path"]
        key = planned_file["key"]
        relative_segments = relative_path.split("/")
        filename = relative_segments[-1]
        relative_parent_path = "/".join(relative_segments[:-1])

        # Create the folder rows needed for this file, then put the file row there.
        # Example: "sub/a.txt" creates/finds folder "sub", then adds "a.txt".
        target_folder = await tree_svc.ensure_folder_path(
            payload.bucket,
            payload.parent_id,
            relative_parent_path,
        )
        action = "replace" if key in existing_file_keys else "create"
        file = await file_svc.create_or_replace_file_row(
            payload.bucket,
            target_folder.id,
            filename,
            key,
            file_in.content_type,
            replace=action == "replace",
        )
        # The URL is signed locally by boto3. This does not call S3 once per
        # file; it only builds a URL that lets the browser PUT this exact key.
        urls, _paths = agent.generate_access_link(
            resource_for_key(payload.bucket, key),
            "write",
            FOLDER_UPLOAD_PUT_EXPIRATION_SECONDS,
        )
        prepared_files.append(FolderUploadPreparedFileOut(
            file_id=file.id,
            relative_path=relative_path,
            key=key,
            action=action,
            url=urls[0],
            expires_in=FOLDER_UPLOAD_PUT_EXPIRATION_SECONDS,
        ))

    logger.info(
        "Folder upload init prepared %s file(s) under %s/%s",
        len(prepared_files),
        payload.bucket,
        common_prefix,
    )

    return FolderUploadInitOut(
        total_files=len(planned_files),
        total_bytes=sum(file_in.size or 0 for file_in in payload.files),
        common_prefix=common_prefix,
        folders_to_create=folders_to_create,
        conflicts=conflicts,
        files=prepared_files,
    )

####################################################################################
@router.post("/folders/upload/complete", response_model=FolderUploadCompleteOut)
async def folder_upload_complete(
    payload: FolderUploadCompleteIn,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> FolderUploadCompleteOut:
    """Complete many folder-upload files after the browser uploads the bytes."""
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, agent = get_instance_agent(instance_manager, payload.instance_name)

    file_svc = FileService(session)
    # Storage events can mark files complete before this endpoint runs, so this
    # endpoint is intentionally idempotent for already-complete file ids.
    files = await file_svc.get_files_for_upload_completion(payload.file_ids)
    file_by_id = {file.id: file for file in files}
    failed: list[FolderUploadCompleteFailureOut] = []
    completed = 0
    already_complete_file_ids: list[int] = []
    skip_head_file_ids: list[int] = []
    head_updates: list[dict] = []

    check = policy_manager.checker(user_uuid, instance_uuid)
    for file_id in payload.file_ids:
        file = file_by_id.get(file_id)
        if not file:
            # Example: bad id, deleted row, or id from another upload.
            failed.append(FolderUploadCompleteFailureOut(
                file_id=file_id,
                detail="File not found",
            ))
            continue

        try:
            # Make sure the user can still write this file key.
            allowed_or_403(check, resource_for_key(file.bucket, file.key), "write")
            if file.status == "complete":
                already_complete_file_ids.append(file.id)
            elif FOLDER_UPLOAD_SKIP_HEAD_CHECK:
                # Trust the browser PUT result and batch-complete these rows later.
                skip_head_file_ids.append(file.id)
            else:
                # Check object storage to confirm the browser uploaded the file.
                head = agent.get_object_metadata(resource_for_key(file.bucket, file.key))
                head_updates.append({
                    "id": file.id,
                    "size": head.get("ContentLength", file.size),
                    "etag": head.get("ETag", file.etag),
                    "last_modified": head.get("LastModified", file.last_modified),
                    "content_type": head.get("ContentType", file.content_type),
                    "status": "complete",
                })
        except HTTPException as e:
            logger.warning(f"Folder upload complete failed: {e.detail}")
            failed.append(FolderUploadCompleteFailureOut(
                file_id=file_id,
                detail=str(e.detail),
            ))
        except Exception as exc:
            logger.warning("Folder upload complete failed: %s", exc)
            failed.append(FolderUploadCompleteFailureOut(
                file_id=file_id,
                detail="Unable to verify uploaded object",
            ))

    if skip_head_file_ids:
        await file_svc.mark_files_complete_without_head(skip_head_file_ids)
    if head_updates:
        await file_svc.update_many_from_head(head_updates)

    completed = await file_svc.count_completed_files(payload.file_ids)

    if failed:
        # Log one summary instead of one line per file. Large folder uploads can
        # have thousands of files, so per-file logs are hard to read.
        logger.warning(
            "Folder upload complete had %s failed file(s) out of %s. First failed ids: %s",
            len(failed),
            len(payload.file_ids),
            [item.file_id for item in failed[:10]],
        )

    if completed:
        tree_svc = TreeService(session)
        completed_folders_by_bucket: dict[str, set[int]] = {}
        already_complete_file_id_set = set(already_complete_file_ids)
        skip_head_file_id_set = set(skip_head_file_ids)
        head_update_file_id_set = {update_item["id"] for update_item in head_updates}
        for file in files:
            if file.id in already_complete_file_id_set:
                completed_folders_by_bucket.setdefault(file.bucket, set()).add(file.folder_id)
            elif FOLDER_UPLOAD_SKIP_HEAD_CHECK:
                if file.id in skip_head_file_id_set:
                    completed_folders_by_bucket.setdefault(file.bucket, set()).add(file.folder_id)
            elif file.id in head_update_file_id_set:
                completed_folders_by_bucket.setdefault(file.bucket, set()).add(file.folder_id)

        # Mark parent folders complete so they show up in the frontend tree.
        for bucket, folder_ids in completed_folders_by_bucket.items():
            for folder_id in folder_ids:
                await tree_svc.mark_folder_ancestors_complete(bucket, folder_id)

    logger.info(
        "Folder upload complete finished: completed=%s failed=%s",
        completed,
        len(failed),
    )

    return FolderUploadCompleteOut(completed=completed, failed=failed)

#################################################################################### initialize upload.It creates the DB record and returns a presigned URL so the client can start uploading the file bytes
@router.post("/files/upload/init", response_model=UploadInitOut)
async def upload_init(
    payload: UploadInitIn,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> UploadInitOut:
    """Initiate a file upload — create a pending DB row and return a presigned upload URL."""
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, agent = get_instance_agent(instance_manager, payload.instance_name)

    tree_svc = TreeService(session)
    folder, key = await tree_svc.build_key(payload.bucket, payload.folder_id, payload.filename)

    policy = Policy(user_uuid=user_uuid, instance_uuid=instance_uuid, resource=resource_for_key(payload.bucket, key), action="write")
    policy_or_403(policy_manager, policy)

    file_svc = FileService(session)
    try:
        file = await file_svc.create_file_row(payload.bucket, folder.id, payload.filename, key, payload.content_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"File '{payload.filename}' already exists in folder",
        )

    urls, _paths = agent.generate_access_link(resource_for_key(payload.bucket, key), "write", 900)
    return UploadInitOut(file_id=file.id, key=key, url=urls[0])

#################################################################################### it verifies the upload succeeded and syncs metadata into the DB.

@router.post("/files/upload/complete", response_model=UploadCompleteOut)
async def upload_complete(
    payload: UploadCompleteIn,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> UploadCompleteOut:
    """Complete an upload — verify the S3 object exists, sync metadata, and mark ancestors complete."""
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, agent = get_instance_agent(instance_manager, payload.instance_name)

    file_svc = FileService(session)
    file = await file_svc.get_file(payload.file_id, include_pending=True)
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    policy = Policy(user_uuid=user_uuid, instance_uuid=instance_uuid, resource=resource_for_key(file.bucket,
                                                                                                file.key), action="write")
    policy_or_403(policy_manager, policy)

    head = agent.get_object_metadata(resource_for_key(file.bucket, file.key))
    await file_svc.update_from_head(file, head)
    # Mark ancestor folders status from pending to complete because upload finished
    tree_svc = TreeService(session)
    await tree_svc.mark_folder_ancestors_complete(file.bucket, file.folder_id)
    return {"status": "ok"}

#################################################################################### Generate a presigned download URL for a file

@router.get("/files/{file_id}/download-url", response_model=DownloadUrlOut)
async def download_url(
    file_id: int,
    instance_name: str,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> DownloadUrlOut:
    """Generate a presigned download URL for a file."""
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, agent = get_instance_agent(instance_manager, instance_name)

    file_svc = FileService(session)
    file = await file_svc.get_file(file_id)
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    policy = Policy(user_uuid=user_uuid, instance_uuid=instance_uuid, resource=resource_for_key(file.bucket, file.key), action="read")
    policy_or_403(policy_manager, policy)

    urls, _paths = agent.generate_access_link(resource_for_key(file.bucket, file.key), "read", 900)
    return {"url": urls[0]}

#################################################################################### It deletes the object from S3 and then deletes the DB row

@router.delete("/files/{file_id}", response_model=DeleteFileOut)
async def delete_file(
    file_id: int,
    instance_name: str,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> DeleteFileOut:
    """Delete a file from S3 and its DB row."""
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, agent = get_instance_agent(instance_manager, instance_name)
    file_svc = FileService(session)
    file = await file_svc.get_file(file_id)
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    policy = Policy(user_uuid=user_uuid, instance_uuid=instance_uuid, resource=resource_for_key(file.bucket, file.key), action="delete")
    policy_or_403(policy_manager, policy)

    agent.delete_object(resource_for_key(file.bucket, file.key))

    await file_svc.delete_file_row(file)
    return {"deleted": True, "file_id": file_id}

#################################################################################### deletes the tree from S3 and then deletes the DB row
def list_keys_under_prefix(s3, bucket: str, prefix: str) -> list[str]:
    """Return all object keys in a bucket that start with prefix (paginated)."""

    keys = []
    token = None # S3 pagination token that is used for continuation of keys after 1000 max
    while True:
        # S3 returns at most 1000 keys per request. so we run the loop to get everything for delete (remember we only do this delete as we do it by backend)

        kwargs = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        # Collect object keys from this page.
        for obj in resp.get("Contents", []) or []:
            keys.append(obj["Key"])
            # Continue until all pages are consumed.
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return keys

@router.delete("/folders/{folder_id}", response_model=DeleteFolderOut)
async def delete_folder(
    folder_id: int,
    instance_name: str,
    bucket: str,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> DeleteFolderOut:
    """Delete a folder subtree — remove all S3 objects under the prefix, then delete DB rows."""
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, agent = get_instance_agent(instance_manager, instance_name)

    folder = (await session.execute(
        select(Folder).where(Folder.id == folder_id, Folder.bucket == bucket)
    )).scalar_one()
    if folder.full_path == "/":
        raise HTTPException(status_code=400, detail="Refusing to delete root folder")

    check = policy_manager.checker(user_uuid, instance_uuid)
    allowed_or_403(check, resource_for_folder(bucket, folder.full_path), "delete")

    if not hasattr(agent, "s3_client"):
        raise HTTPException(status_code=501, detail="Storage agent does not expose s3_client")

    prefix = normalize_folder_full_path(folder.full_path).lstrip("/")
    # TODO: Move prefix listing behind the storage agent abstraction.
    keys = list_keys_under_prefix(agent.s3_client, bucket, prefix)

    # The folder check above doesn't cover every file: check delete on each key, and
    # refuse the whole delete if any is denied, before removing anything.
    keys_or_403(check, bucket, keys, "delete")

    if keys:
        agent.delete_objects([resource_for_key(bucket, key) for key in keys])

    tree_svc = TreeService(session)
    await tree_svc.delete_folder_subtree(bucket, folder_id)
    return {"deleted": True, "folder_id": folder_id}

# --------------- Bundler Endpoints ---------------

def get_bundler_provider() -> str:
    provider = BUNDLER_PROVIDER
    if provider not in {"python", "java"}:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unsupported BUNDLER_PROVIDER '{provider}'. Use 'python' or 'java'."
        )
    return provider


def get_bundler_url(provider: str) -> str:
    if provider == "python":
        return PYTHON_BUNDLER_URL
    if provider == "java":
        return JAVA_BUNDLER_URL
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Unsupported bundler provider '{provider}'."
    )


@router.post(
    "/bundle/zip",
    response_model=BundleCreateResponse,
    summary="Create an asset zip bundle",
    description="Generates a zip archive of requested files using the bundler service."
)
async def create_asset_bundle(
    request: BundleCreateRequest,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager)
):
    """
    Create a zip bundle of requested assets.
    
    Takes a list of file IDs, verifies read access for each, 
    generates presigned URLs, and sends to the bundler to process.
    
    Args:
        request: The bundle request containing instance_name, folder_name, and file_ids
        user: Current authenticated user
        session: Async database session dependency
        user_manager: User manager dependency
        policy_manager: Policy manager dependency
        instance_manager: Instance manager dependency
        
    Returns:
        BundleCreateResponse: Response containing bundle_id, status and folder_name
    """
    logger.info(
        f"Asset bundle request from user '{user['preferred_username']}' on instance "
        f"'{request.instance_name}' with {len(request.file_ids)} file_ids and "
        f"{len(request.folder_ids)} folder_ids."
    )
    
    if not request.file_ids and not request.folder_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided for downloading.")

    user_uuid = user_manager.get_user_uuid(user['preferred_username'])
    instance_uuid, agent = get_instance_agent(instance_manager, request.instance_name)

    file_svc = FileService(session)
    all_presigned_urls = []
    java_bundle_files = []
    files_to_bundle = {}

    # Set of file IDs that were explicitly requested and successfully found as completed file rows
    explicit_file_ids = set()

    # Retrieve the file objects from DB based on file ids
    requested_file_ids = list(dict.fromkeys(request.file_ids))
    files = await file_svc.get_files(requested_file_ids) if requested_file_ids else []
    file_map = {f.id: f for f in files}

    for file_id in requested_file_ids:
        file = file_map.get(file_id)
        if not file:
            logger.warning(f"File ID {file_id} not found in DB.")
            continue
        files_to_bundle.setdefault(file.id, file)
        explicit_file_ids.add(file.id)

    folder_ids = list(dict.fromkeys(request.folder_ids))
    if folder_ids:
        try:
            allowed_buckets = set(agent.fetch_all_buckets()) if hasattr(agent, "fetch_all_buckets") else set()
        except Exception as e:
            logger.error(f"Failed to fetch allowed buckets: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Unable to retrieve bucket information from storage. Please try again later.")
        
        # Get requested folders from db
        folders = list((await session.execute(
            select(Folder)
            .where(
                Folder.id == any_(folder_ids),
                Folder.bucket.in_(allowed_buckets),
                Folder.status == "complete",
            )
        )).scalars().all())

        # Get the files of each folder
        for folder in folders:
            folder_files = list((await session.execute(
                select(File)
                .join(Folder, File.folder_id == Folder.id)
                .where(
                    Folder.bucket == folder.bucket,
                    Folder.path.op("<@")(folder.path),
                    Folder.status == "complete",
                    File.status == "complete",
                )
                .order_by(File.folder_id, File.name)
            )).scalars().all())

            for file in folder_files:
                files_to_bundle.setdefault(file.id, file)

    # Get presigned urls for each file the user may read. Files from a selected folder that
    # the user can't read are skipped; an explicitly selected one refuses the request.
    check = policy_manager.checker(user_uuid, instance_uuid)
    for file in files_to_bundle.values():
        if not check.allows(resource_for_key(file.bucket, file.key), "read"):
            if file.id in explicit_file_ids:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied by policy")
            continue

        try:
            urls, _paths = agent.generate_access_link(
                resource_for_key(file.bucket, file.key),
                "read",
                BUNDLE_SOURCE_URL_EXPIRATION_SECONDS,
            )
            url = urls[0]
            all_presigned_urls.append(url)
            java_bundle_files.append({
                "url": url,
                "relativePath": f"{file.bucket}/{file.key}",
            })
        except Exception as e:
            logger.error(f"Unable to generate presigned URL for file_id {file.id}: {str(e)}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Unable to generate presigned URL for file_id {file.id}: {str(e)}")

    if not all_presigned_urls:
         logger.warning("No files found to bundle from the requested resources")
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No files found to bundle.")

    # If only one file is requested, return its presigned URL directly.
    if len(all_presigned_urls) == 1:
        return BundleCreateResponse(
            bundle_id="single-file",
            status="completed",
            folder_name=request.folder_name or "",
            single_file_url=all_presigned_urls[0]
        )

    # The bundler stores a copy of the archive in object storage, which data held on POSIX
    # machines must not have. Multi-file POSIX downloads wait for the streaming download path.
    if agent.FLAVOUR == "posix":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Downloading several files at once isn't available for POSIX storage yet. Please download files one at a time.",
        )

    # POST to Bundler service's create archive endpoint
    # Top level archive structure is bucket_{uuid}/{folder_name}/
    # Empty string removes the folder_name level
    folder_name = request.folder_name or ""
    provider = get_bundler_provider()
    bundler_url = get_bundler_url(provider)
    
    if provider == "java":
        init_payload = {
            "folderName": folder_name,
            "files": java_bundle_files,
            "compression": "zip"
        }
    else:
        init_payload = {
            "urls": all_presigned_urls,
            "folderName": folder_name
        }
    
    try:
        init_res = await bundler_client.post(f"{bundler_url}/bundles", json=init_payload, timeout=10.0)
    except httpx.RequestError as e:
        logger.error(f"Request error while communicating with Bundler: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Something went wrong while preparing your download. Please try again.")

    if init_res.status_code != 202:
        logger.error(f"Bundler service returned status {init_res.status_code} during initiation: {init_res.text}")
        if init_res.status_code in KNOWN_BUNDLER_ERROR_STATUSES:
            detail = init_res.json().get("detail", "We couldn't prepare your files for download.")
            raise HTTPException(status_code=init_res.status_code, detail=detail)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="We couldn't prepare your files for download. Please try again.")

    bundle_data = init_res.json()
    bundle_id = bundle_data.get("id")
    if not bundle_id:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Something went wrong while preparing your download. Please try again.")

    # Send bundle id and status back to client
    return BundleCreateResponse(bundle_id=bundle_id, status="processing", folder_name=folder_name)


@router.get(
    "/bundle/{bundle_id}/status",
    response_model=BundleStatusOut,
    response_model_exclude_unset=True,
    summary="Check status of an asset bundle",
    description="Check the processing status of a previously requested bundle."
)
async def get_bundle_status(
    bundle_id: str,
    user: dict = Depends(decode_token)
) -> BundleStatusOut:
    """
    Check the processing status of a previously requested bundle.
    
    Args:
        bundle_id: The ID of the bundle to check.
        user: Current authenticated user.
        
    Returns:
        dict: The current status of the bundle.
    """
    try:
        bundler_url = get_bundler_url(get_bundler_provider())
        poll_res = await bundler_client.get(f"{bundler_url}/bundles/{bundle_id}", timeout=5.0)
    except httpx.RequestError as e:
        logger.error(f"Bundler status check failed for bundle {bundle_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="We couldn't check whether the ZIP archive is ready. Please try again.",
        )
        
    if poll_res.status_code == 202:
        return poll_res.json()
    elif poll_res.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This download is no longer available.")
    else:
        logger.error(f"Bundler status check returned status {poll_res.status_code}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="We couldn't check whether the ZIP archive is ready. Please try again.",
        )

@router.get(
    "/bundle/{bundle_id}/download",
    response_model=BundleDownloadUrlResponse,
    summary="Get asset zip bundle object-storage URL",
    description="Returns a presigned object-storage URL for the completed zip archive."
)
async def get_bundle_download_url(
    bundle_id: str,
    user: dict = Depends(decode_token)
):
    # Bundles are downloaded from object storage; this endpoint returns a presigned URL, not ZIP bytes.
    try:
        bundler_url = get_bundler_url(get_bundler_provider())
        url_res = await bundler_client.get(f"{bundler_url}/bundles/{bundle_id}/download", timeout=5.0)
    except httpx.RequestError as e:
        logger.error(f"Bundler download URL request failed for bundle {bundle_id}: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="We couldn't create a secure download link for this ZIP archive. Please try again.")

    if url_res.status_code == 200:
        result_url = url_res.json().get("resultUrl")
        if not result_url:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="We couldn't create a secure download link for this ZIP archive. Please try again.")
        return BundleDownloadUrlResponse(bundle_id=bundle_id, result_url=result_url)
    if url_res.status_code == 202:
        raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail="The ZIP archive is still being prepared.")
    if url_res.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This ZIP archive is not available.")

    logger.error(f"Bundler download URL request returned status {url_res.status_code}")
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="We couldn't create a secure download link for this ZIP archive. Please try again.")

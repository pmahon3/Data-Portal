
from core.model.file import File

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# INN dependencies
from api.v0_1.endpoints.service.auth import decode_token
from core.injection.managers import get_instance_manager, get_policy_manager, get_user_manager
from core.management.instances import AbstractInstanceManager
from core.management.policies import AbstractPolicyManager, Policy
from core.management.users import AbstractUserManager

# DB models
from core.db.session import get_session
from core.model.folder import Folder
from core.util.paths import normalize_folder_full_path
from core.service.tree_service import TreeService
from core.service.file_service import FileService


router = APIRouter(prefix="/tree", tags=["Tree"])

#################################################################################### Pydantic models
class TreeRootQuery(BaseModel):
    instance_name: str
    bucket: str


class CreateFolderIn(BaseModel):
    instance_name: str
    bucket: str
    parent_id: int
    name: str = Field(..., min_length=1, max_length=512)


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

#################################################################################### helper functions
def policy_or_403(policy_manager: AbstractPolicyManager, policy: Policy) -> None:
    if not policy_manager.validate_policy(policy):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied by policy")


def get_instance_agent(instance_manager: AbstractInstanceManager, instance_name: str):
    instance_uuid = instance_manager.get_instance_uuid(instance_name)
    instance = instance_manager.get_instance_by_uuid(instance_uuid)
    return instance_uuid, instance.agent


def resource_for_folder(bucket: str, full_path: str) -> str:
    full_path = normalize_folder_full_path(full_path)
    return f"{bucket}{full_path}"


def resource_for_key(bucket: str, key: str) -> str:
    return f"{bucket}/{key}"

####################################################################################
########################################  ENDPOINTS ################################
####################################################################################

# Resolve user + instance and enforce policy
# Fetch root folder from DB
@router.get("/root")
async def get_root(
    q: TreeRootQuery = Depends(),
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
):
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, _agent = get_instance_agent(instance_manager, q.instance_name)
    policy = Policy(user_uuid=user_uuid, instance_uuid=instance_uuid, resource=resource_for_folder(q.bucket, "/"), action="read")
    policy_or_403(policy_manager, policy)

    tree_svc = TreeService(session)
    root = await tree_svc.get_root(q.bucket)
    return {"id": root.id, "name": root.name, "full_path": root.full_path}

####################################################################################
@router.get("/{folder_id}")
async def list_children(
    folder_id: int,
    q: TreeRootQuery = Depends(),
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
):
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, _agent = get_instance_agent(instance_manager, q.instance_name)

    folder = (await session.execute(
        select(Folder).where(Folder.id == folder_id, Folder.bucket == q.bucket)
    )).scalar_one()
    policy = Policy(user_uuid=user_uuid, instance_uuid=instance_uuid, resource=resource_for_folder(q.bucket,
                                                                                                   folder.full_path), action="read")
    policy_or_403(policy_manager, policy)

    tree_svc = TreeService(session)
    folders, files = await tree_svc.list_children(q.bucket, folder_id)

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

@router.post("/folders")
async def create_folder(
    payload: CreateFolderIn,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
):
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

#################################################################################### initialize upload.It creates the DB record and returns a presigned URL so the client can start uploading the file bytes
@router.post("/files/upload/init", response_model=UploadInitOut)
async def upload_init(
    payload: UploadInitIn,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> UploadInitOut:
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

@router.post("/files/upload/complete")
async def upload_complete(
    payload: UploadCompleteIn,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
):
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, agent = get_instance_agent(instance_manager, payload.instance_name)

    file_svc = FileService(session)
    file = await file_svc.get_file(payload.file_id)
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    policy = Policy(user_uuid=user_uuid, instance_uuid=instance_uuid, resource=resource_for_key(file.bucket,
                                                                                                file.key), action="write")
    policy_or_403(policy_manager, policy)

    if not hasattr(agent, "s3_client"):
        raise HTTPException(status_code=501, detail="Storage agent does not expose s3_client")

    head = agent.s3_client.head_object(Bucket=file.bucket, Key=file.key)
    await file_svc.update_from_head(file, head)
    return {"status": "ok"}

#################################################################################### Generate a presigned download URL for a file

@router.get("/files/{file_id}/download-url")
async def download_url(
    file_id: int,
    instance_name: str,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
):
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, agent = get_instance_agent(instance_manager, instance_name)

    file_svc = FileService(session)
    file = await file_svc.get_file(file_id)
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    policy = Policy(user_uuid=user_uuid, instance_uuid=instance_uuid, resource=resource_for_key(file.bucket, file.key), action="read")
    policy_or_403(policy_manager, policy)

    if not hasattr(agent, "s3_client"):
        raise HTTPException(status_code=501, detail="Storage agent does not expose s3_client")

    url = agent.s3_client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": file.bucket, "Key": file.key},
        ExpiresIn=900,
    )
    return {"url": url}

#################################################################################### It deletes the object from S3 and then deletes the DB row

@router.delete("/files/{file_id}")
async def delete_file(
    file_id: int,
    instance_name: str,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
):
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, agent = get_instance_agent(instance_manager, instance_name)
    file_svc = FileService(session)
    file = (await session.execute(
        select(File).where(File.id == file_id)
    )).scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    policy = Policy(user_uuid=user_uuid, instance_uuid=instance_uuid, resource=resource_for_key(file.bucket, file.key), action="delete")
    policy_or_403(policy_manager, policy)

    if not hasattr(agent, "s3_client"):
        raise HTTPException(status_code=501, detail="Storage agent does not expose s3_client")
    agent.s3_client.delete_object(Bucket=file.bucket, Key=file.key)

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

@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: int,
    instance_name: str,
    bucket: str,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
):
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, agent = get_instance_agent(instance_manager, instance_name)

    folder = (await session.execute(
        select(Folder).where(Folder.id == folder_id, Folder.bucket == bucket)
    )).scalar_one()
    if folder.full_path == "/":
        raise HTTPException(status_code=400, detail="Refusing to delete root folder")

    policy = Policy(user_uuid=user_uuid, instance_uuid=instance_uuid, resource=resource_for_folder(bucket,
                                                                                                   folder.full_path), action="delete")
    policy_or_403(policy_manager, policy)

    if not hasattr(agent, "s3_client"):
        raise HTTPException(status_code=501, detail="Storage agent does not expose s3_client")

    prefix = normalize_folder_full_path(folder.full_path).lstrip("/")
    keys = list_keys_under_prefix(agent.s3_client, bucket, prefix)
    if keys:
        agent.s3_client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": k} for k in keys], "Quiet": True},
        )

    tree_svc = TreeService(session)
    await tree_svc.delete_folder_subtree(bucket, folder_id)
    return {"deleted": True, "folder_id": folder_id}



######################################################################################################################
##### to downlaod a folder, instead of returning all presigned urls, we can also create an archive in the object storage
##### and create a presigned url for it and return it#####
##### problems with this: it creates an archive locally  which is not efficient at all.
##### tempfile.TemporaryDirectory() creates a folder in the system temp location (e.g., /tmp on Linux/macOS). It's
##### automatically deleted when the with block ends. However, this is not a good choice for large files.
######################################################################################################################
from typing import Iterable
import tempfile
import zipfile
from pathlib import Path

@router.post("/folders/{folder_id}/archive")
async def create_folder_archive(
    folder_id: int,
    instance_name: str,
    bucket: str,
    user: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
):
    """
    Create a ZIP archive in S3 for a folder subtree and return a presigned URL.
    """
    user_uuid = user_manager.get_user_uuid(user["preferred_username"])
    instance_uuid, agent = get_instance_agent(instance_manager, instance_name)

    folder = (await session.execute(
        select(Folder).where(Folder.id == folder_id, Folder.bucket == bucket)
    )).scalar_one()
    if folder.full_path == "/":
        raise HTTPException(status_code=400, detail="Refusing to archive root folder")

    policy = Policy(
        user_uuid=user_uuid,
        instance_uuid=instance_uuid,
        resource=resource_for_folder(bucket, folder.full_path),
        action="read"
    )
    policy_or_403(policy_manager, policy)

    if not hasattr(agent, "s3_client"):
        raise HTTPException(status_code=501, detail="Storage agent does not expose s3_client")

    files_q = (
        select(File, Folder.full_path)
        .join(Folder, Folder.id == File.folder_id)
        .where(
            File.bucket == bucket,
            Folder.bucket == bucket,
            Folder.path.op("<@")(folder.path),
        )
        .order_by(Folder.full_path, File.name)
    )
    rows = list((await session.execute(files_q)).all())

    root_full = normalize_folder_full_path(folder.full_path)
    top_folder_name = folder.name.strip("/") or "folder"

    # Build ZIP locally, then upload to S3
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_zip = Path(tmpdir) / f"{top_folder_name}.zip"

        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file, folder_full_path in rows:
                folder_full_path = normalize_folder_full_path(folder_full_path)
                if root_full == "/":
                    rel_prefix = folder_full_path.lstrip("/")
                else:
                    rel_prefix = folder_full_path.replace(root_full, "", 1)
                inner_path = f"{rel_prefix}{file.name}" if rel_prefix else file.name
                arcname = f"{top_folder_name}/{inner_path}"

                # download object to temp file and add to zip
                obj = agent.s3_client.get_object(Bucket=bucket, Key=file.key)
                data = obj["Body"].read()
                zf.writestr(arcname, data)

        # Upload ZIP to S3
        archive_key = f"archives/{top_folder_name}-{folder_id}.zip"
        agent.s3_client.upload_file(str(tmp_zip), bucket, archive_key)

    url = agent.s3_client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": bucket, "Key": archive_key},
        ExpiresIn=900,
    )
    return {"archive_key": archive_key, "url": url}

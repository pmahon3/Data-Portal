from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v0_1.endpoints.auth import decode_token
from api.v0_1.common.models import FileTreeNode
from core.db.postgres.session import get_session
from core.services.injectors import get_instance_manager, get_policy_manager, get_user_manager
from core.services.instances import AbstractInstanceManager
from core.services.policies import CasbinPolicyManager
from core.services.policies import Policy
from core.services.users import AbstractUserManager
from core.services.filetree.models.file import File
from core.services.filetree.models.folder import Folder
from core.utils.paths import normalize_folder_full_path

router = APIRouter(prefix="/tree", tags=["Tree-DB"])


def resource_for_folder(bucket: str, full_path: str) -> str:
    full_path = normalize_folder_full_path(full_path)
    return f"{bucket}{full_path}"


def resource_for_key(bucket: str, key: str) -> str:
    return f"{bucket}/{key}"


@router.get("/dashboard/{instance_uuid}")
async def dashboard_db(
    instance_uuid: str,
    access: Literal["read", "write", "delete"] | None = Query(None, description="Only return one access tree"),
    token_payload: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
):
    """
    DB-backed tree, same shape as /assets/dashboard/{instance_uuid}.
    Returns { assets: {instance_uuid: {read|write|delete: [FileTreeNode...]}} }
    """
    # Resolve Identity and Context
    user_uuid = user_manager.get_user_uuid(token_payload["preferred_username"])
    instance = instance_manager.get_instance_by_uuid(UUID(instance_uuid))
    instance_name = instance.name
    agent = instance.agent

    # Identify buckets associated with the instance agent
    allowed_buckets = set(agent.fetch_all_buckets()) if hasattr(agent, "fetch_all_buckets") else set()

    # Initialize response structure grouped by permission type
    access_types = [access] if access else ["read", "write", "delete"]
    assets: dict[str, dict[str, list[FileTreeNode]]] = {
        instance_uuid: {access: [] for access in access_types}
    }

    # Query root folders for all applicable buckets
    roots = list((await session.execute(
        select(Folder).where(
            Folder.full_path == "/",
            Folder.bucket.in_(allowed_buckets),
        )
    )).scalars().all())

    # Process each root and its assets
    for root in roots:
        root_res = resource_for_folder(root.bucket, root.full_path)
        
        # Determine user's base permissions for this root/bucket
        root_allowed_access = policy_manager.get_allowed_actions(user_uuid, UUID(instance_uuid), root_res, access_types)
        
        # Skip processing if user has no access to the root
        if not root_allowed_access:
            continue

        # Keep track of which folders are allowed
        # Starts with just the root folders and grows
        allowed_folder_ids = {access: {str(root.id)} for access in root_allowed_access}

        # Add root nodes to the result set
        for access in root_allowed_access:
            assets[instance_uuid][access].append(FileTreeNode(
                id=str(root.id),
                parent="#",
                text=root.bucket,
                li_attr={"type": "folder", "bucket": root.bucket},
            ))

        # Fetch all sub-folders in this bucket
        # Ordered by folder path
        folders = list((await session.execute(
            select(Folder).where(
                Folder.bucket == root.bucket,
                Folder.path.op("<@")(root.path),
            ).order_by(Folder.full_path)
        )).scalars().all())

        # Fetch all files within these folders
        # Ordered by file path
        files = list((await session.execute(
            select(File, Folder.full_path)
            .join(Folder, Folder.id == File.folder_id)
            .where(
                File.bucket == root.bucket,
                Folder.bucket == root.bucket,
                Folder.path.op("<@")(root.path),
            )
            .order_by(Folder.full_path, File.name)
        )).all())

        # Filter folders
        for f in folders:
            if f.full_path == "/":
                continue
            parent_id = str(f.parent_id) if f.parent_id else str(root.id)
            
            # Identify which permission types (read, write, delete) are candidates for this folder.
            valid_accesses = []
            for access in root_allowed_access:
                # RECURSIVE CHECK: A folder can only be "valid" for an action if its 
                # parent folder is already in the 'allowed_folder_ids' for that specific action.
                if parent_id in allowed_folder_ids[access]:
                    valid_accesses.append(access)

            # If the parent folder doesn't have any of the 
            # required permissions, we don't bother checking the Policy
            if not valid_accesses:
                continue

            res = resource_for_folder(f.bucket, f.full_path)
            allowed_actions_for_folder = policy_manager.get_allowed_actions(user_uuid, UUID(instance_uuid), res, valid_accesses)
            
            for access in allowed_actions_for_folder:
                # Add this folder to list of allowed folders
                allowed_folder_ids[access].add(str(f.id))

                # Add this folder to results
                assets[instance_uuid][access].append(FileTreeNode(
                    id=str(f.id),
                    parent=parent_id,
                    text=f.name,
                    li_attr={"type": "folder", "bucket": f.bucket, "full_path": f.full_path},
                ))

        # Filter Files
        for file, _folder_full_path in files:
            folder_id_str = str(file.folder_id)
            
            # Identify which permission types (read, write, delete) are candidates for this file.
            valid_accesses = []
            for access in root_allowed_access:
                # LEAF NODE CHECK: A file is only eligible for an action (e.g., 'read')
                # if the folder containing it is already authorized for that action.
                if folder_id_str in allowed_folder_ids[access]:
                    valid_accesses.append(access)

            # If the parent folder doesn't have any of the 
            # required permissions, we don't bother checking the policy
            if not valid_accesses:
                continue

            res = resource_for_key(file.bucket, file.key)
            allowed_actions_for_file = policy_manager.get_allowed_actions(user_uuid, UUID(instance_uuid), res, valid_accesses)
            
            for access in allowed_actions_for_file:
                # Add this file to results
                assets[instance_uuid][access].append(FileTreeNode(
                    id=f"file-{file.id}",
                    parent=folder_id_str,
                    text=file.name,
                    li_attr={"type": "file", "bucket": file.bucket, "key": file.key},
                ))
                    
    # Return combined asset tree and instance mapping
    return {"assets": assets, "instances": {instance_name: instance_uuid}}

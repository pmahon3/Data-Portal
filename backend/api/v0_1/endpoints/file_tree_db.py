from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import ORJSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v0_1.endpoints.auth import decode_token
from api.v0_1.common.auth_dependencies import authenticated_user_uuid
from core.db.postgres.session import get_session
from core.services.injectors import get_instance_manager, get_policy_manager
from core.services.instances import AbstractInstanceManager
from core.services.policies import CasbinPolicyManager
from core.services.policies import Policy
from core.services.filetree.models.file import File
from core.services.filetree.models.folder import Folder
from core.utils.paths import normalize_folder_full_path

logger = logging.getLogger("api.endpoints")

router = APIRouter(prefix="/tree", tags=["Tree-DB"])


def resource_for_folder(bucket: str, full_path: str) -> str:
    full_path = normalize_folder_full_path(full_path)
    return f"{bucket}{full_path}"


def resource_for_key(bucket: str, key: str) -> str:
    return f"{bucket}/{key}"


def folder_node(folder: Folder, parent: str, text: str | None = None, has_children: bool = False) -> dict:
    """Build a jstree-compatible folder node dict from a ``Folder`` model"""
    return {
        "id": str(folder.id),
        "parent": parent,
        "text": text or folder.name,
        "li_attr": {
            "type": "folder",
            "bucket": folder.bucket,
            "full_path": folder.full_path,
            "has_children": has_children,
        },
    }


async def has_folder_children(session: AsyncSession, bucket: str, folder_id: int) -> bool:
    """Return ``True`` if the folder has at least one child folder or file."""
    child_folder = (await session.execute(
        select(Folder.id)
        .where(
            Folder.bucket == bucket,
            Folder.parent_id == folder_id,
            Folder.status == "complete",
        )
        .limit(1)
    )).scalar_one_or_none()
    if child_folder is not None:
        return True

    child_file = (await session.execute(
        select(File.id)
        .where(
            File.bucket == bucket,
            File.folder_id == folder_id,
            File.status == "complete",
        )
        .limit(1)
    )).scalar_one_or_none()
    return child_file is not None


@router.get("/dashboard/{instance_uuid}", response_class=ORJSONResponse)
async def dashboard_db(
    instance_uuid: str,
    access: Literal["read", "write", "delete"] = Query(..., description="Access tree to return"),
    token_payload: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
):
    """
    DB-backed tree for one lazy-loaded access tab.
    Returns { access: "read"|"write"|"delete", assets: [nodes] }
    """
    # Resolve Identity and Context
    user_uuid = authenticated_user_uuid(token_payload)
    instance = instance_manager.get_instance_by_uuid(UUID(instance_uuid))
    agent = instance.agent

    # Identify buckets associated with the instance agent
    try:
        allowed_buckets = set(agent.fetch_all_buckets()) if hasattr(agent, "fetch_all_buckets") else set()
    except Exception as e:
        logger.error(f"Failed to fetch allowed buckets: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to retrieve bucket information from storage. Please try again later.")

    access_types = [access]
    assets: list[dict] = []

    # Query root folders for all applicable buckets
    roots = list((await session.execute(
        select(Folder).where(
            Folder.full_path == "/",
            Folder.bucket.in_(allowed_buckets),
            Folder.status == "complete",
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
        for access_key in root_allowed_access:
            assets.append({
                "id": str(root.id),
                "parent": "#",
                "text": root.bucket,
                "li_attr": {"type": "folder", "bucket": root.bucket},
            })

        # Fetch all folders in this root bucket
        folders = list((await session.execute(
            select(Folder).where(
                Folder.bucket == root.bucket,
                Folder.status == "complete",
            ).order_by(Folder.full_path)
        )).scalars().all())

        # Fetch all files in this root bucket
        files = list((await session.execute(
            select(File)
            .where(
                File.bucket == root.bucket,
                File.status == "complete",
            )
            .order_by(File.folder_id, File.name)
        )).scalars().all())

        # Filter folders
        for f in folders:
            if f.full_path == "/":
                continue
            parent_id = str(f.parent_id) if f.parent_id else str(root.id)
            
            # Identify which permission types (read, write, delete) are candidates for this folder.
            valid_accesses = []
            for access_key in root_allowed_access:
                # RECURSIVE CHECK: A folder can only be "valid" for an action if its 
                # parent folder is already in the 'allowed_folder_ids' for that specific action.
                if parent_id in allowed_folder_ids[access_key]:
                    valid_accesses.append(access_key)

            # If the parent folder doesn't have any of the 
            # required permissions, we don't bother checking the Policy
            if not valid_accesses:
                continue

            res = resource_for_folder(f.bucket, f.full_path)
            allowed_actions_for_folder = policy_manager.get_allowed_actions(user_uuid, UUID(instance_uuid), res, valid_accesses)
            
            for access_key in allowed_actions_for_folder:
                # Add this folder to list of allowed folders
                allowed_folder_ids[access_key].add(str(f.id))

                # Add this folder to results
                assets.append({
                    "id": str(f.id),
                    "parent": parent_id,
                    "text": f.name,
                    "li_attr": {"type": "folder", "bucket": f.bucket, "full_path": f.full_path},
                })

        # Filter Files
        for file in files:
            folder_id_str = str(file.folder_id)
            
            # Identify which permission types (read, write, delete) are candidates for this file.
            valid_accesses = []
            for access_key in root_allowed_access:
                # LEAF NODE CHECK: A file is only eligible for an action (e.g., 'read')
                # if the folder containing it is already authorized for that action.
                if folder_id_str in allowed_folder_ids[access_key]:
                    valid_accesses.append(access_key)

            # If the parent folder doesn't have any of the 
            # required permissions, we don't bother checking the policy
            if not valid_accesses:
                continue

            res = resource_for_key(file.bucket, file.key)
            allowed_actions_for_file = policy_manager.get_allowed_actions(user_uuid, UUID(instance_uuid), res, valid_accesses)
            
            for access_key in allowed_actions_for_file:
                # Add this file to results
                assets.append({
                    "id": f"file-{file.id}",
                    "parent": folder_id_str,
                    "text": file.name,
                    "li_attr": {"type": "file", "bucket": file.bucket, "key": file.key},
                })
                    
    return ORJSONResponse({"access": access, "assets": assets})


@router.get("/dashboard/{instance_uuid}/children", response_class=ORJSONResponse)
async def dashboard_children_db(
    instance_uuid: str,
    access: Literal["read", "write", "delete"] = Query(..., description="Access tree to return"),
    parent_id: int | None = Query(None, description="Folder id to lazy-load. Omit to load roots."),
    token_payload: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
):
    """
    DB-backed lazy tree endpoint.
    Returns authorized roots when parent_id is omitted, otherwise only immediate children.
    """
    user_uuid = authenticated_user_uuid(token_payload)
    instance_uuid_obj = UUID(instance_uuid)
    instance = instance_manager.get_instance_by_uuid(instance_uuid_obj)
    agent = instance.agent
    try:
        allowed_buckets = set(agent.fetch_all_buckets()) if hasattr(agent, "fetch_all_buckets") else set()
    except Exception as e:
        logger.error(f"Failed to fetch allowed buckets: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to retrieve bucket information from storage. Please try again later.")
    access_types = [access]
    assets: list[dict] = []

    # If parent_id is none return roots
    if parent_id is None:
        roots = list((await session.execute(
            select(Folder)
            .where(
                Folder.full_path == "/",
                Folder.bucket.in_(allowed_buckets),
                Folder.status == "complete",
            )
            .order_by(Folder.bucket)
        )).scalars().all())

        for root in roots:
            root_res = resource_for_folder(root.bucket, root.full_path)
            root_allowed_access = policy_manager.get_allowed_actions(
                user_uuid,
                instance_uuid_obj,
                root_res,
                access_types,
            )
            if not root_allowed_access:
                continue

            assets.append(folder_node(
                root,
                "#",
                text=root.bucket,
                has_children=await has_folder_children(session, root.bucket, root.id),
            ))

        return ORJSONResponse({"access": access, "parent_id": None, "assets": assets})

    # parent_id is present so get parent folder
    parent = (await session.execute(
        select(Folder).where(
            Folder.id == parent_id,
            Folder.bucket.in_(allowed_buckets),
            Folder.status == "complete",
        )
    )).scalar_one_or_none()
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    parent_allowed_access = policy_manager.get_allowed_actions(
        user_uuid,
        instance_uuid_obj,
        resource_for_folder(parent.bucket, parent.full_path),
        access_types,
    )
    if not parent_allowed_access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied by policy")

    # Get immediate childen
    folders = list((await session.execute(
        select(Folder)
        .where(
            Folder.bucket == parent.bucket,
            Folder.parent_id == parent.id,
            Folder.status == "complete",
        )
        .order_by(Folder.name)
    )).scalars().all())
    files = list((await session.execute(
        select(File)
        .where(
            File.bucket == parent.bucket,
            File.folder_id == parent.id,
            File.status == "complete",
        )
        .order_by(File.name)
    )).scalars().all())

    # Check permissions through casbin
    for folder in folders:
        folder_allowed_access = policy_manager.get_allowed_actions(
            user_uuid,
            instance_uuid_obj,
            resource_for_folder(folder.bucket, folder.full_path),
            access_types,
        )
        if folder_allowed_access:
            assets.append(folder_node(
                folder,
                str(parent.id),
                has_children=await has_folder_children(session, folder.bucket, folder.id),
            ))

    for file in files:
        file_allowed_access = policy_manager.get_allowed_actions(
            user_uuid,
            instance_uuid_obj,
            resource_for_key(file.bucket, file.key),
            access_types,
        )
        if file_allowed_access:
            assets.append({
                "id": f"file-{file.id}",
                "parent": str(file.folder_id),
                "text": file.name,
                "li_attr": {"type": "file", "bucket": file.bucket, "key": file.key},
            })

    return ORJSONResponse({"access": access, "parent_id": parent_id, "assets": assets})

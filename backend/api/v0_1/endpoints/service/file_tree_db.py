from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v0_1.endpoints.service.auth import decode_token
from api.v0_1.endpoints.service.models import FileTreeNode
from core.injection.managers import get_instance_manager, get_policy_manager, get_user_manager
from core.management.instances import AbstractInstanceManager
from core.management.policies import AbstractPolicyManager, Policy
from core.management.users import AbstractUserManager

from core.db.session import get_session
from core.model.folder import Folder
from core.model.file import File
from core.util.paths import normalize_folder_full_path

router = APIRouter(prefix="/tree", tags=["Tree-DB"])


def resource_for_folder(bucket: str, full_path: str) -> str:
    full_path = normalize_folder_full_path(full_path)
    return f"{bucket}{full_path}"


def resource_for_key(bucket: str, key: str) -> str:
    return f"{bucket}/{key}"


@router.get("/dashboard/{instance_uuid}")
async def dashboard_db(
    instance_uuid: str,
    token_payload: dict = Depends(decode_token),
    session: AsyncSession = Depends(get_session),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
):
    """
    DB-backed tree, same shape as /assets/dashboard/{instance_uuid}.
    Returns { assets: {instance_uuid: {read|write|delete: [FileTreeNode...]}} }
    """
    user_uuid = user_manager.get_user_uuid(token_payload["preferred_username"])
    instance = instance_manager.get_instance_by_uuid(UUID(instance_uuid))
    instance_name = instance.name
    agent = instance.agent
    allowed_buckets = set(agent.fetch_all_buckets()) if hasattr(agent, "fetch_all_buckets") else set()

    access_types = ["read", "write", "delete"]
    assets: dict[str, dict[str, list[FileTreeNode]]] = {instance_uuid: {}}

    roots = list((await session.execute(
        select(Folder).where(
            Folder.full_path == "/",
            Folder.bucket.in_(allowed_buckets),
        )
    )).scalars().all())

    for access in access_types:
        nodes: list[FileTreeNode] = []

        for root in roots:
            root_res = resource_for_folder(root.bucket, root.full_path)
            if not policy_manager.validate_policy(
                Policy(user_uuid=user_uuid, instance_uuid=UUID(instance_uuid), resource=root_res, action=access)
            ):
                continue

            folders = list((await session.execute(
                select(Folder).where(
                    Folder.bucket == root.bucket,
                    Folder.path.op("<@")(root.path),
                ).order_by(Folder.full_path)
            )).scalars().all())

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

            bucket_nodes: list[FileTreeNode] = []

            for f in folders:
                if f.full_path == "/":
                    continue
                res = resource_for_folder(f.bucket, f.full_path)
                if not policy_manager.validate_policy(
                    Policy(user_uuid=user_uuid, instance_uuid=UUID(instance_uuid), resource=res, action=access)
                ):
                    continue

                parent_id = str(f.parent_id) if f.parent_id else str(root.id)
                bucket_nodes.append(FileTreeNode(
                    id=str(f.id),
                    parent=parent_id,
                    text=f.name,
                    li_attr={"type": "folder", "bucket": f.bucket, "full_path": f.full_path},
                ))

            for file, _folder_full_path in files:
                res = resource_for_key(file.bucket, file.key)
                if not policy_manager.validate_policy(
                    Policy(user_uuid=user_uuid, instance_uuid=UUID(instance_uuid), resource=res, action=access)
                ):
                    continue

                bucket_nodes.append(FileTreeNode(
                    id=f"file-{file.id}",
                    parent=str(file.folder_id),
                    text=file.name,
                    li_attr={"type": "file", "bucket": file.bucket, "key": file.key},
                ))

            nodes.append(FileTreeNode(
                id=str(root.id),
                parent="#",
                text=root.bucket,
                li_attr={"type": "folder", "bucket": root.bucket},
            ))
            if bucket_nodes: nodes.extend(bucket_nodes)

        assets[instance_uuid][access] = nodes

    return {"assets": assets, "instances": {instance_name: instance_uuid}}

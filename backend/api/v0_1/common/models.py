from typing import Dict, Type, List, Any, Literal, Union, Annotated

from pydantic import BaseModel, Field, create_model

from core.storage_agents import AVAILABLE_FLAVOURS
from core.storage_agents.s3_agent import S3StorageAgent
from core.storage_agents.dummy_agent import DummyStorageAgent
from core.services.policies import Policy
from core.services.users.models import User


class GetAssetRequest(BaseModel):
    resource: str = Field(..., description="The resource to be accessed.")
    instance_name: str = Field(..., description="The name of the access point.")
    action: str = Field(..., description="The action to be performed on the resource.")


class GetAssetResponse(BaseModel):
    presigned_urls: list[str] = Field(..., description="The presigned URLs for the asset.")
    file_paths: list[str] = Field(..., description="The file paths for the asset.")


class BundleCreateRequest(BaseModel):
    instance_name: str = Field(..., description="The name of the access point.")
    file_ids: list[int] = Field(..., description="List of file IDs to bundle.")
    folder_name: Union[str, None] = Field(default="archive", description="Optional folder name for the bundle.")


class BundleCreateResponse(BaseModel):
    bundle_id: str = Field(..., description="The ID of the requested bundle.")
    status: str = Field(..., description="The current status of the bundle request.")
    folder_name: str = Field(..., description="The name of the archive file.")


class PutAssetRequest(BaseModel):
    resource: str = Field(..., description="Target path/key to write to (e.g. 'folder/sub/file.txt').")
    instance_name: str = Field(..., description="Name of the storage access point.")


class PutAssetResponse(BaseModel):
    presigned_urls: list[str] = Field(..., description="List of presigned PUT URLs (one per file).")
    file_paths: list[str] = Field(..., description="List of file paths these URLs correspond to.")


class DeleteAssetRequest(BaseModel):
    resource: str = Field(..., description="Path/key to delete (e.g. 'folder/sub/file.txt').")
    instance_name: str = Field(..., description="Name of the storage access point.")


class DeleteAssetResponse(BaseModel):
    presigned_urls: list[str] = Field(..., description="List of presigned DELETE URLs.")
    file_paths: list[str] = Field(..., description="List of file paths these URLs correspond to.")


class AddUserRequest(BaseModel):
    username: str = Field(..., description="The username of the user.")
    email: str = Field(..., description="The email of the user.")
    roles: list[str] = Field(..., description="The roles of the user.")


class AddUserResponse(BaseModel):
    success: bool = Field(..., description="Indicates whether the user was successfully added.")
    details: User = Field(..., description="The details of the user that was added.")


class RemoveUserResponse(BaseModel):
    success: bool = Field(..., description="Indicates whether the user was successfully removed.")
    details: User = Field(None, description="The details of the user that was removed.")


class AddPolicyRequest(BaseModel):
    username: str = Field(..., description="The username of the user.")
    instance_name: str = Field(..., description="The name of the instance.")
    resource: str = Field(..., description="The resource to be accessed.")
    action: str = Field(..., description="The action to be performed on the resource.")


class AddPolicyResponse(BaseModel):
    success: bool = Field(..., description="Indicates whether the policies were successfully updated.")
    details: list[Policy] = Field(..., description="The details of the policies that were updated.")

#this is temporary
# class RemovePolicyRequest(BaseModel):
#     username: str = Field(..., description="The username of the user.")
#     instance_name: str = Field(..., description="The name of the instance.")
#     resource: str = Field(..., description="The resource to be accessed.")
#     action: str = Field(..., description="The action to be performed on the resource.")

class RemovePolicyRequest(BaseModel):
    user_uuid: str = Field(..., description="The username of the user.")
    instance_uuid: str = Field(..., description="The name of the instance.")
    resource: str = Field(..., description="The resource to be accessed.")
    action: str = Field(..., description="The action to be performed on the resource.")


class RemovePolicyResponse(BaseModel):
    success: bool = Field(..., description="Indicates whether the policies were successfully removed.")
    details: list[Policy] = Field(..., description="The details of the policies that were removed.")


class GetPolicyResponse(BaseModel):
    success: bool = Field(..., description="Indicates whether the policies were successfully retrieved.")
    details: list[Policy] = Field(..., description="The details of the policies that were retrieved.")


# Model registration structure
model_registry: Dict[str, Type[BaseModel]] = {}


def register_model(model_name: str, model_class: Type[BaseModel], instance: str):
    """Registers a model and its associated endpoint."""
    model_registry[model_name] = {
        "model_class": model_class,
        "instance": instance
    }


# Register models

register_model("AddUserRequest", AddUserRequest, "/admin/user/")
register_model("AddUserResponse", AddUserResponse, "/admin/user/")
register_model("RemoveUserResponse", RemoveUserResponse, "/admin/user/")
register_model("GetPolicyResponse", GetPolicyResponse, "/admin/policy/")
register_model("AddPolicyResponse", AddPolicyResponse, "/admin/policy/")
register_model("AddPolicyRequest", AddPolicyRequest, "/admin/policy/")
register_model("RemovePolicyRequest", RemovePolicyRequest, "/admin/policy/")
register_model("RemovePolicyResponse", RemovePolicyResponse, "/admin/policy/")
register_model("GetPolicyResponse", GetPolicyResponse, "/admin/policy/")


# Dashboard Data Models

class FileTreeNode(BaseModel):
    id: str = Field(..., description="The node identifier.")
    parent: str = Field(..., description="The parent node identifier or '#' for root.")
    text: str = Field(..., description="The display text for the node.")
    li_attr: Dict[str, str] = Field(..., description="Additional attributes for the node.")


class InstanceFileTree(BaseModel):
    instance_name: str = Field(..., description="Name of the instance.")
    instance_uuid: str = Field(..., description="UUID of the instance.")
    file_tree: List[FileTreeNode] = Field(..., description="The file tree nodes.")


class UserFileTree(BaseModel):
    user_uuid: str = Field(..., description="UUID of the user.")
    username: str = Field(..., description="Username.")
    instances: Dict[str, Dict[str, List[FileTreeNode]]] = Field(
        ..., description="File trees organized by instance and access type."
    )


# Used for UNUSED legacy endpoint /api/assets/dashboard which has been replaced
# with /api/assets/dashboard/{instance}
class AssetManagementData(BaseModel):
    assets: Dict[str, Dict[str, List[FileTreeNode]]] = Field(
        ..., description="File trees organized by instance UUID and access type."
    )
    instances: Dict[str, str] = Field(..., description="Instance name to UUID mapping.")


class UserHomeData(BaseModel):
    assets: Dict[str, List[FileTreeNode]] = Field(
        ..., description="User's accessible file trees by instance."
    )
    instances: Dict[str, Any] = Field(..., description="Accessible instances information.")


class UserAssetsData(BaseModel):
    assets: Dict[str, List[FileTreeNode]] = Field(
        ..., description="User's file trees organized by instance UUID."
    )
    instances: Dict[str, str] = Field(..., description="Instance name to UUID mapping.")


class UserInstancesList(BaseModel):
    instances: Dict[str, str] = Field(..., description="Instance name to UUID mapping for the user.")


# Storage Instance Models (moved from interface/schemas to avoid circular imports)

# shared base:
class InstanceBase(BaseModel):
    flavour: Literal[tuple(AVAILABLE_FLAVOURS.keys())]
    instance_name: str
    instance_url: str


# build per-flavour create models:
S3InstanceCreate = create_model(
    "S3InstanceCreate",
    __base__=InstanceBase,
    flavour=(Literal[S3StorageAgent.FLAVOUR], ...),
    **{name: (typ, ...) for name, typ in S3StorageAgent.CONFIG.items()}
)

DummyInstanceCreate = create_model(
    "DummyInstanceCreate",
    __base__=InstanceBase,
    flavour=(Literal[DummyStorageAgent.FLAVOUR], ...),
    **{name: (typ, ...) for name, typ in DummyStorageAgent.CONFIG.items()}
)

# discriminated union:
InstanceCreate = Annotated[
    Union[S3InstanceCreate, DummyInstanceCreate],
    Field(discriminator="flavour")
]

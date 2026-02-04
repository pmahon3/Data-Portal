from typing import Dict, Type, List, Any, Literal, Union, Annotated
from uuid import UUID

from pydantic import BaseModel, Field, create_model, HttpUrl

from core.management.policies import Policy
from core.management.users.models import User
from core.connectivity.agents import (
    S3StorageAgent,
    DummyStorageAgent
)
from core.connectivity import AVAILABLE_FLAVOURS


class GetAssetRequest(BaseModel):
    resource: str = Field(..., description="The resource to be accessed.")
    instance_name: str = Field(..., description="The name of the access point.")
    action: str = Field(..., description="The action to be performed on the resource.")


class GetAssetResponse(BaseModel):
    presigned_urls: list[str] = Field(..., description="The presigned URLs for the asset.")
    file_paths: list[str] = Field(..., description="The file paths for the asset.")


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


class PolicyManagementData(BaseModel):
    assets: Dict[str, List[FileTreeNode]] = Field(
        ..., description="File trees for instances with admin access."
    )
    instances: List[Any] = Field(..., description="List of accessible instances.")


class UserManagementData(BaseModel):
    users: List[User] = Field(..., description="List of all users.")
    file_trees: Dict[str, Dict[str, Dict[str, List[FileTreeNode]]]] = Field(
        ..., description="File trees organized by user UUID, then instance, then access type."
    )
    models: Dict[str, Any] = Field(..., description="Model schemas for forms.")


class InstanceManagementData(BaseModel):
    instances: Dict[str, tuple] = Field(..., description="Instance configurations.")
    flavours: List[str] = Field(..., description="Available instance flavours.")


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

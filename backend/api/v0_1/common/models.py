from typing import Any, Dict, Type, Literal, Union, Annotated, Optional
from uuid import UUID

from pydantic import BaseModel, Field, create_model

from core.storage_agents import AVAILABLE_FLAVOURS
from core.storage_agents.s3_agent import S3StorageAgent
from core.storage_agents.dummy_agent import DummyStorageAgent
from core.services.policies import Policy
from core.services.users.models import User


class BundleCreateRequest(BaseModel):
    instance_name: str = Field(..., description="The name of the access point.")
    file_ids: list[int] = Field(default_factory=list, description="List of file IDs to bundle.")
    folder_ids: list[int] = Field(default_factory=list, description="List of folder IDs to bundle.")
    folder_name: Union[str, None] = Field(default="", description="Optional folder name for the bundle.")


class ManifestRequest(BaseModel):
    instance_name: str = Field(..., description="The name of the access point.")
    file_ids: list[int] = Field(default_factory=list, description="List of file IDs to include.")
    folder_ids: list[int] = Field(default_factory=list, description="List of folder IDs to expand and include.")
    ttl_seconds: Union[int, None] = Field(default=None, ge=60, le=604800,
                                          description="Lifetime of the returned URLs. Defaults to the server setting.")


class ManifestEntry(BaseModel):
    file_id: int = Field(..., description="The file's id.")
    bucket: str = Field(..., description="The bucket holding the object.")
    key: str = Field(..., description="The object key within the bucket.")
    relative_path: str = Field(..., description="Path to reconstruct on the client, as bucket/key.")
    size: Union[int, None] = Field(default=None, description="Size in bytes, if known.")
    etag: Union[str, None] = Field(
        default=None,
        description="The object's etag, if known. A change detector, not a content hash: "
                    "multipart uploads yield '<hash>-<partcount>', which depends on part size.",
    )
    url: str = Field(..., description="Presigned GET URL for the object.")


class ManifestResponse(BaseModel):
    instance_name: str = Field(..., description="The access point the entries belong to.")
    count: int = Field(..., description="Number of entries returned.")
    total_bytes: int = Field(..., description="Sum of entry sizes where known.")
    expires_in: int = Field(..., description="Lifetime of the URLs in seconds.")
    entries: list[ManifestEntry] = Field(..., description="One entry per authorized file.")


class BundleCreateResponse(BaseModel):
    bundle_id: str = Field(..., description="The ID of the requested bundle.")
    status: str = Field(..., description="The current status of the bundle request.")
    folder_name: str = Field(..., description="The name of the archive file.")
    single_file_url: Union[str, None] = Field(default=None, description="Direct presigned URL if downloading a single file.")


class BundleDownloadUrlResponse(BaseModel):
    bundle_id: str = Field(..., description="The ID of the requested bundle.")
    result_url: str = Field(..., description="Presigned URL for the completed bundle archive.")


class AddUserRequest(BaseModel):
    username: str = Field(..., description="The username of the user.")
    email: str = Field(..., description="The email of the user.")
    password: str = Field(..., description="The password for the user.")
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


class ProjectResponse(BaseModel):
    name: str = Field(..., description="The project name.")
    users: list[str] = Field(default_factory=list, description="Project users.")
    managers: list[str] = Field(default_factory=list, description="Project managers.")
    storageInstances: list[str] = Field(default_factory=list, description="Project storage instances.")


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="The project name.")


class ProjectUserRequest(BaseModel):
    username: str = Field(..., min_length=1, description="The username to add or remove.")


class ProjectStorageInstanceRequest(BaseModel):
    instance_name: str = Field(..., min_length=1, description="The storage instance name to add or remove.")


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


class UserInstancesList(BaseModel):
    instances: Dict[str, str] = Field(..., description="Instance name to UUID mapping for the user.")


# Storage Instance Models (moved from interface/schemas to avoid circular imports)

# shared base:
class InstanceBase(BaseModel):
    flavour: Literal[tuple(AVAILABLE_FLAVOURS.keys())]
    instance_name: str
    instance_url: str
    project_names: list[str] = Field(default_factory=list)


# build per-flavour create models:
S3InstanceCreate = create_model(
    "S3InstanceCreate",
    __base__=InstanceBase,
    flavour=(Literal[S3StorageAgent.FLAVOUR], ...),
    **{name: (typ, ...) for name, typ in S3StorageAgent.CONFIG.items()},
    region_name=(Optional[str], None)
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

class InstanceUpdate(BaseModel):
    instance_name: str | None = None


class InstanceOut(BaseModel):
    uuid: UUID
    name: str
    flavour: str
    config: dict[str, Any]


class InstanceListOut(BaseModel):
    instances: list[InstanceOut]


class CreatedInstanceOut(BaseModel):
    uuid: UUID
    name: str
    flavour: str
    project_names: list[str]


class CreateInstanceOut(BaseModel):
    message: str
    instance: CreatedInstanceOut


class BucketSyncOut(BaseModel):
    bucket: str
    files_synced: int
    folders_synced: int


class SyncSummaryOut(BaseModel):
    bucket_count: int
    file_count: int
    folder_count: int
    buckets: list[BucketSyncOut]


class SyncInstanceOut(BaseModel):
    message: str
    sync: SyncSummaryOut


class UpdateInstanceOut(BaseModel):
    message: str
    uuid: UUID


class DeleteInstanceOut(BaseModel):
    message: str

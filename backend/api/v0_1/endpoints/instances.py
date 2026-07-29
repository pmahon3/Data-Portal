"""
Storage Instance Management API Endpoints

Handles storage instance CRUD operations and instance-related dashboard data.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.responses import JSONResponse

from api.v0_1.common.auth_dependencies import is_user_admin, require_admin, require_admin_or_manager
from core.db.postgres.session import AsyncSessionMaker
from core.services.filetree.object_storage_sync import sync_s3_agent_to_postgres
from core.services.filetree.tree_service import TreeService
from core.services.injectors import get_instance_manager, get_policy_manager, get_project_manager
from core.services.instances import AbstractInstanceManager
from core.services.policies import CasbinPolicyManager
from core.services.policies import Policy
from core.services.projects import AbstractProjectManager, ProjectNotFoundError
from api.v0_1.common.models import InstanceCreate, InstanceUpdate

instances_router = APIRouter(prefix='/instances', tags=["Storage Instance Management"])
logger = logging.getLogger("api.endpoints")


def _managed_project_names(current_user: dict) -> set[str]:
    # JWT project paths are the source of truth for manager-scoped create access.
    managed_projects = set()
    for path in current_user.get("projects", []):
        clean_path = str(path).strip("/")
        if clean_path.endswith("/managers"):
            managed_projects.add(clean_path.split("/")[0])
    return managed_projects


def _can_access_instance(current_user: dict, instance_name: str, project_manager: AbstractProjectManager) -> bool:
    if is_user_admin(current_user):
        return True

    for project_name in _managed_project_names(current_user):
        try:
            if instance_name in project_manager.get_project_storage_instances(project_name):
                return True
        except ProjectNotFoundError:
            continue
    return False


@instances_router.get(
    "/",
    summary="List all storage instances",
    description="Retrieve list of all configured storage instances with their details."
)
async def list_instances(
    current_user: dict = Depends(require_admin_or_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
    project_manager: AbstractProjectManager = Depends(get_project_manager)
) -> JSONResponse:
    """
    Get list of all storage instances.
    
    Args:
        _current_user: Current user (must have admin or manager privileges)
        instance_manager: Instance manager dependency
        
    Returns:
        JSONResponse: List of instances with their configurations
    """
    if is_user_admin(current_user):
        # If admin get all instances
        instances = instance_manager.instances
    else:
        # If manager get only instances they have permission for
        instance_names = set()
        for project_name in _managed_project_names(current_user):
            try:
                instance_names.update(project_manager.get_project_storage_instances(project_name))
            except ProjectNotFoundError:
                continue
        instances = list(instance_manager.get_instances(instance_names).values())
    
    instance_list = []
    for instance in instances:
        instance_data = {
            "uuid": str(instance.uuid),
            "name": instance.name,
            "flavour": instance.flavour,
            "config": instance.config(secrets=False)  # Don't expose secrets
        }
        instance_list.append(instance_data)
    
    return JSONResponse(
        status_code=200,
        content={"instances": instance_list}
    )

@instances_router.get(
    "/{instance_id}",
    summary="Get storage instance details",
    description="Retrieve detailed information about a specific storage instance."
)
async def get_instance(
    instance_id: str,
    admin_user: dict = Depends(require_admin),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager)
) -> JSONResponse:
    """
    Get details for a specific storage instance (admin only).
    
    Args:
        instance_id: UUID of the instance to retrieve
        admin_user: Current user (must have admin privileges)
        instance_manager: Instance manager dependency
        
    Returns:
        JSONResponse: Instance details and configuration
        
    Raises:
        HTTPException: 404 if instance not found
        HTTPException: 400 if invalid UUID format
    """
    try:
        instance_uuid = UUID(instance_id)
    except ValueError:
        logger.error(f"Invalid instance ID format: {instance_id}")
        raise HTTPException(
            status_code=400, 
            detail="Invalid instance ID format. Must be a valid UUID."
        )
    
    try:
        instance = instance_manager.get_instance_by_uuid(instance_uuid)
    except ValueError:
        logger.error(f"Instance not found: {instance_id}")
        raise HTTPException(status_code=404, detail="Instance not found")
    
    return JSONResponse(
        status_code=200,
        content={
            "uuid": str(instance.uuid),
            "name": instance.name,
            "flavour": instance.flavour,
            "config": instance.config(secrets=False)
        }
    )


@instances_router.post(
    "/",
    summary="Create a new storage instance",
    description="Add a new storage instance configuration and automatically grant admin access to creator.",
    status_code=status.HTTP_201_CREATED
)
async def create_instance(
    config: InstanceCreate = Body(...),
    current_user: dict = Depends(require_admin_or_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    project_manager: AbstractProjectManager = Depends(get_project_manager)
) -> JSONResponse:
    """
    Create a new storage instance.
    
    Accepts JSON payload with flavour and configuration details.
    Automatically grants admin access to the creating user.
    
    Args:
        config: Instance creation configuration
        current_user: Current user (must have admin or manager privileges)
        instance_manager: Instance manager dependency
        policy_manager: Policy manager dependency
        
    Returns:
        JSONResponse: Success message with created instance details
        
    Raises:
        HTTPException: 400 if configuration invalid
        HTTPException: 500 if policy creation fails
    """

    name_value = getattr(config, "instance_name", None)
    if not name_value:
        logger.error(f"Instance creation failed: 'instance_name' is missing. Received: {name_value}")
        raise HTTPException(status_code=422,
                            detail="'instance_name' field is required")

    # Managers may attach projects only as part of creating a new instance.
    project_names = list(dict.fromkeys(
        name.strip()
        for name in getattr(config, "project_names", [])
        if isinstance(name, str) and name.strip()
    ))

    if project_names:
        if not is_user_admin(current_user):
            # Reject any project outside the manager's JWT-scoped assignments before saving.
            unmanaged_projects = sorted(set(project_names) - _managed_project_names(current_user))
            if unmanaged_projects:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: not a project manager or admin"
                )

        try:
            # Validate project existence up front so failed selections do not create instances.
            for project_name in project_names:
                project_manager.get_project_id(project_name)
        except ProjectNotFoundError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    
    # Save the instance directly to database
    try:
        instance_uuid = instance_manager.save_instance(config)
    except ValueError as e:
        error_msg = str(e)
        logger.error(f"Error when saving instance '{name_value}': {error_msg}")
        if "already exists" in error_msg:
            # Differentiate between name colllision and URL+key collision for friendliness
            if "name" in error_msg:
                raise HTTPException(status_code=409, detail=f"An instance with the name '{name_value}' already exists. Please choose a different name.")
            else:
                raise HTTPException(status_code=409, detail="An instance with this URL and access key combination already exists.")
        elif "failed to create storage agent" in error_msg.lower():
            raise HTTPException(status_code=400, detail="Failed to connect to the requested storage service. Please check your credentials and URL.")
        else:
            raise HTTPException(status_code=422, detail="Invalid instance configuration provided.")
    except Exception as e:
        logger.error(f"Failed to save configuration for instance '{name_value}': {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save instance configuration: {str(e)}"
        )

    # Add admin policy for the creating user
    user_uuid_str = current_user.get("sub")
    user_uuid = UUID(user_uuid_str)
    new_admin_policy = Policy(
        user_uuid=user_uuid,
        instance_uuid=instance_uuid,
        resource='.*',
        action='admin'
    )
    
    try:
        if not policy_manager.add_policy(new_admin_policy):
            # Policy failed so go to exception block
            raise RuntimeError("Add policy returned false")
    except Exception as e:
        logger.error(f"Failed to add admin policy for instance '{name_value}': {str(e)}")
        # If policy fails, remove the newly created instance
        instance_manager.delete_instance(instance_uuid)
        raise HTTPException(
            status_code=500,
            detail="Failed to grant administrator access for the new instance"
        )

    try:
        # Keep project assignment creation-time only for managers; later edits use admin-only project APIs.
        for project_name in project_names:
            project_manager.add_project_storage_instance(project_name, name_value)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except Exception as e:
        logger.error(f"Failed to attach instance '{name_value}' to projects {project_names}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add storage instance to selected projects"
        )

    logger.info(f"Created instance '{name_value}' (UUID: {instance_uuid}) by user '{current_user.get('preferred_username')}'")
    return JSONResponse(
        status_code=201,
        content={
            "message": f"Instance '{name_value}' created successfully",
            "instance": {
                "uuid": str(instance_uuid),
                "name": name_value,
                "flavour": config.flavour,
                "project_names": project_names
            }
        }
    )


@instances_router.post(
    "/{instance_id}/sync",
    summary="Sync storage instance metadata",
    description="Synchronize an S3 storage instance's object storage contents into PostgreSQL."
)
async def sync_instance(
    instance_id: str,
    current_user: dict = Depends(require_admin_or_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
    project_manager: AbstractProjectManager = Depends(get_project_manager),
) -> JSONResponse:
    try:
        instance_uuid = UUID(instance_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid instance ID format. Must be a valid UUID."
        )

    try:
        instance = instance_manager.get_instance_by_uuid(instance_uuid)
    except ValueError:
        raise HTTPException(status_code=404, detail="Instance not found")

    if not _can_access_instance(current_user, instance.name, project_manager):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not a project manager or admin"
        )

    if instance.flavour != "s3":
        raise HTTPException(
            status_code=400,
            detail="Sync is only supported for S3 storage instances"
        )

    try:
        async with AsyncSessionMaker() as session:
            sync_summary = await sync_s3_agent_to_postgres(instance.agent, session)
    except Exception as e:
        logger.error(f"Failed to sync object storage metadata for instance '{instance.name}': {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to synchronize object storage metadata for the instance"
        )

    logger.info(
        "Synced object storage metadata for instance '%s' (UUID: %s): %s",
        instance.name,
        instance_uuid,
        sync_summary.to_dict(),
    )
    return JSONResponse(
        status_code=200,
        content={
            "message": f"Instance '{instance.name}' synchronized successfully",
            "sync": sync_summary.to_dict(),
        }
    )


@instances_router.patch(
    "/{instance_id}",
    summary="Update a storage instance",
    description="Update an existing storage instance."
)
async def update_instance(
    instance_id: str,
    admin_user: dict = Depends(require_admin),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
    config: InstanceUpdate = Body(...)
):
    # Format the instance id to be update to UUID
    try:
        instance_uuid = UUID(instance_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid instance ID format. Must be a valid UUID."
        )

    # Retrieve instance to be update
    instances = instance_manager.get_instances_by_uuid([instance_uuid])
    if not instances:
        raise HTTPException(status_code=404, detail="Instance not found")
        
    instance = instances[0]

    # Try to update instance
    try:
        updated = instance_manager.update_instance(instance_uuid, config.instance_name)
        if not updated:
            raise HTTPException(status_code=422, detail="No changes were detected or the update failed.")
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=409, detail=f"An instance with the name '{config.instance_name}' already exists. Please choose a different name.")
        raise HTTPException(status_code=422, detail="Invalid instance configuration provided.")
    except Exception as e:
        logger.error(f"Failed to update instance '{instance.name}': {str(e)}")
        raise HTTPException(status_code=422, detail="An unexpected error occurred while updating the instance.")
    
    return JSONResponse(
        status_code=200,
        content={
            "message": f"Instance updated successfully",
            "uuid": str(instance_uuid)
        }
    )

@instances_router.delete(
    "/{instance_id}",
    summary="Remove a storage instance",
    description="Remove a storage instance and all its associated policies."
)
async def delete_instance(
    instance_id: str,
    admin_user: dict = Depends(require_admin),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    project_manager: AbstractProjectManager = Depends(get_project_manager)
) -> JSONResponse:
    """
    Remove a storage instance and cleanup associated policies (admin only).
    
    Args:
        instance_id: UUID of the instance to remove
        admin_user: Current user (must have admin privileges)
        instance_manager: Instance manager dependency
        policy_manager: Policy manager dependency
        
    Returns:
        JSONResponse: Success message
        
    Raises:
        HTTPException: 400 if invalid UUID format
        HTTPException: 404 if instance not found
        HTTPException: 400 if deletion fails
    """
    try:
        instance_uuid = UUID(instance_id)
    except ValueError:
        logger.error(f"Invalid instance ID format for deletion: {instance_id}")
        raise HTTPException(
            status_code=400,
            detail="Invalid instance ID format. Must be a valid UUID."
        )

    # Get instance details before deletion
    try:
        instance = instance_manager.get_instance_by_uuid(instance_uuid)
    except ValueError:
        logger.error(f"Instance not found for deletion: {instance_id}")
        raise HTTPException(status_code=404, detail="Instance not found")

    # Remove database object tree records from database
    try:
        bucket_names = instance.agent.fetch_all_buckets() or []
        async with AsyncSessionMaker() as session:
            tree_svc = TreeService(session)
            await tree_svc.delete_buckets(bucket_names)
    except Exception as e:
        logger.error(
            f"Failed to clean up object tree metadata for instance '{instance.name}' ({instance_id}): {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to remove the instance"
        )

    # Delete the instance
    try:
        instance_manager.delete_instance(instance_uuid)
    except KeyError as e:
        logger.error(f"Failed to remove instance '{instance.name}' ({instance_id}): {str(e)}")
        raise HTTPException(
            status_code=404,
            detail="The requested instance could not be found for deletion."
        )

    # Remove project-instance links so deleted instances disappear from project/group assignments.
    try:
        project_manager.remove_instance_from_all_projects(instance_uuid)
    except Exception as e:
        logger.warning(f"Failed to remove project assignments for deleted instance '{instance.name}': {str(e)}")

    # Delete associated policies
    try:
        policies = policy_manager.get_instance_policies(instance_uuid)
        if policies:
            policy_manager.remove_policies(policies)
            logger.info(f"Removed {len(policies)} policies associated with instance '{instance.name}'")
    except ValueError as e:
        # Log warning but don't fail the deletion
        # The instance is already removed
        logger.warning(f"Failed to remove policies for deleted instance '{instance.name}': {str(e)}")
        pass

    logger.info(f"Deleted instance '{instance.name}' (UUID: {instance_id}) by user '{admin_user.get('preferred_username')}'")

    return JSONResponse(
        status_code=200,
        content={"message": f"Instance '{instance_id}' removed successfully"}
    )

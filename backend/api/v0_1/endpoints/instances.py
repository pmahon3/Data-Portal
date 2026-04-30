"""
Storage Instance Management API Endpoints

Handles storage instance CRUD operations and instance-related dashboard data.
All endpoints require admin privileges as instances control system storage access.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.responses import JSONResponse

from api.v0_1.common.auth_dependencies import require_admin
from core.services.injectors import get_instance_manager, get_policy_manager
from core.services.instances import AbstractInstanceManager
from core.services.policies import CasbinPolicyManager
from core.services.policies import Policy
from api.v0_1.common.models import InstanceCreate, InstanceUpdate

instances_router = APIRouter(prefix='/instances', tags=["Storage Instance Management"])
logger = logging.getLogger("api.endpoints")


# Helper functions can be added here as needed


@instances_router.get(
    "/",
    summary="List all storage instances",
    description="Retrieve list of all configured storage instances with their details."
)
async def list_instances(
    admin_user: dict = Depends(require_admin),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager)
) -> JSONResponse:
    """
    Get list of all storage instances (admin only).
    
    Args:
        admin_user: Current user (must have admin privileges)
        instance_manager: Instance manager dependency
        
    Returns:
        JSONResponse: List of instances with their configurations
    """
    instances = instance_manager.instances
    
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
    admin_user: dict = Depends(require_admin),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager)
) -> JSONResponse:
    """
    Create a new storage instance (admin only).
    
    Accepts JSON payload with flavour and configuration details.
    Automatically grants admin access to the creating user.
    
    Args:
        config: Instance creation configuration
        admin_user: Current user (must have admin privileges)
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
    user_uuid_str = admin_user.get("sub")
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
    logger.info(f"Created instance '{name_value}' (UUID: {instance_uuid}) by user '{admin_user.get('preferred_username')}'")
    return JSONResponse(
        status_code=201,
        content={
            "message": f"Instance '{name_value}' created successfully",
            "instance": {
                "uuid": str(instance_uuid),
                "name": name_value,
                "flavour": config.flavour
            }
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
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager)
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

    # Delete the instance
    try:
        instance_manager.delete_instance(instance_uuid)
    except KeyError as e:
        logger.error(f"Failed to remove instance '{instance.name}' ({instance_id}): {str(e)}")
        raise HTTPException(
            status_code=404,
            detail="The requested instance could not be found for deletion."
        )

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

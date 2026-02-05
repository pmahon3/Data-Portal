"""
Storage Instance Management API Endpoints

Handles storage instance CRUD operations and instance-related dashboard data.
All endpoints require admin privileges as instances control system storage access.
"""

import logging
from uuid  import uuid5, NAMESPACE_DNS, UUID
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.responses import JSONResponse

from core.injection import get_instance_manager, get_policy_manager
from core.connectivity import agent_factory
from core.management.instances.models import Instance
from core.management.instances import AbstractInstanceManager
from core.management.policies import AbstractPolicyManager, Policy

from ..auth_dependencies import require_admin
from .models import InstanceCreate

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
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager)
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

    name_value = getattr(config, "instance_name", None) or getattr(config, "name", None)
    if not name_value:
        logger.error(f"Instance creation failed: 'instance_name' or 'name' is missing. Received: {name_value}")
        raise HTTPException(status_code=422,
                            detail="'instance_name' or 'name' field is required")
    flavour = config.flavour
    
    # Generate stable UUID for the instance from its name
    instance_uuid = uuid5(NAMESPACE_DNS, name_value)

    # Convert Pydantic model to dict for instance factory
    agent_cfg = config.dict(exclude={"flavour", "instance_name", "name"})

    config_dict = {"agent": agent_cfg, "flavour": flavour}

    # Create the storage agent for the instance
    try:
        agent = agent_factory(config_dict)
    except Exception as e:
        logger.error(f"Failed to create storage agent for instance '{name_value}': {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create storage agent: {str(e)}"
        )

    # Create the instance object
    new_instance = Instance(
        uuid=instance_uuid,
        name=config.instance_name,
        flavour=flavour,
        agent=agent
    )

    # Register with the instance manager
    instance_manager.instances.append(new_instance)

    # Save the configuration
    try:
        instance_manager.save_configuration()
    except Exception as e:
        logger.error(f"Failed to save configuration for instance '{config.instance_name}': {str(e)}")
        # Remove from instances list if save fails
        instance_manager.instances.remove(new_instance)
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

    # Add the admin policy
    try:
        if not policy_manager.add_policy(new_admin_policy):
            logger.error(f"Failed to add admin policy for instance '{new_instance.name}' ({instance_uuid})")
            # If policy fails, remove the instance
            instance_manager.delete_instance(new_instance)
            raise HTTPException(
                status_code=500,
                detail="Failed to add administrator policy for new instance"
            )
    except ValueError as e:
        logger.error(f"ValueError when adding admin policy for instance '{new_instance.name}': {str(e)}")
        # If policy fails, remove the instance
        instance_manager.delete_instance(new_instance)
        raise HTTPException(
            status_code=400,
            detail=f"Failed to add administrator policy: {str(e)}"
        )

    return JSONResponse(
        status_code=201,
        content={
            "message": f"Instance '{new_instance.name}' created successfully",
            "instance": {
                "uuid": str(new_instance.uuid),
                "name": new_instance.name,
                "flavour": new_instance.flavour
            }
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
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager)
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

    # Create instance object for deletion
    instance_to_delete = Instance(
        uuid=instance_uuid,
        name=instance.name,
        flavour=instance.flavour,
        agent=instance.agent
    )

    # Delete the instance
    try:
        instance_manager.delete_instance(instance_to_delete)
    except KeyError as e:
        logger.error(f"Failed to remove instance '{instance.name}' ({instance_id}): {str(e)}")
        raise HTTPException(
            status_code=404,
            detail=f"Failed to remove instance: {str(e)}"
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

    return JSONResponse(
        status_code=200,
        content={"message": f"Instance '{instance_id}' removed successfully"}
    )
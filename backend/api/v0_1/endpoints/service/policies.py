"""
Policy Management API Endpoints

Handles policy CRUD operations and policy-related dashboard data.
All endpoints require admin privileges as policies control system access.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from core.injection import get_user_manager, get_policy_manager, get_instance_manager
from core.management.users import AbstractUserManager
from core.management.policies import AbstractPolicyManager, Policy
from core.management.instances import AbstractInstanceManager

from ..auth_dependencies import require_admin
from .models import (
    GetPolicyResponse, AddPolicyResponse, AddPolicyRequest,
    RemovePolicyRequest, RemovePolicyResponse
)

policies_router = APIRouter(prefix='/policies', tags=["Policy Management"])
logger = logging.getLogger("api.endpoints")


@policies_router.get(
    "/",
    response_model=GetPolicyResponse,
    summary="Get policies",
    description="Retrieve policies based on filter criteria. If no filters provided, returns all policies."
)
async def get_policies(
    policy_filter: Policy = Depends(),
    admin_user: dict = Depends(require_admin),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager)
) -> GetPolicyResponse:
    """
    Retrieve policies based on filter criteria (admin only).
    
    Args:
        policy_filter: Policy filter criteria from query parameters
        admin_user: Current user (must have admin privileges)
        policy_manager: Policy manager dependency
        
    Returns:
        GetPolicyResponse: Filtered policies
        
    Raises:
        HTTPException: 404 if no policies found
    """
    # Default empty filter if none provided
    if policy_filter is None:
        policy_filter = Policy(
            user_uuid=None,
            endpoint_uuid=None,
            resource=None,
            action=None
        )

    policies = policy_manager.filter_policies(policy_filter)
    if policies is None:
        logger.error("No policies found matching the filter criteria")
        raise HTTPException(status_code=404, detail="No policies found")

    return GetPolicyResponse(success=True, details=policies)


@policies_router.post(
    "/",
    response_model=AddPolicyResponse,
    summary="Create a policy",
    description="Add a new access policy for a user on a specific instance and resource.",
    status_code=status.HTTP_201_CREATED
)
async def create_policy(
    new_policy: AddPolicyRequest,
    admin_user: dict = Depends(require_admin),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager)
) -> AddPolicyResponse:
    """
    Create a new access policy (admin only).
    
    Args:
        new_policy: Policy creation request data
        admin_user: Current user (must have admin privileges)
        user_manager: User manager dependency
        policy_manager: Policy manager dependency
        instance_manager: Instance manager dependency
        
    Returns:
        AddPolicyResponse: Success status and created policy details
        
    Raises:
        HTTPException: 404 if user or instance not found
        HTTPException: 400 if policy creation fails
    """
    # Get user and instance UUIDs
    try:
        user_uuid = user_manager.get_user_uuid(new_policy.username)
    except KeyError:
        logger.error(f"User '{new_policy.username}' not found for policy creation")
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        instance_uuid = instance_manager.get_instance_uuid(new_policy.instance_name)
    except KeyError:
        logger.error(f"Instance '{new_policy.instance_name}' not found for policy creation")
        raise HTTPException(status_code=404, detail="Instance not found")

    # Create policy object
    policy = Policy(
        user_uuid=user_uuid,
        instance_uuid=instance_uuid,
        resource=new_policy.resource,
        action=new_policy.action
    )

    # Validate user and instance exist
    if user_manager.get_user(policy.user_uuid) is None:
        logger.error(f"User UUID {policy.user_uuid} not found during policy validation")
        raise HTTPException(status_code=404, detail="User not found")
    if instance_manager.get_instance_by_uuid(policy.instance_uuid) is None:
        logger.error(f"Instance UUID {policy.instance_uuid} not found during policy validation")
        raise HTTPException(status_code=404, detail="Instance not found")

    # Add policy
    try:
        policy_manager.add_policies([policy])
    except ValueError as e:
        logger.error(f"Policy creation failed for user '{new_policy.username}' on instance '{new_policy.instance_name}' with action '{new_policy.action}' on resource '{new_policy.resource}': {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to add policy: {e}")

    logger.info(f"Created policy for user UUID '{user_uuid}' on instance UUID '{instance_uuid}' with action '{new_policy.action}' on resource '{new_policy.resource}'")
    return AddPolicyResponse(success=True, details=[policy])


@policies_router.delete(
    "/",
    response_model=RemovePolicyResponse,
    summary="Remove a policy",
    description="Remove an existing access policy."
)
async def delete_policy(
    old_policy: RemovePolicyRequest,
    admin_user: dict = Depends(require_admin),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager)
) -> RemovePolicyResponse:
    """
    Remove an existing policy (admin only).
    
    Args:
        old_policy: Policy removal request data
        admin_user: Current user (must have admin privileges)
        user_manager: User manager dependency
        policy_manager: Policy manager dependency
        instance_manager: Instance manager dependency
        
    Returns:
        RemovePolicyResponse: Success status and removed policy details
        
    Raises:
        HTTPException: 404 if user or instance not found
        HTTPException: 400 if policy removal fails
    """
    # Get user and instance UUIDs
    try:
        #This is temporary
        # user_uuid = user_manager.get_user_uuid(old_policy.username)
        user_uuid = old_policy.user_uuid
    except KeyError:
        logger.error(f"User not found for policy deletion: {old_policy.user_uuid}")
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        # This is temporary
        # instance_uuid = instance_manager.get_instance_uuid(old_policy.instance_name)
        instance_uuid = old_policy.instance_uuid
    except KeyError:
        logger.error(f"Instance not found for policy deletion: {old_policy.instance_uuid}")
        raise HTTPException(status_code=404, detail="Instance not found")

    # Create policy object to remove
    policy = Policy(
        user_uuid=user_uuid,
        instance_uuid=instance_uuid,
        resource=old_policy.resource,
        action=old_policy.action
    )

    # Remove policy
    try:
        policy_manager.remove_policy(policy)
    except ValueError as e:
        logger.error(f"Policy deletion failed for user UUID '{user_uuid}' on instance UUID '{instance_uuid}' with action '{old_policy.action}' on resource '{old_policy.resource}': {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to remove policy: {e}")

    logger.info(f"Deleted policy for user UUID '{user_uuid}' on instance UUID '{instance_uuid}' with action '{old_policy.action}' on resource '{old_policy.resource}'")
    return RemovePolicyResponse(success=True, details=[policy])


@policies_router.post(
    "/validate",
    summary="Validate a policy",
    description="Check if a specific policy would be allowed by the current policy configuration."
)
async def validate_policy(
    policy_data: Policy,
    admin_user: dict = Depends(require_admin),
    policy_manager: AbstractPolicyManager = Depends(get_policy_manager)
) -> JSONResponse:
    """
    Validate if a policy would be allowed (admin only).
    
    Useful for testing policy configurations before applying them.
    
    Args:
        policy_data: Policy to validate
        admin_user: Current user (must have admin privileges)
        policy_manager: Policy manager dependency
        
    Returns:
        JSONResponse: Validation result
    """
    is_valid = policy_manager.validate_policy(policy_data)
    return JSONResponse(
        status_code=200,
        content={
            "valid": is_valid,
            "policy": {
                "user_uuid": str(policy_data.user_uuid),
                "instance_uuid": str(policy_data.instance_uuid),
                "resource": policy_data.resource,
                "action": policy_data.action
            }
        }
    )
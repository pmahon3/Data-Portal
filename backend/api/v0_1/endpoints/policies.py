"""
Policy Management API Endpoints

Handles policy CRUD operations and policy-related dashboard data.
Policy management endpoints require elevated privileges; user-specific
read-only endpoints require standard authentication.
"""

import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from api.v0_1.common.auth_dependencies import get_current_user, is_user_admin, require_admin, require_admin_or_manager
from api.v0_1.startup import init_db_roots
from core.services.injectors import get_user_manager, get_policy_manager, get_instance_manager, get_project_manager
from core.services.instances import AbstractInstanceManager
from core.services.policies import CasbinPolicyManager
from core.services.policies import Policy
from core.services.projects import AbstractProjectManager
from core.services.users import AbstractUserManager
from api.v0_1.common.models import (
    GetPolicyResponse, AddPolicyResponse, AddPolicyRequest,
    RemovePolicyRequest, RemovePolicyResponse
)

policies_router = APIRouter(prefix='/policies', tags=["Policy Management"])
logger = logging.getLogger("api.endpoints")


@policies_router.get(
    "/me",
    response_model=GetPolicyResponse,
    response_model_exclude_none=True,
    summary="Get my policies",
    description="Retrieve access policies for the current authenticated user."
)
async def get_my_policies(
    current_user: dict = Depends(get_current_user),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> GetPolicyResponse:
    """
    Retrieve policies for the current authenticated user.

    Returns an empty list when the user has no policies.
    """
    user_uuid = UUID(current_user["sub"])
    policies = policy_manager.get_user_policies(user_uuid)

    # Map instance uuid to name
    unique_instance_uuids = list({policy.instance_uuid for policy in policies if policy.instance_uuid})
    resolved_instances = instance_manager.get_instances_by_uuid(unique_instance_uuids)
    uuid_to_instance_name = {instance.uuid: instance.name for instance in resolved_instances}

    for policy in policies:
        policy.instance_name = uuid_to_instance_name.get(policy.instance_uuid, "Unknown Instance")

    return GetPolicyResponse(success=True, details=policies)


@policies_router.get(
    "/",
    response_model=GetPolicyResponse,
    summary="Get policies",
    description="Retrieve policies based on filter criteria. If no filters provided, returns all policies."
)
async def get_policies(
    policy_filter: Policy = Depends(),
    current_user: dict = Depends(require_admin_or_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    project_manager: AbstractProjectManager = Depends(get_project_manager),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
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

    uuid_to_username = {}
    # Filter the policies if the current user is a manager
    # TODO: Change to use mongo queries instead of looping through each policy
    if not is_user_admin(current_user):
        visible_policies = []
        for policy in policies:
            if policy.user_uuid not in uuid_to_username:
                uuid_to_username[policy.user_uuid] = user_manager.get_user_slug(policy.user_uuid)
            username = uuid_to_username[policy.user_uuid]


            if project_manager.can_manage_instance_for_user(current_user, username, policy.instance_uuid):
                visible_policies.append(policy)

        policies = visible_policies

    # Collect unique user and instance UUIDs
    unique_user_uuids = {policy.user_uuid for policy in policies if policy.user_uuid}
    unique_instance_uuids = list({policy.instance_uuid for policy in policies if policy.instance_uuid})

    # Create lookup dictionary via batch fetch for instances
    # Instance Manager has get_instances_by_uuid which takes a list
    resolved_instances = instance_manager.get_instances_by_uuid(unique_instance_uuids)
    uuid_to_instance_name = {instance.uuid: instance.name for instance in resolved_instances}

    # Create dict of UUID to username sequentially
    for u_uuid in unique_user_uuids:
        if u_uuid in uuid_to_username:
            continue
        try:
            uuid_to_username[u_uuid] = user_manager.get_user_slug(u_uuid)
        except Exception as e:
            logger.error(f"Could not resolve username for UUID {u_uuid}: {e}")
            uuid_to_username[u_uuid] = "Unknown User"

    # Repopulate policies using the maps
    for policy in policies:
        policy.username = uuid_to_username.get(policy.user_uuid, "Unknown User")
        policy.instance_name = uuid_to_instance_name.get(policy.instance_uuid, "Unknown Instance")

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
    current_user: dict = Depends(require_admin_or_manager),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    project_manager: AbstractProjectManager = Depends(get_project_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
) -> AddPolicyResponse:
    """
    Create a new access policy.
    
    Args:
        new_policy: Policy creation request data
        current_user: Current user (must be admin or project manager)
        user_manager: User manager dependency
        policy_manager: Policy manager dependency
        instance_manager: Instance manager dependency
        
    Returns:
        AddPolicyResponse: Success status and created policy details
        
    Raises:
        HTTPException: 404 if user or instance not found
        HTTPException: 400 if policy creation fails
    """
    try:
        re.compile(new_policy.resource)
    except re.error:
        raise HTTPException(status_code=400, detail="Invalid regular expression syntax.")

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

    # Managers can grant access only inside a project they manage.
    if not is_user_admin(current_user) and not project_manager.can_manage_instance_for_user(
        current_user,
        new_policy.username,
        instance_uuid
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: user and instance must belong to the same project"
        )

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

    # Ensure bucket roots exist in DB for all instances
    try:
        await init_db_roots()
        logger.info(f"Ensured bucket roots exist in DB for all instances")
    except Exception as e:
        logger.warning(f"Failed to ensure bucket roots: {e}")
        # Continue anyway, policy creation shouldn't fail if DB sync fails
    
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
    current_user: dict = Depends(require_admin_or_manager),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    project_manager: AbstractProjectManager = Depends(get_project_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
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
        user_uuid = UUID(str(old_policy.user_uuid))
    except (TypeError, ValueError):
        logger.error(f"User not found for policy deletion: {old_policy.user_uuid}")
        raise HTTPException(status_code=400, detail="Invalid user UUID")
    
    try:
        instance_uuid = UUID(str(old_policy.instance_uuid))
    except (TypeError, ValueError):
        logger.error(f"Instance not found for policy deletion: {old_policy.instance_uuid}")
        raise HTTPException(status_code=400, detail="Invalid instance UUID")

    if not is_user_admin(current_user):
        # If manager
        try:
            username = user_manager.get_user_slug(user_uuid)
        except Exception as e:
            logger.error(f"User UUID {user_uuid} not found for policy deletion: {e}")
            raise HTTPException(status_code=404, detail="User not found")

        if not project_manager.can_manage_instance_for_user(current_user, username, instance_uuid):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: user and instance must belong to the same project managed by the requester"
            )

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
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager)
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

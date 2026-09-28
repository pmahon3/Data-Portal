"""
User Management API Endpoints

Handles user CRUD operations using FastAPI dependency injection for authorization.
Supports admin, project-manager, authenticated, and owner-or-admin access patterns.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status, Request

from api.v0_1.common.auth_dependencies import (
    get_current_user,
    is_user_admin,
    require_admin,
    require_admin_or_manager,
    require_user_owner_or_admin,
)
from core.services.injectors import get_user_manager, get_policy_manager, get_instance_manager
from core.services.instances import AbstractInstanceManager
from core.services.policies import CasbinPolicyManager
from core.services.users import (
    AbstractUserManager,
    InvalidUserEmailError,
    InvalidUserRoleError,
    UserAlreadyExistsError,
    UsernameRequiredError,
)
from core.services.users.models import UserCreate
from api.v0_1.common.models import (
    User, AddUserRequest, AddUserResponse, RemoveUserResponse, UserInstancesList
)

users_router = APIRouter(prefix='/users', tags=["User Management"])
logger = logging.getLogger("api.endpoints")


@users_router.get(
    "/",
    response_model=list[User],
    summary="List all users",
    description="Retrieve list of all users in the system. Requires admin or project manager privileges."
)
async def list_users(
    current_user: dict = Depends(require_admin_or_manager),
    user_manager: AbstractUserManager = Depends(get_user_manager)
) -> list[User]:
    """Get list of all users (admin or project manager)."""
    return user_manager.get_all_users()


@users_router.get(
    "/me",
    response_model=User,
    summary="Get current user information",
    description="Retrieve information about the currently authenticated user."
)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    user_manager: AbstractUserManager = Depends(get_user_manager)
) -> User:
    """Get current user's own information (authenticated user)."""
    current_username = current_user.get("preferred_username")
    if not current_username:
        logger.error("Username not found in token for current user")
        raise HTTPException(status_code=400, detail="Username not found in token")

    try:
        uuid = user_manager.get_user_uuid(current_username)
        return user_manager.get_user(uuid)
    except KeyError:
        logger.error(f"User '{current_username}' not found in system")
        raise HTTPException(status_code=404, detail="User not found in system")


@users_router.get(
    "/{username}",
    response_model=User,
    summary="Get user information",
    description="Users can view their own profile, admins can view any user."
)
async def get_user(
    username: str,
    request: Request,
    current_user: dict = Depends(require_user_owner_or_admin()),
    user_manager: AbstractUserManager = Depends(get_user_manager)
) -> User:
    """Get user details (owner or admin)."""
    try:
        uuid = user_manager.get_user_uuid(username)
        return user_manager.get_user(uuid)
    except KeyError:
        logger.error(f"User '{username}' not found")
        raise HTTPException(status_code=404, detail="User not found")


@users_router.get(
    "/{username}/instances",
    response_model=UserInstancesList,
    summary="Get user's available instances",
    description="Retrieve list of storage instances accessible to a specific user. Users can view their own instances, admins can view any user's instances."
)
async def get_user_instances(
    username: str,
    current_user: dict = Depends(require_user_owner_or_admin()),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager)
) -> UserInstancesList:
    """Get list of instances available to a user (owner or admin)."""
    try:
        uuid = user_manager.get_user_uuid(username)
    except KeyError:
        logger.error(f"User '{username}' not found")
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get all storage instances the user has access to
    instance_uuids = list(
        set(policy.instance_uuid for policy in policy_manager.get_user_policies(str(uuid)))
    )
    instances = instance_manager.get_instances_by_uuid(instance_uuids)
    
    # Convert to instance name → UUID mapping
    instance_names = {instance.name: str(instance.uuid) for instance in instances}
    
    return UserInstancesList(instances=instance_names)


@users_router.post(
    "/",
    response_model=AddUserResponse,
    summary="Create a new user",
    description="Creates user in auth service and sets up policies. Admins and project managers only.",
    status_code=status.HTTP_201_CREATED
)
async def create_user(
    user_data: AddUserRequest,
    current_user: dict = Depends(require_admin_or_manager),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager)
) -> AddUserResponse:
    """Create new user with auth and policy setup (admin or project manager)."""
    if not is_user_admin(current_user) and "admin" in {role.lower() for role in user_data.roles}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Project managers cannot create admin users"
        )

    user_create = UserCreate(
        username=user_data.username,
        email=user_data.email,
        roles=user_data.roles,
        password=user_data.password
    )

    # Check if email field is present
    if not user_data.email:
        logger.error(f"Email is required for user creation: {user_data.username}")
        raise HTTPException(status_code=400, detail="Email is required")

    if not user_data.password:
        logger.error(f"Password is required for user creation: {user_data.username}")
        raise HTTPException(status_code=400, detail="Password is required")

    # Check if user exists
    try:
        if user_manager.get_user_uuid(user_create.username):
            logger.error(f"User '{user_create.username}' already exists")
            raise HTTPException(status_code=409, detail="User already exists")
    except KeyError:
        pass

    # Create user
    try:
        user_manager.create_user(user_create)
        uuid = user_manager.get_user_uuid(user_data.username)
    except InvalidUserEmailError as e:
        logger.error(f"Invalid email format for user '{user_data.username}' and email '{user_data.email}': {e}")
        raise HTTPException(status_code=400, detail="Invalid email format")
    except UsernameRequiredError as e:
        logger.error(f"Username is required for user creation: {e}")
        raise HTTPException(status_code=400, detail="Username is required")
    except UserAlreadyExistsError as e:
        logger.error(f"User '{user_data.username}' already exists: {e}")
        raise HTTPException(status_code=409, detail="User already exists")
    except InvalidUserRoleError as e:
        logger.error(
            f"Invalid role(s) for user '{user_data.username}': {e.invalid_roles}"
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown role(s): {', '.join(e.invalid_roles)}. "
                "Check the role names and try again."
            )
        )
    except Exception as e:
        logger.exception(f"Failed to create user '{user_data.username}': {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create user due to an internal error."
        )

    user_details = user_manager.get_user(uuid)
    logger.info(f"Created user '{user_data.username}'")
    return AddUserResponse(success=True, details=user_details)


@users_router.delete(
    "/{username}",
    response_model=RemoveUserResponse,
    summary="Remove a user",
    description="Users can delete their own account, admins can delete any user."
)
async def delete_user(
    username: str,
    request: Request,
    current_user: dict = Depends(require_user_owner_or_admin()),
    user_manager: AbstractUserManager = Depends(get_user_manager),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager)
) -> RemoveUserResponse:
    """Delete user and cleanup policies (owner or admin)."""
    try:
        uuid = user_manager.get_user_uuid(username)
        user_details = user_manager.get_user(uuid)
    except KeyError:
        logger.error(f"User '{username}' not found for deletion")
        raise HTTPException(status_code=404, detail="User not found")

    if not user_manager.delete_user(uuid):
        logger.error(f"Failed to delete user '{username}' (UUID: {uuid})")
        raise HTTPException(status_code=400, detail="Failed to delete user")

    if not policy_manager.remove_user_policy_store(uuid):
        logger.error(f"Failed to remove policy store for user '{username}' (UUID: {uuid})")
        raise HTTPException(status_code=500, detail="Failed to remove user policy file")

    logger.info(f"Deleted user '{username}'")
    return RemoveUserResponse(success=True, details=user_details)

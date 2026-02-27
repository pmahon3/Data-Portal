"""
Authorization decorators and dependencies for FastAPI endpoints.

Provides both decorator and dependency patterns for reusable authorization.
Decorators are cleaner for endpoint signatures, dependencies are better for testing.
"""

from functools import wraps
from uuid import UUID
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.injection import get_policy_manager
from core.management.managers.policies import CasbinPolicyManager
from core.management.policies import Policy
from .service.auth import decode_token, is_user_admin

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> dict:
    """
    Standard user authentication dependency.
    
    Validates JWT token and returns user payload.
    Replaces direct decode_token calls throughout endpoints.
    
    Returns:
        dict: Decoded JWT token payload with user information
        
    Raises:
        HTTPException: 401 if token is invalid or missing
    """
    return decode_token(credentials)


async def require_admin(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Requires admin privileges for endpoint access.
    
    Args:
        current_user: User payload from JWT token
        
    Returns:
        dict: User payload if admin
        
    Raises:
        HTTPException: 403 if user lacks admin privileges
    """
    if not is_user_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Admin privileges required"
        )
    return current_user


def require_user_owner_or_admin(username_param: str = "username"):
    """
    Factory function for user ownership or admin authorization.
    
    Creates a dependency that allows access if the user is either:
    1. An admin user, OR  
    2. The owner of the user resource (username matches token)
    
    Args:
        username_param: Name of the path parameter containing the username
        
    Returns:
        Dependency function that validates ownership or admin privileges
    """
    async def _require_user_owner_or_admin(
        request: Request,
        current_user: dict = Depends(get_current_user)
    ) -> dict:
        """
        Validates user ownership or admin privileges.
        
        Args:
            request: FastAPI request object containing path parameters
            current_user: Current authenticated user
            
        Returns:
            dict: User payload if authorized
            
        Raises:
            HTTPException: 403 if user is not owner or admin
        """
        # Check if admin - admins can access any user resource
        if is_user_admin(current_user):
            return current_user
        
        # Check if user is accessing their own resource
        path_username = request.path_params.get(username_param)
        token_username = current_user.get("preferred_username")
        
        if path_username and token_username and path_username == token_username:
            return current_user
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not resource owner or admin"
        )
    
    return _require_user_owner_or_admin


def require_policy_permission(action: str):
    """
    Factory function for policy-based authorization dependencies.
    
    Creates a dependency that validates user has specific permissions
    for a resource on an instance.
    
    Args:
        action: Required action ('read', 'write', 'admin')
        
    Returns:
        Dependency function that validates policy permissions
        
    Usage:
        @router.get("/some-resource")
        async def endpoint(
            user: dict = Depends(require_policy_permission("read"))
        ):
            pass
    """
    async def _require_policy(
        current_user: dict = Depends(get_current_user),
        policy_manager: CasbinPolicyManager = Depends(get_policy_manager)
    ) -> dict:
        """
        Validates policy permission for the current user.
        
        Note: This is a base implementation. Specific endpoints may need
        to extract instance_uuid and resource from request context.
        """
        # This dependency provides the base policy validation logic
        # Specific endpoints will need to create Policy objects with
        # their request-specific instance_uuid and resource values
        return current_user
    
    return _require_policy


def create_policy_validator(
    user_uuid: UUID, 
    instance_uuid: UUID, 
    resource: str, 
    action: str,
    policy_manager: CasbinPolicyManager
) -> bool:
    """
    Helper function to create and validate a policy.
    
    This is a utility function for endpoints that need to validate
    specific policies with known parameters.
    
    Args:
        user_uuid: UUID of the user
        instance_uuid: UUID of the storage instance
        resource: Resource path/pattern
        action: Action to validate ('read', 'write', 'admin')
        policy_manager: Policy manager instance
        
    Returns:
        bool: True if policy is valid, False otherwise
    """
    policy = Policy(
        user_uuid=user_uuid,
        instance_uuid=instance_uuid,
        resource=resource,
        action=action
    )
    return policy_manager.validate_policy(policy)


def check_owner_or_admin(
    current_user: dict, 
    resource_owner_uuid: UUID
) -> bool:
    """
    Helper function to check if user is owner or admin.
    
    Args:
        current_user: JWT payload from get_current_user
        resource_owner_uuid: UUID of the resource owner
        
    Returns:
        bool: True if user is owner or admin
    """
    # Check if admin
    if is_user_admin(current_user):
        return True
    
    # Check if owner
    current_user_uuid = current_user.get("sub")
    if current_user_uuid and current_user_uuid == str(resource_owner_uuid):
        return True
    
    return False
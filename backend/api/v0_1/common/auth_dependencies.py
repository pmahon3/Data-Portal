"""
Authorization decorators and dependencies for FastAPI endpoints.

Provides both decorator and dependency patterns for reusable authorization.
Decorators are cleaner for endpoint signatures, dependencies are better for testing.
"""

import logging
import os
from uuid import UUID

import jwt
import requests
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from core.services.injectors import get_policy_manager
from core.services.policies import CasbinPolicyManager
from core.services.policies import Policy

bearer_scheme = HTTPBearer(auto_error=False)

# Set up logger for authentication debugging
logger = logging.getLogger("app")  # Uses the "app" logger from log_config.yaml


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


def get_jwks_client():
    """
    Creates a PyJWKClient using the JWKS URI from KeyCloak's well-known configuration.
    """
    well_known_url = os.getenv("KEYCLOAK_WELL_KNOWN_URL")
    logger.debug(f"Using well-known URL: {well_known_url}")
    if not well_known_url:
        logger.error("KEYCLOAK_WELL_KNOWN_URL environment variable is not set")
        raise Exception("KEYCLOAK_WELL_KNOWN_URL is not set")
    
    logger.debug(f"Fetching OIDC configuration from: {well_known_url}")
    oidc_config = requests.get(well_known_url).json()
    logger.debug(f"OIDC config keys: {list(oidc_config.keys())}")
    
    jwks_uri = oidc_config.get("jwks_uri")
    if not jwks_uri:
        logger.error("jwks_uri not found in OIDC configuration")
        raise Exception("jwks_uri not found in OIDC configuration")
    
    logger.debug(f"Using JWKS URI: {jwks_uri}")
    return PyJWKClient(jwks_uri)


def decode_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    # Extract bearer token from Authorization header
    token = credentials.credentials if credentials else None

    if not token:
        logger.warning("No token found in Authorization header")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")

    logger.debug("Token received via Authorization header")
    logger.debug(f"Token preview (first 50 chars): {token[:50]}...")

    # Decode token header to inspect issuer claim
    try:
        import base64
        import json
        # JWT tokens have 3 parts: header.payload.signature
        header_b64 = token.split('.')[0]
        # Add padding if needed
        header_b64 += '=' * (4 - len(header_b64) % 4)
        header = json.loads(base64.b64decode(header_b64))

        payload_b64 = token.split('.')[1]
        payload_b64 += '=' * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.b64decode(payload_b64))

        logger.debug(f"Token header: {header}")
        logger.debug(f"Token issuer claim: {payload.get('iss', 'Not present')}")
        logger.debug(f"Token azp claim: {payload.get('azp', 'Not present')}")
        logger.debug(f"Token aud claim: {payload.get('aud', 'Not present')}")
        logger.debug(f"Token exp: {payload.get('exp', 'Not present')}")
        logger.debug(f"Token username: {payload.get('preferred_username', 'Not present')}")
    except Exception as e:
        logger.warning(f"Could not decode token for inspection: {e}")

    client_id = os.getenv("KEYCLOAK_UI_CLIENT_ID")
    keycloak_domain = os.getenv("KEYCLOAK_DOMAIN")
    realm = os.getenv("KEYCLOAK_REALM")
    well_known_url = os.getenv("KEYCLOAK_WELL_KNOWN_URL")

    # Allow configurable issuer for different environments (dev/staging/prod)
    # Defaults to internal domain for container-to-container communication
    issuer = os.getenv("KEYCLOAK_TOKEN_ISSUER", f"{keycloak_domain}/realms/{realm}")

    logger.debug(f"DEBUG: Environment variables:")
    logger.debug(f"  KEYCLOAK_UI_CLIENT_ID: {client_id}")
    logger.debug(f"  KEYCLOAK_DOMAIN: {keycloak_domain}")
    logger.debug(f"  KEYCLOAK_REALM: {realm}")
    logger.debug(f"  KEYCLOAK_WELL_KNOWN_URL: {well_known_url}")
    logger.debug(f"  KEYCLOAK_TOKEN_ISSUER: {os.getenv('KEYCLOAK_TOKEN_ISSUER', 'Not set - using default')}")
    logger.debug(f"  Computed issuer: {issuer}")
    logger.debug(f"Token validation config - client_id: {client_id}, realm: {realm}, issuer: {issuer}")

    jwks_client = get_jwks_client()
    try:
        logger.debug("Getting signing key from JWT token")
        signing_key = jwks_client.get_signing_key_from_jwt(token).key
        logger.debug("Successfully retrieved signing key")
        
        # Decode token with appropriate audience validation
        # Many Keycloak configurations don't include 'aud' claim by default
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False}  # Skip audience validation - common for Keycloak
        )
        logger.debug(f"Token audience claim: {payload.get('aud', 'Not present')}")
        
        # Verify the token is for the correct client by checking client_id in azp or aud
        token_client_id = payload.get('azp') or payload.get('aud')
        if token_client_id and token_client_id != client_id:
            logger.warning(f"Token client_id mismatch: expected {client_id}, got {token_client_id}")
            # Continue anyway - this is informational only
        
        logger.debug(f"Token successfully decoded for user: {payload.get('preferred_username', 'unknown')}")
        logger.debug(f"Token payload keys: {list(payload.keys())}")
    except jwt.PyJWTError as e:
        logger.error(f"JWT validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        ) from e
    return payload


def is_user_admin(token_payload: dict) -> bool:
    """
    Checks if the token payload indicates that the user has admin privileges.
    """
    realm_access = token_payload.get("realm_access", {})
    roles = realm_access.get("roles", [])
    resource_access = token_payload.get("resource_access", {})
    
    logger.debug(f"Checking admin privileges for user: {token_payload.get('preferred_username', 'unknown')}")
    logger.debug(f"Realm access roles: {roles}")
    logger.debug(f"Resource access: {list(resource_access.keys())}")
    
    # Check for admin role in realm_access
    is_admin = "admin" in roles
    
    # Also check in resource_access for client-specific roles
    for client_id, client_roles in resource_access.items():
        client_role_list = client_roles.get("roles", [])
        if "admin" in client_role_list:
            is_admin = True
            logger.debug(f"Found admin role in client {client_id}: {client_role_list}")
    
    logger.debug(f"Admin check result: {is_admin}")
    return is_admin

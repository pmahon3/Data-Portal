import logging
import os

from fastapi import HTTPException, status
from keycloak.keycloak_admin import KeycloakAdmin
from keycloak.openid_connection import KeycloakOpenIDConnection

from core.services.instances import AbstractInstanceManager
from core.services.policies import CasbinPolicyManager
from core.services.projects import AbstractProjectManager
from core.services.users import AbstractUserManager
from core.utils.encryption import get_secret_encryption_key

logger = logging.getLogger("user-manager")

# Global manager instances - created lazily on first access
_user_manager = None
_project_manager = None
_instance_manager = None
_policy_manager = None
_keycloak_admin = None


def _get_keycloak_admin() -> KeycloakAdmin:
    """
    Returns the shared Keycloak admin client, creating it lazily on first access.
    """
    global _keycloak_admin
    if _keycloak_admin is None:
        admin_secret = os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET")
        logger.info(f"Admin secret available: {'YES' if admin_secret else 'NO'}")
        logger.info(f"Admin secret length: {len(admin_secret) if admin_secret else 0}")
        logger.info(f"Admin secret preview: {admin_secret[:8]}..." if admin_secret else "Admin secret is None/empty")

        logger.info(f"KEYCLOAK_REALM: {os.getenv('KEYCLOAK_REALM')}")
        logger.info(f"KEYCLOAK_ADMIN_CLIENT_ID: {os.getenv('KEYCLOAK_ADMIN_CLIENT_ID')}")
        logger.info(f"KEYCLOAK_DOMAIN: {os.getenv('KEYCLOAK_DOMAIN')}")

        if not admin_secret:
            logger.error("Admin client secret not available during Keycloak admin initialization")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Keycloak admin client secret not available. Please wait for application startup to complete."
            )

        keycloak_connection = KeycloakOpenIDConnection(
            server_url=os.getenv("KEYCLOAK_DOMAIN"),
            realm_name=os.getenv("KEYCLOAK_REALM"),
            client_id=os.getenv("KEYCLOAK_ADMIN_CLIENT_ID"),
            client_secret_key=admin_secret,
            verify=True
        )

        _keycloak_admin = KeycloakAdmin(connection=keycloak_connection)
        logger.info("Shared KeycloakAdmin instance created, testing connection...")
        try:
            test_users = _keycloak_admin.get_users(query={"max": 1})
            logger.info(f"Connection test successful - got {len(test_users)} user(s)")
        except Exception as e:
            logger.error(f"Connection test FAILED: {e}")
            logger.error(f"Exception type: {type(e)}")
            if hasattr(e, 'response_code'):
                logger.error(f"Response code: {e.response_code}")
            if hasattr(e, 'response_body'):
                logger.error(f"Response body: {e.response_body}")
            raise

    return _keycloak_admin


def get_user_manager() -> AbstractUserManager:
    """
    Returns the user manager instance, creating it lazily on first access.
    """
    global _user_manager
    if _user_manager is None:
        # Lazy import to avoid circular dependencies
        from core.services.users import KeycloakUserManager

        logger.info("Initializing user manager...")
        logger.info("Creating KeycloakUserManager instance...")
        _user_manager = KeycloakUserManager(
            identity_manager=_get_keycloak_admin()
        )
        logger.info("KeycloakUserManager instance created successfully")

    return _user_manager


def get_project_manager() -> AbstractProjectManager:
    """
    Returns the project manager instance, creating it lazily on first access.
    """
    global _project_manager
    if _project_manager is None:
        # Lazy import to avoid circular dependencies
        from core.db.mongodb.mongo_client import get_project_instance_association_collection
        from core.services.projects import KeycloakProjectManager

        logger.info("Initializing project manager...")
        _project_manager = KeycloakProjectManager(
            identity_manager=_get_keycloak_admin(),
            project_instance_association_collection=get_project_instance_association_collection(),
            instance_manager=get_instance_manager()
        )
        logger.info("KeycloakProjectManager instance created successfully")

    return _project_manager


def get_policy_manager() -> CasbinPolicyManager:
    """
    Returns the policy manager instance, creating it lazily on first access.
    Loads all user policies from the policy store on initialization.
    """
    global _policy_manager
    if _policy_manager is None:
        # Lazy import to avoid circular dependencies
        from core.services.policies.casbin import CasbinPolicyManager

        logger.info("Initializing policy manager...")

        # Initialize policy manager with all user UUIDs to load policies from disk
        _policy_manager = CasbinPolicyManager()
        logger.info("CasbinPolicyManager instance created successfully")

    return _policy_manager


def get_instance_manager() -> AbstractInstanceManager:
    """
    Returns the instance manager instance, creating it lazily on first access.
    """
    global _instance_manager
    if _instance_manager is None:
        # Lazy import to avoid circular dependencies
        from core.services.instances import InstanceManager
        from core.db.mongodb.mongo_client import get_instance_collection

        logger.info("Initializing instance manager...")

        collection = get_instance_collection()
        _instance_manager = InstanceManager(
            collection=collection,
            encryption_key=get_secret_encryption_key()
        )

        logger.info("InstanceManager instance created successfully...")

    return _instance_manager

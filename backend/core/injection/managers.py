import os
import logging
from pathlib import Path
from fastapi import HTTPException, status
from core.management.instances import AbstractInstanceManager
from core.management.users import AbstractUserManager
from core.management.managers.policies import CasbinPolicyManager

logger = logging.getLogger("user-manager")

# Global manager instances - created lazily on first access
_user_manager = None
_instance_manager = None
_policy_manager = None


def get_user_manager() -> AbstractUserManager:
    """
    Returns the user manager instance, creating it lazily on first access.
    """
    global _user_manager
    if _user_manager is None:
        # Lazy import to avoid circular dependencies
        from core.management.managers.users.keycloak import KeycloakUserManager

        # Check if required environment variables are available
        logger.info("Initializing user manager...")
        admin_secret = os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET")
        logger.info(f"Admin secret available: {'YES' if admin_secret else 'NO'}")
        logger.info(f"Admin secret length: {len(admin_secret) if admin_secret else 0}")
        logger.info(f"Admin secret preview: {admin_secret[:8]}..." if admin_secret else "Admin secret is None/empty")

        logger.info(f"KEYCLOAK_REALM: {os.getenv('KEYCLOAK_REALM')}")
        logger.info(f"KEYCLOAK_ADMIN_CLIENT_ID: {os.getenv('KEYCLOAK_ADMIN_CLIENT_ID')}")
        logger.info(f"KEYCLOAK_DOMAIN: {os.getenv('KEYCLOAK_DOMAIN')}")

        if not admin_secret:
            logger.error("Admin client secret not available during user manager initialization")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Keycloak admin client secret not available. Please wait for application startup to complete."
            )

        logger.info("Creating KeycloakUserManager instance...")
        _user_manager = KeycloakUserManager(
            realm_name=os.getenv("KEYCLOAK_REALM"),
            client_id=os.getenv("KEYCLOAK_ADMIN_CLIENT_ID"),
            client_secret=admin_secret,
            base_url=os.getenv("KEYCLOAK_DOMAIN")
        )
        logger.info("KeycloakUserManager instance created successfully")

    return _user_manager


def get_policy_manager() -> CasbinPolicyManager:
    """
    Returns the policy manager instance, creating it lazily on first access.
    Loads all user policies from the policy store on initialization.
    """
    global _policy_manager
    if _policy_manager is None:
        # Lazy import to avoid circular dependencies
        from core.management.managers.policies.casbin.CasbinPolicyManager import CasbinPolicyManager

        # Get all user UUIDs from the user manager to load their policies
        user_manager = get_user_manager()
        user_uuids = user_manager.get_user_uuids()

        # Initialize policy manager with all user UUIDs to load policies from disk
        _policy_manager = CasbinPolicyManager(uuids=user_uuids)

    return _policy_manager


def get_instance_manager() -> AbstractInstanceManager:
    """
    Returns the instance manager instance, creating it lazily on first access.
    """
    global _instance_manager
    if _instance_manager is None:
        # Lazy import to avoid circular dependencies
        from core.management.managers.instances.InstanceManager import InstanceManager

        _instance_manager = InstanceManager()

        # Load instance configurations if available
        instance_configs_dir = os.getenv("INSTANCE_CONFIGS")
        if instance_configs_dir and Path(instance_configs_dir).exists():
            import json
            from uuid import UUID
            from core.connectivity import agent_factory
            from core.management.instances.models import Instance

            config_files = [f for f in os.listdir(instance_configs_dir) if f.endswith('.json')]
            for file in config_files:
                uuid = file.split(".")[0]
                config_path = f"{instance_configs_dir}/{file}"

                with open(config_path) as f:
                    instance_config = json.load(f)

                name = instance_config["name"]
                config_data = {
                    "flavour": instance_config["flavour"],
                    "agent": instance_config["agent"]
                }

                # Create the instance agent
                instance = agent_factory(config_data)

                # Create the instance object
                new_instance = Instance(
                    uuid=UUID(uuid),
                    name=name,
                    flavour=config_data["flavour"],
                    agent=instance
                )

                # Add the instance to the instance manager
                _instance_manager.instances.append(new_instance)

    return _instance_manager

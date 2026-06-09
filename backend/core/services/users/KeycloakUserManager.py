import logging
from uuid import UUID

from keycloak.keycloak_admin import KeycloakAdmin
from keycloak.openid_connection import KeycloakOpenIDConnection

from core.services.users import AbstractUserManager
from core.services.users.models import User, UserCreate

logger = logging.getLogger("user-manager")


class KeycloakUserManager(AbstractUserManager):

    def __init__(self, realm_name: str, client_id: str, client_secret: str, base_url: str):

        logger.info(f"Initializing KeycloakUserManager with realm={realm_name}, client_id={client_id}, base_url={base_url}")
        logger.info(f"Client Secret: {client_secret[:8] if client_secret else 'None'}... (length: {len(client_secret) if client_secret else 0})")

        keycloak_connection = KeycloakOpenIDConnection(
            server_url=base_url,
            realm_name=realm_name,
            client_id=client_id,
            client_secret_key=client_secret,
            verify=True
        )

        self.identity_manager = KeycloakAdmin(connection=keycloak_connection)
        logger.info("KeycloakAdmin instance created, testing connection...")

        # Test the connection immediately to see if credentials work
        try:
            test_users = self.identity_manager.get_users(query={"max": 1})
            logger.info(f"Connection test successful - got {len(test_users)} user(s)")
        except Exception as e:
            logger.error(f"Connection test FAILED: {e}")
            logger.error(f"Exception type: {type(e)}")
            if hasattr(e, 'response_code'):
                logger.error(f"Response code: {e.response_code}")
            if hasattr(e, 'response_body'):
                logger.error(f"Response body: {e.response_body}")
            raise

    def create_user(self, user_details: UserCreate) -> User:
        # Create user in Keycloak
        user_payload = {
            "username": user_details.username,
            "email": user_details.email,
            "enabled": True,
            "credentials": [
                {
                    "type": "password",
                    "value": user_details.password,
                    "temporary": False
                }
            ]
        }

        user_uuid = self.identity_manager.create_user(user_payload)

        if user_uuid is None:
            logger.error(f"Failed to create user in Keycloak: {user_details.username}")
            raise ValueError("Failed to create user")

        user_info = self.identity_manager.get_user(user_id=user_uuid)

        # Add roles to the user
        try:
            roles_info = [self.identity_manager.get_realm_role(role) for role in user_details.roles]
        except Exception as e:
            raise ValueError(f"Failed to get roles: {e}")

        self.identity_manager.assign_realm_roles(
            user_id=user_uuid,
            roles=roles_info
        )

        if user_uuid != user_info['id']:
            logger.error(f"User UUID mismatch for {user_details.username}")
            raise ValueError("User UUID mismatch")

        # Get the roles assigned to the user
        user_roles = self.get_user_roles(UUID(user_uuid))

        new_user = User(
            username=user_info['username'],
            uuid=user_info['id'],
            email=user_info['email'],
            roles=user_roles
        )

        return new_user

    def get_user(self, uuid: UUID) -> User:
        user_info = self.identity_manager.get_user(user_id=uuid.__str__())
        user_roles = self.get_user_roles(uuid)

        user = User(
            username=user_info['username'],
            uuid=user_info['id'],
            email=user_info['email'],
            roles=user_roles
        )
        return user

    def delete_user(self, uuid: UUID) -> bool:
        self.identity_manager.delete_user(user_id=uuid.__str__())
        return True

    def get_user_roles(self, uuid: UUID) -> list[str]:
        role_info = self.identity_manager.get_all_roles_of_user(user_id=uuid.__str__())
        # Return only the role names
        roles = [role['name'] for role in role_info['realmMappings']]
        logger.info(f"User {uuid} has {len(roles)} role(s): {roles}")
        return roles

    def get_all_users(self) -> list[User]:
        users_ = self.identity_manager.get_users()
        logger.info(f"Found {len(users_)} user(s) in Keycloak")
        result = []
        for user in users_:
            user_roles = self.get_user_roles(UUID(user['id']))
            result.append(User(
                username=user['username'],
                uuid=user['id'],
                email=user['email'],
                roles=user_roles
            ))
        return result

    def user_exists(self, user_slug: str) -> bool:
        if self.identity_manager.get_user_id(username=user_slug) is not None:
            return True
        return False

    def get_user_slug(self, uuid: UUID) -> str:
        user = self.identity_manager.get_user(uuid.__str__())
        return user['username']

    def get_user_uuid(self, user_slug: str) -> UUID:
        uuid = self.identity_manager.get_user_id(username=user_slug)
        if uuid is None:
            raise KeyError("User not found")
        return UUID(self.identity_manager.get_user_id(username=user_slug))

    def get_user_uuids(self) -> list:
        return [UUID(user['id']) for user in self.identity_manager.get_users()]

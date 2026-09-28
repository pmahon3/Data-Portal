import logging
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from keycloak.exceptions import KeycloakPostError
from keycloak.keycloak_admin import KeycloakAdmin

from core.services.users.abstract_user_manager import (
    AbstractUserManager,
    InvalidUserEmailError,
    UserAlreadyExistsError,
    UsernameRequiredError,
)
from core.services.users.models import User, UserCreate

logger = logging.getLogger("user-manager")


class KeycloakUserManager(AbstractUserManager):

    def __init__(
        self,
        identity_manager: KeycloakAdmin
    ):

        logger.info("Initializing KeycloakUserManager")
        self.identity_manager = identity_manager
        logger.info("Testing KeycloakAdmin connection...")

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
        if not user_details.username.strip():
            raise UsernameRequiredError("Username is required")

        try:
            validate_email(user_details.email, check_deliverability=False)
        except EmailNotValidError as e:
            raise InvalidUserEmailError("Invalid email format") from e

        if self.user_exists(user_details.username):
            raise UserAlreadyExistsError(user_details.username)

        # Create user in Keycloak
        user_payload = {
            "username": user_details.username,
            "email": user_details.email,
            "enabled": True,
            "credentials": [
                {
                    "type": "password",
                    "value": user_details.password,
                    "temporary": True
                }
            ]
        }

        try:
            user_uuid = self.identity_manager.create_user(user_payload)
        except KeycloakPostError as e:
            if e.response_code == 409:
                raise UserAlreadyExistsError(user_details.username) from e
            raise

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
        return UUID(self._get_user_id(user_slug))

    def get_user_uuids(self) -> list:
        return [UUID(user['id']) for user in self.identity_manager.get_users()]

    def _get_user_id(self, username: str) -> str:
        """Helper to fetch a user ID and handle missing users."""
        user_id = self.identity_manager.get_user_id(username=username)
        if not user_id:
            raise KeyError("User not found")
        return user_id

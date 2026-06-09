import logging
from uuid import UUID

from keycloak.exceptions import KeycloakGetError
from keycloak.keycloak_admin import KeycloakAdmin
from keycloak.openid_connection import KeycloakOpenIDConnection
from pymongo.collection import Collection

from core.services.instances import AbstractInstanceManager
from core.services.users import AbstractUserManager, ProjectAlreadyExistsError, ProjectNotFoundError
from core.services.users.models import User, UserCreate

logger = logging.getLogger("user-manager")


class KeycloakUserManager(AbstractUserManager):

    def __init__(
        self,
        realm_name: str,
        client_id: str,
        client_secret: str,
        base_url: str,
        project_instance_association_collection: Collection,
        instance_manager: AbstractInstanceManager
    ):

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
        self.project_instance_association_collection = project_instance_association_collection
        self.instance_manager = instance_manager
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
        return UUID(self._get_user_id(user_slug))

    def get_user_uuids(self) -> list:
        return [UUID(user['id']) for user in self.identity_manager.get_users()]

    def get_all_projects(self) -> list[str]:
        return sorted({group["name"] for group in self.identity_manager.get_groups() if group.get("name")})

    def get_project_id(self, project_name: str) -> str:
        return self._get_group(project_name)["id"]

    def _get_group(self, project_name: str, is_manager: bool = False) -> dict:
        """Helper to fetch a group and handle 404 Keycloak errors."""
        path = f"/{project_name}/managers" if is_manager else f"/{project_name}"
        try:
            return self.identity_manager.get_group_by_path(path)
        except KeycloakGetError as e:
            if getattr(e, "response_code", None) == 404:
                raise ProjectNotFoundError(project_name) from e
            raise

    def _get_user_id(self, username: str) -> str:
        """Helper to fetch a user ID and handle missing users."""
        user_id = self.identity_manager.get_user_id(username=username)
        if not user_id:
            raise KeyError("User not found")
        return user_id

    def create_project(self, project_name: str) -> str:
        project_name = project_name.strip()
        if not project_name:
            raise ValueError("Project name is required")
        if "/" in project_name:
            raise ValueError("Project name cannot contain '/'")

        project_path = f"/{project_name}"

        # Check for duplicate group
        try:
            self.identity_manager.get_group_by_path(project_path)
            raise ProjectAlreadyExistsError(project_name)
        except KeycloakGetError as e:
            if getattr(e, "response_code", None) != 404:
                raise

        # Create root group
        root_group_id = self.identity_manager.create_group({"name": project_name})

        if not root_group_id:
            logger.error(f"Failed to create project group in Keycloak: {project_name}")
            raise ValueError("Failed to create project")

        # Create "/{project}/managers" subgroup
        try:
            self.identity_manager.create_group({"name": "managers"}, parent=root_group_id)
        except Exception:
            logger.error(f"Failed to create managers subgroup for project: {project_name}")
            raise

        return project_name

    def delete_project(self, project_name: str) -> None:
        group = self._get_group(project_name)
        group_id = group["id"]
        # Deleting the root group with also delete the child "managers" group
        self.identity_manager.delete_group(group_id)
        self.project_instance_association_collection.delete_many({"project_id": group_id})

    def get_project_users(self, project_name: str) -> list[str]:
        group = self._get_group(project_name)
        members = self.identity_manager.get_group_members(group["id"])
        return sorted(member["username"] for member in members if member.get("username"))

    def get_project_managers(self, project_name: str) -> list[str]:
        group = self._get_group(project_name, is_manager=True)
        members = self.identity_manager.get_group_members(group["id"])
        return sorted(member["username"] for member in members if member.get("username"))

    def get_project_storage_instances(self, project_name: str) -> list[str]:
        group_id = self.get_project_id(project_name)
        # Associations store UUIDs so instance renames do not break project membership.
        docs = self.project_instance_association_collection.find(
            {"project_id": group_id},
            {"_id": 0, "instance_uuid": 1}
        )
        instance_uuids = []
        for doc in docs:
            try:
                instance_uuids.append(UUID(str(doc["instance_uuid"])))
            except (KeyError, ValueError):
                logger.warning(f"Skipping invalid project-instance association for project '{project_name}': {doc}")

        instances = self.instance_manager.get_instances_by_uuid(instance_uuids)
        return sorted(instance.name for instance in instances)

    def add_project_user(self, project_name: str, username: str) -> None:
        group = self._get_group(project_name)
        user_id = self._get_user_id(username)
        self.identity_manager.group_user_add(user_id=user_id, group_id=group["id"])

    def remove_project_user(self, project_name: str, username: str) -> None:
        group = self._get_group(project_name)
        user_id = self._get_user_id(username)
        self.identity_manager.group_user_remove(user_id=user_id, group_id=group["id"])

    def add_project_manager(self, project_name: str, username: str) -> None:
        group = self._get_group(project_name, is_manager=True)
        user_id = self._get_user_id(username)
        self.identity_manager.group_user_add(user_id=user_id, group_id=group["id"])

    def remove_project_manager(self, project_name: str, username: str) -> None:
        group = self._get_group(project_name, is_manager=True)
        user_id = self._get_user_id(username)
        self.identity_manager.group_user_remove(user_id=user_id, group_id=group["id"])

    def add_project_storage_instance(self, project_name: str, instance_name: str) -> None:
        group_id = self.get_project_id(project_name)
        instance_uuid = self.instance_manager.get_instance_uuid(instance_name)
        # Keep the public API name-based, but persist the stable instance UUID.
        self.project_instance_association_collection.update_one(
            {"project_id": group_id, "instance_uuid": str(instance_uuid)},
            {"$setOnInsert": {"project_id": group_id, "instance_uuid": str(instance_uuid)}},
            upsert=True
        )

    def remove_project_storage_instance(self, project_name: str, instance_name: str) -> None:
        group_id = self.get_project_id(project_name)
        instance_uuid = self.instance_manager.get_instance_uuid(instance_name)
        self.project_instance_association_collection.delete_one(
            {"project_id": group_id, "instance_uuid": str(instance_uuid)}
        )

    def remove_instance_from_all_projects(self, instance_uuid: UUID) -> None:
        self.project_instance_association_collection.delete_many(
            {"instance_uuid": str(instance_uuid)}
        )

    def _managed_project_names(self, current_user: dict) -> set[str]:
        managed_projects = set()
        for path in current_user.get("projects", []):
            clean_path = str(path).strip("/")
            if clean_path.endswith("/managers"):
                managed_projects.add(clean_path.split("/")[0])
        return managed_projects

    def can_manage_instance_for_user(self, current_user: dict, target_username: str, instance_uuid: UUID) -> bool:
        for project_name in self._managed_project_names(current_user):
            try:
                group = self._get_group(project_name)
                managers_group = self._get_group(project_name, is_manager=True)
            except ProjectNotFoundError:
                continue

            association = self.project_instance_association_collection.find_one(
                {"project_id": group["id"], "instance_uuid": str(instance_uuid)},
                {"_id": 1}
            )
            if not association:
                continue

            # Check project users group
            members = self.identity_manager.get_group_members(group["id"])
            if any(member.get("username") == target_username for member in members):
                return True

            # Also check managers group so managers can create policies
            # for themselves and other managers without being project users
            manager_members = self.identity_manager.get_group_members(managers_group["id"])
            if any(member.get("username") == target_username for member in manager_members):
                return True

        return False

    def is_project_manager(self, username: str, project_name: str) -> bool:
        user_id = self.identity_manager.get_user_id(username=username)
        if not user_id:
            return False
            
        user_groups = self.identity_manager.get_user_groups(user_id=user_id)
        target_path = f"/{project_name}/managers"
        
        return any(group.get("path") == target_path for group in user_groups)

import logging
from uuid import UUID

from keycloak.exceptions import KeycloakGetError
from keycloak.keycloak_admin import KeycloakAdmin
from pymongo.collection import Collection

from core.services.instances import AbstractInstanceManager
from core.services.projects import AbstractProjectManager, ProjectAlreadyExistsError, ProjectNotFoundError

logger = logging.getLogger("project-manager")


class KeycloakProjectManager(AbstractProjectManager):

    def __init__(
        self,
        identity_manager: KeycloakAdmin,
        project_instance_association_collection: Collection,
        instance_manager: AbstractInstanceManager
    ):
        self.identity_manager = identity_manager
        self.project_instance_association_collection = project_instance_association_collection
        self.instance_manager = instance_manager

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
        target_user_id = self.identity_manager.get_user_id(username=target_username)
        if not target_user_id:
            return False

        # Get a list of target users keycloak groups
        target_group_paths = {
            str(group.get("path", "")).rstrip("/")
            for group in self.identity_manager.get_user_groups(user_id=target_user_id)
            if group.get("path")
        }

        # For each project that the manager has access to
        for project_name in self._managed_project_names(current_user):
            project_path = f"/{project_name}"
            managers_path = f"{project_path}/managers"
            # Check if target user belongs to one of the managed projects
            if project_path not in target_group_paths and managers_path not in target_group_paths:
                continue

            try:
                group = self._get_group(project_name)
            except ProjectNotFoundError:
                continue
            
            # Find association between target user's project and target instance
            association = self.project_instance_association_collection.find_one(
                {"project_id": group["id"], "instance_uuid": str(instance_uuid)},
                {"_id": 1}
            )
            if association:
                return True

        return False

    def is_project_manager(self, username: str, project_name: str) -> bool:
        user_id = self.identity_manager.get_user_id(username=username)
        if not user_id:
            return False

        user_groups = self.identity_manager.get_user_groups(user_id=user_id)
        target_path = f"/{project_name}/managers"

        return any(group.get("path") == target_path for group in user_groups)

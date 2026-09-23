import logging

from fastapi import APIRouter, Depends, HTTPException, status

from api.v0_1.common.auth_dependencies import is_user_admin, require_admin, require_admin_or_manager, require_admin_or_project_manager
from api.v0_1.common.models import ProjectCreateRequest, ProjectResponse, ProjectStorageInstanceRequest, ProjectUserRequest
from core.services.injectors import get_instance_manager, get_project_manager
from core.services.instances import AbstractInstanceManager
from core.services.projects import (
    AbstractProjectManager,
    InvalidProjectNameError,
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
)

projects_router = APIRouter(prefix="/projects", tags=["Project Management"])
logger = logging.getLogger("api.endpoints")


@projects_router.get("", response_model=list[ProjectResponse])
async def list_projects(
    current_user: dict = Depends(require_admin_or_manager),
    project_manager: AbstractProjectManager = Depends(get_project_manager)
) -> list[ProjectResponse]:
    try:
        if is_user_admin(current_user):
            # Admins see all projects
            project_names = project_manager.get_all_projects()
        else:
            # Managers see what they're assigned to
            managed_projects = set()
            # Clean path for expected output
            for path in current_user.get("projects", []):
                clean_path = path.strip("/")
                if clean_path.endswith("/managers"):
                    project_name = clean_path.split("/")[0]
                    managed_projects.add(project_name)
            
            project_names = sorted(managed_projects)

        project_responses = []
        for name in project_names:
            project_responses.append(ProjectResponse(
                name=name,
                users=project_manager.get_project_users(name),
                managers=project_manager.get_project_managers(name),
                storageInstances=project_manager.get_project_storage_instances(name)
            ))
    except Exception as e:
        logger.error(f"Failed to retrieve projects: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve projects"
        )

    return project_responses


@projects_router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreateRequest,
    admin_user: dict = Depends(require_admin),
    project_manager: AbstractProjectManager = Depends(get_project_manager)
) -> ProjectResponse:
    try:
        project_name = project_manager.create_project(project_data.name)
    except ProjectAlreadyExistsError:
        logger.error(f"Project '{project_data.name}' already exists")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project already exists"
        )
    except ValueError as e:
        error_msg = str(e)
        logger.error(f"Invalid project create request for '{project_data.name}': {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    except Exception as e:
        logger.error(f"Failed to create project '{project_data.name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create project"
        )

    logger.info(f"Created project '{project_name}'")
    return ProjectResponse(
        name=project_name,
        users=project_manager.get_project_users(project_name),
        managers=project_manager.get_project_managers(project_name),
        storageInstances=project_manager.get_project_storage_instances(project_name)
    )


@projects_router.patch("/{project_name}", response_model=ProjectResponse)
async def rename_project(
    project_name: str,
    project_data: ProjectCreateRequest,
    current_user: dict = Depends(require_admin_or_project_manager()),
    project_manager: AbstractProjectManager = Depends(get_project_manager)
) -> ProjectResponse:
    try:
        new_name = project_manager.rename_project(project_name, project_data.name)
    except ProjectNotFoundError:
        logger.error(f"Project '{project_name}' not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    except ProjectAlreadyExistsError:
        logger.error(f"Project '{project_data.name}' already exists")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project already exists"
        )
    except InvalidProjectNameError:
        logger.error(f"Invalid project name '{project_data.name}' for rename of '{project_name}'")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project name is required and cannot contain '/'"
        )
    except Exception as e:
        logger.error(f"Failed to rename project '{project_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rename project"
        )

    logger.info(f"Renamed project '{project_name}' to '{new_name}'")
    return ProjectResponse(
        name=new_name,
        users=project_manager.get_project_users(new_name),
        managers=project_manager.get_project_managers(new_name),
        storageInstances=project_manager.get_project_storage_instances(new_name)
    )


@projects_router.delete("/{project_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_name: str,
    admin_user: dict = Depends(require_admin),
    project_manager: AbstractProjectManager = Depends(get_project_manager)
) -> None:
    try:
        project_manager.delete_project(project_name)
    except ProjectNotFoundError:
        logger.error(f"Project '{project_name}' not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    except Exception as e:
        logger.error(f"Failed to delete project '{project_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete project"
        )

    logger.info(f"Deleted project '{project_name}'")


@projects_router.post("/{project_name}/users", response_model=ProjectResponse)
async def add_project_user(
    project_name: str,
    user_data: ProjectUserRequest,
    current_user: dict = Depends(require_admin_or_project_manager()),
    project_manager: AbstractProjectManager = Depends(get_project_manager)
) -> ProjectResponse:
    try:
        project_manager.add_project_user(project_name, user_data.username)
        return ProjectResponse(
            name=project_name,
            users=project_manager.get_project_users(project_name),
            managers=project_manager.get_project_managers(project_name),
            storageInstances=project_manager.get_project_storage_instances(project_name)
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    except Exception as e:
        logger.error(f"Failed to add user '{user_data.username}' to project '{project_name}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add project user")


@projects_router.delete("/{project_name}/users/{username}", response_model=ProjectResponse)
async def remove_project_user(
    project_name: str,
    username: str,
    current_user: dict = Depends(require_admin_or_project_manager()),
    project_manager: AbstractProjectManager = Depends(get_project_manager)
) -> ProjectResponse:
    try:
        project_manager.remove_project_user(project_name, username)
        return ProjectResponse(
            name=project_name,
            users=project_manager.get_project_users(project_name),
            managers=project_manager.get_project_managers(project_name),
            storageInstances=project_manager.get_project_storage_instances(project_name)
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    except Exception as e:
        logger.error(f"Failed to remove user '{username}' from project '{project_name}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove project user")


@projects_router.post("/{project_name}/managers", response_model=ProjectResponse)
async def add_project_manager(
    project_name: str,
    user_data: ProjectUserRequest,
    admin_user: dict = Depends(require_admin),
    project_manager: AbstractProjectManager = Depends(get_project_manager)
) -> ProjectResponse:
    try:
        project_manager.add_project_manager(project_name, user_data.username)
        return ProjectResponse(
            name=project_name,
            users=project_manager.get_project_users(project_name),
            managers=project_manager.get_project_managers(project_name),
            storageInstances=project_manager.get_project_storage_instances(project_name)
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    except Exception as e:
        logger.error(f"Failed to add manager '{user_data.username}' to project '{project_name}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add project manager")


@projects_router.delete("/{project_name}/managers/{username}", response_model=ProjectResponse)
async def remove_project_manager(
    project_name: str,
    username: str,
    admin_user: dict = Depends(require_admin),
    project_manager: AbstractProjectManager = Depends(get_project_manager)
) -> ProjectResponse:
    try:
        project_manager.remove_project_manager(project_name, username)
        return ProjectResponse(
            name=project_name,
            users=project_manager.get_project_users(project_name),
            managers=project_manager.get_project_managers(project_name),
            storageInstances=project_manager.get_project_storage_instances(project_name)
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    except Exception as e:
        logger.error(f"Failed to remove manager '{username}' from project '{project_name}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove project manager")


@projects_router.post("/{project_name}/storage-instances", response_model=ProjectResponse)
async def add_project_storage_instance(
    project_name: str,
    instance_data: ProjectStorageInstanceRequest,
    admin_user: dict = Depends(require_admin),
    project_manager: AbstractProjectManager = Depends(get_project_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager)
) -> ProjectResponse:
    try:
        instance_manager.get_instance_uuid(instance_data.instance_name)
        project_manager.add_project_storage_instance(project_name, instance_data.instance_name)
        return ProjectResponse(
            name=project_name,
            users=project_manager.get_project_users(project_name),
            managers=project_manager.get_project_managers(project_name),
            storageInstances=project_manager.get_project_storage_instances(project_name)
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage instance not found")
    except Exception as e:
        logger.error(f"Failed to add storage instance '{instance_data.instance_name}' to project '{project_name}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add project storage instance")


@projects_router.delete("/{project_name}/storage-instances/{instance_name}", response_model=ProjectResponse)
async def remove_project_storage_instance(
    project_name: str,
    instance_name: str,
    admin_user: dict = Depends(require_admin),
    project_manager: AbstractProjectManager = Depends(get_project_manager)
) -> ProjectResponse:
    try:
        project_manager.remove_project_storage_instance(project_name, instance_name)
        return ProjectResponse(
            name=project_name,
            users=project_manager.get_project_users(project_name),
            managers=project_manager.get_project_managers(project_name),
            storageInstances=project_manager.get_project_storage_instances(project_name)
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except Exception as e:
        logger.error(f"Failed to remove storage instance '{instance_name}' from project '{project_name}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove project storage instance")

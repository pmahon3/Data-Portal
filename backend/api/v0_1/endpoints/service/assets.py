import logging
from uuid import UUID
from treelib import node

from fastapi import HTTPException, APIRouter, Depends, status, Query
from fastapi.responses import JSONResponse

from core.injection import get_policy_manager
from core.injection.managers import get_instance_manager, get_user_manager
from api.v0_1.endpoints.service.auth import decode_token
from ..auth_dependencies import require_admin
from api.v0_1.endpoints.service.models import (GetAssetRequest, GetAssetResponse, PutAssetRequest, PutAssetResponse,
                                               DeleteAssetRequest, DeleteAssetResponse,
                                               UserHomeData, UserAssetsData, AssetManagementData)
from .utils import convert_file_tree_to_dict
from core.management.instances import AbstractInstanceManager
from core.management.managers.policies import CasbinPolicyManager
from core.management.policies import Policy
from core.management.users import AbstractUserManager

assets_router = APIRouter(prefix='/assets', tags=["Asset Management"])
logger = logging.getLogger("api.endpoints")


@assets_router.put("/upload", dependencies=[Depends(decode_token)])
def put_asset(asset: PutAssetRequest = Depends(),
              user: dict = Depends(decode_token),
              user_manager: AbstractUserManager = Depends(get_user_manager),
              policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
              instance_manager: AbstractInstanceManager = Depends(get_instance_manager)
              ) -> PutAssetResponse:

    logger.info(f"Asset upload request from user '{user['preferred_username']}' for instance '{asset.instance_name}', resource '{asset.resource}'")
    
    # Get user UUID from token payload
    user_uuid = user_manager.get_user_uuid(user['preferred_username'])
    instance_name = asset.instance_name
    instance_uuid = instance_manager.get_instance_uuid(instance_name)
    resource = asset.resource

    policy = Policy(
        user_uuid=user_uuid,
        instance_uuid=instance_uuid,
        resource=resource,
        action='write'
    )

    if policy_manager.validate_policy(policy):
        try:
            agent = instance_manager.get_instance_by_uuid(instance_uuid).agent
        except KeyError:
            logger.error(f"Instance '{instance_name}' not found for asset upload")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Instance {instance_name} not found.")

        presigned_urls, file_paths = agent.generate_access_link(str(resource), 'write', 3600)
        print(presigned_urls)
        return PutAssetResponse(
            presigned_urls=presigned_urls,
            file_paths=file_paths
        )


    else:
        logger.error(f"User {user['preferred_username']} denied write access to resource '{resource}' on instance '{instance_name}'")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="User does not have write access to this resource")


@assets_router.delete("/delete", dependencies=[Depends(decode_token)])
def delete_asset(asset: DeleteAssetRequest = Depends(),
                 user: dict = Depends(decode_token),
                 user_manager: AbstractUserManager = Depends(get_user_manager),
                 policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
                 instance_manager: AbstractInstanceManager = Depends(get_instance_manager)
                 ) -> DeleteAssetResponse:

    logger.info(f"Asset deletion request from user '{user['preferred_username']}' for instance '{asset.instance_name}', resource '{asset.resource}'")
    
    # Get user UUID from token payload
    user_uuid = user_manager.get_user_uuid(user['preferred_username'])
    instance_name = asset.instance_name
    instance_uuid = instance_manager.get_instance_uuid(instance_name)
    resource = asset.resource

    policy = Policy(
        user_uuid=user_uuid,
        instance_uuid=instance_uuid,
        resource=resource,
        action='delete'
    )

    if policy_manager.validate_policy(policy):
        try:
            agent = instance_manager.get_instance_by_uuid(instance_uuid).agent
        except KeyError:
            logger.error(f"Instance '{instance_name}' not found for asset deletion")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Instance {instance_name} not found.")

        presigned_urls, file_paths = agent.generate_access_link(str(resource), 'delete', 3600)
        return DeleteAssetResponse(
            presigned_urls=presigned_urls,
            file_paths=file_paths
        )

    else:
        logger.error(f"User {user['preferred_username']} denied delete access to resource '{resource}' on instance '{instance_name}'")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="User does not have delete access to this resource")


@assets_router.get("/download", dependencies=[Depends(decode_token)])
def get_asset(asset: GetAssetRequest = Depends(),
              user: dict = Depends(decode_token),
              user_manager: AbstractUserManager = Depends(get_user_manager),
              policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
              instance_manager: AbstractInstanceManager = Depends(get_instance_manager)
              ) -> GetAssetResponse:

    logger.info(f"Asset download request from user '{user['preferred_username']}' for instance '{asset.instance_name}', resource '{asset.resource}', action '{asset.action}'")
    
    # Get the user uuid
    user_uuid = user_manager.get_user_uuid(user['preferred_username'])

    #
    try:
        instance_uuid = instance_manager.get_instance_uuid(asset.instance_name)
    except KeyError:
        logger.error(f"Instance '{asset.instance_name}' not found for asset download")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Instance {asset.instance_name} not found.")

    # Build the policy
    policy = Policy(
        user_uuid=user_uuid,
        instance_uuid=instance_uuid,
        resource=asset.resource,
        action=asset.action
    )

    if policy_manager.validate_policy(policy):
        agent = instance_manager.get_instance_by_uuid(instance_uuid).agent
        try:
            presigned_urls, file_paths = agent.generate_access_link(policy.resource, policy.action, 600)
        except ValueError as e:
            logger.error(f"Unable to generate presigned URL for resource '{policy.resource}' on instance '{asset.instance_name}': {str(e)}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Unable to generate presigned URL: {str(e)}")
        return GetAssetResponse(
            presigned_urls=presigned_urls,
            file_paths=file_paths
        )
    else:
        logger.error(f"User {user['preferred_username']} denied {asset.action} access to resource '{asset.resource}' on instance '{asset.instance_name}'")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="User does not have access to the specified resource")


# User Asset Data instances

@assets_router.get("/user-home-data",
                  response_model=UserHomeData,
                  summary="Get user home page data", 
                  description="Retrieve user's accessible file trees and instances for home page.",
                  dependencies=[Depends(decode_token)])
async def get_user_home_data(
        token_payload: dict = Depends(decode_token),
        policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
        instance_manager: AbstractInstanceManager = Depends(get_instance_manager)
) -> UserHomeData:
    """
    Get aggregated data for user home page.
    """
    uid = token_payload.get("preferred_username")

    # Get all storage instance names the user has read access to
    instance_names = set([policy[1] for policy in policy_manager.get_user_policies(uid)])
    user_file_tree = dict.fromkeys(instance_names)

    # Loop through each storage instance and filter its file tree
    storage_instances = instance_manager.get_instances(instance_names)
    for instance in storage_instances.keys():
        def node_filter(n: node):
            vals = (uid, instance, n.identifier, 'write')
            return policy_manager.enforcer.enforce(*vals)

        user_file_tree[instance] = convert_file_tree_to_dict(
            storage_instances[instance].filter_file_tree(node_filter)
        )
        logger.debug(f"Filtered file tree for instance '{instance}' for user '{uid}'")
    
    logger.info(f"Successfully retrieved user home data for '{uid}' with {len(storage_instances)} instances")
    return UserHomeData(assets=user_file_tree, instances=storage_instances)


@assets_router.get("/user-assets-data", 
                  response_model=UserAssetsData,
                  summary="Get user assets page data",
                  description="Retrieve user's file trees organized by instance UUID.",
                  dependencies=[Depends(decode_token)])
async def get_user_assets_data(
        token_payload: dict = Depends(decode_token),
        policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
        instance_manager: AbstractInstanceManager = Depends(get_instance_manager)
) -> UserAssetsData:
    """
    Get aggregated data for user assets page.
    """
    # Retrieve the user's user_uuid from the token payload
    uuid = token_payload.get("sub")

    # Get all storage access points the user has read access to
    instance_point_uids = set([UUID(policy[1]) for policy in policy_manager.get_user_policies(uuid)])
    instances = {instance.uuid: instance for instance in instance_manager.get_instances_by_uuid(list(instance_point_uids))}

    file_trees = {}

    # Loop through each storage instance and filter its file tree
    for uid, agent in instances.items():
        def node_filter(n: node):
            vals = (uuid, str(uid), n.identifier, '*')
            return policy_manager.validate_policy(*vals)

        file_trees[str(uid)] = convert_file_tree_to_dict(
            agent.filter_file_tree(node_filter)
        )

    instance_names_map = {instance.name: str(uid) for uid, instance in instances.items()}
    
    logger.info(f"Successfully retrieved user assets data for UUID '{uuid}' with {len(instances)} instances")
    return UserAssetsData(assets=file_trees, instances=instance_names_map)


# LEGACY ENDPOINT superceded by /api/assets/dashboard/{instance}
# Currently unused. Provides a dashboard with file trees for all accessible instances
@assets_router.get(
    "/dashboard",
    response_model=AssetManagementData,
    summary="Get asset management dashboard data",
    description="Admin dashboard with file trees and instance mappings for asset management interface."
)
async def get_asset_dashboard(
    admin_user: dict = Depends(require_admin),
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
        user_manager: AbstractUserManager = Depends(get_user_manager),
        refresh: bool = Query(True, description="If true, rebuild file trees before responding")

) -> AssetManagementData:
    """
    Get aggregated data for asset management dashboard (admin only).
    
    Provides file trees and instance information for administrative
    asset management interface.
    
    Args:
        admin_user: Current user (must have admin privileges)
        policy_manager: Policy manager dependency
        instance_manager: Instance manager dependency
        
    Returns:
        AssetManagementData: Dashboard data with assets and instances
    """
    # Retrieve the user's user_uuid from the token payload
    subject_uuid = user_manager.get_user_uuid(admin_user.get("preferred_username"))

    uuid = admin_user.get("sub")
    logger.info(f"preferred_username: {admin_user.get('preferred_username')}")
    logger.info(f"sub (keycloak): {admin_user.get('sub')}")
    logger.info(f"internal subject_uuid: {subject_uuid}")

    policies = policy_manager.get_user_policies(subject_uuid)
    logger.debug(f"policies_len: {len(policies)}, sample: {policies}")
    # Get all storage access points the user has read access to
    instance_uuids = list(
        set(policy.instance_uuid for policy in policy_manager.get_user_policies(uuid))
    )
    instances = instance_manager.get_instances_by_uuid(instance_uuids)

    # Refresh file trees if requested (using smart refresh for efficiency)
    if refresh:
        for instance in instances:
            try:
                instance.agent.smart_refresh_file_tree()
            except Exception as e:
                # don't fail the whole request on a single agent refresh error
                logger.warning(f"Failed to refresh tree for {instance.name}: {e}")

    file_trees = {}
    for instance in instances:

        f_trees = instance.agent.partition_file_tree_by_access(
            policy_manager, uuid, instance.uuid, ["read", "write", "delete"]
        )
        if f_trees is not None:
            file_trees[str(instance.uuid)] = {
                access_type: convert_file_tree_to_dict(tree)
                for access_type, tree in f_trees.items()
            }

    # Convert to simple string → string mapping for JSON encoding
    instance_names = {instance.name: str(instance.uuid) for instance in instances}

    return AssetManagementData(assets=file_trees, instances=instance_names)


# Get assets for a specific instance to allow for lazy loading
@assets_router.get(
    "/dashboard/{instance}",
    response_model=AssetManagementData,
    summary="Fetch dashboard assets for a specific instance",
    description="Retrieve file trees and instance information for a specific storage instance."
)
async def get_instance_assets(
    instance: str,
    admin_user: dict = Depends(require_admin), # Maybe better to use require_user_owner_or_admin or just current user to allow for non-admin use
    policy_manager: CasbinPolicyManager = Depends(get_policy_manager),
    instance_manager: AbstractInstanceManager = Depends(get_instance_manager),
    refresh: bool = Query(True, description="If true, rebuild file trees before responding"),
) -> AssetManagementData:
    """
    Gets a list of accessible assets for a specific instance.
    
    Provides file trees and instance information for the specified instance,
    partitioned by access type (read, write, delete).
    
    Args:
        instance: UUID of the instance to fetch assets
        admin_user: Current user (must have admin privileges)
        policy_manager: Policy manager dependency
        instance_manager: Instance manager dependency
        refresh: Whether the tree should be rebuilt before responding
        
    Returns:
        AssetManagementData: Dashboard data with assets and instances
    """
    # Get the UUID of the current user
    subject_uuid = admin_user.get("sub")
    logger.info(f"preferred_username: {admin_user.get('preferred_username')}")
    logger.info(f"internal subject_uuid: {subject_uuid}")

    # Get the details about the specified instance
    try:
        instance_uuid = UUID(instance)
        instance_details = instance_manager.get_instance_by_uuid(instance_uuid)
    except ValueError:
        logger.error(f"Invalid UUID format: '{instance}'")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid UUID format: {instance}")
    except KeyError:
        logger.error(f"Instance '{instance}' not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Instance {instance} not found.")

    # Refresh file trees if requested (using smart refresh for efficiency)
    if refresh:
        try:
            instance_details.agent.smart_refresh_file_tree()
        except Exception as e:
            logger.warning(f"Failed to refresh tree for {instance_details.name}: {e}")

    # Build the file trees partitioned by access type
    file_trees = {}
    f_trees = instance_details.agent.partition_file_tree_by_access(
        policy_manager, subject_uuid, instance_details.uuid, ["read", "write", "delete"]
    )
    
    if f_trees is not None:
        file_trees[str(instance_details.uuid)] = {
            access_type: convert_file_tree_to_dict(tree)
            for access_type, tree in f_trees.items()
        }

    # Create instance name mapping
    instance_names = {instance_details.name: str(instance_details.uuid)}
    
    logger.info(f"Successfully retrieved instance assets for '{instance}' requested by user '{admin_user.get('preferred_username')}'")
    
    return AssetManagementData(assets=file_trees, instances=instance_names)
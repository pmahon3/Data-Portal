from fastapi import APIRouter

from api.v0_1.endpoints.service.auth import auth_router
from api.v0_1.endpoints.service.assets import assets_router
from api.v0_1.endpoints.service.users import users_router
from api.v0_1.endpoints.service.policies import policies_router
from api.v0_1.endpoints.service.instances import instances_router
from api.v0_1.endpoints.service.health import router as health_router

service_router = APIRouter(tags=["Service"])

# Entity-based service routers
service_router.include_router(auth_router)
service_router.include_router(users_router)
service_router.include_router(policies_router)
service_router.include_router(instances_router)
service_router.include_router(assets_router)
service_router.include_router(health_router)

from api.v0_1.endpoints.service.s3_endpoints import router as s3_router
service_router.include_router(s3_router)

from api.v0_1.endpoints.service.file_tree_db import router as tree_db_router
service_router.include_router(tree_db_router)

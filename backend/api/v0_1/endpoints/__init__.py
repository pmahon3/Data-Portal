from fastapi import APIRouter

from .assets import assets_router
from .auth import auth_router
from .file_tree_db import router as tree_db_router
from .health import router as health_router
from .instances import instances_router
from .policies import policies_router
from .s3_endpoints import router as s3_router
from .users import users_router

application_router = APIRouter(prefix="/api")

application_router.include_router(auth_router)
application_router.include_router(users_router)
application_router.include_router(policies_router)
application_router.include_router(instances_router)
application_router.include_router(assets_router)
application_router.include_router(health_router)
application_router.include_router(s3_router)
application_router.include_router(tree_db_router)

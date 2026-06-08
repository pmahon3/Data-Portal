from core.db.mongodb.init_db import ensure_instance_indexes, ensure_project_instance_association_indexes
from core.db.postgres.init_db import ensure_roots_for_instances
from core.db.postgres.session import AsyncSessionMaker
from core.services.injectors import get_instance_manager
import logging

logger = logging.getLogger(__name__)


# Initialize mongo indexes as unique
def init_mongo_indexes():
    ensure_instance_indexes()
    ensure_project_instance_association_indexes()

#DB init for s3
async def init_db_roots():
    instance_manager = get_instance_manager()
    async with AsyncSessionMaker() as session:
        await ensure_roots_for_instances(session, instance_manager)

# Central place to run all startup tasks such as DB init. We may end up adding more start up tasks
async def run_startup_tasks():
    logger.info("Running MongoDB startup tasks")
    init_mongo_indexes()
    logger.info("Completed MongoDB startup tasks")

    logger.info("Running postgres startup tasks")
    await init_db_roots()
    logger.info("Completed postgres startup tasks")

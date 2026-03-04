
from core.db.postgres.session import AsyncSessionMaker
from core.db.postgres.init_db import ensure_roots_for_instances
from core.injection.managers import get_instance_manager

#DB init for s3
async def init_db_roots():
    instance_manager = get_instance_manager()
    async with AsyncSessionMaker() as session:
        await ensure_roots_for_instances(session, instance_manager)

# Central place to run all startup tasks such as DB init. We may end up adding more start up tasks
async def run_startup_tasks():

    await init_db_roots()

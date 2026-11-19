from core.db.mongodb.init_db import ensure_instance_indexes, ensure_project_instance_association_indexes
from core.db.postgres.init_db import ensure_roots_for_instances
from core.db.postgres.session import AsyncSessionMaker
from core.services.injectors import get_instance_manager
import logging
from pathlib import Path

from core.db.postgres.session import engine

logger = logging.getLogger(__name__)

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "core/db/postgres/scripts/schema.sql"

# The advisory lock that lets one backend process at a time create the schema. Any fixed number
# works, as long as every process uses the same one; nothing else here uses advisory locks.
SCHEMA_LOCK_ID = 1


# Create the PostgreSQL extensions, tables and indexes if they don't exist, so the backend
# starts on a blank database. Safe on every start: schema.sql uses IF NOT EXISTS.
async def init_db_schema():
    sql = SCHEMA_SQL.read_text()
    logger.info("Ensuring PostgreSQL tables")
    async with engine.connect() as conn:
        raw = (await conn.get_raw_connection()).driver_connection
        # One transaction, holding a lock that other backends starting at the same time wait on:
        # IF NOT EXISTS alone doesn't stop two processes creating the same object at once. The lock
        # is released when the transaction ends. asyncpg's own execute runs a script of several
        # statements; SQLAlchemy's runs one.
        async with raw.transaction():
            await raw.execute(f"SELECT pg_advisory_xact_lock({SCHEMA_LOCK_ID})")
            await raw.execute(sql)
    logger.info("PostgreSQL tables are ready")


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
    await init_db_schema()
    await init_db_roots()
    logger.info("Completed postgres startup tasks")

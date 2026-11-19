from core.db.mongodb.init_db import ensure_instance_indexes, ensure_project_instance_association_indexes
from core.db.postgres.init_db import ensure_roots_for_instances
from core.db.postgres.session import AsyncSessionMaker
from core.services.injectors import get_instance_manager
import logging
from pathlib import Path

from core.db.postgres.session import engine

logger = logging.getLogger(__name__)

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "core/db/postgres/scripts/schema.sql"


# Create the PostgreSQL extensions, tables and indexes if they don't exist, so the backend
# starts on a blank database. Safe on every start: schema.sql uses IF NOT EXISTS.
async def init_db_schema():
    sql = SCHEMA_SQL.read_text()
    logger.info("Ensuring PostgreSQL tables")
    async with engine.connect() as conn:
        raw = await conn.get_raw_connection()
        # asyncpg's own execute runs a script of several statements; SQLAlchemy's runs one
        await raw.driver_connection.execute(sql)
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

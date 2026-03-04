import os
DATABASE_URL = os.environ["DATABASE_URL"]
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

engine: AsyncEngine = create_async_engine(
   DATABASE_URL,
    echo=False, # don’t log all SQL statements
    pool_pre_ping=True, #check if a connection is alive before using
)

AsyncSessionMaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncSession:
    async with AsyncSessionMaker() as session:
        yield session

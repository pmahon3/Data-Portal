import asyncio

from core.db import AsyncSessionMaker
from core.db.postgres.init_db import ensure_roots_for_instances
from core.injection.managers import get_instance_manager


async def main():
    instance_manager = get_instance_manager()
    async with AsyncSessionMaker() as session:
        roots = await ensure_roots_for_instances(session, instance_manager)
        print(f"created/ensured {len(roots)} roots")
        for r in roots:
            print(f"bucket={r.bucket} id={r.id} full_path={r.full_path}")


if __name__ == "__main__":
    asyncio.run(main())
"""Select the job store backend from the environment."""

from __future__ import annotations

import os

from bundler_core.job_store.memory import InMemoryJobStore
from bundler_core.job_store.protocol import JobStorePort


def create_job_store(*, mongo_uri: str | None = None) -> JobStorePort:
    """Return Mongo store when ``MONGO_URI`` is set, otherwise in-memory.

    ``mongo_uri`` overrides the environment (useful in tests).
    """
    uri = mongo_uri if mongo_uri is not None else os.environ.get("MONGO_URI", "").strip()
    if uri:
        from bundler_core.job_store.mongo import MongoJobStore

        return MongoJobStore(uri)
    return InMemoryJobStore()

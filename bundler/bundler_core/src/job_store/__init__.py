"""Job record persistence backends (memory default, Mongo when ``MONGO_URI`` is set)."""

from bundler_core.job_store.factory import create_job_store
from bundler_core.job_store.memory import InMemoryJobStore
from bundler_core.job_store.protocol import JobStorePort

__all__ = [
    "JobStorePort",
    "InMemoryJobStore",
    "create_job_store",
]

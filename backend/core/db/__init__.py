"""Database helpers exposed by :mod:`core.db`.

PostgreSQL session helpers are intentionally not imported here. Importing the
session module creates the SQLAlchemy engine, so doing that eagerly would make
model-only imports require a valid DATABASE_URL.
"""

from .mongodb.mongo_client import get_mongo_client, get_mongo_database

__all__ = [
    "AsyncSessionMaker",
    "get_session",
    "get_mongo_client",
    "get_mongo_database",
]


def __getattr__(name: str):
    """Load PostgreSQL session objects only when they are explicitly used."""
    if name in {"AsyncSessionMaker", "get_session"}:
        # This is the point where DATABASE_URL is read and the engine is built
        from .postgres.session import AsyncSessionMaker, get_session

        # Cache both exports so future access behaves like a normal import and
        # does not invoke this fallback again.
        globals().update(
            AsyncSessionMaker=AsyncSessionMaker,
            get_session=get_session,
        )
        return globals()[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""Lazy SQLAlchemy engine access.

The engine is created on first use, never at import time, so the app can start
even while Postgres is briefly unreachable.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.core.config import settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the process-wide engine, creating it on first call."""
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


def reset_engine() -> None:
    """Drop the cached engine (used by tests and config reloads)."""
    get_engine.cache_clear()

"""Async SQLAlchemy engine, session factory, and FastAPI DB dependency.

Contract from ``civio-cloud/CLAUDE.md``:

* ``engine`` — a process-wide ``AsyncEngine``.
* ``AsyncSessionLocal`` — an ``async_sessionmaker[AsyncSession]``.
* ``get_db()`` — FastAPI dependency that commits on success and rolls back on exception.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings

_settings = get_settings()

engine: AsyncEngine = create_async_engine(
    _settings.database_url,
    # ``future=True`` is the default in SQLAlchemy 2.x but we set it explicitly
    # to signal the 2.0-style usage contract to readers.
    future=True,
    # ``pool_pre_ping`` guards against stale connections after DB restarts or
    # network blips, which is cheap and worth it for a long-lived API service.
    pool_pre_ping=True,
    # Only log SQL when running locally — production logs get too noisy otherwise.
    echo=_settings.environment == "local",
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an ``AsyncSession``.

    Commits on success, rolls back on any exception, and always closes the
    session. Routers should depend on this rather than instantiating sessions
    themselves.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()

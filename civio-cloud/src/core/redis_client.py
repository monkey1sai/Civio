"""Async Redis client factory.

A single process-wide ``Redis`` instance is created at import time. The
underlying connection pool is lazy — no network I/O happens until the first
command — so importing this module from tests or Alembic env.py is safe.

Usage:

* FastAPI dependency — ``redis: Redis = Depends(get_redis)``
* Lifespan shutdown — ``await close_redis()`` in ``src/main.py`` / ``worker.py``
"""

from __future__ import annotations

from redis.asyncio import Redis

from src.core.config import get_settings

_settings = get_settings()

# ``decode_responses=True`` hands back ``str`` rather than ``bytes`` so OTP
# challenges and cache keys flow through the service layer without manual
# decode calls. Tokens and blobs that must stay binary should use a dedicated
# client with ``decode_responses=False``.
redis_client: Redis = Redis.from_url(
    _settings.redis_url,
    decode_responses=True,
    encoding="utf-8",
)


async def get_redis() -> Redis:
    """FastAPI dependency yielding the shared Redis client."""
    return redis_client


async def close_redis() -> None:
    """Close the connection pool. Call from app/worker lifespan shutdown."""
    await redis_client.aclose()

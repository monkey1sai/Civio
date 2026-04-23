"""FastAPI app factory — the HTTP entry point for civio-cloud-api."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1 import api_router
from src.core.exceptions import register_handlers
from src.core.logging import configure_logging, get_logger
from src.core.redis_client import close_redis


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log = get_logger("civio.main")
    log.info("app_starting")
    try:
        yield
    finally:
        await close_redis()
        log.info("app_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Civio Cloud API",
        version="0.1.0",
        lifespan=_lifespan,
    )

    # CORS is wide-open locally so the Flutter web target and admin-web can
    # both hit the API without per-origin config; tighten this in Phase 11
    # when admin-web lands and the origin list is known.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["infra"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

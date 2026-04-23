"""Structured logging setup.

Configures ``structlog`` to emit JSON in staging/production and a
human-friendly renderer in local dev. Also bridges stdlib ``logging`` so
third-party libraries (uvicorn, sqlalchemy, aio-pika) feed into the same
pipeline.

``configure_logging()`` must be called exactly once at process start — the
FastAPI app factory (``src/main.py``) and the worker entry point
(``src/worker.py``) are the two call sites.
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.types import Processor

from src.core.config import get_settings

_DEFAULT_LEVEL = logging.INFO
# Libraries whose INFO output is mostly noise in production. Promoted to
# WARNING here rather than per-call so the decision lives in one place.
_NOISY_LOGGERS = ("uvicorn.access", "httpx", "httpcore")


def configure_logging() -> None:
    """Initialise structlog + stdlib logging. Idempotent within a process."""
    settings = get_settings()
    is_local = settings.environment == "local"

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[Processor] = [
        # ``contextvars`` carries per-request fields (request_id, user_id)
        # bound by middleware into every log line on the same asyncio task.
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Processor = (
        structlog.dev.ConsoleRenderer(colors=True)
        if is_local
        else structlog.processors.JSONRenderer()
    )

    # structlog hands off to stdlib via ``wrap_for_formatter``; the renderer
    # only runs inside ``ProcessorFormatter`` below, so every log line is
    # rendered exactly once regardless of whether it originated from structlog
    # or a third-party stdlib logger.
    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(_DEFAULT_LEVEL)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger. Prefer module-level ``logger = get_logger(__name__)``."""
    return structlog.stdlib.get_logger(name)

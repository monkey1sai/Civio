"""Domain exception hierarchy and FastAPI handlers.

Services raise subclasses of :class:`CivioException`; routers never catch
them explicitly. :func:`register_handlers` mounts the three handlers on the
FastAPI app so every error surfaces as a JSON body of the form
``{"code": str, "message": str, "details": dict}`` with the appropriate HTTP
status.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status

from src.core.logging import get_logger

_log = get_logger(__name__)


class CivioException(Exception):  # noqa: N818 — contract in civio-cloud/CLAUDE.md mandates this name
    """Base class for every domain-level error surfaced to HTTP clients."""

    code: str = "civio_error"
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}


class AuthenticationError(CivioException):
    code = "authentication_error"
    http_status = status.HTTP_401_UNAUTHORIZED


class AuthorizationError(CivioException):
    code = "authorization_error"
    http_status = status.HTTP_403_FORBIDDEN


class NotFoundError(CivioException):
    code = "not_found"
    http_status = status.HTTP_404_NOT_FOUND


class ConflictError(CivioException):
    code = "conflict"
    http_status = status.HTTP_409_CONFLICT


class ValidationError(CivioException):
    """Raised for domain-level rule violations (distinct from Pydantic's)."""

    code = "validation_error"
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY


def _payload(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"code": code, "message": message, "details": details}


async def civio_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # FastAPI routes to this handler only for CivioException subclasses, but
    # the stdlib-compatible handler signature is ``(Request, Exception)``.
    assert isinstance(exc, CivioException), f"unexpected {type(exc).__name__}"
    _log.warning(
        "civio_exception",
        code=exc.code,
        message=exc.message,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=exc.http_status,
        content=_payload(exc.code, exc.message, exc.details),
    )


async def request_validation_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_payload(
            "validation_error",
            "request validation failed",
            {"errors": exc.errors()},
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Swallow the exception here — never leak tracebacks to clients — but log
    # with full context so the incident is fully reconstructable.
    _log.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        exc_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_payload("internal_error", "internal server error", {}),
    )


def register_handlers(app: FastAPI) -> None:
    app.add_exception_handler(CivioException, civio_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

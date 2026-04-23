"""Aggregator for the v1 API surface.

Sub-routers import this module's ``api_router`` to mount their endpoints.
``src/main.py`` includes it under ``/api/v1``.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.api.v1 import auth

api_router = APIRouter()
api_router.include_router(auth.router)

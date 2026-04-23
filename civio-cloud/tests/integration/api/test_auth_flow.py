"""Integration tests for the ``/auth`` router.

Exercises the full HTTP pipeline (routing, Pydantic validation, exception
handlers, response shaping) with the DB layer stubbed via dependency
overrides. The DB-backed variant lives in Phase 4's test matrix once
tenant/user CRUD endpoints exist to seed state through the API itself.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from src.api.v1.auth import get_auth_service
from src.core.dependencies import get_current_user
from src.main import create_app
from src.models.user import User
from src.services.auth_service import AuthService


@pytest.fixture
async def client(
    fake_redis: FakeAsyncRedis,
    sample_user: User,
    user_repo: AsyncMock,
) -> AsyncIterator[AsyncClient]:
    app = create_app()
    user_repo.list_by_mobile.return_value = [sample_user]
    user_repo.get.return_value = sample_user
    svc = AuthService(user_repo, fake_redis)

    async def _override_service() -> AuthService:
        return svc

    async def _override_user() -> User:
        return sample_user

    app.dependency_overrides[get_auth_service] = _override_service
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def bare_client(
    fake_redis: FakeAsyncRedis,
    user_repo: AsyncMock,
) -> AsyncIterator[AsyncClient]:
    """Client with no ``get_current_user`` override — used to hit real auth."""
    app = create_app()
    svc = AuthService(user_repo, fake_redis)

    async def _override_service() -> AuthService:
        return svc

    app.dependency_overrides[get_auth_service] = _override_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_returns_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_otp_send_validation_error_body_shape(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/otp/send", json={"mobile": "abc"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "validation_error"
    assert "errors" in body["details"]


async def test_otp_full_roundtrip(
    client: AsyncClient,
    fake_redis: FakeAsyncRedis,
    sample_user: User,
) -> None:
    send = await client.post(
        "/api/v1/auth/otp/send",
        json={"mobile": sample_user.mobile},
    )
    assert send.status_code == 200
    challenge = send.json()
    assert challenge["mobile"] == sample_user.mobile

    raw = await fake_redis.get(f"otp:{challenge['challenge_id']}")
    assert raw is not None
    code = json.loads(raw)["code"]

    verify = await client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge["challenge_id"], "code": code},
    )
    assert verify.status_code == 200
    tokens = verify.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    logout = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert logout.status_code == 204


async def test_otp_send_unknown_mobile_returns_401(
    client: AsyncClient,
    user_repo: AsyncMock,
) -> None:
    user_repo.list_by_mobile.return_value = []
    resp = await client.post(
        "/api/v1/auth/otp/send",
        json={"mobile": "+886999999999"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "authentication_error"


async def test_logout_without_auth_returns_401(bare_client: AsyncClient) -> None:
    resp = await bare_client.post("/api/v1/auth/logout")
    assert resp.status_code == 401
    assert resp.json()["code"] == "authentication_error"

"""Shared test fixtures.

Environment variables are seeded at module import time — before any ``src.*``
module is loaded — so :func:`src.core.config.get_settings` never touches a
real ``.env`` file or the developer's environment.
"""

from __future__ import annotations

import os

# Settings are cached at first import; set everything up front.
os.environ.setdefault("ENV", "local")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/civio_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("RABBITMQ_URL", "amqp://localhost")
os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault("SIP_DOMAIN_SUFFIX", "sip.civio.local")
os.environ.setdefault("OPENSIPS_AUTH_SHARED_SECRET", "test-shared-secret")
os.environ.setdefault("ASTERISK_AMI_USER", "civio")
os.environ.setdefault("ASTERISK_AMI_SECRET", "test-ami-secret")

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fakeredis import FakeAsyncRedis
from src.models.enums import AuthStatus, UserRole
from src.models.user import User


@pytest.fixture
async def fake_redis() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def user_repo() -> AsyncMock:
    """Mocked ``UserRepository`` — override methods per-test."""
    repo = AsyncMock()
    # Services touch ``repo.session.flush()`` when promoting PENDING users;
    # use a plain AsyncMock rather than spec'ing AsyncSession to stay light.
    repo.session = AsyncMock()
    return repo


def _make_user(
    *,
    mobile: str = "+886912345678",
    auth_status: AuthStatus = AuthStatus.VERIFIED,
    role: UserRole = UserRole.OWNER,
) -> User:
    return User(
        id=uuid4(),
        community_id=uuid4(),
        name="Test User",
        mobile=mobile,
        email=None,
        role=role,
        auth_status=auth_status,
        call_policy_group=None,
        friendship_enabled=True,
        user_metadata={},
    )


@pytest.fixture
def sample_user() -> User:
    return _make_user()


@pytest.fixture
def pending_user() -> User:
    return _make_user(auth_status=AuthStatus.PENDING)


@pytest.fixture
def revoked_user() -> User:
    return _make_user(auth_status=AuthStatus.REVOKED)

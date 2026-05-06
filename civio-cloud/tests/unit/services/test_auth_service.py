"""Unit tests for :class:`AuthService` covering OTP + refresh flows."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fakeredis import FakeAsyncRedis
from src.core.exceptions import AuthenticationError, ValidationError
from src.core.security import create_access_token, create_refresh_token
from src.models.enums import AuthStatus
from src.models.user import User
from src.services.auth_service import AuthService


@pytest.fixture
def auth_service(user_repo: AsyncMock, fake_redis: FakeAsyncRedis) -> AuthService:
    return AuthService(user_repo, fake_redis)


async def _read_challenge(redis: FakeAsyncRedis, challenge_id: object) -> dict[str, object]:
    raw = await redis.get(f"otp:{challenge_id}")
    assert raw is not None
    data: dict[str, object] = json.loads(raw)
    return data


async def test_send_otp_happy(
    auth_service: AuthService,
    user_repo: AsyncMock,
    fake_redis: FakeAsyncRedis,
    sample_user: User,
) -> None:
    user_repo.list_by_mobile.return_value = [sample_user]

    challenge = await auth_service.send_otp("+886912345678")

    assert challenge.mobile == "+886912345678"
    data = await _read_challenge(fake_redis, challenge.challenge_id)
    assert data["mobile"] == "+886912345678"
    assert isinstance(data["code"], str) and len(data["code"]) == 6
    assert data["attempts"] == 0


async def test_send_otp_unknown_mobile_raises(
    auth_service: AuthService,
    user_repo: AsyncMock,
) -> None:
    user_repo.list_by_mobile.return_value = []
    with pytest.raises(AuthenticationError):
        await auth_service.send_otp("+886900000000")


async def test_verify_otp_happy_returns_tokens(
    auth_service: AuthService,
    user_repo: AsyncMock,
    fake_redis: FakeAsyncRedis,
    sample_user: User,
) -> None:
    user_repo.list_by_mobile.return_value = [sample_user]
    user_repo.get.return_value = sample_user

    challenge = await auth_service.send_otp("+886912345678")
    data = await _read_challenge(fake_redis, challenge.challenge_id)
    code = str(data["code"])

    tokens = await auth_service.verify_otp(challenge.challenge_id, code)

    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.token_type == "bearer"
    # Challenge should be burned after success.
    assert await fake_redis.get(f"otp:{challenge.challenge_id}") is None


async def test_verify_otp_wrong_code_increments_attempts(
    auth_service: AuthService,
    user_repo: AsyncMock,
    fake_redis: FakeAsyncRedis,
    sample_user: User,
) -> None:
    user_repo.list_by_mobile.return_value = [sample_user]
    challenge = await auth_service.send_otp("+886912345678")

    with pytest.raises(AuthenticationError):
        await auth_service.verify_otp(challenge.challenge_id, "000000")

    data = await _read_challenge(fake_redis, challenge.challenge_id)
    assert data["attempts"] == 1


async def test_verify_otp_too_many_attempts_burns_challenge(
    auth_service: AuthService,
    user_repo: AsyncMock,
    fake_redis: FakeAsyncRedis,
    sample_user: User,
) -> None:
    user_repo.list_by_mobile.return_value = [sample_user]
    challenge = await auth_service.send_otp("+886912345678")

    # 5 wrong attempts fills the counter; 6th wipes the challenge.
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            await auth_service.verify_otp(challenge.challenge_id, "000000")
    with pytest.raises(AuthenticationError):
        await auth_service.verify_otp(challenge.challenge_id, "000000")

    assert await fake_redis.get(f"otp:{challenge.challenge_id}") is None


async def test_verify_otp_missing_challenge_raises(auth_service: AuthService) -> None:
    with pytest.raises(AuthenticationError):
        await auth_service.verify_otp(uuid4(), "123456")


async def test_verify_otp_promotes_pending_user(
    auth_service: AuthService,
    user_repo: AsyncMock,
    fake_redis: FakeAsyncRedis,
    pending_user: User,
) -> None:
    user_repo.list_by_mobile.return_value = [pending_user]
    user_repo.get.return_value = pending_user

    challenge = await auth_service.send_otp("+886912345678")
    code = str((await _read_challenge(fake_redis, challenge.challenge_id))["code"])

    await auth_service.verify_otp(challenge.challenge_id, code)

    assert pending_user.auth_status == AuthStatus.VERIFIED


async def test_verify_otp_revoked_user_rejected(
    auth_service: AuthService,
    user_repo: AsyncMock,
    fake_redis: FakeAsyncRedis,
    revoked_user: User,
) -> None:
    user_repo.list_by_mobile.return_value = [revoked_user]
    user_repo.get.return_value = revoked_user

    challenge = await auth_service.send_otp("+886912345678")
    code = str((await _read_challenge(fake_redis, challenge.challenge_id))["code"])

    with pytest.raises(AuthenticationError):
        await auth_service.verify_otp(challenge.challenge_id, code)


async def test_verify_otp_ambiguous_mobile_raises(
    auth_service: AuthService,
    user_repo: AsyncMock,
    fake_redis: FakeAsyncRedis,
    sample_user: User,
    pending_user: User,
) -> None:
    # Same mobile number, two communities — service can't decide.
    pending_user.mobile = sample_user.mobile
    user_repo.list_by_mobile.return_value = [sample_user, pending_user]

    challenge = await auth_service.send_otp(sample_user.mobile)
    code = str((await _read_challenge(fake_redis, challenge.challenge_id))["code"])

    with pytest.raises(ValidationError):
        await auth_service.verify_otp(challenge.challenge_id, code)


async def test_refresh_happy(
    auth_service: AuthService,
    user_repo: AsyncMock,
    sample_user: User,
) -> None:
    user_repo.get.return_value = sample_user
    rt = create_refresh_token(str(sample_user.id))

    tokens = await auth_service.refresh(rt)

    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.token_type == "bearer"


async def test_refresh_rejects_access_token(
    auth_service: AuthService,
    sample_user: User,
) -> None:
    at = create_access_token(str(sample_user.id))
    with pytest.raises(AuthenticationError):
        await auth_service.refresh(at)


async def test_refresh_rejects_revoked_user(
    auth_service: AuthService,
    user_repo: AsyncMock,
    revoked_user: User,
) -> None:
    user_repo.get.return_value = revoked_user
    rt = create_refresh_token(str(revoked_user.id))
    with pytest.raises(AuthenticationError):
        await auth_service.refresh(rt)


async def test_refresh_rejects_unknown_user(
    auth_service: AuthService,
    user_repo: AsyncMock,
) -> None:
    user_repo.get.return_value = None
    rt = create_refresh_token(str(uuid4()))
    with pytest.raises(AuthenticationError):
        await auth_service.refresh(rt)

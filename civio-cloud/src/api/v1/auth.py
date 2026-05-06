"""``/auth`` endpoints — OTP challenge, verify, refresh, logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.core.logging import get_logger
from src.core.redis_client import get_redis
from src.models.user import User
from src.repositories.user_repo import UserRepository
from src.schemas.auth import (
    OtpChallenge,
    OtpSendRequest,
    OtpVerifyRequest,
    RefreshRequest,
    TokenPair,
)
from src.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
_log = get_logger(__name__)


def get_auth_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AuthService:
    return AuthService(UserRepository(db), redis)


@router.post("/otp/send", response_model=OtpChallenge)
async def otp_send(
    payload: OtpSendRequest,
    svc: AuthService = Depends(get_auth_service),
) -> OtpChallenge:
    return await svc.send_otp(payload.mobile)


@router.post("/otp/verify", response_model=TokenPair)
async def otp_verify(
    payload: OtpVerifyRequest,
    svc: AuthService = Depends(get_auth_service),
) -> TokenPair:
    return await svc.verify_otp(payload.challenge_id, payload.code)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    svc: AuthService = Depends(get_auth_service),
) -> TokenPair:
    return await svc.refresh(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: User = Depends(get_current_user)) -> Response:
    # Stateless MVP — clients drop both tokens on logout. A refresh-token
    # blocklist (``blacklist:<jti>`` keyed with remaining TTL) is a follow-up
    # item tracked outside this PR to keep Phase 3 scoped to the core flow.
    _log.info("logout", user_id=str(user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

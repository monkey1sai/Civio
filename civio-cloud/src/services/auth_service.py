"""OTP-based authentication flow.

Flow summary:

1. ``send_otp(mobile)`` — resolves users by mobile, stores a challenge in
   Redis (``otp:<challenge_id>``) with a 5-attempt cap and ``OTP_TTL_SEC`` TTL,
   returns the challenge envelope. The plaintext code is delivered out-of-band
   via SMS (Phase 3 stubs this — the code lives in Redis for local testing).

2. ``verify_otp(challenge_id, code)`` — constant-time compares the code,
   burns the challenge on success, promotes ``PENDING`` users to ``VERIFIED``,
   and returns a ``TokenPair``.

3. ``refresh(refresh_token)`` — issues a new ``TokenPair`` from a valid
   refresh token, re-checking the user's current ``auth_status``.
"""

from __future__ import annotations

import hmac
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from redis.asyncio import Redis

from src.core.config import get_settings
from src.core.exceptions import AuthenticationError, ValidationError
from src.core.logging import get_logger
from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_otp,
)
from src.models.enums import AuthStatus
from src.models.user import User
from src.repositories.user_repo import UserRepository
from src.schemas.auth import OtpChallenge, TokenPair

_MAX_ATTEMPTS = 5
_log = get_logger(__name__)


def _challenge_key(challenge_id: UUID) -> str:
    return f"otp:{challenge_id}"


class AuthService:
    def __init__(self, user_repo: UserRepository, redis: Redis) -> None:
        self.user_repo = user_repo
        self.redis = redis
        self._settings = get_settings()

    async def send_otp(self, mobile: str) -> OtpChallenge:
        users = await self.user_repo.list_by_mobile(mobile)
        if not users:
            # Failing here leaks user existence; acceptable trade-off for MVP
            # because admin-provisioned users are the only path into the
            # system. Revisit once self-service registration ships.
            raise AuthenticationError(
                "mobile not registered",
                details={"mobile": mobile},
            )

        challenge_id = uuid4()
        code = generate_otp()
        expires_at = datetime.now(UTC) + timedelta(seconds=self._settings.otp_ttl_sec)

        payload = {
            "mobile": mobile,
            "code": code,
            "attempts": 0,
            "user_ids": [str(u.id) for u in users],
        }
        await self.redis.setex(
            _challenge_key(challenge_id),
            self._settings.otp_ttl_sec,
            json.dumps(payload),
        )

        # Never log the plaintext code even at DEBUG — rotated through JSON
        # logs it could surface in incident dumps. Log the challenge_id only.
        _log.info(
            "otp_sent",
            challenge_id=str(challenge_id),
            user_count=len(users),
            ttl_sec=self._settings.otp_ttl_sec,
        )
        return OtpChallenge(
            challenge_id=challenge_id,
            mobile=mobile,
            expires_at=expires_at,
        )

    async def verify_otp(self, challenge_id: UUID, code: str) -> TokenPair:
        key = _challenge_key(challenge_id)
        raw = await self.redis.get(key)
        if raw is None:
            raise AuthenticationError("otp challenge expired or not found")

        payload = json.loads(raw)
        attempts = int(payload["attempts"])
        if attempts >= _MAX_ATTEMPTS:
            await self.redis.delete(key)
            raise AuthenticationError("too many otp attempts")

        # ``compare_digest`` prevents timing-oracle leaks on the code.
        if not hmac.compare_digest(str(payload["code"]), code):
            payload["attempts"] = attempts + 1
            # Preserve the remaining TTL so brute-force can't be reset by
            # retrying; ``keepttl=True`` keeps the original expiry.
            await self.redis.set(key, json.dumps(payload), keepttl=True)
            raise AuthenticationError(
                "invalid otp code",
                details={"attempts_remaining": _MAX_ATTEMPTS - payload["attempts"]},
            )

        user_ids = [UUID(uid) for uid in payload["user_ids"]]
        if len(user_ids) != 1:
            # Ambiguous: same mobile across multiple communities. Admin UX
            # will need a community selector before we can resolve this.
            await self.redis.delete(key)
            raise ValidationError(
                "mobile matches multiple users; community selection required",
                details={"user_count": len(user_ids)},
            )

        user = await self.user_repo.get(user_ids[0])
        if user is None:
            await self.redis.delete(key)
            raise AuthenticationError("user no longer exists")

        await self._promote_or_check(user)
        await self.redis.delete(key)

        _log.info("otp_verified", user_id=str(user.id), community_id=str(user.community_id))
        return self._issue_tokens(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        payload = decode_token(refresh_token)
        if payload.type != "refresh":
            raise AuthenticationError("access token cannot be used to refresh")

        try:
            user_id = UUID(payload.sub)
        except ValueError as exc:
            raise AuthenticationError("invalid token subject") from exc

        user = await self.user_repo.get(user_id)
        if user is None:
            raise AuthenticationError("user not found")
        if user.auth_status != AuthStatus.VERIFIED:
            raise AuthenticationError(
                "user is not verified",
                details={"auth_status": user.auth_status.value},
            )

        return self._issue_tokens(user)

    async def _promote_or_check(self, user: User) -> None:
        if user.auth_status == AuthStatus.REVOKED:
            raise AuthenticationError("account revoked")
        if user.auth_status == AuthStatus.PENDING:
            user.auth_status = AuthStatus.VERIFIED
            # flush so the commit in ``get_db`` sees the change
            await self.user_repo.session.flush()

    def _issue_tokens(self, user: User) -> TokenPair:
        extras: dict[str, object] = {
            "community_id": str(user.community_id),
            "role": user.role.value,
        }
        return TokenPair(
            access_token=create_access_token(str(user.id), extras),
            refresh_token=create_refresh_token(str(user.id)),
        )

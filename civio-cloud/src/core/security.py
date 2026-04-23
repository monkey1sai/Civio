"""JWT, password hashing, and OTP primitives.

Contract (from ``civio-cloud/CLAUDE.md``):

* ``hash_password`` / ``verify_password`` — passlib[bcrypt], cost 12.
* ``create_access_token`` / ``create_refresh_token`` — HS256 JWTs whose TTLs
  come from :mod:`src.core.config`.
* ``decode_token`` — returns :class:`TokenPayload`; raises
  :class:`TokenExpiredError` for expired tokens and :class:`InvalidTokenError`
  for every other JWT failure so callers can map them to 401/403.
* ``generate_otp`` — cryptographically strong numeric code used by
  ``AuthService`` for OTP challenges.

``TokenPayload`` lives here (not in ``schemas/auth.py``) because it describes a
security-layer claim set, not a request/response contract. ``schemas/auth.py``
may re-export it for API documentation.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import uuid4

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict

from src.core.config import get_settings
from src.core.exceptions import AuthenticationError

_settings = get_settings()

# bcrypt cost 12 is the security baseline agreed in ``CLAUDE.md``. Raising the
# cost requires coordinated re-hashing on next login; lowering it is forbidden.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

_JWT_ALGORITHM = "HS256"
_RESERVED_CLAIMS = frozenset({"sub", "type", "iat", "exp", "jti"})

TokenType = Literal["access", "refresh"]


class TokenPayload(BaseModel):
    """Decoded JWT claims. Extra claims flow through (e.g. community_id, role)."""

    model_config = ConfigDict(extra="allow")

    sub: str
    type: TokenType
    iat: int
    exp: int
    jti: str


class TokenError(AuthenticationError):
    """Base class for token decode failures; maps to HTTP 401."""


class TokenExpiredError(TokenError):
    """Raised when the JWT ``exp`` claim is in the past."""

    code = "token_expired"


class InvalidTokenError(TokenError):
    """Raised for malformed, tampered, or otherwise unverifiable tokens."""

    code = "token_invalid"


def hash_password(plain: str) -> str:
    return cast(str, _pwd_context.hash(plain))


def verify_password(plain: str, hashed: str) -> bool:
    return cast(bool, _pwd_context.verify(plain, hashed))


def _build_token(
    sub: str,
    token_type: TokenType,
    ttl: timedelta,
    extra: dict[str, object] | None = None,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": sub,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": uuid4().hex,
    }
    if extra:
        overlap = _RESERVED_CLAIMS & extra.keys()
        if overlap:
            # Refuse to let callers silently overwrite standard claims — that
            # would be a trivial privilege-escalation surface.
            raise ValueError(f"extra claims conflict with reserved names: {sorted(overlap)}")
        claims.update(extra)
    encoded = jwt.encode(
        claims,
        _settings.jwt_secret.get_secret_value(),
        algorithm=_JWT_ALGORITHM,
    )
    return cast(str, encoded)


def create_access_token(sub: str, extra: dict[str, object] | None = None) -> str:
    return _build_token(
        sub,
        "access",
        timedelta(minutes=_settings.jwt_access_ttl_min),
        extra,
    )


def create_refresh_token(sub: str) -> str:
    return _build_token(
        sub,
        "refresh",
        timedelta(days=_settings.jwt_refresh_ttl_days),
    )


def decode_token(token: str) -> TokenPayload:
    try:
        raw = jwt.decode(
            token,
            _settings.jwt_secret.get_secret_value(),
            algorithms=[_JWT_ALGORITHM],
        )
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("token expired") from exc
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    try:
        return TokenPayload.model_validate(raw)
    except ValueError as exc:
        raise InvalidTokenError(f"invalid token payload: {exc}") from exc


def generate_otp(length: int = 6) -> str:
    # 4-10 digits covers every realistic OTP surface while rejecting both
    # trivially guessable (<4) and user-hostile (>10) lengths.
    if not 4 <= length <= 10:
        raise ValueError("otp length must be between 4 and 10")
    return f"{secrets.randbelow(10**length):0{length}d}"

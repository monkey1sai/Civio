"""Pydantic request/response models for the ``/auth`` endpoints."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.security import TokenPayload

# Accept E.164-style (``+886912345678``) or local (``0912345678``). 8-15 digits
# total after stripping the optional ``+`` covers every realistic TW case as
# well as future overseas tenants.
_MOBILE_PATTERN = re.compile(r"^\+?[0-9]{8,15}$")


class OtpSendRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    mobile: str = Field(min_length=8, max_length=16, examples=["+886912345678"])

    @field_validator("mobile")
    @classmethod
    def _check_mobile(cls, v: str) -> str:
        if not _MOBILE_PATTERN.match(v):
            raise ValueError("mobile must be E.164 digits (optionally prefixed with +)")
        return v


class OtpVerifyRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    challenge_id: UUID
    code: Annotated[str, Field(pattern=r"^\d{6}$", examples=["123456"])]


class RefreshRequest(BaseModel):
    refresh_token: str


class OtpChallenge(BaseModel):
    """Response to ``POST /auth/otp/send``.

    The plaintext OTP is never returned — clients receive it via SMS.
    """

    challenge_id: UUID
    mobile: str
    expires_at: datetime


class TokenPair(BaseModel):
    """Response to ``POST /auth/otp/verify`` and ``POST /auth/refresh``."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


# Re-export so downstream modules (dependencies, routers) can
# ``from src.schemas.auth import TokenPayload`` without a double-source of
# truth. Definition lives in ``core/security.py`` because it describes a
# security-layer claim set rather than an API contract.
__all__ = [
    "OtpChallenge",
    "OtpSendRequest",
    "OtpVerifyRequest",
    "RefreshRequest",
    "TokenPair",
    "TokenPayload",
]

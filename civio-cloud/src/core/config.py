"""Application settings loaded from environment variables.

All env vars listed in the root ``CLAUDE.md`` have a corresponding field here.
Every secret is wrapped in ``SecretStr`` so it never appears in repr/logs.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "staging", "production"]
PaymentProvider = Literal["ecpay", "newebpay", "stripe"]


class Settings(BaseSettings):
    """Typed container for every runtime configuration value."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Environment = Field(default="local", validation_alias="ENV")

    database_url: str
    redis_url: str
    rabbitmq_url: str

    jwt_secret: SecretStr
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 7
    otp_ttl_sec: int = 300

    sip_domain_suffix: str
    opensips_auth_shared_secret: SecretStr

    asterisk_ami_user: str
    asterisk_ami_secret: SecretStr

    payment_provider: PaymentProvider = "ecpay"

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        # CLAUDE.md mandates a minimum of 32 bytes so signed tokens survive a rotation window.
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached ``Settings`` instance."""
    # pydantic-settings fills the required fields from env vars at runtime;
    # Pyright can't see through that, so silence its false positive here.
    return Settings()  # pyright: ignore[reportCallIssue]

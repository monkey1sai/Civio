"""``sip_endpoints`` — 1:1 SIP credentials per user."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.community import Community
    from src.models.user import User


class SipEndpoint(Base, TimestampMixin):
    __tablename__ = "sip_endpoints"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    community_id: Mapped[UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    # Bcrypt-hashed. ``api/v1/sip/endpoints/{user_id}`` MUST NEVER return this column.
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    transport: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'tls'"))
    context: Mapped[str] = mapped_column(String(64), nullable=False)
    codec_order: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        server_default=text("ARRAY['opus', 'PCMU', 'PCMA']"),
    )
    webrtc_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )

    user: Mapped[User] = relationship("User")
    community: Mapped[Community] = relationship("Community")

    __table_args__ = (
        UniqueConstraint(
            "community_id", "username", name="sip_endpoints_community_id_username_key"
        ),
        Index("idx_sip_endpoints_user", "user_id"),
        Index("idx_sip_endpoints_community", "community_id"),
    )

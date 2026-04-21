"""``users`` — anyone with a login in the system (resident, admin, staff)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin
from src.models.enums import AuthStatus, UserRole, auth_status_type, user_role_type

if TYPE_CHECKING:
    from src.models.community import Community


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    community_id: Mapped[UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    mobile: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(String(128))
    role: Mapped[UserRole] = mapped_column(user_role_type, nullable=False)
    auth_status: Mapped[AuthStatus] = mapped_column(
        auth_status_type,
        nullable=False,
        server_default=text("'pending'"),
    )
    call_policy_group: Mapped[str | None] = mapped_column(String(32))
    friendship_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    user_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'"),
    )

    community: Mapped[Community] = relationship("Community")

    __table_args__ = (
        UniqueConstraint("community_id", "mobile", name="users_community_id_mobile_key"),
        Index("idx_users_mobile", "mobile"),
        Index("idx_users_role", "role"),
        Index("idx_users_community", "community_id"),
    )

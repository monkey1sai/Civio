"""``friend_mappings`` — undirected friendship pairs with ``user_a_id < user_b_id``."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import TIMESTAMP, CheckConstraint, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin
from src.models.enums import FriendStatus, friend_status_type

if TYPE_CHECKING:
    from src.models.user import User


class FriendMapping(Base, TimestampMixin):
    __tablename__ = "friend_mappings"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    user_a_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_b_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[FriendStatus] = mapped_column(
        friend_status_type,
        nullable=False,
        server_default=text("'pending'"),
    )
    initiated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    effective_to: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Three FKs to ``users`` — disambiguate each relationship via ``foreign_keys``.
    user_a: Mapped[User] = relationship("User", foreign_keys=[user_a_id])
    user_b: Mapped[User] = relationship("User", foreign_keys=[user_b_id])
    initiator: Mapped[User] = relationship("User", foreign_keys=[initiated_by])

    __table_args__ = (
        CheckConstraint("user_a_id <> user_b_id", name="ck_distinct_users"),
        CheckConstraint("user_a_id < user_b_id", name="ck_sorted_users"),
        Index(
            "idx_friend_active",
            "user_a_id",
            "user_b_id",
            postgresql_where=text("status = 'active'"),
        ),
    )

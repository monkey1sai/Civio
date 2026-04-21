"""``announcements`` — community-wide broadcast messages."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import TIMESTAMP, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin
from src.models.enums import AnnouncementPriority, announcement_priority_type

if TYPE_CHECKING:
    from src.models.community import Community
    from src.models.user import User


class Announcement(Base, TimestampMixin):
    __tablename__ = "announcements"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    community_id: Mapped[UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[AnnouncementPriority] = mapped_column(
        announcement_priority_type,
        nullable=False,
        server_default=text("'normal'"),
    )
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    community: Mapped[Community] = relationship("Community")
    author: Mapped[User] = relationship("User")

    __table_args__ = (
        Index("idx_announcements_community", "community_id", text("published_at DESC")),
    )

"""``tasks`` — 交辦: things residents or staff need to act on."""

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


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    community_id: Mapped[UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # ``open`` / ``in_progress`` / ``resolved`` / ``closed`` — kept as String to match DDL.
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'open'"))
    priority: Mapped[AnnouncementPriority] = mapped_column(
        announcement_priority_type,
        nullable=False,
        server_default=text("'normal'"),
    )
    due_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    community: Mapped[Community] = relationship("Community")
    creator: Mapped[User] = relationship("User", foreign_keys=[created_by])
    assignee: Mapped[User | None] = relationship("User", foreign_keys=[assigned_to])

    __table_args__ = (Index("idx_tasks_community_status", "community_id", "status"),)

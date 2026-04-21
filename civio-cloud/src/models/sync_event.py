"""``sync_events`` — monotonic per-community changelog consumed by edge nodes."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base
from src.models.enums import SyncAckStatus, sync_ack_status_type

if TYPE_CHECKING:
    from src.models.community import Community


class SyncEvent(Base):
    __tablename__ = "sync_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    community_id: Mapped[UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    ack_status: Mapped[SyncAckStatus] = mapped_column(
        sync_ack_status_type,
        nullable=False,
        server_default=text("'pending'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    acked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    community: Mapped[Community] = relationship("Community")

    __table_args__ = (
        UniqueConstraint("community_id", "version", name="sync_events_community_id_version_key"),
        Index(
            "idx_sync_events_pending",
            "community_id",
            "version",
            postgresql_where=text("ack_status = 'pending'"),
        ),
    )

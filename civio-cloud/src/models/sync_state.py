"""``sync_state`` — one row per community tracking last-sync position.

Unusually, this table's primary key IS the FK to ``communities.id`` — there is
only ever one state row per community. DDL omits ``created_at``; only
``updated_at`` is present.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import TIMESTAMP, BigInteger, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.community import Community


class SyncState(Base):
    __tablename__ = "sync_state"

    community_id: Mapped[UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_full_sync_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_full_sync_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    last_delta_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    merkle_root: Mapped[str | None] = mapped_column(String(128))
    # ``healthy`` / ``stale`` / ``resyncing`` — kept as free-form String to match DDL.
    health_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'healthy'")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    community: Mapped[Community] = relationship("Community")

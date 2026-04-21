"""``call_logs`` — CDR row per SIP call."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base
from src.models.enums import BillingScope, CallStatus, billing_scope_type, call_status_type

if TYPE_CHECKING:
    from src.models.community import Community
    from src.models.user import User


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    sip_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    community_id: Mapped[UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    caller_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    callee_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    caller_sip_uri: Mapped[str] = mapped_column(String(256), nullable=False)
    callee_sip_uri: Mapped[str] = mapped_column(String(256), nullable=False)
    callee_type: Mapped[str | None] = mapped_column(String(16))
    call_status: Mapped[CallStatus] = mapped_column(call_status_type, nullable=False)
    start_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    answer_time: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    hangup_cause: Mapped[str | None] = mapped_column(String(64))
    billing_scope: Mapped[BillingScope | None] = mapped_column(billing_scope_type)
    token_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default=text("0")
    )
    reject_reason: Mapped[str | None] = mapped_column(String(64))
    call_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    community: Mapped[Community] = relationship("Community")
    caller: Mapped[User | None] = relationship("User", foreign_keys=[caller_user_id])
    callee: Mapped[User | None] = relationship("User", foreign_keys=[callee_user_id])

    __table_args__ = (
        UniqueConstraint(
            "community_id", "sip_call_id", name="call_logs_community_id_sip_call_id_key"
        ),
        Index("idx_call_logs_community_start", "community_id", text("start_time DESC")),
        Index("idx_call_logs_caller", "caller_user_id", text("start_time DESC")),
        Index("idx_call_logs_callee", "callee_user_id", text("start_time DESC")),
    )

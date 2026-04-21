"""``billing_records`` — one row per charged call, linked to its ledger entry."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import TIMESTAMP, BigInteger, ForeignKey, Index, Numeric, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base
from src.models.enums import BillingScope, billing_scope_type

if TYPE_CHECKING:
    from src.models.call_log import CallLog
    from src.models.community import Community
    from src.models.token_ledger import TokenLedger


class BillingRecord(Base):
    __tablename__ = "billing_records"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    call_id: Mapped[UUID] = mapped_column(
        ForeignKey("call_logs.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    community_id: Mapped[UUID] = mapped_column(
        ForeignKey("communities.id"),
        nullable=False,
    )
    token_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    billing_scope: Mapped[BillingScope] = mapped_column(billing_scope_type, nullable=False)
    ledger_entry_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("token_ledger.id"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    call: Mapped[CallLog] = relationship("CallLog")
    community: Mapped[Community] = relationship("Community")
    ledger_entry: Mapped[TokenLedger | None] = relationship("TokenLedger")

    __table_args__ = (Index("idx_billing_community", "community_id", text("created_at DESC")),)

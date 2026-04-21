"""``payment_orders`` — top-up orders routed to ecpay / newebpay / apple_iap."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.community import Community
    from src.models.user import User


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    community_id: Mapped[UUID] = mapped_column(ForeignKey("communities.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String(128))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'TWD'"))
    token_credit: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    # ``pending`` / ``paid`` / ``failed`` / ``refunded`` — kept as String per DDL.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    user: Mapped[User] = relationship("User")
    community: Mapped[Community] = relationship("Community")

    __table_args__ = (
        Index("idx_payment_user", "user_id", text("created_at DESC")),
        Index("idx_payment_provider_ref", "provider", "provider_ref"),
    )

"""``token_ledger`` — append-only double-entry ledger for community & user tokens.

The DDL enforces append-only via ``trg_forbid_ledger_update`` /
``trg_forbid_ledger_delete``. Do not call ``session.delete(TokenLedger(...))``
or update rows — Postgres will raise.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base
from src.models.enums import TokenScope, token_scope_type

if TYPE_CHECKING:
    from src.models.community import Community
    from src.models.user import User


class TokenLedger(Base):
    __tablename__ = "token_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[TokenScope] = mapped_column(token_scope_type, nullable=False)
    community_id: Mapped[UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    community: Mapped[Community] = relationship("Community")
    user: Mapped[User | None] = relationship("User")

    __table_args__ = (
        CheckConstraint(
            "(scope = 'community' AND user_id IS NULL) OR "
            "(scope = 'user' AND user_id IS NOT NULL)",
            name="ck_scope_owner",
        ),
        Index("idx_ledger_community", "community_id", text("created_at DESC")),
        Index(
            "idx_ledger_user",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("user_id IS NOT NULL"),
        ),
    )

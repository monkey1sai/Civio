"""``user_unit_relations`` — temporal many-to-many between users and units."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import TIMESTAMP, CheckConstraint, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base
from src.models.enums import RelationType, relation_type_type

if TYPE_CHECKING:
    from src.models.unit import Unit
    from src.models.user import User


class UserUnitRelation(Base):
    __tablename__ = "user_unit_relations"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    unit_id: Mapped[UUID] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[RelationType] = mapped_column(relation_type_type, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # ``effective_to IS NULL`` = still active — that's what the partial indexes filter on.
    effective_to: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship("User")
    unit: Mapped[Unit] = relationship("Unit")

    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_effective_range",
        ),
        Index(
            "idx_uur_user",
            "user_id",
            postgresql_where=text("effective_to IS NULL"),
        ),
        Index(
            "idx_uur_unit",
            "unit_id",
            postgresql_where=text("effective_to IS NULL"),
        ),
    )

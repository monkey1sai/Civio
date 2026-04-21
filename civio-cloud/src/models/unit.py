"""``units`` — a single apartment / room within a community."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin
from src.models.enums import (
    OccupancyStatus,
    OwnershipStatus,
    occupancy_status_type,
    ownership_status_type,
)

if TYPE_CHECKING:
    from src.models.community import Community


class Unit(Base, TimestampMixin):
    __tablename__ = "units"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    community_id: Mapped[UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    unit_code: Mapped[str] = mapped_column(String(64), nullable=False)
    building_no: Mapped[str | None] = mapped_column(String(32))
    floor_no: Mapped[int | None] = mapped_column(Integer)
    room_no: Mapped[str | None] = mapped_column(String(32))
    ownership_status: Mapped[OwnershipStatus] = mapped_column(
        ownership_status_type,
        nullable=False,
        server_default=text("'owned'"),
    )
    occupancy_status: Mapped[OccupancyStatus] = mapped_column(
        occupancy_status_type,
        nullable=False,
        server_default=text("'vacant'"),
    )
    sync_version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    unit_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'"),
    )

    community: Mapped[Community] = relationship("Community")

    __table_args__ = (
        UniqueConstraint("community_id", "unit_code", name="units_community_id_unit_code_key"),
        Index("idx_units_community", "community_id"),
        Index("idx_units_ownership", "ownership_status"),
    )

"""``communities`` — top-level tenant (one per building/管委會)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin
from src.models.enums import CommunityStatus, community_status_type


class Community(Base, TimestampMixin):
    __tablename__ = "communities"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sip_domain: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[CommunityStatus] = mapped_column(
        community_status_type,
        nullable=False,
        server_default=text("'pending'"),
    )
    current_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    # ``metadata`` is reserved on ``DeclarativeBase`` (it's the registry). Column
    # is still exposed as ``metadata`` in the DB but mapped to ``community_metadata``
    # on the Python side.
    community_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'"),
    )

    __table_args__ = (
        Index("idx_communities_status", "status"),
        Index(
            "idx_communities_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

"""Declarative base and shared mixins for SQLAlchemy ORM models.

All entity tables in ``docs/02-database-schema.sql`` use:

* ``UUID PRIMARY KEY DEFAULT uuid_generate_v4()`` for entity rows
* ``TIMESTAMPTZ NOT NULL DEFAULT NOW()`` for both ``created_at`` and ``updated_at``

``updated_at`` is bumped by the ``tg_set_updated_at`` trigger defined in the
DDL — we still declare ``server_default`` on the column so Alembic autogenerate
sees the same default the DB has, otherwise every run would show drift.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import TIMESTAMP, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base every ORM model inherits from."""

    # Map the Python ``UUID`` annotation to a PostgreSQL native ``uuid`` column
    # so ``Mapped[UUID]`` just works across every model without per-column overrides.
    type_annotation_map = {  # noqa: RUF012 — SQLAlchemy reads this as a plain dict
        UUID: PG_UUID(as_uuid=True),
    }


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` TIMESTAMPTZ columns.

    Both columns default to ``NOW()`` at the DB. ``updated_at`` is then maintained
    by the ``tg_set_updated_at`` trigger on every UPDATE — we do **not** set
    ``onupdate`` on the ORM side to avoid double-writes fighting the trigger.
    """

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

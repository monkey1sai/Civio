"""``processed_events`` — idempotency marker for RabbitMQ consumers.

Every consumer stores the CloudEvent ``id`` here after successful handling so a
redelivery becomes a no-op. Not a UUID table — ``event_id`` is the CloudEvent
ID string (``evt_<uuid4>``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import TIMESTAMP, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    consumer_name: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

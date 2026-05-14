from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class KpiEventType(str, enum.Enum):
    WEBHOOK_RECEIVED = "WEBHOOK_RECEIVED"
    DRAFT_GENERATED = "DRAFT_GENERATED"
    DRAFT_VIEWED = "DRAFT_VIEWED"
    DRAFT_EDITED = "DRAFT_EDITED"
    DRAFT_APPROVED = "DRAFT_APPROVED"
    DRAFT_REJECTED = "DRAFT_REJECTED"
    CLASSIFICATION_CORRECTED = "CLASSIFICATION_CORRECTED"
    RESPONSE_SENT = "RESPONSE_SENT"


class KpiEvent(Base, TimestampMixin):
    __tablename__ = "kpi_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[KpiEventType] = mapped_column(SAEnum(KpiEventType), index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(500), nullable=True)

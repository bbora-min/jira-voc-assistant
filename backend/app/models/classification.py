from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Classification(Base, TimestampMixin):
    """AI VOC 분류 결과 (FR-13~17).
    category_id: 운영자가 최종 확정한 카테고리. 초기에는 predicted == category.
    """

    __tablename__ = "classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    predicted_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    was_corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    corrected_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

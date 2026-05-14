from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Draft(Base, TimestampMixin):
    """LLM이 생성한 답변 초안. body_html_edited는 운영자가 수정한 결과."""

    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    prompt_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id"), nullable=True
    )
    body_html: Mapped[str] = mapped_column(Text)
    body_html_edited: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(80))
    generation_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    edit_distance: Mapped[int | None] = mapped_column(Integer, nullable=True)

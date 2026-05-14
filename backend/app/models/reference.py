from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Reference(Base, TimestampMixin):
    """LLM 초안 생성에 참고된 RAG 청크 (FR-07/19)."""

    __tablename__ = "references_"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(120))
    source_title: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(40), default="confluence")
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    position: Mapped[int] = mapped_column(Integer, default=0)

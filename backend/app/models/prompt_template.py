from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PromptKind(str, enum.Enum):
    CLASSIFY = "CLASSIFY"
    DRAFT = "DRAFT"


class PromptTemplate(Base, TimestampMixin):
    """Jinja2 기반 프롬프트 템플릿. kind별로 활성 버전 1개를 유지."""

    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[PromptKind] = mapped_column(SAEnum(PromptKind), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum as SAEnum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedText
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.operator_action import OperatorAction


class TicketStatus(str, enum.Enum):
    PENDING = "PENDING"          # webhook 수신, 초안 생성 대기
    IN_PROGRESS = "IN_PROGRESS"  # 초안 생성 완료, 운영자 검토 중
    DONE = "DONE"                # 승인되어 Jira 코멘트 등록됨
    REJECTED = "REJECTED"        # 운영자 거부 (수동 답변 작성)


class Ticket(Base, TimestampMixin):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    jira_key: Mapped[str] = mapped_column(String(60), unique=True, index=True)

    title_enc: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    body_enc: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    reporter_enc: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    attachments_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    assignee: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[TicketStatus] = mapped_column(
        SAEnum(TicketStatus), default=TicketStatus.PENDING, index=True
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    actions: Mapped[list[OperatorAction]] = relationship(back_populates="ticket")

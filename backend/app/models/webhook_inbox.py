from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedText
from app.models.base import Base


class InboxStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class WebhookInbox(Base):
    """FR-04: Webhook 수신 실패 시 최대 3회 재시도. 멱등키로 중복 webhook 차단."""

    __tablename__ = "webhook_inbox"
    __table_args__ = (
        UniqueConstraint("jira_key", "changelog_id", name="uq_webhook_inbox_jira_changelog"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    jira_key: Mapped[str] = mapped_column(String(60), index=True)
    changelog_id: Mapped[str] = mapped_column(String(80), default="initial")
    payload_enc: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    status: Mapped[InboxStatus] = mapped_column(SAEnum(InboxStatus), default=InboxStatus.RECEIVED)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.ticket import TicketStatus


class TicketSummary(BaseModel):
    """티켓 목록용 요약 (FR-18).

    not_adopted: status=DONE 한정으로 AI 초안 미채택 여부.
    True면 운영자가 AI 초안을 채택하지 않고 직접 작성한 답변을 등록한 케이스.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    jira_key: str
    title: str
    status: TicketStatus
    assignee: str | None
    received_at: datetime
    completed_at: datetime | None
    not_adopted: bool = False


class ClassificationOut(BaseModel):
    category_code: str | None
    category_label: str | None
    predicted_category_code: str | None
    confidence: int
    was_corrected: bool


class DraftOut(BaseModel):
    id: int
    body_html: str
    body_html_edited: str | None
    confidence: int
    model: str
    generation_ms: int | None


class ReferenceOut(BaseModel):
    source_id: str
    source_title: str
    source_url: str
    kind: str
    snippet: str | None
    score: float
    position: int


class TicketDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    jira_key: str
    title: str
    body: str | None
    reporter: str | None
    attachments: list | None
    assignee: str | None
    status: TicketStatus
    received_at: datetime
    completed_at: datetime | None
    classification: ClassificationOut | None
    draft: DraftOut | None
    references: list[ReferenceOut]


class WebhookAck(BaseModel):
    ok: bool
    duplicate: bool
    jira_key: str
    inbox_id: int


class TicketListResponse(BaseModel):
    items: list[TicketSummary]
    total: int
    counts: dict[str, int]

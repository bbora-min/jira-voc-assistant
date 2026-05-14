"""Webhook → Ticket → 분류/RAG/초안 파이프라인.

Phase 2: webhook → Ticket 저장 + WS push.
Phase 4 (현재): webhook → Ticket 저장(PENDING) → asyncio.gather(retrieve, classify)
              → draft → Draft + Classification + References persist → 상태 IN_PROGRESS
              → ticket_updated WS push.

WS 매니저 초기화가 안 된 환경(seed script 등)에서도 동작하도록 broadcast는 RuntimeError를 흡수.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.core.ws_manager import get_ws_manager
from app.db import session_scope
from app.deps import get_tracker
from app.models import (
    Classification,
    Draft,
    InboxStatus,
    KpiEvent,
    KpiEventType,
    Reference,
    Ticket,
    TicketStatus,
    WebhookInbox,
)
from app.providers.rag.base import RetrievedChunk
from app.providers.tracker.mock import MockJira
from app.services.classifier import classify, code_to_category_id
from app.services.drafter import generate as generate_draft
from app.services.retriever import retrieve

logger = logging.getLogger(__name__)


def _extract_keys(payload: dict) -> tuple[str, str]:
    issue = payload.get("issue") or {}
    key = issue.get("key") or payload.get("issue_key") or "UNKNOWN"
    changelog = payload.get("changelog") or {}
    changelog_id = str(changelog.get("id") or payload.get("timestamp") or "initial")
    return key, changelog_id


async def enqueue_webhook(payload: dict) -> dict[str, Any]:
    """Sync 진입점: webhook_inbox에 INSERT (멱등)."""
    jira_key, changelog_id = _extract_keys(payload)
    payload_json = json.dumps(payload, ensure_ascii=False)

    with session_scope() as s:
        existing = (
            s.query(WebhookInbox)
            .filter_by(jira_key=jira_key, changelog_id=changelog_id)
            .one_or_none()
        )
        if existing:
            logger.info("webhook duplicate jira_key=%s changelog=%s", jira_key, changelog_id)
            return {"jira_key": jira_key, "changelog_id": changelog_id, "duplicate": True,
                    "inbox_id": existing.id}

        inbox = WebhookInbox(
            jira_key=jira_key,
            changelog_id=changelog_id,
            payload_enc=payload_json,
            status=InboxStatus.RECEIVED,
        )
        s.add(inbox)
        s.flush()
        s.add(KpiEvent(event_type=KpiEventType.WEBHOOK_RECEIVED, ticket_id=None))
        return {"jira_key": jira_key, "changelog_id": changelog_id, "duplicate": False,
                "inbox_id": inbox.id}


async def _broadcast(event: dict) -> None:
    try:
        await get_ws_manager().broadcast(event)
    except RuntimeError:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("ws broadcast failed")


async def process_webhook(inbox_id: int) -> None:
    """BackgroundTask 본체. webhook_inbox 처리 → 티켓 + 분류 + 초안 + 참고문서 영속화."""
    # 1) inbox 잠금 + 페이로드 디코드
    with session_scope() as s:
        inbox = s.get(WebhookInbox, inbox_id)
        if not inbox:
            return
        if inbox.status == InboxStatus.PROCESSED:
            return
        inbox.status = InboxStatus.PROCESSING
        inbox.attempts += 1
        payload = json.loads(inbox.payload_enc) if inbox.payload_enc else {}

    # 2) Tracker 등록 + 티켓 메타데이터 확보
    tracker = get_tracker()
    try:
        if isinstance(tracker, MockJira):
            ticket_view = await tracker.register_from_webhook(payload)
        else:
            jira_key, _ = _extract_keys(payload)
            ticket_view = await tracker.fetch_ticket(jira_key)
    except Exception as exc:  # noqa: BLE001
        logger.exception("tracker register failed for inbox %s", inbox_id)
        with session_scope() as s:
            inbox = s.get(WebhookInbox, inbox_id)
            if inbox:
                inbox.status = InboxStatus.FAILED
                inbox.last_error = str(exc)[:480]
        return

    # 3) Ticket 저장 (PII 자동 암호화)
    with session_scope() as s:
        existing_ticket = s.query(Ticket).filter_by(jira_key=ticket_view.key).one_or_none()
        if existing_ticket is None:
            ticket = Ticket(
                jira_key=ticket_view.key,
                title_enc=ticket_view.title,
                body_enc=ticket_view.body,
                reporter_enc=ticket_view.reporter,
                attachments_json=ticket_view.attachments or None,
                assignee=ticket_view.assignee,
                status=TicketStatus.PENDING,
            )
            s.add(ticket)
            s.flush()
            ticket_id = ticket.id
            new_ticket = True
        else:
            ticket_id = existing_ticket.id
            new_ticket = False

    # 4) 즉시 ticket_created push (운영자 화면에 "생성 중" 상태로 등장)
    await _broadcast({
        "type": "ticket_created" if new_ticket else "ticket_updated",
        "id": f"ws-{inbox_id}",
        "payload": {
            "id": ticket_id,
            "jira_key": ticket_view.key,
            "title": ticket_view.title,
            "status": TicketStatus.PENDING.value,
            "received_at": ticket_view.created_at.isoformat() if ticket_view.created_at else None,
            "stage": "GENERATING",
        },
    })

    # 5) 병렬: RAG retrieve + 분류
    title = ticket_view.title or ""
    body = ticket_view.body or ""
    query_text = f"{title}\n{body}".strip()

    t_pipeline = time.monotonic()
    try:
        retrieval_task = asyncio.create_task(retrieve(query_text, k=5))
        classify_task = asyncio.create_task(classify(title=title, body=body))
        chunks, cls = await asyncio.gather(retrieval_task, classify_task)
    except Exception as exc:  # noqa: BLE001
        logger.exception("retrieve/classify failed for ticket %s", ticket_id)
        chunks, cls = [], None  # type: ignore[assignment]

    # 6) Drafter (retrieval chunk 의존)
    try:
        draft = await generate_draft(title=title, body=body, chunks=chunks)
    except Exception as exc:  # noqa: BLE001
        logger.exception("draft failed for ticket %s", ticket_id)
        draft = None

    pipeline_ms = int((time.monotonic() - t_pipeline) * 1000)

    # 7) 영속화
    with session_scope() as s:
        # Classification
        if cls is not None:
            cat_id = code_to_category_id(cls.category_code)
            s.add(Classification(
                ticket_id=ticket_id,
                category_id=cat_id,
                predicted_category_id=cat_id,
                confidence=cls.confidence,
            ))

        # References
        for idx, c in enumerate(chunks):
            s.add(Reference(
                ticket_id=ticket_id,
                source_id=c.source_id,
                source_title=c.source_title,
                source_url=c.source_url,
                kind=c.kind,
                snippet=(c.text[:500] if c.text else None),
                score=float(c.score),
                position=idx,
            ))

        # Draft
        if draft is not None:
            s.add(Draft(
                ticket_id=ticket_id,
                body_html=draft.body_html,
                confidence=draft.confidence,
                model=draft.raw_model,
                generation_ms=draft.generation_ms,
            ))
            # 상태 전환
            tk = s.get(Ticket, ticket_id)
            if tk:
                tk.status = TicketStatus.IN_PROGRESS

        # KPI
        s.add(KpiEvent(
            event_type=KpiEventType.DRAFT_GENERATED,
            ticket_id=ticket_id,
            value_num=float(pipeline_ms),
        ))

        # inbox 종료
        inbox = s.get(WebhookInbox, inbox_id)
        if inbox:
            inbox.status = InboxStatus.PROCESSED
            inbox.processed_at = datetime.now(timezone.utc)

    # 8) ticket_updated push (초안 완료)
    await _broadcast({
        "type": "ticket_updated",
        "id": f"ws-{inbox_id}-done",
        "payload": {
            "id": ticket_id,
            "jira_key": ticket_view.key,
            "status": TicketStatus.IN_PROGRESS.value if draft else TicketStatus.PENDING.value,
            "stage": "READY" if draft else "FAILED",
            "generation_ms": pipeline_ms,
        },
    })

    logger.info(
        "processed inbox=%s ticket_id=%s key=%s draft=%s class=%s chunks=%d ms=%d",
        inbox_id, ticket_id, ticket_view.key,
        bool(draft), (cls.category_code if cls else "-"), len(chunks), pipeline_ms,
    )

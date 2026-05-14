"""운영자 워크플로 API.

PATCH /api/tickets/:id/draft       — 초안 편집 저장 (body_html_edited)
POST  /api/tickets/:id/approve     — 승인 → MockJira 코멘트 등록 → status=DONE
POST  /api/tickets/:id/reject      — 거부(사유) → status=REJECTED
POST  /api/tickets/:id/reclassify  — 카테고리 수정 → was_corrected=true + CLASSIFICATION_CORRECTED KPI
POST  /api/tickets/:id/regenerate  — 같은 컨텍스트로 drafter 재호출 → 새 Draft 추가
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.ws_manager import get_ws_manager
from app.db import get_db, session_scope
from app.deps import get_tracker
from app.models import (
    ActionType,
    Category,
    Classification,
    Draft,
    KpiEventType,
    Reference,
    Ticket,
    TicketStatus,
)
from app.providers.rag.base import RetrievedChunk
from app.providers.tracker.mock import MockJira
from app.services.actions import html_to_plain, levenshtein, record_action, record_kpi
from app.services.drafter import generate as generate_draft

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tickets", tags=["actions"])


# ─────────────────────────── 공통 헬퍼 ────────────────────────────


async def _broadcast(event: dict) -> None:
    try:
        await get_ws_manager().broadcast(event)
    except RuntimeError:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("ws broadcast failed")
    # Phase 7.7: 운영자 액션은 KPI 카드/시계열에 영향 → 캐시 무효화
    try:
        from app.services.kpi_cache import get_kpi_cache
        get_kpi_cache().invalidate()
    except Exception:  # noqa: BLE001
        logger.exception("kpi cache invalidation failed")


def _get_latest_draft(db: Session, ticket_id: int) -> Draft | None:
    return db.execute(
        select(Draft).where(Draft.ticket_id == ticket_id).order_by(desc(Draft.id)).limit(1)
    ).scalar_one_or_none()


def _get_latest_classification(db: Session, ticket_id: int) -> Classification | None:
    return db.execute(
        select(Classification).where(Classification.ticket_id == ticket_id)
        .order_by(desc(Classification.id)).limit(1)
    ).scalar_one_or_none()


# ─────────────────────────── 1) 초안 편집 저장 ────────────────────────────


class DraftPatch(BaseModel):
    body_html_edited: str = Field(..., min_length=0, max_length=200_000)


@router.patch("/{ticket_id}/draft")
def patch_draft(
    ticket_id: int,
    payload: DraftPatch,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    draft = _get_latest_draft(db, ticket_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    draft.body_html_edited = payload.body_html_edited
    record_action(db, ticket_id=ticket_id, user_id=None, action=ActionType.EDIT,
                  payload={"len": len(payload.body_html_edited)})
    db.commit()
    return {"ok": True, "id": draft.id}


# ─────────────────────────── 2) 승인 → MockJira 코멘트 + DONE ────────────────────────────


@router.post("/{ticket_id}/approve")
async def approve(ticket_id: int) -> dict:
    """승인은 외부(MockJira) 호출이 필요해 await + async."""
    with session_scope() as s:
        ticket = s.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="ticket not found")
        draft = _get_latest_draft(s, ticket_id)
        if not draft:
            raise HTTPException(status_code=400, detail="no draft to approve")

        final_html = draft.body_html_edited or draft.body_html
        orig_plain = html_to_plain(draft.body_html)
        edited_plain = html_to_plain(final_html)
        edit_distance = levenshtein(orig_plain, edited_plain)
        draft.edit_distance = edit_distance

        jira_key = ticket.jira_key
        received_at = ticket.received_at

    # MockJira 호출 (트랜잭션 밖)
    tracker = get_tracker()
    comment_id = ""
    try:
        comment_id = await tracker.post_comment(jira_key, final_html)
    except Exception as exc:  # noqa: BLE001
        logger.exception("post_comment failed for %s", jira_key)
        raise HTTPException(status_code=502, detail=f"tracker error: {exc}")

    with session_scope() as s:
        ticket = s.get(Ticket, ticket_id)
        response_ms = 0.0
        if ticket:
            now = datetime.now(timezone.utc)
            ticket.status = TicketStatus.DONE
            ticket.completed_at = now
            # SQLite는 datetime을 naive로 저장 — 비교 전 UTC로 정규화
            received = ticket.received_at
            if received and received.tzinfo is None:
                received = received.replace(tzinfo=timezone.utc)
            if received:
                response_ms = (now - received).total_seconds() * 1000.0

        record_action(s, ticket_id=ticket_id, user_id=None, action=ActionType.APPROVE,
                      payload={"comment_id": comment_id, "edit_distance": edit_distance})
        record_kpi(s, event_type=KpiEventType.DRAFT_APPROVED, ticket_id=ticket_id,
                   value_num=float(edit_distance))
        record_kpi(s, event_type=KpiEventType.RESPONSE_SENT, ticket_id=ticket_id,
                   value_num=float(response_ms))
        if edit_distance > 0:
            record_kpi(s, event_type=KpiEventType.DRAFT_EDITED, ticket_id=ticket_id,
                       value_num=float(edit_distance))

    await _broadcast({
        "type": "ticket_updated",
        "id": f"approve-{ticket_id}",
        "payload": {
            "id": ticket_id,
            "jira_key": jira_key,
            "status": TicketStatus.DONE.value,
            "stage": "DONE",
            "comment_id": comment_id,
        },
    })
    logger.info("approved ticket=%s jira_key=%s comment=%s edit_dist=%d",
                ticket_id, jira_key, comment_id, edit_distance)
    return {
        "ok": True, "status": TicketStatus.DONE.value,
        "comment_id": comment_id, "edit_distance": edit_distance,
    }


# ─── 3) AI 초안 미채택 + 운영자 직접 작성본 등록 + 사유 수집 (UI: "수정 후 등록") ───
# 운영팀 워크플로상 모든 티켓은 반드시 코멘트 등록됨. "답변 없이 종결"은 없음.
# 이 엔드포인트는 AI 초안을 채택하지 않고 운영자가 직접 작성한 답변을 Jira에 등록하면서
# 미채택 사유를 LLM 학습용 negative feedback 으로 보존한다.


class RejectBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    manual_body_html: str | None = Field(default=None, max_length=200_000)


@router.post("/{ticket_id}/reject")
async def reject(ticket_id: int, body: RejectBody) -> dict:
    with session_scope() as s:
        ticket = s.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="ticket not found")
        draft = _get_latest_draft(s, ticket_id)
        if not draft:
            raise HTTPException(status_code=400, detail="no draft to reject")

        # 운영자 작성본 우선, 없으면 편집본, 없으면 AI 원본
        final_html = body.manual_body_html or draft.body_html_edited or draft.body_html
        orig_plain = html_to_plain(draft.body_html)
        edited_plain = html_to_plain(final_html)
        edit_distance = levenshtein(orig_plain, edited_plain)
        draft.body_html_edited = final_html
        draft.edit_distance = edit_distance

        jira_key = ticket.jira_key

    tracker = get_tracker()
    comment_id = ""
    try:
        comment_id = await tracker.post_comment(jira_key, final_html)
    except Exception as exc:  # noqa: BLE001
        logger.exception("post_comment failed for %s", jira_key)
        raise HTTPException(status_code=502, detail=f"tracker error: {exc}")

    with session_scope() as s:
        ticket = s.get(Ticket, ticket_id)
        response_ms = 0.0
        if ticket:
            now = datetime.now(timezone.utc)
            ticket.status = TicketStatus.DONE
            ticket.completed_at = now
            received = ticket.received_at
            if received and received.tzinfo is None:
                received = received.replace(tzinfo=timezone.utc)
            if received:
                response_ms = (now - received).total_seconds() * 1000.0

        record_action(s, ticket_id=ticket_id, user_id=None, action=ActionType.REJECT,
                      payload={"reason": body.reason, "comment_id": comment_id,
                               "edit_distance": edit_distance})
        # DRAFT_REJECTED 의미 = "AI 초안 미채택" — value_text 는 LLM 학습용 negative feedback
        record_kpi(s, event_type=KpiEventType.DRAFT_REJECTED, ticket_id=ticket_id,
                   value_num=float(edit_distance), value_text=body.reason[:480])
        record_kpi(s, event_type=KpiEventType.RESPONSE_SENT, ticket_id=ticket_id,
                   value_num=float(response_ms))
        if edit_distance > 0:
            record_kpi(s, event_type=KpiEventType.DRAFT_EDITED, ticket_id=ticket_id,
                       value_num=float(edit_distance))

    await _broadcast({
        "type": "ticket_updated",
        "id": f"reject-{ticket_id}",
        "payload": {
            "id": ticket_id, "jira_key": jira_key,
            "status": TicketStatus.DONE.value, "stage": "DONE",
            "comment_id": comment_id, "not_adopted": True,
        },
    })
    logger.info("rejected(not_adopted) ticket=%s jira_key=%s comment=%s edit_dist=%d reason=%r",
                ticket_id, jira_key, comment_id, edit_distance, body.reason[:80])
    return {
        "ok": True, "status": TicketStatus.DONE.value,
        "comment_id": comment_id, "edit_distance": edit_distance,
        "not_adopted": True,
    }


# ─────────────────────────── 4) 재분류 (카테고리 수정) ────────────────────────────


class ReclassifyBody(BaseModel):
    category_id: int


@router.post("/{ticket_id}/reclassify")
async def reclassify(
    ticket_id: int,
    body: ReclassifyBody,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="ticket not found")
    cat = db.get(Category, body.category_id)
    if not cat or not cat.is_active:
        raise HTTPException(status_code=400, detail="invalid category")

    cls = _get_latest_classification(db, ticket_id)
    if not cls:
        raise HTTPException(status_code=400, detail="no classification yet")

    if cls.category_id == body.category_id:
        return {"ok": True, "changed": False}

    prev_code = None
    if cls.category_id is not None:
        prev = db.get(Category, cls.category_id)
        prev_code = prev.code if prev else None

    cls.category_id = body.category_id
    cls.was_corrected = True
    cls.corrected_at = datetime.now(timezone.utc)
    record_action(db, ticket_id=ticket_id, user_id=None, action=ActionType.RECLASSIFY,
                  payload={"from": prev_code, "to": cat.code})
    record_kpi(db, event_type=KpiEventType.CLASSIFICATION_CORRECTED, ticket_id=ticket_id,
               value_text=f"{prev_code}→{cat.code}")
    db.commit()

    await _broadcast({
        "type": "ticket_updated",
        "id": f"reclassify-{ticket_id}",
        "payload": {
            "id": ticket_id, "jira_key": ticket.jira_key,
            "stage": "RECLASSIFIED", "category_code": cat.code,
        },
    })
    return {"ok": True, "changed": True, "to": cat.code}


# ─────────────────────────── 5) 재생성 (drafter 재호출) ────────────────────────────


@router.post("/{ticket_id}/regenerate")
async def regenerate(ticket_id: int, background: BackgroundTasks) -> dict:
    """현재 ticket + 저장된 references 를 컨텍스트로 drafter 재호출.
    무거운 작업이므로 BackgroundTask 처리, 202 즉시 반환."""
    with session_scope() as s:
        ticket = s.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="ticket not found")
        if ticket.status in (TicketStatus.DONE, TicketStatus.REJECTED):
            raise HTTPException(status_code=400, detail=f"cannot regenerate in status {ticket.status.value}")

    background.add_task(_regenerate_task, ticket_id)
    return {"ok": True, "queued": True}


async def _regenerate_task(ticket_id: int) -> None:
    with session_scope() as s:
        ticket = s.get(Ticket, ticket_id)
        if not ticket:
            return
        title = ticket.title_enc or ""
        body = ticket.body_enc or ""
        jira_key = ticket.jira_key
        refs = s.execute(
            select(Reference).where(Reference.ticket_id == ticket_id)
            .order_by(Reference.position)
        ).scalars().all()
        chunks = [
            RetrievedChunk(
                text=(r.snippet or ""),
                source_id=r.source_id, source_title=r.source_title,
                source_url=r.source_url, score=r.score, kind=r.kind,
            ) for r in refs
        ]

    await _broadcast({
        "type": "ticket_updated",
        "id": f"regen-start-{ticket_id}",
        "payload": {"id": ticket_id, "jira_key": jira_key, "stage": "GENERATING"},
    })

    t0 = time.monotonic()
    try:
        draft = await generate_draft(title=title, body=body, chunks=chunks)
    except Exception:  # noqa: BLE001
        logger.exception("regenerate failed for ticket %s", ticket_id)
        return
    took_ms = int((time.monotonic() - t0) * 1000)

    with session_scope() as s:
        s.add(Draft(
            ticket_id=ticket_id, body_html=draft.body_html,
            confidence=draft.confidence, model=draft.raw_model,
            generation_ms=draft.generation_ms,
        ))
        record_action(s, ticket_id=ticket_id, user_id=None, action=ActionType.REGENERATE,
                      payload={"model": draft.raw_model, "gen_ms": draft.generation_ms})
        record_kpi(s, event_type=KpiEventType.DRAFT_GENERATED, ticket_id=ticket_id,
                   value_num=float(took_ms))

    await _broadcast({
        "type": "ticket_updated",
        "id": f"regen-done-{ticket_id}",
        "payload": {"id": ticket_id, "jira_key": jira_key, "stage": "READY", "generation_ms": took_ms},
    })


# ─────────────────────────── 6) Mock Jira 코멘트 조회 (검증용) ────────────────────────────


@router.get("/{ticket_id}/jira-comments")
async def list_jira_comments(ticket_id: int) -> dict:
    """승인 후 MockJira에 실제로 코멘트가 등록되었는지 UI에서 보여주기 위한 헬퍼."""
    with session_scope() as s:
        ticket = s.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="ticket not found")
        jira_key = ticket.jira_key

    tracker = get_tracker()
    if not isinstance(tracker, MockJira):
        return {"items": [], "note": "real tracker — fetch via Jira UI"}
    return {"items": await tracker.list_comments(jira_key)}

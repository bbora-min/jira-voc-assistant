from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    ActionType,
    Category,
    Classification,
    Draft,
    OperatorAction,
    Reference,
    Ticket,
    TicketStatus,
)
from app.schemas.ticket import (
    ClassificationOut,
    DraftOut,
    ReferenceOut,
    TicketDetail,
    TicketListResponse,
    TicketSummary,
)

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


def _to_summary(t: Ticket, *, not_adopted: bool = False) -> TicketSummary:
    return TicketSummary(
        id=t.id,
        jira_key=t.jira_key,
        title=t.title_enc or "(제목 없음)",
        status=t.status,
        assignee=t.assignee,
        received_at=t.received_at,
        completed_at=t.completed_at,
        not_adopted=not_adopted,
    )


@router.get("", response_model=TicketListResponse)
def list_tickets(
    db: Annotated[Session, Depends(get_db)],
    status: TicketStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TicketListResponse:
    base = select(Ticket).order_by(desc(Ticket.received_at))
    if status is not None:
        base = base.where(Ticket.status == status)
    rows = db.execute(base.offset(offset).limit(limit)).scalars().all()

    count_stmt = select(func.count(Ticket.id))
    if status is not None:
        count_stmt = count_stmt.where(Ticket.status == status)
    total = db.scalar(count_stmt) or 0

    counts_rows = db.execute(
        select(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status)
    ).all()
    counts_map = {r[0].value: r[1] for r in counts_rows if r[0]}

    # DONE 티켓의 미채택 여부 = 마지막 종결 액션(APPROVE/REJECT)이 REJECT인 경우만.
    # (한 번 REJECT 후 다시 APPROVE된 케이스는 채택으로 간주)
    done_ids = [t.id for t in rows if t.status == TicketStatus.DONE]
    not_adopted_set: set[int] = set()
    if done_ids:
        action_rows = db.execute(
            select(OperatorAction.ticket_id, OperatorAction.action)
            .where(OperatorAction.ticket_id.in_(done_ids),
                   OperatorAction.action.in_([ActionType.REJECT, ActionType.APPROVE]))
            .order_by(desc(OperatorAction.id))
        ).all()
        last_action: dict[int, ActionType] = {}
        for tid, act in action_rows:
            if tid not in last_action:
                last_action[tid] = act
        not_adopted_set = {tid for tid, act in last_action.items() if act == ActionType.REJECT}

    return TicketListResponse(
        items=[_to_summary(t, not_adopted=t.id in not_adopted_set) for t in rows],
        total=total,
        counts={s.value: counts_map.get(s.value, 0) for s in TicketStatus},
    )


def _category_lookup(db: Session) -> dict[int, tuple[str, str]]:
    rows = db.execute(select(Category.id, Category.code, Category.label_ko)).all()
    return {r[0]: (r[1], r[2]) for r in rows}


@router.get("/{ticket_id}", response_model=TicketDetail)
def get_ticket(
    ticket_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> TicketDetail:
    t = db.get(Ticket, ticket_id)
    if not t:
        raise HTTPException(status_code=404, detail="ticket not found")

    cls = db.execute(
        select(Classification).where(Classification.ticket_id == ticket_id)
        .order_by(desc(Classification.id)).limit(1)
    ).scalar_one_or_none()

    drafts = db.execute(
        select(Draft).where(Draft.ticket_id == ticket_id)
        .order_by(desc(Draft.id)).limit(1)
    ).scalar_one_or_none()

    refs = db.execute(
        select(Reference).where(Reference.ticket_id == ticket_id)
        .order_by(Reference.position.asc())
    ).scalars().all()

    cat_lookup = _category_lookup(db)

    classification_out: ClassificationOut | None = None
    if cls is not None:
        cat_code, cat_label = cat_lookup.get(cls.category_id or 0, (None, None))
        pred_code, _ = cat_lookup.get(cls.predicted_category_id or 0, (None, None))
        classification_out = ClassificationOut(
            category_code=cat_code,
            category_label=cat_label,
            predicted_category_code=pred_code,
            confidence=cls.confidence,
            was_corrected=cls.was_corrected,
        )

    draft_out: DraftOut | None = None
    if drafts is not None:
        draft_out = DraftOut(
            id=drafts.id,
            body_html=drafts.body_html,
            body_html_edited=drafts.body_html_edited,
            confidence=drafts.confidence,
            model=drafts.model,
            generation_ms=drafts.generation_ms,
        )

    return TicketDetail(
        id=t.id,
        jira_key=t.jira_key,
        title=t.title_enc or "",
        body=t.body_enc,
        reporter=t.reporter_enc,
        attachments=t.attachments_json,
        assignee=t.assignee,
        status=t.status,
        received_at=t.received_at,
        completed_at=t.completed_at,
        classification=classification_out,
        draft=draft_out,
        references=[
            ReferenceOut(
                source_id=r.source_id, source_title=r.source_title, source_url=r.source_url,
                kind=r.kind, snippet=r.snippet, score=r.score, position=r.position,
            ) for r in refs
        ],
    )

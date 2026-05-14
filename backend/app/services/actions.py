"""운영자 액션 → operator_actions + kpi_events 기록 헬퍼."""
from __future__ import annotations

import re
from sqlalchemy.orm import Session

from app.models import (
    ActionType,
    KpiEvent,
    KpiEventType,
    OperatorAction,
)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def html_to_plain(html: str) -> str:
    text = _TAG_RE.sub(" ", html or "")
    text = _WS_RE.sub(" ", text).strip()
    return text


def levenshtein(a: str, b: str) -> int:
    """단순 Levenshtein. 짧은 답변 비교에 충분."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            row.append(min(row[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = row
    return prev[-1]


def record_action(
    db: Session,
    *,
    ticket_id: int,
    user_id: int | None,
    action: ActionType,
    payload: dict | None = None,
) -> OperatorAction:
    row = OperatorAction(
        ticket_id=ticket_id,
        user_id=user_id,
        action=action,
        payload_json=payload,
    )
    db.add(row)
    return row


def record_kpi(
    db: Session,
    *,
    event_type: KpiEventType,
    ticket_id: int | None = None,
    value_num: float | None = None,
    value_text: str | None = None,
) -> KpiEvent:
    row = KpiEvent(
        event_type=event_type,
        ticket_id=ticket_id,
        value_num=value_num,
        value_text=value_text,
    )
    db.add(row)
    return row

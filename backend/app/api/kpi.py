"""KPI 집계 API.

핵심 산식 (Phase 5 보완 보고서 §6 - 운영 도메인 기준):
  - 채택률 (adoption_rate)        = APPROVED / (APPROVED + REJECTED)
  - 분류 정확도 (cls_accuracy)    = 1 - CORRECTED / GENERATED
  - 평균 수정거리 (avg_edit_dist) = avg(DRAFT_EDITED.value_num)
  - 평균 응답시간 (avg_resp_ms)   = avg(RESPONSE_SENT.value_num)

엔드포인트:
  GET /api/kpi/summary?from=&to=&group_by=day  — 4개 카드 + 일별 시계열
  GET /api/kpi/rejection-reasons?from=&to=&limit=20 — 미채택 사유 목록 + 키워드 빈도
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import KpiEvent, KpiEventType, Ticket
from app.services.kpi_cache import get_kpi_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/kpi", tags=["kpi"])


# ─────────────────────────── 공통 헬퍼 ────────────────────────────

DEFAULT_RANGE_DAYS = 30


def _parse_range(from_: str | None, to_: str | None) -> tuple[datetime, datetime]:
    """[from, to] 를 UTC datetime 으로 정규화. 누락 시 최근 30일."""
    if to_:
        to_dt = datetime.fromisoformat(to_).replace(tzinfo=timezone.utc)
    else:
        to_dt = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59, microsecond=999_999)
    if from_:
        from_dt = datetime.fromisoformat(from_).replace(tzinfo=timezone.utc)
    else:
        from_dt = (to_dt - timedelta(days=DEFAULT_RANGE_DAYS - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return from_dt, to_dt


def _count_events(db: Session, evt: KpiEventType, lo: datetime, hi: datetime) -> int:
    stmt = (
        select(func.count(KpiEvent.id))
        .where(KpiEvent.event_type == evt, KpiEvent.created_at >= lo, KpiEvent.created_at <= hi)
    )
    return int(db.execute(stmt).scalar() or 0)


def _avg_value(db: Session, evt: KpiEventType, lo: datetime, hi: datetime) -> tuple[float, int]:
    stmt = (
        select(func.avg(KpiEvent.value_num), func.count(KpiEvent.id))
        .where(KpiEvent.event_type == evt, KpiEvent.created_at >= lo, KpiEvent.created_at <= hi,
               KpiEvent.value_num.isnot(None))
    )
    row = db.execute(stmt).one()
    return (float(row[0] or 0.0), int(row[1] or 0))


def _ratio(num: int, den: int) -> float:
    return float(num) / float(den) if den > 0 else 0.0


# ─────────────────────────── 1) /summary ────────────────────────────


@router.get("/summary")
def summary(
    db: Annotated[Session, Depends(get_db)],
    from_: str | None = Query(default=None, alias="from"),
    to_: str | None = Query(default=None, alias="to"),
    group_by: str = Query(default="day", pattern="^(day|week)$"),
) -> dict:
    cache_key = ("summary", from_, to_, group_by)
    cache = get_kpi_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = _compute_summary(db, from_, to_, group_by)
    cache.set(cache_key, result)
    return result


def _compute_summary(
    db: Session, from_: str | None, to_: str | None, group_by: str
) -> dict:
    lo, hi = _parse_range(from_, to_)

    # 4개 카드 산식
    n_generated = _count_events(db, KpiEventType.DRAFT_GENERATED, lo, hi)
    n_approved = _count_events(db, KpiEventType.DRAFT_APPROVED, lo, hi)
    n_rejected = _count_events(db, KpiEventType.DRAFT_REJECTED, lo, hi)
    n_corrected = _count_events(db, KpiEventType.CLASSIFICATION_CORRECTED, lo, hi)
    avg_edit, n_edit = _avg_value(db, KpiEventType.DRAFT_EDITED, lo, hi)
    avg_resp, n_resp = _avg_value(db, KpiEventType.RESPONSE_SENT, lo, hi)

    adoption_rate = _ratio(n_approved, n_approved + n_rejected)
    cls_accuracy = 1.0 - _ratio(n_corrected, n_generated)

    # 일별 / 주별 시계열 — SQLite/MySQL 양쪽 호환을 위해 strftime 사용
    # SQLite: strftime('%Y-%m-%d', col),  MySQL 8: 동일 지원
    if group_by == "week":
        # ISO week (월요일 기준) — %Y-%W
        bucket_expr = func.strftime("%Y-%W", KpiEvent.created_at)
    else:
        bucket_expr = func.strftime("%Y-%m-%d", KpiEvent.created_at)

    def _bucket_counts(evt: KpiEventType) -> dict[str, int]:
        rows = db.execute(
            select(bucket_expr.label("bucket"), func.count(KpiEvent.id))
            .where(KpiEvent.event_type == evt, KpiEvent.created_at >= lo, KpiEvent.created_at <= hi)
            .group_by("bucket")
        ).all()
        return {str(r[0]): int(r[1]) for r in rows}

    def _bucket_avg(evt: KpiEventType) -> dict[str, float]:
        rows = db.execute(
            select(bucket_expr.label("bucket"), func.avg(KpiEvent.value_num))
            .where(KpiEvent.event_type == evt, KpiEvent.created_at >= lo, KpiEvent.created_at <= hi,
                   KpiEvent.value_num.isnot(None))
            .group_by("bucket")
        ).all()
        return {str(r[0]): float(r[1] or 0.0) for r in rows}

    gen_by_bucket = _bucket_counts(KpiEventType.DRAFT_GENERATED)
    app_by_bucket = _bucket_counts(KpiEventType.DRAFT_APPROVED)
    rej_by_bucket = _bucket_counts(KpiEventType.DRAFT_REJECTED)
    cor_by_bucket = _bucket_counts(KpiEventType.CLASSIFICATION_CORRECTED)
    resp_by_bucket = _bucket_avg(KpiEventType.RESPONSE_SENT)
    edit_by_bucket = _bucket_avg(KpiEventType.DRAFT_EDITED)

    all_buckets = sorted(
        set(gen_by_bucket) | set(app_by_bucket) | set(rej_by_bucket) | set(cor_by_bucket)
        | set(resp_by_bucket) | set(edit_by_bucket)
    )
    series = []
    for b in all_buckets:
        a = app_by_bucket.get(b, 0)
        r = rej_by_bucket.get(b, 0)
        g = gen_by_bucket.get(b, 0)
        c = cor_by_bucket.get(b, 0)
        series.append({
            "bucket": b,
            "generated": g,
            "approved": a,
            "rejected": r,
            "corrected": c,
            "adoption_rate": _ratio(a, a + r),
            "classification_accuracy": (1.0 - _ratio(c, g)) if g > 0 else None,
            "avg_response_ms": resp_by_bucket.get(b),
            "avg_edit_distance": edit_by_bucket.get(b),
        })

    return {
        "period": {"from": lo.date().isoformat(), "to": hi.date().isoformat(), "group_by": group_by},
        "cards": {
            "adoption_rate": {"value": adoption_rate, "num": n_approved, "den": n_approved + n_rejected},
            "classification_accuracy": {"value": cls_accuracy, "num": n_generated - n_corrected, "den": n_generated},
            "avg_edit_distance": {"value": avg_edit, "samples": n_edit},
            "avg_response_ms": {"value": avg_resp, "samples": n_resp},
        },
        "counts": {
            "DRAFT_GENERATED": n_generated,
            "DRAFT_APPROVED": n_approved,
            "DRAFT_REJECTED": n_rejected,
            "CLASSIFICATION_CORRECTED": n_corrected,
        },
        "series": series,
    }


# ─────────────────────────── 2) /rejection-reasons ────────────────────────────


# 한국어 토큰 추출 — 형태소 분석 없이 단순 2자 이상 한글/영문 토큰
_TOKEN_RE = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9_-]{1,}")

# 의미 없는 빈출 토큰 (도메인 stopwords) — 실제 의미 있는 단어가 묻히지 않게
_STOPWORDS = {
    "초안", "내용", "답변", "수정", "직접", "작성", "관련", "필요", "경우", "사용",
    "있음", "없음", "있는", "없는", "있어", "있다", "한다", "합니다", "한다고",
    "있고", "하지만", "그리고", "또는", "그래서", "때문", "위해", "통해", "대한", "대해",
    "the", "and", "or", "for", "with", "this", "that", "have", "has", "but",
}


def _extract_keywords(text: str) -> list[str]:
    return [tok for tok in _TOKEN_RE.findall(text.lower()) if tok not in _STOPWORDS]


@router.get("/rejection-reasons")
def rejection_reasons(
    db: Annotated[Session, Depends(get_db)],
    from_: str | None = Query(default=None, alias="from"),
    to_: str | None = Query(default=None, alias="to"),
    limit: int = Query(default=20, ge=1, le=200),
) -> dict:
    """미채택 사유 빈도 분석 + 최근 사유 목록.

    value_text 가 LLM 학습용 negative feedback. 단순 토큰 빈도 + 최근 N건 목록 반환.
    """
    cache_key = ("rejection-reasons", from_, to_, limit)
    cache = get_kpi_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = _compute_rejection_reasons(db, from_, to_, limit)
    cache.set(cache_key, result)
    return result


def _compute_rejection_reasons(
    db: Session, from_: str | None, to_: str | None, limit: int
) -> dict:
    lo, hi = _parse_range(from_, to_)

    # 미채택 이벤트 + ticket 메타 join (title 은 EncryptedText 컬럼)
    rows = db.execute(
        select(KpiEvent.id, KpiEvent.ticket_id, KpiEvent.value_text, KpiEvent.value_num,
               KpiEvent.created_at, Ticket.jira_key, Ticket.title_enc)
        .join(Ticket, KpiEvent.ticket_id == Ticket.id, isouter=True)
        .where(and_(
            KpiEvent.event_type == KpiEventType.DRAFT_REJECTED,
            KpiEvent.created_at >= lo, KpiEvent.created_at <= hi,
            KpiEvent.value_text.isnot(None),
        ))
        .order_by(KpiEvent.id.desc())
    ).all()

    total = len(rows)
    counter: Counter[str] = Counter()
    items: list[dict] = []
    for r in rows:
        text = r[2] or ""
        counter.update(_extract_keywords(text))
        if len(items) < limit:
            items.append({
                "ticket_id": r[1],
                "jira_key": r[5],
                "ticket_title": r[6],
                "reason": text,
                "edit_distance": float(r[3]) if r[3] is not None else None,
                "created_at": r[4].isoformat() if r[4] else None,
            })

    top_keywords = [{"keyword": k, "count": c} for k, c in counter.most_common(20)]

    return {
        "period": {"from": lo.date().isoformat(), "to": hi.date().isoformat()},
        "total": total,
        "top_keywords": top_keywords,
        "items": items,
    }

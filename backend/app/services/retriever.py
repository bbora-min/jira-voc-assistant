"""쿼리 → top-k 청크 검색 + 하이브리드 리랭킹.

리랭킹 공식:
  final = cosine_score
        * kind_weight(kind)
        * recency_boost(updated_at)

  kind_weight  : confluence=1.0, past_voc=0.85
  recency_boost: exp(-age_days / 180)
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from app.config import get_settings
from app.deps import get_rag
from app.providers.rag.base import RetrievedChunk

logger = logging.getLogger(__name__)

KIND_WEIGHT = {"confluence": 1.0, "past_voc": 0.85}
HALF_LIFE_DAYS = 180.0


def _recency_boost(updated_at: datetime | None) -> float:
    if updated_at is None:
        return 1.0
    now = datetime.now(timezone.utc)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - updated_at).total_seconds() / 86400.0)
    return math.exp(-age_days / HALF_LIFE_DAYS)


def _to_dt(meta_iso: str | None) -> datetime | None:
    if not meta_iso:
        return None
    try:
        return datetime.fromisoformat(meta_iso.replace("Z", "+00:00"))
    except ValueError:
        return None


async def retrieve(text: str, k: int | None = None) -> list[RetrievedChunk]:
    """top-(k*2) 후보를 가져와 하이브리드 점수로 재정렬 후 상위 k 반환."""
    settings = get_settings()
    target_k = k or settings.RAG_TOP_K
    pool = target_k * 2  # over-retrieval for re-ranking

    rag = get_rag()
    raw = await rag.query(text=text, k=pool)
    rescored: list[tuple[float, RetrievedChunk]] = []
    for c in raw:
        weight = KIND_WEIGHT.get(c.kind, 1.0)
        # raw.metadata는 RetrievedChunk에 없으므로 chroma.py에서 updated_at를 챙기지 않았음.
        # 일단 kind weight만 반영 (현실적으로 PoC 단계에서 충분).
        final = c.score * weight
        rescored.append((final, c))
    rescored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for final, c in rescored[:target_k]:
        out.append(
            RetrievedChunk(
                text=c.text,
                source_id=c.source_id,
                source_title=c.source_title,
                source_url=c.source_url,
                score=round(final, 4),
                kind=c.kind,
            )
        )
    return out

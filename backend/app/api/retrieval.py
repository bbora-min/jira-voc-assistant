"""RAG 검색 디버그 엔드포인트. Phase 4 이전까지 운영자가 검색 품질을 확인할 수 있게 한다."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.retriever import retrieve

router = APIRouter(prefix="/api/retrieval", tags=["retrieval"])


@router.get("/preview")
async def preview(
    q: str = Query(..., min_length=1, max_length=500, description="검색 쿼리"),
    k: int = Query(default=5, ge=1, le=20),
) -> dict:
    chunks = await retrieve(q, k=k)
    return {
        "query": q,
        "k": k,
        "items": [
            {
                "source_id": c.source_id,
                "source_title": c.source_title,
                "source_url": c.source_url,
                "kind": c.kind,
                "score": c.score,
                "snippet": (c.text[:280] + "…") if len(c.text) > 280 else c.text,
            }
            for c in chunks
        ],
    }

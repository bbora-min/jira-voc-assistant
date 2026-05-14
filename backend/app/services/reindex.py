"""Confluence 가이드 + 과거 VOC를 청킹·임베딩하여 Chroma에 upsert.

호출 트리거:
  1) APScheduler 시간당 잡 (main.py lifespan)
  2) POST /api/admin/reindex 수동 트리거
  3) 운영자가 티켓을 승인하면 해당 티켓 본문/답변을 past_voc로 추가 색인 (Phase 5)

멱등성: delete_by_source 후 upsert.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db import session_scope
from app.deps import get_kb, get_rag
from app.models import Ticket, TicketStatus
from app.providers.rag.base import IndexDocument
from app.services.chunk import chunk_markdown

logger = logging.getLogger(__name__)


async def reindex_confluence() -> dict[str, Any]:
    rag = get_rag()
    kb = get_kb()
    docs = await kb.list_documents(since=None)
    total_chunks = 0
    for d in docs:
        await rag.delete_by_source(d.id)
        chunks = chunk_markdown(d.content_md)
        if not chunks:
            continue
        idx_docs = [
            IndexDocument(
                source_id=d.id,
                text=c.text,
                metadata={
                    "source_title": d.title,
                    "source_url": d.url,
                    "kind": d.kind,
                    "position": c.position,
                    "heading_path": " > ".join(c.heading_path) or "",
                    "updated_at": d.updated_at.isoformat(),
                },
            )
            for c in chunks
        ]
        await rag.upsert(idx_docs)
        total_chunks += len(idx_docs)
    logger.info("reindex_confluence: %d docs, %d chunks", len(docs), total_chunks)
    return {"docs": len(docs), "chunks": total_chunks, "kind": "confluence"}


async def reindex_past_voc() -> dict[str, Any]:
    """승인 완료된 과거 티켓을 past_voc kind로 색인."""
    rag = get_rag()
    rows: list[Ticket] = []
    with session_scope() as s:
        rows = list(
            s.execute(
                select(Ticket).where(Ticket.status == TicketStatus.DONE)
            ).scalars()
        )
    total_chunks = 0
    for t in rows:
        source_id = f"past-voc-{t.id}"
        await rag.delete_by_source(source_id)
        text = f"# {t.title_enc or ''}\n\n{t.body_enc or ''}".strip()
        if len(text) < 50:
            continue
        chunks = chunk_markdown(text)
        idx_docs = [
            IndexDocument(
                source_id=source_id,
                text=c.text,
                metadata={
                    "source_title": f"[과거 VOC] {t.jira_key}",
                    "source_url": f"app://tickets/{t.id}",
                    "kind": "past_voc",
                    "position": c.position,
                    "updated_at": (t.completed_at or t.received_at).isoformat()
                                  if (t.completed_at or t.received_at) else "",
                },
            )
            for c in chunks
        ]
        await rag.upsert(idx_docs)
        total_chunks += len(idx_docs)
    logger.info("reindex_past_voc: %d tickets, %d chunks", len(rows), total_chunks)
    return {"docs": len(rows), "chunks": total_chunks, "kind": "past_voc"}


async def reindex_all() -> dict[str, Any]:
    conf = await reindex_confluence()
    voc = await reindex_past_voc()
    return {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "confluence": conf,
        "past_voc": voc,
    }

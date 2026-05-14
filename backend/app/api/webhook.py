"""FR-01..04: Jira Webhook 수신.
응답을 100ms 이내로 돌려주기 위해 BackgroundTask로 파이프라인을 분리한다."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Request

from app.services.pipeline import enqueue_webhook, process_webhook

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhook"])


@router.post("/api/webhook/jira")
async def jira_webhook(
    background: BackgroundTasks,
    payload: dict[str, Any] = Body(...),
    request: Request = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    meta = await enqueue_webhook(payload)
    if not meta["duplicate"]:
        background.add_task(process_webhook, meta["inbox_id"])
    return {
        "ok": True,
        "duplicate": meta["duplicate"],
        "jira_key": meta["jira_key"],
        "inbox_id": meta["inbox_id"],
    }

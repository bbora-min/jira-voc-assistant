"""Dev-only endpoints. INTEGRATION_MODE=mock 일 때만 main.py에 등록된다.

운영자 UI에서 'Inject sample ticket' 버튼이 호출하는 엔드포인트.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.deps import APP_ROOT
from app.services.pipeline import enqueue_webhook, process_webhook

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dev", tags=["dev"])

WEBHOOKS_DIR = APP_ROOT / "seed" / "webhooks"


def _list_payloads() -> list[Path]:
    return sorted(WEBHOOKS_DIR.glob("*.json"))


@router.get("/sample-webhooks")
def list_sample_webhooks() -> dict:
    files = _list_payloads()
    return {"items": [p.name for p in files]}


@router.post("/inject-webhook/{name}")
async def inject(name: str, background: BackgroundTasks) -> dict:
    p = WEBHOOKS_DIR / name
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail=f"sample {name} not found")
    payload = json.loads(p.read_text(encoding="utf-8"))
    meta = await enqueue_webhook(payload)
    if not meta["duplicate"]:
        background.add_task(process_webhook, meta["inbox_id"])
    return {"ok": True, "duplicate": meta["duplicate"], "jira_key": meta["jira_key"]}


@router.post("/inject-random")
async def inject_random(background: BackgroundTasks) -> dict:
    """랜덤 샘플을 주입하되 jira_key를 새 UUID 접미사로 바꿔 매번 신규로 인식되게 함."""
    import random
    import uuid

    files = _list_payloads()
    if not files:
        raise HTTPException(status_code=404, detail="no sample webhooks")
    p = random.choice(files)
    payload = json.loads(p.read_text(encoding="utf-8"))
    issue = payload.setdefault("issue", {})
    issue["key"] = f"DEMO-{uuid.uuid4().hex[:6].upper()}"
    payload["changelog"] = {"id": uuid.uuid4().hex[:10]}
    meta = await enqueue_webhook(payload)
    if not meta["duplicate"]:
        background.add_task(process_webhook, meta["inbox_id"])
    return {"ok": True, "jira_key": meta["jira_key"], "sample": p.name}

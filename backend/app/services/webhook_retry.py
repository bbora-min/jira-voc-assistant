"""Webhook 실패 재시도 (Phase 7.4).

webhook_inbox.status=FAILED 인 행을 주기적으로 재처리. 멱등키 UNIQUE 제약으로
중복 처리 위험은 없고, 멱등 처리(같은 jira_key 면 기존 ticket 재사용)는 pipeline 이 보장.

지수 백오프: attempts 별 대기 분(分) = [1, 5, 30, 180]. attempts >= MAX_ATTEMPTS 면 영구 포기.

운영자가 admin/inbox 페이지에서 수동 재시도도 가능 (POST /api/admin/inbox/{id}/retry — 7.4 미구현,
필요 시 Phase 8 추가).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import session_scope
from app.models import InboxStatus, WebhookInbox

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4   # 0 → 1 → 2 → 3 → 4 (4회 실패 시 영구 포기)
BACKOFF_MINUTES = [0, 1, 5, 30, 180]  # attempts=N 일 때 다음 시도까지 대기 분


def _next_retry_after(attempts: int) -> timedelta:
    idx = min(attempts, len(BACKOFF_MINUTES) - 1)
    return timedelta(minutes=BACKOFF_MINUTES[idx])


def _eligible(inbox: WebhookInbox, now: datetime) -> bool:
    if inbox.status != InboxStatus.FAILED:
        return False
    if inbox.attempts >= MAX_ATTEMPTS:
        return False
    # received_at + backoff(attempts) <= now
    received = inbox.received_at
    if received and received.tzinfo is None:
        received = received.replace(tzinfo=timezone.utc)
    if received is None:
        return True
    return (received + _next_retry_after(inbox.attempts)) <= now


async def retry_failed_inboxes() -> dict:
    """APScheduler 가 호출. 재시도 후보를 RECEIVED 로 되돌려 다음 process_webhook 진입 가능하게 함.

    실제 처리는 process_webhook 가 담당하므로, 여기서는 status 만 리셋하고
    별도 BackgroundTask 또는 직접 호출로 트리거한다.
    """
    from app.services.pipeline import process_webhook   # 지연 import 로 순환 방지

    now = datetime.now(timezone.utc)
    to_retry: list[int] = []
    with session_scope() as s:
        rows = s.execute(
            select(WebhookInbox).where(WebhookInbox.status == InboxStatus.FAILED)
        ).scalars().all()
        for inbox in rows:
            if _eligible(inbox, now):
                inbox.status = InboxStatus.RECEIVED
                to_retry.append(inbox.id)

    if to_retry:
        logger.info("webhook retry: re-enqueueing %d failed inboxes: %s", len(to_retry), to_retry)
        for inbox_id in to_retry:
            try:
                await process_webhook(inbox_id)
            except Exception:  # noqa: BLE001
                logger.exception("retry_failed_inboxes: process_webhook(%s) failed", inbox_id)

    return {"retried": len(to_retry), "inbox_ids": to_retry}

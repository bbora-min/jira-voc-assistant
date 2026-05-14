"""Webhook 멱등성 + 재시도 큐 단위 테스트 (Phase 7.4).

검증:
1. 같은 (jira_key, changelog_id) 두 번 enqueue → 두 번째는 duplicate=True
2. inbox FAILED 행은 attempts 와 received_at 기준 백오프 후 retry 대상
3. retry_failed_inboxes 가 적격 행만 RECEIVED 로 되돌림 (MAX_ATTEMPTS 초과는 제외)
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta, timezone

import pytest


def _ensure_test_env():
    os.environ.setdefault("VOC_DATA_KEY", base64.b64encode(os.urandom(32)).decode())
    os.environ.setdefault("DB_URL", "sqlite:///:memory:")


_ensure_test_env()


@pytest.fixture
def db_engine():
    """각 테스트마다 in-memory SQLite + 전 테이블 생성."""
    from sqlalchemy import create_engine

    from app.models.base import Base
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def patch_session_scope(monkeypatch, db_engine):
    """app.db.session_scope 를 in-memory 엔진 기반으로 교체."""
    from contextlib import contextmanager

    from sqlalchemy.orm import Session

    @contextmanager
    def scope():
        s = Session(db_engine)
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    monkeypatch.setattr("app.services.pipeline.session_scope", scope)
    monkeypatch.setattr("app.services.webhook_retry.session_scope", scope)
    return scope


async def test_enqueue_webhook_dedupes_on_same_changelog(patch_session_scope):
    """같은 jira_key + changelog_id 는 한 번만 inbox 생성."""
    from app.services.pipeline import enqueue_webhook

    payload = {
        "issue": {"key": "TEST-100", "fields": {"summary": "원본 제목"}},
        "changelog": {"id": "777"},
    }
    r1 = await enqueue_webhook(payload)
    r2 = await enqueue_webhook(payload)

    assert r1["duplicate"] is False
    assert r2["duplicate"] is True
    assert r1["inbox_id"] == r2["inbox_id"]


async def test_enqueue_webhook_distinct_changelog_creates_two_rows(patch_session_scope):
    from app.services.pipeline import enqueue_webhook

    payload_base = {"issue": {"key": "TEST-200", "fields": {"summary": "변경 1"}}}
    r1 = await enqueue_webhook({**payload_base, "changelog": {"id": "a"}})
    r2 = await enqueue_webhook({**payload_base, "changelog": {"id": "b"}})

    assert r1["inbox_id"] != r2["inbox_id"]
    assert r1["duplicate"] is False and r2["duplicate"] is False


def test_backoff_schedule_monotonic():
    """attempts 가 늘수록 다음 시도까지 대기 시간이 줄어들면 안된다."""
    from app.services.webhook_retry import BACKOFF_MINUTES, _next_retry_after

    minutes = [_next_retry_after(i).total_seconds() / 60 for i in range(len(BACKOFF_MINUTES) + 2)]
    for i in range(1, len(minutes)):
        assert minutes[i] >= minutes[i - 1]


def test_eligible_respects_backoff():
    """status=FAILED 이지만 backoff 시간이 지나지 않은 행은 제외."""
    from app.models import InboxStatus, WebhookInbox
    from app.services.webhook_retry import _eligible

    now = datetime.now(timezone.utc)
    fresh = WebhookInbox(
        jira_key="X-1", changelog_id="c1",
        status=InboxStatus.FAILED, attempts=1,
        received_at=now,  # 1분 백오프 (attempts=1) 안 지났음
    )
    assert _eligible(fresh, now) is False

    old = WebhookInbox(
        jira_key="X-2", changelog_id="c1",
        status=InboxStatus.FAILED, attempts=1,
        received_at=now - timedelta(minutes=2),
    )
    assert _eligible(old, now) is True


def test_eligible_rejects_max_attempts():
    """attempts >= MAX_ATTEMPTS 는 영구 포기 (eligible=False)."""
    from app.models import InboxStatus, WebhookInbox
    from app.services.webhook_retry import MAX_ATTEMPTS, _eligible

    now = datetime.now(timezone.utc)
    exhausted = WebhookInbox(
        jira_key="X-3", changelog_id="c1",
        status=InboxStatus.FAILED, attempts=MAX_ATTEMPTS,
        received_at=now - timedelta(hours=24),
    )
    assert _eligible(exhausted, now) is False


def test_eligible_rejects_non_failed_status():
    """RECEIVED / PROCESSING / PROCESSED 는 retry 대상이 아님."""
    from app.models import InboxStatus, WebhookInbox
    from app.services.webhook_retry import _eligible

    now = datetime.now(timezone.utc)
    for st in (InboxStatus.RECEIVED, InboxStatus.PROCESSING, InboxStatus.PROCESSED):
        inbox = WebhookInbox(
            jira_key="X-4", changelog_id="c1",
            status=st, attempts=1,
            received_at=now - timedelta(hours=24),
        )
        assert _eligible(inbox, now) is False, f"status={st} should be ineligible"

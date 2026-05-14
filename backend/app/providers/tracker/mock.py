"""In-memory mock Jira. Webhook payload으로 등록한 티켓을 보관하고,
운영자가 승인하면 코멘트를 남긴다."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.providers.tracker.base import IssueTracker, TrackerTicket

logger = logging.getLogger(__name__)


class MockJira(IssueTracker):
    def __init__(self) -> None:
        self._tickets: dict[str, TrackerTicket] = {}
        self._comments: dict[str, list[dict]] = {}
        self._lock = asyncio.Lock()

    async def register_from_webhook(self, payload: dict) -> TrackerTicket:
        issue = payload.get("issue", {}) or {}
        fields = issue.get("fields", {}) or {}
        key = issue.get("key") or payload.get("issue_key") or "MOCK-?"
        reporter = (fields.get("reporter") or {}).get("displayName")
        assignee = (fields.get("assignee") or {}).get("accountId")
        ticket = TrackerTicket(
            key=key,
            title=fields.get("summary") or "(제목 없음)",
            body=fields.get("description") or "",
            reporter=reporter,
            assignee=assignee,
            status=(fields.get("status") or {}).get("name", "To Do"),
            attachments=fields.get("attachment") or [],
            created_at=datetime.now(timezone.utc),
        )
        async with self._lock:
            self._tickets[key] = ticket
            self._comments.setdefault(key, [])
        return ticket

    async def fetch_ticket(self, key: str) -> TrackerTicket:
        async with self._lock:
            t = self._tickets.get(key)
        if not t:
            raise KeyError(f"Mock Jira에 {key} 없음")
        return t

    async def post_comment(self, key: str, body_html: str) -> str:
        comment_id = f"cmt-{uuid.uuid4().hex[:10]}"
        entry = {
            "id": comment_id,
            "body_html": body_html,
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        async with self._lock:
            self._comments.setdefault(key, []).append(entry)
        logger.info("MockJira.post_comment %s -> %s (%d chars)", key, comment_id, len(body_html))
        return comment_id

    async def transition(self, key: str, status: str) -> None:
        async with self._lock:
            t = self._tickets.get(key)
            if t:
                t.status = status

    async def list_comments(self, key: str) -> list[dict]:
        async with self._lock:
            return list(self._comments.get(key, []))

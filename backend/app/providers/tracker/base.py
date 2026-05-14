from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class TrackerTicket:
    key: str
    title: str
    body: str
    reporter: str | None
    assignee: str | None
    status: str
    attachments: list[dict] = field(default_factory=list)
    created_at: datetime | None = None


class IssueTracker(Protocol):
    async def fetch_ticket(self, key: str) -> TrackerTicket: ...
    async def post_comment(self, key: str, body_html: str) -> str: ...
    async def transition(self, key: str, status: str) -> None: ...

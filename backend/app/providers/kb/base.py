from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class KBDoc:
    id: str
    title: str
    url: str
    content_md: str
    updated_at: datetime
    kind: str = "confluence"  # confluence | past_voc


class KnowledgeBase(Protocol):
    async def list_documents(self, since: datetime | None = None) -> list[KBDoc]: ...
    async def fetch_document(self, doc_id: str) -> KBDoc: ...

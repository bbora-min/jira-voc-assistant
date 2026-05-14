from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class IndexDocument:
    source_id: str
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    text: str
    source_id: str
    source_title: str
    source_url: str
    score: float
    kind: str = "confluence"
    updated_at: datetime | None = None


class RAGProvider(Protocol):
    """Phase 3에서 실 구현. Phase 2에서는 인터페이스만 존재."""
    async def upsert(self, docs: list[IndexDocument]) -> None: ...
    async def query(
        self, *, text: str, k: int = 5, filters: dict | None = None
    ) -> list[RetrievedChunk]: ...
    async def delete_by_source(self, source_id: str) -> None: ...

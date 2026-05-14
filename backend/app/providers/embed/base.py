from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    """Document/query 텍스트를 고정 길이 벡터로 변환."""

    @property
    def name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...

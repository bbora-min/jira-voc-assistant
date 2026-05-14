"""Voyage AI 임베딩 클라이언트. VOYAGE_API_KEY 가 있을 때만 사용."""
from __future__ import annotations

import asyncio
import logging

import voyageai

from app.providers.embed.base import Embedder

logger = logging.getLogger(__name__)


class VoyageEmbedder(Embedder):
    def __init__(self, api_key: str, model: str = "voyage-3-large") -> None:
        self._client = voyageai.Client(api_key=api_key)
        self._model = model
        # voyage-3-large dim = 1024 (필요 시 / probe 가능)
        self._dim: int | None = None

    @property
    def name(self) -> str:
        return f"voyage:{self._model}"

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._dim = 1024  # voyage-3-large default
        return self._dim

    async def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        def _call() -> list[list[float]]:
            r = self._client.embed(texts=texts, model=self._model, input_type=input_type)
            return r.embeddings  # type: ignore[return-value]

        return await asyncio.to_thread(_call)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "document")

    async def embed_query(self, text: str) -> list[float]:
        out = await self._embed([text], "query")
        return out[0]

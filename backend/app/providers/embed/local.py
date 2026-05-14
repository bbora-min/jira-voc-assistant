"""로컬 ONNX 임베딩 (chromadb 기본 함수 = all-MiniLM-L6-v2, 384-dim).

API 키 없이 동작하므로 PoC/CI 환경에 적합. 최초 호출 시 모델 ONNX를 자동 다운로드한다.
"""
from __future__ import annotations

import asyncio
import logging

from app.providers.embed.base import Embedder

logger = logging.getLogger(__name__)


class LocalEmbedder(Embedder):
    def __init__(self) -> None:
        # 지연 import: chromadb load 시 비싼 의존성을 회피
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        self._fn = DefaultEmbeddingFunction()
        self._dim = 384  # all-MiniLM-L6-v2

    @property
    def name(self) -> str:
        return "local:all-MiniLM-L6-v2"

    @property
    def dim(self) -> int:
        return self._dim

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        def _call() -> list[list[float]]:
            return [list(map(float, v)) for v in self._fn(texts)]

        return await asyncio.to_thread(_call)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        out = await self._embed([text])
        return out[0]

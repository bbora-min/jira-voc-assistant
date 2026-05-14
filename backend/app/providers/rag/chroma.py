"""ChromaDB 기반 RAGProvider. PersistentClient를 쓰므로 docker 없이도 동작.

문서 1건은 (source_id, chunk_position)으로 식별되는 다수의 청크로 쪼개진다.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import chromadb

from app.providers.embed.base import Embedder
from app.providers.rag.base import IndexDocument, RAGProvider, RetrievedChunk

logger = logging.getLogger(__name__)


def _chunk_id(source_id: str, position: int) -> str:
    return f"{source_id}::{position}"


class ChromaRAGProvider(RAGProvider):
    def __init__(
        self,
        *,
        persist_dir: Path,
        collection_name: str,
        embedder: Embedder,
    ) -> None:
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._embedder = embedder
        # embedding_function은 None — 외부에서 vector 직접 전달
        # hnsw:space=cosine → 거리 ∈ [0, 2], 유사도 = 1 - distance/2  (수식은 query()에서 적용)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=None,
            metadata={
                "embedder": embedder.name,
                "dim": embedder.dim,
                "hnsw:space": "cosine",
            },
        )

    async def upsert(self, docs: list[IndexDocument]) -> None:
        if not docs:
            return
        texts = [d.text for d in docs]
        embeddings = await self._embedder.embed_documents(texts)
        ids = [_chunk_id(d.source_id, d.metadata.get("position", i)) for i, d in enumerate(docs)]
        metadatas = [
            {**d.metadata, "source_id": d.source_id}
            for d in docs
        ]
        await asyncio.to_thread(
            self._collection.upsert,
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=texts,
        )
        logger.info("Chroma upsert: %d chunks", len(docs))

    async def query(
        self,
        *,
        text: str,
        k: int = 5,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:
        embedding = await self._embedder.embed_query(text)
        result: dict[str, Any] = await asyncio.to_thread(
            self._collection.query,
            query_embeddings=[embedding],
            n_results=k,
            where=filters or None,
        )
        out: list[RetrievedChunk] = []
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        for cid, doc, meta, dist in zip(ids, docs, metas, dists, strict=False):
            meta = meta or {}
            # Chroma hnsw:cosine은 distance ∈ [0, 2]. 정규화된 유사도 = 1 - distance/2 ∈ [0, 1]
            score = max(0.0, 1.0 - float(dist) / 2.0)
            out.append(
                RetrievedChunk(
                    text=doc,
                    source_id=str(meta.get("source_id") or cid.split("::", 1)[0]),
                    source_title=str(meta.get("source_title") or ""),
                    source_url=str(meta.get("source_url") or ""),
                    score=score,
                    kind=str(meta.get("kind") or "confluence"),
                )
            )
        return out

    async def delete_by_source(self, source_id: str) -> None:
        await asyncio.to_thread(self._collection.delete, where={"source_id": source_id})

    def count(self) -> int:
        return int(self._collection.count())

    def collection_meta(self) -> dict:
        return {
            "name": self._collection.name,
            "count": self.count(),
            "embedder": self._embedder.name,
            "dim": self._embedder.dim,
        }

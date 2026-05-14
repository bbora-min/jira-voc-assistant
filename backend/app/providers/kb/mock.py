"""Markdown frontmatter 기반 mock Confluence. seed/corpus/*.md를 읽는다."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from app.providers.kb.base import KBDoc, KnowledgeBase

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw, body = m.group(1), m.group(2)
    meta: dict = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body.strip()


def _to_dt(s: str | None) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


class MockKnowledgeBase(KnowledgeBase):
    def __init__(self, corpus_dir: Path):
        self.corpus_dir = corpus_dir

    def _all_docs(self) -> list[KBDoc]:
        if not self.corpus_dir.exists():
            return []
        docs: list[KBDoc] = []
        for p in sorted(self.corpus_dir.glob("*.md")):
            try:
                text = p.read_text(encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                logger.warning("MockKB: %s 읽기 실패: %s", p, e)
                continue
            meta, body = _parse_frontmatter(text)
            docs.append(
                KBDoc(
                    id=meta.get("id") or p.stem,
                    title=meta.get("title") or p.stem,
                    url=meta.get("url") or f"mock://confluence/{p.stem}",
                    content_md=body,
                    updated_at=_to_dt(meta.get("updated_at")),
                    kind=meta.get("kind", "confluence"),
                )
            )
        return docs

    async def list_documents(self, since: datetime | None = None) -> list[KBDoc]:
        docs = self._all_docs()
        if since is None:
            return docs
        return [d for d in docs if d.updated_at >= since]

    async def fetch_document(self, doc_id: str) -> KBDoc:
        for d in self._all_docs():
            if d.id == doc_id:
                return d
        raise KeyError(f"MockKB에 {doc_id} 없음")

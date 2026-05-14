"""실제 Atlassian Confluence Cloud REST API v2 클라이언트 (Phase 7.3 skeleton).

INTEGRATION_MODE=real 일 때 사용. MockKnowledgeBase 와 동일한 KnowledgeBase Protocol 구현.

요구 환경 변수:
- CONFLUENCE_BASE_URL  (예: https://your.atlassian.net/wiki)
- CONFLUENCE_API_USER
- CONFLUENCE_API_TOKEN
- CONFLUENCE_SPACE_KEY (예: SPIM, SBOM — 인덱싱 대상 스페이스)

Phase 7.3 의 목표는 컴파일/타입 검증과 인터페이스 일치 확인. 라이브 통합은 별도 검증.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone

import httpx

from app.providers.kb.base import KBDoc, KnowledgeBase

logger = logging.getLogger(__name__)


class ConfluenceClient(KnowledgeBase):
    """Atlassian Confluence Cloud REST API v2 호출 클라이언트.

    문서: https://developer.atlassian.com/cloud/confluence/rest/v2/intro/
    """

    def __init__(
        self,
        base_url: str,
        user: str,
        token: str,
        space_keys: list[str],
        timeout: float = 15.0,
    ) -> None:
        if not base_url:
            raise ValueError("CONFLUENCE_BASE_URL required")
        if not space_keys:
            raise ValueError("at least one space_key required")
        self._base = base_url.rstrip("/")
        self._space_keys = space_keys
        basic = base64.b64encode(f"{user}:{token}".encode()).decode()
        self._client = httpx.AsyncClient(
            base_url=self._base,
            timeout=timeout,
            headers={
                "Authorization": f"Basic {basic}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    async def list_documents(self, since: datetime | None = None) -> list[KBDoc]:
        """대상 스페이스의 페이지 목록을 페이지네이션으로 수집.

        since 가 주어지면 그 시각 이후 수정된 페이지만 반환 (증분 색인용).
        """
        # space_key → space_id 조회 (v2 는 space_id 사용)
        space_ids: list[str] = []
        for key in self._space_keys:
            r = await self._client.get("/api/v2/spaces", params={"keys": key, "limit": 1})
            r.raise_for_status()
            results = r.json().get("results", [])
            if results:
                space_ids.append(results[0]["id"])

        docs: list[KBDoc] = []
        cursor: str | None = None
        for sid in space_ids:
            while True:
                params: dict[str, str | int] = {
                    "space-id": sid,
                    "body-format": "storage",
                    "limit": 100,
                }
                if cursor:
                    params["cursor"] = cursor
                r = await self._client.get("/api/v2/pages", params=params)
                r.raise_for_status()
                data = r.json()
                for page in data.get("results", []):
                    doc = _page_to_kbdoc(page, base=self._base)
                    if since is None or (doc.updated_at and doc.updated_at >= since):
                        docs.append(doc)
                next_cursor = data.get("_links", {}).get("next")
                if not next_cursor:
                    break
                cursor = next_cursor
        return docs

    async def fetch_document(self, doc_id: str) -> KBDoc:
        r = await self._client.get(
            f"/api/v2/pages/{doc_id}",
            params={"body-format": "storage"},
        )
        r.raise_for_status()
        return _page_to_kbdoc(r.json(), base=self._base)

    async def aclose(self) -> None:
        await self._client.aclose()


def _page_to_kbdoc(page: dict, *, base: str) -> KBDoc:
    page_id = str(page.get("id", ""))
    title = page.get("title") or ""
    body = (page.get("body") or {}).get("storage", {}).get("value", "") or ""
    # storage format 은 XHTML. 단순 텍스트 추출은 reindex 단계에서 BeautifulSoup 등으로 처리.
    updated_str = page.get("version", {}).get("createdAt")
    updated_at = _parse_iso(updated_str) or datetime.now(timezone.utc)
    web_url = f"{base}/spaces/_/pages/{page_id}"
    return KBDoc(
        id=page_id,
        title=title,
        url=web_url,
        content_md=body,
        updated_at=updated_at,
        kind="confluence",
    )


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None

"""실제 Atlassian Jira REST API v3 클라이언트 (Phase 7.3 skeleton).

INTEGRATION_MODE=real 일 때 사용. MockJira 와 동일한 IssueTracker Protocol 구현.

요구 환경 변수:
- JIRA_BASE_URL    (예: https://your.atlassian.net)
- JIRA_API_USER    (이메일)
- JIRA_API_TOKEN   (Atlassian account 에서 발급)

Phase 7.3 의 목표는 컴파일/타입 검증과 인터페이스 일치 확인. 실제 라이브 통합은
Production 배포 시점에 별도 통합 테스트(stage Jira 인스턴스 대상)로 검증.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone

import httpx

from app.providers.tracker.base import IssueTracker, TrackerTicket

logger = logging.getLogger(__name__)


class JiraClient(IssueTracker):
    """Atlassian Jira Cloud REST API v3 호출 클라이언트.

    문서: https://developer.atlassian.com/cloud/jira/platform/rest/v3/
    """

    def __init__(self, base_url: str, user: str, token: str, timeout: float = 10.0) -> None:
        if not base_url:
            raise ValueError("JIRA_BASE_URL required")
        self._base = base_url.rstrip("/")
        # Basic auth: base64(email:api_token)
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

    async def fetch_ticket(self, key: str) -> TrackerTicket:
        # GET /rest/api/3/issue/{issueIdOrKey}?fields=summary,description,reporter,assignee,status,attachment
        r = await self._client.get(
            f"/rest/api/3/issue/{key}",
            params={"fields": "summary,description,reporter,assignee,status,attachment,created"},
        )
        r.raise_for_status()
        data = r.json()
        f = data.get("fields", {}) or {}

        # Jira description 은 ADF(Atlassian Document Format) — 단순 텍스트만 추출
        description = _adf_to_text(f.get("description"))

        return TrackerTicket(
            key=data["key"],
            title=f.get("summary") or "",
            body=description,
            reporter=(f.get("reporter") or {}).get("displayName"),
            assignee=(f.get("assignee") or {}).get("accountId"),
            status=(f.get("status") or {}).get("name", "To Do"),
            attachments=f.get("attachment") or [],
            created_at=_parse_jira_dt(f.get("created")),
        )

    async def post_comment(self, key: str, body_html: str) -> str:
        # POST /rest/api/3/issue/{issueIdOrKey}/comment
        # Jira v3 는 ADF 본문 요구. PoC 는 HTML → 단순 paragraph 변환 (실제 도입 시 jira-text-to-adf 같은 라이브러리 권장)
        adf_body = _html_to_adf(body_html)
        r = await self._client.post(
            f"/rest/api/3/issue/{key}/comment",
            json={"body": adf_body},
        )
        r.raise_for_status()
        data = r.json()
        comment_id = str(data.get("id", ""))
        logger.info("Jira.post_comment %s -> %s (%d chars html)", key, comment_id, len(body_html))
        return comment_id

    async def transition(self, key: str, status: str) -> None:
        # POST /rest/api/3/issue/{issueIdOrKey}/transitions
        # status 이름 → transition id 매핑이 인스턴스마다 다르므로 GET 으로 먼저 조회
        r = await self._client.get(f"/rest/api/3/issue/{key}/transitions")
        r.raise_for_status()
        transitions = r.json().get("transitions", [])
        target = next(
            (t for t in transitions if (t.get("to") or {}).get("name", "").lower() == status.lower()),
            None,
        )
        if not target:
            raise ValueError(f"no transition to status={status!r} for {key}")
        r = await self._client.post(
            f"/rest/api/3/issue/{key}/transitions",
            json={"transition": {"id": target["id"]}},
        )
        r.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()


# ─────────────────────────── helpers ────────────────────────────


def _parse_jira_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    # 예: "2026-05-11T06:21:13.547+0000"
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _adf_to_text(adf: dict | None) -> str:
    """ADF JSON 트리에서 텍스트 노드만 평탄화. 완전 충실한 변환 아님."""
    if not adf:
        return ""
    out: list[str] = []

    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "text":
            out.append(node.get("text", ""))
        for child in node.get("content") or []:
            walk(child)
        if node.get("type") in {"paragraph", "heading"}:
            out.append("\n")

    walk(adf)
    return "".join(out).strip()


def _html_to_adf(html: str) -> dict:
    """매우 단순한 HTML → ADF 변환. 실제 도입 시에는 atlaskit/adf-utils 또는
    third-party 라이브러리 사용 권장. 여기서는 HTML 전체를 하나의 paragraph 로 감싸서
    Jira 코멘트로 전송 가능한 최소 형식만 만든다."""
    import re

    # 모든 태그 제거 → 순수 텍스트로 변환 (정보 손실 있음, PoC 한정)
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text).strip()
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": text or "(empty)"}]}
        ],
    }

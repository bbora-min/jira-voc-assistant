"""VOC 본문 + RAG 청크 → 답변 초안 HTML (FR-09~11).

claude-opus-4-7 + draft_voc_response tool 강제 호출.
초안은 [#N] citation 마커를 사용하며 N은 retrieval 인덱스 (1-based).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from jinja2 import Template
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.deps import get_llm
from app.models import PromptKind, PromptTemplate
from app.providers.llm.base import CacheBlock
from app.providers.rag.base import RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class DraftResult:
    body_html: str
    confidence: int
    citations: list[int]   # 1-based indices into the references list
    raw_model: str
    generation_ms: int


DEFAULT_SYSTEM = """\
당신은 SPIM/SBOM 운영팀의 VOC 응대 보조원입니다.
입력된 VOC 본문과 사내 가이드 발췌(References)를 바탕으로 운영자가 검토할 답변 초안을 작성하세요.

원칙:
- 친절하고 정중한 한국어 존댓말로 작성합니다.
- 본문은 HTML 형식 (<p>, <ul>, <li>, <pre>, <code> 등을 사용 가능).
- References 항목을 인용할 때는 [#1], [#2] 같은 마커를 사용합니다. 마커 숫자는 References 1-based 인덱스와 일치해야 합니다.
- 추측은 피하고, References에서 확신할 수 없는 경우 운영자에게 확인을 요청합니다.
- 답변 마지막에 추가 문의 안내 한 줄을 포함합니다.

confidence는 0~100:
- 80+: References가 직접적이고 답변이 명확한 경우
- 50~80: 부분적으로 매칭되거나 일부 추정이 필요한 경우
- 50 미만: References가 거의 도움이 안 되는 경우
"""


USER_TEMPLATE = """\
[참고 문서 (References)]
{% if chunks %}{% for c in chunks %}[#{{ loop.index }}] {{ c.source_title }}
{{ c.text }}
---
{% endfor %}{% else %}(검색된 참고 문서 없음){% endif %}

[VOC 티켓]
제목: {{ ticket.title }}
본문: {{ ticket.body }}
"""


DRAFT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "body_html": {
            "type": "string",
            "description": "운영자가 검토/수정할 답변 초안 (HTML)",
        },
        "confidence": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "초안 신뢰도",
        },
        "citations": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1},
            "description": "본문에서 사용한 References의 1-based 인덱스 목록",
        },
    },
    "required": ["body_html", "confidence", "citations"],
}


def _load_active_template(kind: PromptKind) -> str | None:
    with session_scope() as s:
        row = s.execute(
            select(PromptTemplate)
            .where(PromptTemplate.kind == kind, PromptTemplate.is_active.is_(True))
            .order_by(PromptTemplate.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        return row.content if row else None


async def generate(*, title: str, body: str, chunks: list[RetrievedChunk]) -> DraftResult:
    settings = get_settings()
    llm = get_llm()

    override = _load_active_template(PromptKind.DRAFT)
    system_text = override or DEFAULT_SYSTEM

    rendered_user = Template(USER_TEMPLATE).render(
        ticket={"title": title or "", "body": body or ""},
        chunks=[
            {"source_title": c.source_title, "text": c.text[:1500]}
            for c in chunks
        ],
    )

    t0 = time.monotonic()
    result = await llm.call_tool(
        model=settings.LLM_DRAFT_MODEL,
        system_blocks=[CacheBlock(text=system_text, cache=True)],
        user_text=rendered_user,
        tool_name="draft_voc_response",
        tool_description="Generate a VOC response draft (HTML) with confidence and citation indices.",
        tool_schema=DRAFT_TOOL_SCHEMA,
        max_tokens=2048,
        effort="high",
        thinking=True,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )
    took_ms = int((time.monotonic() - t0) * 1000)

    out = result.output
    return DraftResult(
        body_html=str(out.get("body_html") or ""),
        confidence=int(out.get("confidence") or 0),
        citations=[int(x) for x in (out.get("citations") or [])],
        raw_model=result.model,
        generation_ms=took_ms,
    )

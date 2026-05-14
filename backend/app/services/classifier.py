"""VOC 본문 → 3가지 카테고리 분류 (FR-13/14).

claude-sonnet-4-6 + classify_voc tool 강제 호출로 구조화 출력.
프롬프트 템플릿은 DB(prompt_templates kind=CLASSIFY)에서 로드.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from jinja2 import Template
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.deps import get_llm
from app.models import Category, PromptKind, PromptTemplate
from app.providers.llm.base import CacheBlock

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    category_code: str
    confidence: int
    raw_model: str
    generation_ms: int


DEFAULT_SYSTEM = """\
당신은 사내 SW 도구(SPIM/SBOM) 운영팀의 VOC 분류 보조원입니다.
입력된 Jira VOC 본문을 다음 세 가지 카테고리 중 하나로 분류하세요.

1) SYSTEM_ISSUE - 시스템 장애, 에러, 오작동, 빌드 실패 등 기존 동작이 정상 작동하지 않는 경우
2) FEATURE_INQUIRY - 사용법, 설정, 가이드 등 기존 기능에 대한 단순 문의
3) FEATURE_REQUEST - 신규 기능, 개선, 추가 지원 요청

분류 시 다음 원칙을 따르세요:
- '실패/에러/안 됨'은 SYSTEM_ISSUE
- '~ 있으면 좋겠다 / ~ 추가해 주세요'는 FEATURE_REQUEST
- '~ 어떻게 하나요 / ~ 가능한가요'는 FEATURE_INQUIRY

confidence는 0~100. 단서가 명확하면 80 이상, 애매하면 50~70.
"""

USER_TEMPLATE = """\
[티켓 제목]
{{ ticket.title }}

[티켓 본문]
{{ ticket.body }}
"""

CLASSIFY_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "category_code": {
            "type": "string",
            "enum": ["SYSTEM_ISSUE", "FEATURE_INQUIRY", "FEATURE_REQUEST"],
            "description": "분류 결과 카테고리 코드",
        },
        "confidence": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "분류 신뢰도 (0-100)",
        },
    },
    "required": ["category_code", "confidence"],
}


def _load_active_template(kind: PromptKind) -> tuple[int | None, str | None]:
    with session_scope() as s:
        row = s.execute(
            select(PromptTemplate)
            .where(PromptTemplate.kind == kind, PromptTemplate.is_active.is_(True))
            .order_by(PromptTemplate.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row:
            return row.id, row.content
        return None, None


async def classify(*, title: str, body: str) -> ClassificationResult:
    settings = get_settings()
    llm = get_llm()

    _, override = _load_active_template(PromptKind.CLASSIFY)
    system_text = override or DEFAULT_SYSTEM

    rendered_user = Template(USER_TEMPLATE).render(
        ticket={"title": title or "", "body": body or ""}
    )

    import time
    t0 = time.monotonic()
    result = await llm.call_tool(
        model=settings.LLM_CLASSIFY_MODEL,
        system_blocks=[CacheBlock(text=system_text, cache=True)],
        user_text=rendered_user,
        tool_name="classify_voc",
        tool_description="Classify the given VOC ticket text into one of 3 categories with a confidence score.",
        tool_schema=CLASSIFY_TOOL_SCHEMA,
        max_tokens=200,
        effort="low",
        thinking=False,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )
    took_ms = int((time.monotonic() - t0) * 1000)

    out = result.output
    code = str(out.get("category_code") or "FEATURE_INQUIRY")
    conf = int(out.get("confidence") or 0)
    return ClassificationResult(
        category_code=code,
        confidence=conf,
        raw_model=result.model,
        generation_ms=took_ms,
    )


def code_to_category_id(code: str) -> int | None:
    """category_code → categories.id 매핑."""
    with session_scope() as s:
        row = s.execute(select(Category).where(Category.code == code)).scalar_one_or_none()
        return row.id if row else None

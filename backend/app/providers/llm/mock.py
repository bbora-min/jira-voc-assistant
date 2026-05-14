"""ANTHROPIC_API_KEY 부재 시 fallback. 키워드 매칭 기반 결정적 분류 + 템플릿 초안.

실제 LLM 품질은 안 나지만 파이프라인이 끝까지 동작함을 보장하고,
CI/오프라인 환경에서 end-to-end 테스트를 가능하게 한다.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.providers.llm.base import CacheBlock, LLMProvider, LLMResult

logger = logging.getLogger(__name__)


_CATEGORY_RULES = [
    ("SYSTEM_ISSUE",
     ["실패", "에러", "오류", "오작동", "error", "fail", "crash", "안 됨", "안됨", "버그"]),
    ("FEATURE_REQUEST",
     ["요청", "추가", "기능 개발", "feature request", "있으면 좋겠", "지원해", "되었으면"]),
    ("FEATURE_INQUIRY",
     ["문의", "어떻게", "사용법", "방법", "가이드", "가능한가", "지원하나"]),
]


def _classify(text: str) -> tuple[str, int]:
    text_l = (text or "").lower()
    best_code, best_hits = "FEATURE_INQUIRY", 0
    for code, kws in _CATEGORY_RULES:
        hits = sum(1 for kw in kws if kw.lower() in text_l)
        if hits > best_hits:
            best_code, best_hits = code, hits
    # 신뢰도: 1~3 매칭 → 60/72/82, 그 이상 → 88. 매칭 0 → 50 (FEATURE_INQUIRY 기본).
    conf = {0: 50, 1: 60, 2: 72, 3: 82}.get(best_hits, 88)
    return best_code, conf


def _draft(text: str, retrieval: str | None) -> tuple[str, int, list[int]]:
    """간단한 마크다운 → HTML 변환된 답변. 신뢰도와 citation index 리턴."""
    cites = [1, 2, 3] if retrieval else []
    body = []
    body.append("<p>안녕하세요, 운영팀입니다. 문의 주셔서 감사합니다.</p>")
    if retrieval:
        body.append("<p>관련 사내 가이드를 검토한 결과 아래와 같이 안내드립니다.</p>")
        body.append("<ul>")
        body.append("<li>먼저 첨부된 가이드 문서를 참조해주세요. [#1]</li>")
        body.append("<li>유사한 사례에서는 설정값 점검이 우선이었습니다. [#2]</li>")
        body.append("<li>추가 정보가 필요한 경우 운영팀에 회신 부탁드립니다. [#3]</li>")
        body.append("</ul>")
    else:
        body.append("<p>현재 사내 가이드 문서를 추가 확인 중이며, 답변을 곧 제공드리겠습니다.</p>")
    body.append("<p>추가 문의사항은 본 티켓에 회신 부탁드립니다.</p>")
    return "\n".join(body), 70, cites


class MockLLMProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "mock"

    async def call_tool(
        self,
        *,
        model: str,
        system_blocks: list[CacheBlock],
        user_text: str,
        tool_name: str,
        tool_description: str,
        tool_schema: dict,
        max_tokens: int = 4096,
        effort: str | None = None,
        thinking: bool = False,
        timeout_seconds: float = 8.0,
    ) -> LLMResult:
        await asyncio.sleep(0.05)  # 약간의 지연 (현실감)

        # tool_name 기준으로 결과 형태 결정
        if tool_name == "classify_voc":
            code, conf = _classify(user_text)
            return LLMResult(
                output={"category_code": code, "confidence": conf},
                model=f"mock:{model}",
                input_tokens=len(user_text) // 3,
                output_tokens=20,
            )
        if tool_name == "draft_voc_response":
            # user_text에 retrieval 블록이 있으면 cites 포함
            has_retrieval = "[#1]" in user_text or "참고 문서" in user_text
            body, conf, cites = _draft(user_text, "yes" if has_retrieval else None)
            return LLMResult(
                output={"body_html": body, "confidence": conf, "citations": cites},
                model=f"mock:{model}",
                input_tokens=len(user_text) // 3,
                output_tokens=120,
            )
        raise NotImplementedError(f"MockLLM does not know tool {tool_name}")

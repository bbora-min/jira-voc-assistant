from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class CacheBlock:
    """system 메시지 구성 블록. cache=True → cache_control: ephemeral 적용."""
    text: str
    cache: bool = False


@dataclass
class LLMResult:
    """tool-use forced 호출의 결과."""
    output: dict[str, Any]
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    raw: Any = field(default=None, repr=False)


class LLMProvider(Protocol):
    """tool 강제 호출 기반 구조화 출력 인터페이스.

    호출자는 단일 tool을 정의하고 tool_choice로 강제한다.
    응답은 dict 형태의 tool 입력으로 반환된다.
    """

    @property
    def name(self) -> str: ...

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
    ) -> LLMResult: ...

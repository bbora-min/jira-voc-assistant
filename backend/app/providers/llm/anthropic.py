"""Anthropic Claude API 통합.

핵심 설계:
  - tool_choice로 단일 tool을 강제 호출해 구조화된 JSON 출력을 받는다.
  - system_blocks 중 cache=True 블록에 cache_control: ephemeral 을 붙여 prompt caching 활용.
  - Opus 4.7은 adaptive thinking만 지원 → thinking=True일 때 type:adaptive로 호출.
  - output_config.effort 로 thinking depth 조절 (low/medium/high/xhigh/max).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import anthropic

from app.providers.llm.base import CacheBlock, LLMProvider, LLMResult

logger = logging.getLogger(__name__)


class AnthropicLLMProvider(LLMProvider):
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    @property
    def name(self) -> str:
        return "anthropic"

    def _build_system(self, blocks: list[CacheBlock]) -> list[dict[str, Any]]:
        """system은 항상 list[TextBlockParam]. cache=True 블록에 cache_control 추가."""
        out: list[dict[str, Any]] = []
        for b in blocks:
            block: dict[str, Any] = {"type": "text", "text": b.text}
            if b.cache:
                block["cache_control"] = {"type": "ephemeral"}
            out.append(block)
        return out

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
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": self._build_system(system_blocks),
            "tools": [
                {
                    "name": tool_name,
                    "description": tool_description,
                    "input_schema": tool_schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": tool_name},
            "messages": [{"role": "user", "content": user_text}],
        }
        if thinking:
            request["thinking"] = {"type": "adaptive"}
        output_config: dict[str, Any] = {}
        if effort is not None:
            output_config["effort"] = effort
        if output_config:
            request["output_config"] = output_config

        try:
            resp = await asyncio.wait_for(
                self._client.messages.create(**request),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("Anthropic call_tool timeout (%.1fs) model=%s tool=%s",
                           timeout_seconds, model, tool_name)
            raise

        # tool_use 블록 찾기
        tool_output: dict[str, Any] | None = None
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", "") == tool_name:
                tool_output = dict(block.input)  # type: ignore[arg-type]
                break
        if tool_output is None:
            raise RuntimeError(f"Anthropic response did not include tool_use for {tool_name}")

        u = resp.usage
        return LLMResult(
            output=tool_output,
            model=resp.model,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
            raw=resp,
        )

"""Markdown 청킹.

전략: 헤딩 구조를 보존한 슬라이딩 윈도우.
  - 단위: 단어/공백 기반 (한글은 글자 기준 가중치) — 정확한 LLM 토큰 카운트는 아니지만 PoC에 충분.
  - 윈도우: ~800 token 분량 = 약 1200 글자, overlap 약 200글자
  - heading path : 직전에 만난 #/##/### 누적을 metadata에 보존

복잡한 ML 토크나이저를 끌어들이지 않기 위해 휴리스틱 라인 단위 청킹을 한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 한 청크의 목표 크기 (글자 수). 800 LLM 토큰 ≈ 한글 1200~1600 글자.
CHUNK_CHARS = 1200
OVERLAP_CHARS = 200
MIN_CHUNK_CHARS = 200

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


@dataclass
class Chunk:
    text: str
    heading_path: list[str] = field(default_factory=list)
    position: int = 0


def _heading_level(line: str) -> tuple[int, str] | None:
    m = _HEADING_RE.match(line)
    if not m:
        return None
    return len(m.group(1)), m.group(2).strip()


def chunk_markdown(content: str) -> list[Chunk]:
    """heading path를 추적하며 라인을 모아 윈도우를 만든다."""
    lines = content.splitlines()
    heading_stack: list[str] = []  # depth-indexed: heading_stack[lvl-1] = title
    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_len = 0
    buf_heading_snapshot: list[str] = []

    def flush() -> None:
        nonlocal buf, buf_len, buf_heading_snapshot
        text = "\n".join(buf).strip()
        if len(text) < MIN_CHUNK_CHARS and not chunks:
            # 너무 짧지만 어쨌든 1개는 만들어줌 (corpus 짧은 경우 대응)
            chunks.append(Chunk(text=text, heading_path=list(buf_heading_snapshot),
                                position=len(chunks)))
        elif len(text) >= MIN_CHUNK_CHARS:
            chunks.append(Chunk(text=text, heading_path=list(buf_heading_snapshot),
                                position=len(chunks)))
        # overlap: 다음 청크 시작에 마지막 부분 일부 carry
        if text and len(text) > OVERLAP_CHARS:
            tail = text[-OVERLAP_CHARS:]
            buf = [tail]
            buf_len = len(tail)
        else:
            buf = []
            buf_len = 0
        buf_heading_snapshot = list(heading_stack)

    for line in lines:
        h = _heading_level(line)
        if h is not None:
            lvl, title = h
            # heading 변경 시 현재 buf flush (논리 단위 분할 + 새 heading_path)
            if buf_len >= MIN_CHUNK_CHARS:
                flush()
            # heading stack 갱신
            del heading_stack[lvl - 1:]
            heading_stack.append(title)
            buf_heading_snapshot = list(heading_stack)
            buf.append(line)
            buf_len += len(line) + 1
            continue
        buf.append(line)
        buf_len += len(line) + 1
        if buf_len >= CHUNK_CHARS:
            flush()

    # 마지막 flush
    if buf:
        flush()

    # 끝 부분 overlap이 남아 빈 청크가 생긴 경우 제거
    return [c for c in chunks if c.text.strip()]

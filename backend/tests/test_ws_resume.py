"""WS resume from last_event_id 단위 테스트 (Phase 7.5).

Redis 없이 in-memory ring buffer 로 broadcast 시 sequence 번호를 부여하고
replay 가 올바른지 검증.
"""
from __future__ import annotations

import asyncio
import base64
import os

import pytest


def _ensure_test_env():
    os.environ.setdefault("VOC_DATA_KEY", base64.b64encode(os.urandom(32)).decode())
    os.environ.setdefault("DB_URL", "sqlite:///:memory:")


_ensure_test_env()


class _FakeWS:
    """WebSocket stub — send_text 호출을 기록."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        self.sent.append(text)


async def _make_manager_without_redis():
    from app.core.ws_manager import ConnectionManager
    # 의도적으로 잘못된 URL 로 redis 연결 실패 → single-process mode
    m = ConnectionManager("redis://nonexistent-host:9999/0")
    await m.start()
    assert m._redis is None, "test setup expects redis to be unavailable"
    return m


async def test_broadcast_assigns_sequence():
    m = await _make_manager_without_redis()
    try:
        assert m.latest_seq == 0
        await m.broadcast({"type": "ticket_created", "id": "a"})
        assert m.latest_seq == 1
        await m.broadcast({"type": "ticket_updated", "id": "b"})
        assert m.latest_seq == 2
    finally:
        await m.stop()


async def test_replay_returns_only_after_last_event_id():
    import json

    m = await _make_manager_without_redis()
    try:
        # 5건 broadcast (수신자 없음 — 단순 버퍼링)
        for i in range(5):
            await m.broadcast({"type": "ticket_updated", "id": f"t{i}"})

        # 새 클라이언트가 last_event_id=2 로 연결 → seq 3, 4, 5 만 replay
        ws = _FakeWS()
        await m.connect(ws, user_id="u1", last_event_id=2)  # type: ignore[arg-type]
        assert ws.accepted is True
        assert len(ws.sent) == 3
        seqs = [json.loads(p)["seq"] for p in ws.sent]
        assert seqs == [3, 4, 5]
    finally:
        await m.stop()


async def test_connect_without_last_event_id_does_not_replay():
    m = await _make_manager_without_redis()
    try:
        await m.broadcast({"type": "ticket_updated", "id": "x"})
        ws = _FakeWS()
        await m.connect(ws, user_id="u2", last_event_id=None)  # type: ignore[arg-type]
        assert ws.sent == []  # replay 없음, 신규 메시지만 받게 됨
    finally:
        await m.stop()


async def test_replay_with_future_last_event_id_returns_nothing():
    """클라이언트가 미래의 seq 를 보내면 (서버보다 앞선 상황 — 비정상) 빈 replay."""
    m = await _make_manager_without_redis()
    try:
        for _ in range(3):
            await m.broadcast({"type": "x"})
        ws = _FakeWS()
        await m.connect(ws, user_id="u3", last_event_id=999)  # type: ignore[arg-type]
        assert ws.sent == []
    finally:
        await m.stop()


async def test_ring_buffer_caps_at_maxlen():
    """LOCAL_BUFFER_SIZE 를 초과하는 broadcast 후 가장 오래된 메시지는 제거됨."""
    import json

    from app.core.ws_manager import LOCAL_BUFFER_SIZE

    m = await _make_manager_without_redis()
    try:
        for i in range(LOCAL_BUFFER_SIZE + 50):
            await m.broadcast({"type": "spam", "i": i})

        # last_event_id=0 으로 전부 replay 요청 → 최대 LOCAL_BUFFER_SIZE 만 받음
        ws = _FakeWS()
        await m.connect(ws, user_id="u4", last_event_id=0)  # type: ignore[arg-type]
        assert len(ws.sent) == LOCAL_BUFFER_SIZE
        # 가장 처음 seq 는 50을 초과해야 함 (앞쪽 50개는 deque maxlen 으로 잘림)
        first_seq = json.loads(ws.sent[0])["seq"]
        assert first_seq > 50
    finally:
        await m.stop()


async def test_broadcast_event_keeps_original_id():
    """sequence(seq) 는 부여되지만 기존 event['id'] 는 보존."""
    import json

    m = await _make_manager_without_redis()
    try:
        await m.broadcast({"type": "ticket_updated", "id": "human-readable-id"})
        ws = _FakeWS()
        await m.connect(ws, user_id="u5", last_event_id=0)  # type: ignore[arg-type]
        msg = json.loads(ws.sent[0])
        assert msg["id"] == "human-readable-id"  # 원본 id 보존
        assert msg["seq"] == 1
    finally:
        await m.stop()

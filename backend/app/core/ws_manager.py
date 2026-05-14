"""WebSocket connection manager with Redis pub/sub fanout.

Phase 1: in-process broadcast works standalone; Redis bridge is wired but only
becomes essential once we run multiple FastAPI instances. If Redis is
unreachable the manager logs a warning and stays in single-process mode so the
demo can run without docker-compose.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict, deque
from typing import Any

import redis.asyncio as aioredis
from fastapi import WebSocket

logger = logging.getLogger(__name__)

CHANNEL = "voc:events"
STREAM = "voc:events:stream"
STREAM_MAXLEN = 500
LOCAL_BUFFER_SIZE = 500   # Phase 7.5: Redis 없을 때 in-memory ring buffer 크기


class ConnectionManager:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None
        self._sockets: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._listener: asyncio.Task[None] | None = None
        # Phase 7.5: 로컬 ring buffer — (seq, payload). Redis fallback 시 client 가
        # last_event_id 를 보내면 그 이후 메시지를 replay.
        self._local_buffer: deque[tuple[int, str]] = deque(maxlen=LOCAL_BUFFER_SIZE)
        self._seq: int = 0

    async def start(self) -> None:
        try:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            self._listener = asyncio.create_task(self._listen(), name="ws-redis-listener")
            logger.info("ws_manager: connected to redis %s", self._redis_url)
        except Exception as exc:
            logger.warning(
                "ws_manager: redis unavailable (%s) — running in single-process mode", exc
            )
            self._redis = None

    async def stop(self) -> None:
        if self._listener:
            self._listener.cancel()
            try:
                await self._listener
            except (asyncio.CancelledError, Exception):
                pass
        if self._redis:
            await self._redis.close()

    async def connect(self, ws: WebSocket, user_id: str = "_anon",
                      last_event_id: int | None = None) -> None:
        await ws.accept()
        async with self._lock:
            self._sockets[user_id].add(ws)
            # Phase 7.5: replay
            replay = self._collect_replay(last_event_id) if last_event_id is not None else []
        logger.info(
            "ws_manager: connect user=%s total=%d replay=%d",
            user_id, self._socket_count(), len(replay),
        )
        for seq, payload in replay:
            try:
                await ws.send_text(payload)
            except Exception:
                logger.debug("ws_manager: replay send failed; client gone")
                return

    def _collect_replay(self, after_seq: int) -> list[tuple[int, str]]:
        """ring buffer 에서 after_seq 보다 큰 seq 만 추출 (시간순)."""
        return [(s, p) for s, p in self._local_buffer if s > after_seq]

    @property
    def latest_seq(self) -> int:
        return self._seq

    async def disconnect(self, ws: WebSocket, user_id: str = "_anon") -> None:
        async with self._lock:
            self._sockets[user_id].discard(ws)
            if not self._sockets[user_id]:
                self._sockets.pop(user_id, None)
        logger.info("ws_manager: disconnect user=%s total=%d", user_id, self._socket_count())

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Publish to all instances. In single-process mode falls back to local fanout.

        Phase 7.5: 모든 모드에서 sequence 번호(_seq)를 부여하고 로컬 ring buffer 에도 저장.
        클라이언트가 재연결 시 last_event_id 로 누락된 메시지를 받을 수 있다.
        """
        self._seq += 1
        event = {**event, "seq": self._seq}
        payload = json.dumps(event, ensure_ascii=False)
        self._local_buffer.append((self._seq, payload))

        if self._redis:
            try:
                await self._redis.publish(CHANNEL, payload)
                await self._redis.xadd(STREAM, {"data": payload}, maxlen=STREAM_MAXLEN, approximate=True)
                return
            except Exception as exc:
                logger.warning("ws_manager: redis publish failed (%s) — local fanout", exc)
        await self._fanout_local(payload)

    async def _listen(self) -> None:
        assert self._redis is not None
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(CHANNEL)
        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                await self._fanout_local(msg["data"])
        except asyncio.CancelledError:
            await pubsub.unsubscribe(CHANNEL)
            raise

    async def _fanout_local(self, payload: str) -> None:
        async with self._lock:
            targets = [ws for sockets in self._sockets.values() for ws in sockets]
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                logger.debug("ws_manager: send failed; client likely disconnected")

    def _socket_count(self) -> int:
        return sum(len(s) for s in self._sockets.values())


_manager: ConnectionManager | None = None


def get_ws_manager() -> ConnectionManager:
    if _manager is None:
        raise RuntimeError("WS manager not initialized — call init_ws_manager() in lifespan")
    return _manager


def init_ws_manager(redis_url: str) -> ConnectionManager:
    global _manager
    _manager = ConnectionManager(redis_url)
    return _manager

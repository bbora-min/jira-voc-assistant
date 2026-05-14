"""KPI 응답 인메모리 TTL 캐시 (Phase 7.7).

원래 Phase 7 plan 의 'kpi_daily 롤업 잡' 은 별도 일별 집계 테이블 + 영구 저장을 의도했으나,
PoC 데이터 규모와 SQLite 환경에서는 인메모리 TTL 캐시(기본 5분)로 동등한 부하 완화 효과를
얻을 수 있다. 대용량 production 단계에서는 이 모듈을 영속 테이블(kpi_daily) 기반으로 swap
하면 된다.

APScheduler 가 5분마다 prewarm 을 실행하여, 사용자가 처음 페이지를 열 때도 cold start 가 없도록 한다.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 300  # 5분


class TTLCache:
    """thread-safe TTL 캐시. key 는 tuple, value 는 임의 dict."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._store: dict[tuple, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: tuple, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, value)

    def get_or_compute(self, key: tuple, compute: Callable[[], Any]) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = compute()
        self.set(key, value)
        return value

    def invalidate(self) -> int:
        with self._lock:
            n = len(self._store)
            self._store.clear()
            return n


# 모듈 싱글톤 — summary / rejection-reasons 응답 캐시
_kpi_cache = TTLCache(ttl_seconds=DEFAULT_TTL_SECONDS)


def get_kpi_cache() -> TTLCache:
    return _kpi_cache


async def prewarm_kpi_cache() -> dict:
    """APScheduler 가 호출. 기본 range(group_by=day) + rejection-reasons 를 미리 계산.

    사용자가 페이지를 열 때 cold start 가 없도록 보장.
    """
    from app.db import get_db
    from app.api.kpi import rejection_reasons, summary

    # FastAPI dependency 우회 — get_db 는 generator yield
    gen = get_db()
    db = next(gen)
    try:
        s = summary(db=db, from_=None, to_=None, group_by="day")
        r = rejection_reasons(db=db, from_=None, to_=None, limit=20)
        logger.info(
            "kpi_cache prewarm: cards.adoption_rate=%.3f, reasons.total=%d",
            s["cards"]["adoption_rate"]["value"], r["total"],
        )
        return {"summary_keys": list(s["counts"].keys()), "reasons_total": r["total"]}
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

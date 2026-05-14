"""KPI TTL 캐시 단위 테스트 (Phase 7.7)."""
from __future__ import annotations

import base64
import os
import time

import pytest


def _ensure_test_env():
    os.environ.setdefault("VOC_DATA_KEY", base64.b64encode(os.urandom(32)).decode())
    os.environ.setdefault("DB_URL", "sqlite:///:memory:")


_ensure_test_env()


def test_cache_get_returns_none_initially():
    from app.services.kpi_cache import TTLCache

    c = TTLCache(ttl_seconds=60)
    assert c.get(("k1",)) is None


def test_cache_set_then_get():
    from app.services.kpi_cache import TTLCache

    c = TTLCache(ttl_seconds=60)
    c.set(("k1",), {"value": 42})
    assert c.get(("k1",)) == {"value": 42}


def test_cache_expires_after_ttl():
    from app.services.kpi_cache import TTLCache

    c = TTLCache(ttl_seconds=0)  # 즉시 만료
    c.set(("k1",), "v1")
    time.sleep(0.01)
    assert c.get(("k1",)) is None


def test_get_or_compute_caches_result():
    from app.services.kpi_cache import TTLCache

    c = TTLCache(ttl_seconds=60)
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"computed": calls["n"]}

    r1 = c.get_or_compute(("k",), compute)
    r2 = c.get_or_compute(("k",), compute)
    assert r1 == r2 == {"computed": 1}
    assert calls["n"] == 1


def test_invalidate_clears_all():
    from app.services.kpi_cache import TTLCache

    c = TTLCache(ttl_seconds=60)
    c.set(("a",), 1)
    c.set(("b",), 2)
    n = c.invalidate()
    assert n == 2
    assert c.get(("a",)) is None
    assert c.get(("b",)) is None


def test_different_keys_are_independent():
    from app.services.kpi_cache import TTLCache

    c = TTLCache(ttl_seconds=60)
    c.set(("summary", "2026-01-01", "2026-01-31", "day"), "A")
    c.set(("summary", "2026-02-01", "2026-02-28", "day"), "B")
    assert c.get(("summary", "2026-01-01", "2026-01-31", "day")) == "A"
    assert c.get(("summary", "2026-02-01", "2026-02-28", "day")) == "B"

"""Wiring tests for two fixed dead registration hooks (2026-09-16).

1. ``app/context.py::set_request_id`` — CorrelationIDMiddleware must set the
   request-id ContextVar per request, so ``get_request_id()`` returns a real
   per-request value during a request instead of the ``"-"`` default.
2. ``app/metrics.py::set_cache_hit_ratio`` — cache adapters must update the
   CACHE_HIT_RATIO gauge on their hit/miss path, so guru_cache_hit_ratio
   moves after a hit/miss window instead of staying at zero forever.
"""

from __future__ import annotations

import asyncio


def _run(coro):
    return asyncio.run(coro)


def test_get_request_id_defaults_to_dash_outside_request():
    from app.context import get_request_id

    assert get_request_id() == "-"


def test_correlation_middleware_sets_request_id_from_header():
    from app.context import get_request_id
    from app.main import CorrelationIDMiddleware

    captured: dict = {}

    async def inner(scope, receive, send):
        captured["request_id_during_request"] = get_request_id()
        await send({"type": "http.response.start", "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request"}

    sent: list = []

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "headers": [(b"x-correlation-id", b"test-cid-123")],
    }
    _run(CorrelationIDMiddleware(inner)(scope, receive, send))

    assert captured["request_id_during_request"] == "test-cid-123"
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert (b"x-correlation-id", b"test-cid-123") in start["headers"]


def test_correlation_middleware_generates_request_id_when_no_header():
    from app.context import get_request_id
    from app.main import CorrelationIDMiddleware

    captured: dict = {}

    async def inner(scope, receive, send):
        captured["request_id_during_request"] = get_request_id()
        await send({"type": "http.response.start", "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        pass

    _run(CorrelationIDMiddleware(inner)({"type": "http", "headers": []}, receive, send))

    assert captured["request_id_during_request"] not in ("-", "")


def test_hot_cache_hit_miss_window_moves_gauge():
    from app.metrics import CACHE_HIT_RATIO
    from services.cache.hot_cache_adapter import HotCache

    cache = HotCache()
    assert cache.get("nope-missing-key") is None  # 0/1 -> ratio 0.0
    assert CACHE_HIT_RATIO.labels(cache_type="hot")._value.get() == 0.0
    cache.put("q-hot", "a-hot", [], intent="QUERY")
    assert cache.get("q-hot") is not None  # 1/2 -> ratio 0.5
    assert CACHE_HIT_RATIO.labels(cache_type="hot")._value.get() == 0.5


def test_exact_cache_hit_miss_window_moves_gauge():
    from app.metrics import CACHE_HIT_RATIO
    from services.cache.memory_adapter import InMemoryCacheAdapter

    cache = InMemoryCacheAdapter()
    assert cache.get("nope-missing-key") is None  # 0/1 -> ratio 0.0
    assert CACHE_HIT_RATIO.labels(cache_type="exact")._value.get() == 0.0
    cache.put("q-exact", "a-exact", "QUERY", [])
    assert cache.get("q-exact") is not None  # 1/2 -> ratio 0.5
    assert CACHE_HIT_RATIO.labels(cache_type="exact")._value.get() == 0.5

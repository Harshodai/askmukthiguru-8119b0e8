"""Regression tests for the global rate limiter's Redis-outage resilience.

Live chaos-testing discovery (2026-09-05): killing Redis crashed EVERY
/api/chat request with an uncaught redis.exceptions.ConnectionError raised
from inside slowapi's rate-limit check, before the route handler ever ran.
Fixed by constructing the Limiter with in_memory_fallback_enabled +
swallow_errors. These tests guard against that configuration silently
regressing (e.g. someone removing the kwargs during a refactor).
"""

from __future__ import annotations

import pytest
from slowapi import Limiter
from starlette.requests import Request


def _key_func(request):
    return "test-client"


def _make_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/chat",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
        "endpoint": None,
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_limiter_survives_unreachable_redis_storage():
    """A Limiter built the same way app/core/limiter.py builds its production
    instances must not raise when its Redis storage is unreachable — it must
    fall back to in-memory limiting instead of crashing the request."""
    limiter = Limiter(
        key_func=_key_func,
        storage_uri="redis://127.0.0.1:1/0",  # deliberately unreachable
        default_limits=["200/minute"],
        in_memory_fallback_enabled=True,
        in_memory_fallback=["200/minute"],
        swallow_errors=True,
    )

    async def _endpoint():
        return "ok"

    # This must not raise — the whole point of the fix.
    limiter._check_request_limit(_make_request(), _endpoint, False)


def test_app_core_limiter_module_has_outage_resilience_kwargs():
    """Guard against the fix regressing silently: the module's actual
    Limiter construction must always carry in_memory_fallback_enabled and
    swallow_errors, whichever storage branch (explicit override, Redis,
    or no-Redis-configured) is taken."""
    import app.core.limiter as limiter_module

    assert limiter_module._REDIS_OUTAGE_KWARGS["in_memory_fallback_enabled"] is True
    assert limiter_module._REDIS_OUTAGE_KWARGS["swallow_errors"] is True
    assert limiter_module.limiter._in_memory_fallback_enabled is True
    assert limiter_module.limiter._swallow_errors is True

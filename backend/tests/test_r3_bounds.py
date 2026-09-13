"""R3 bounds guard: E1 middleware-timeout separation + E2 Redis pool caps.

E1 root cause: the middleware 504 and the pipeline deadline shared one knob
(pipeline_timeout), so the outer 504 could fire before the pipeline's own
graceful fallback. E2 root cause: unbounded Redis client pools in the cache
adapter and job queue; mirror services/cost_tracker.py:73 (max_connections=5).

S1 (2026-09-13) supersedes the bare 5-cap on the two hot-path clients:
20 pilot + headroom → 32. cost_tracker.py stays at 5 (background accounting,
not the request hot path).
"""
import pathlib
import re

import pytest


def test_middleware_timeout_defaults_to_pipeline_plus_15():
    from app.config import Settings

    s = Settings()
    assert s.middleware_timeout == s.pipeline_timeout + 15


def test_middleware_timeout_must_exceed_pipeline_timeout():
    from app.config import Settings

    with pytest.raises(ValueError, match="middleware_timeout"):
        Settings(middleware_timeout=50, pipeline_timeout=105)


def test_middleware_uses_separate_setting():
    src = pathlib.Path("app/main.py").read_text()
    assert 'getattr(settings, "middleware_timeout"' in src


def test_redis_pool_caps_mirror_cost_tracker():
    adapter = pathlib.Path("services/cache/redis_adapter.py").read_text()
    queue = pathlib.Path("app/services/job_queue.py").read_text()
    # S1: hot-path pools sized for 20 pilot + headroom (32), not bare 5.
    assert max(int(m) for m in re.findall(r"max_connections=(\d+)", adapter)) >= 32, (
        "redis_adapter pool undersized for 20 pilot"
    )
    assert max(int(m) for m in re.findall(r"max_connections=(\d+)", queue)) >= 32, (
        "job_queue pool undersized for 20 pilot"
    )

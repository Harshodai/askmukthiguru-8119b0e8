"""Regression tests for CRIT-1: JWT_SECRET must never act as a benchmark backdoor.

The benchmark X-Test-Key header only exempts requests from rate limiting (and
skips server-side history population) when the header value matches
BENCHMARK_SECRET, and only when ENABLE_TEST_AUTH=true and IS_PRODUCTION=false.
A leaked JWT_SECRET must NEVER unlock that bypass.

Covered here:
  - the rate-limit key function (backend/app/core/limiter.py)
  - the shared is_benchmark_request helper (backend/app/security_utils.py)
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.core.limiter import _rate_limit_key_func
from app.security_utils import is_benchmark_request

# These are SYNTHETIC test-fixture values, NOT real credentials.
# They exist to prove that a leaked JWT_SECRET cannot unlock the benchmark
# bypass — only a matching BENCHMARK_SECRET can. The names are intentionally
# fake to make that clear; they have never appeared in any production config.
JWT_SECRET = "leaked-token-signing-secret"  # gitleaks:allow
BENCHMARK_SECRET = "benchmark-secret-for-tests"  # gitleaks:allow


def _make_request(headers: dict | None = None) -> Request:
    headers = headers or {}
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/chat",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": ("1.2.3.4", 1234),
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _pin_settings():
    from app.config import settings

    saved = {
        "benchmark_secret": settings.benchmark_secret,
        "jwt_secret": settings.jwt_secret,
        "enable_test_auth": settings.enable_test_auth,
        "is_production": settings.is_production,
    }
    settings.benchmark_secret = BENCHMARK_SECRET
    settings.jwt_secret = JWT_SECRET
    settings.enable_test_auth = True
    settings.is_production = False
    yield
    settings.benchmark_secret = saved["benchmark_secret"]
    settings.jwt_secret = saved["jwt_secret"]
    settings.enable_test_auth = saved["enable_test_auth"]
    settings.is_production = saved["is_production"]


class TestRateLimitKeyFunc:
    def test_jwt_secret_does_not_bypass_limiter(self):
        req = _make_request({"X-Test-Key": JWT_SECRET})
        assert _rate_limit_key_func(req) == "1.2.3.4"

    def test_benchmark_secret_bypasses_limiter(self):
        req = _make_request({"X-Test-Key": BENCHMARK_SECRET})
        assert _rate_limit_key_func(req).startswith("benchmark_exempt_")

    def test_benchmark_disabled_in_prod(self):
        from app.config import settings

        settings.is_production = True
        req = _make_request({"X-Test-Key": BENCHMARK_SECRET})
        assert _rate_limit_key_func(req) == "1.2.3.4"

    def test_enable_test_auth_false_blocks(self):
        from app.config import settings

        settings.enable_test_auth = False
        req = _make_request({"X-Test-Key": BENCHMARK_SECRET})
        assert _rate_limit_key_func(req) == "1.2.3.4"


class TestIsBenchmarkRequest:
    def test_benchmark_secret_allows(self):
        req = _make_request({"X-Test-Key": BENCHMARK_SECRET})
        assert is_benchmark_request(req) is True

    def test_jwt_secret_rejected(self):
        req = _make_request({"X-Test-Key": JWT_SECRET})
        assert is_benchmark_request(req) is False

    def test_missing_header_rejected(self):
        req = _make_request({})
        assert is_benchmark_request(req) is False

    def test_disabled_in_prod(self):
        from app.config import settings

        settings.is_production = True
        req = _make_request({"X-Test-Key": BENCHMARK_SECRET})
        assert is_benchmark_request(req) is False

    def test_test_auth_disabled_blocks(self):
        from app.config import settings

        settings.enable_test_auth = False
        req = _make_request({"X-Test-Key": BENCHMARK_SECRET})
        assert is_benchmark_request(req) is False


class TestLimiterRateLimitBehavior:
    """End-to-end rate-limit behavior: correct key -> exempt, wrong key -> 429."""

    def _fresh_limiter(self) -> Limiter:
        return Limiter(
            key_func=_rate_limit_key_func,
            default_limits=["1/minute"],
        )

    def test_jwt_secret_does_not_bypass_limiter(self):
        limiter = self._fresh_limiter()
        req = _make_request({"X-Test-Key": JWT_SECRET})
        limiter._check_request_limit(req, None)
        with pytest.raises(RateLimitExceeded):
            limiter._check_request_limit(req, None)

    def test_benchmark_secret_bypasses_limiter(self):
        limiter = self._fresh_limiter()
        req = _make_request({"X-Test-Key": BENCHMARK_SECRET})
        for _ in range(5):
            limiter._check_request_limit(req, None)

    def test_benchmark_disabled_in_prod(self):
        from app.config import settings

        settings.is_production = True
        limiter = self._fresh_limiter()
        req = _make_request({"X-Test-Key": BENCHMARK_SECRET})
        limiter._check_request_limit(req, None)
        with pytest.raises(RateLimitExceeded):
            limiter._check_request_limit(req, None)

    def test_enable_test_auth_false_blocks(self):
        from app.config import settings

        settings.enable_test_auth = False
        limiter = self._fresh_limiter()
        req = _make_request({"X-Test-Key": BENCHMARK_SECRET})
        limiter._check_request_limit(req, None)
        with pytest.raises(RateLimitExceeded):
            limiter._check_request_limit(req, None)


class TestChatV2Endpoint:
    """The /api/chat/v2 handler must route its is_benchmark flag through the
    shared is_benchmark_request guard — never a raw `test_key == jwt_secret`
    comparison. These tests drive the decorated handler (record_token_usage
    wrapper) and stub out ChatEngine via monkeypatch."""

    def _chat_request(self):
        from app.schemas import ChatRequest

        return ChatRequest(
            user_message="Namaste, who are you?",
            messages=[],
            session_id=None,
            meditation_step=0,
            language="en",
        )

    def _call_handler(self, monkeypatch, headers, settings_flags):
        from app.config import settings

        for key, value in settings_flags.items():
            setattr(settings, key, value)

        from app.api import chat as chat_api

        engine_calls = []

        class _FakeEngine:
            def __init__(self, container):
                self.container = container

            async def chat_advanced(self, chat_body, user, is_benchmark):
                engine_calls.append(is_benchmark)
                return self._make_result()

            @staticmethod
            def _make_result():
                from types import SimpleNamespace

                return SimpleNamespace(
                    final_answer="ok",
                    intent="casual",
                    meditation_step=0,
                    citations=[],
                    blocked=False,
                    block_reason=None,
                    trace_id=None,
                    latency_ms=1,
                    model_used=None,
                    model_provider=None,
                    route_decision=None,
                    query_tier=None,
                    cache_hit=False,
                    proactive_serene_mind=None,
                    faithfulness_score=None,
                    hallucination_flag=False,
                    node_timings=None,
                    audio_url=None,
                    kg_concept_nodes=[],
                    daily_practice_card=None,
                    verification=None,
                    answer_evidence=None,
                    guidance_plan=None,
                    grounding_state=None,
                )

        async def _fake_history(chat_body, user, container, is_benchmark):
            return None

        import app.chat_engine as chat_engine_module

        monkeypatch.setattr(chat_engine_module, "ChatEngine", _FakeEngine)

        class _MockAnonQuotaService:
            async def check_and_record(self, user):
                from services.anon_quota_service import QuotaResult

                return QuotaResult(allowed=True, remaining=10, total_limit=10)

        class _MockContainer:
            anon_quota_service = _MockAnonQuotaService()

        body = self._chat_request()
        resp = asyncio.run(
            chat_api.chat_v2_endpoint(
                _make_request(headers),
                body,
                background_tasks=None,
                user={"id": "test-user"},
                container=_MockContainer(),
            )
        )
        assert resp is not None
        return engine_calls

    def test_jwt_secret_not_benchmark(self, monkeypatch):
        engine_calls = self._call_handler(
            monkeypatch,
            {"X-Test-Key": JWT_SECRET},
            {"enable_test_auth": True, "is_production": False},
        )
        assert engine_calls == [False]

    def test_benchmark_secret_plus_gate_is_benchmark(self, monkeypatch):
        engine_calls = self._call_handler(
            monkeypatch,
            {"X-Test-Key": BENCHMARK_SECRET},
            {"enable_test_auth": True, "is_production": False},
        )
        assert engine_calls == [True]

    def test_benchmark_secret_blocked_in_prod(self, monkeypatch):
        engine_calls = self._call_handler(
            monkeypatch,
            {"X-Test-Key": BENCHMARK_SECRET},
            {"enable_test_auth": True, "is_production": True},
        )
        assert engine_calls == [False]

    def test_benchmark_secret_requires_test_auth(self, monkeypatch):
        engine_calls = self._call_handler(
            monkeypatch,
            {"X-Test-Key": BENCHMARK_SECRET},
            {"enable_test_auth": False, "is_production": False},
        )
        assert engine_calls == [False]

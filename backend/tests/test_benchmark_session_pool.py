"""Unit tests for BenchmarkSessionPool (Invariant B1)."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from evaluation.session_pool import BenchmarkSessionPool


@pytest.mark.asyncio
async def test_session_pool_warmup_and_lease():
    # Mock httpx client
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "token": "test_hmac_token_12345",
        "session_id": "test_hmac_token_12345",
    }
    mock_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_resp

    pool = BenchmarkSessionPool(
        endpoint="http://localhost:8000",
        pool_size=2,
        client=mock_client,
        warmup_delay_s=0.01,  # Fast for test
    )

    minted = await pool.warm_up()
    assert minted == 2
    assert pool.is_warmed is True
    assert pool.available_count == 2

    # Lease session 1
    async with pool.acquire_session() as token1:
        assert token1 == "test_hmac_token_12345"
        assert pool.available_count == 1

    # Returned after exit
    assert pool.available_count == 2


@pytest.mark.asyncio
async def test_session_pool_add_token_manually():
    pool = BenchmarkSessionPool(endpoint="http://localhost:8000", pool_size=1)
    pool.add_token("manual_token_abc")
    assert pool.available_count == 1
    assert pool.is_warmed is True

    async with pool.acquire_session() as t:
        assert t == "manual_token_abc"


def _resp(status: int, json_body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_body or {}
    resp.headers = {}
    resp.text = ""
    if status >= 400:
        request = httpx.Request("POST", "http://localhost:8000/api/auth/anon-session")
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "rate limited", request=request, response=httpx.Response(status, request=request)
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_warm_up_429_raises_instead_of_filling_a_short_pool():
    mock_client = AsyncMock()
    mock_client.post.return_value = _resp(429)
    pool = BenchmarkSessionPool(
        "http://localhost:8000", pool_size=2, client=mock_client, warmup_delay_s=0
    )

    with pytest.raises(httpx.HTTPStatusError):
        await pool.warm_up()
    assert pool.available_count == 0
    assert pool.is_warmed is False


@pytest.mark.asyncio
async def test_bench_mints_a_fresh_session_per_question():
    """Reusing a session hits the anonymous chat quota (5 per session per 24 h):
    on 2026-09-26 a pooled token got a 429 with Retry-After ~85,764 s and the
    benchmark slept for a day. The bench mints one session per question."""
    from evaluation.bench import _ask_anonymous

    mock_client = AsyncMock()
    tokens = iter(["t1", "t2", "t3"])

    def post(url, **kwargs):
        if url.endswith("/api/auth/anon-session"):
            return _resp(200, {"token": next(tokens)})
        return _resp(200, {"answer": "ok"})

    mock_client.post.side_effect = post
    for _ in range(3):
        await _ask_anonymous(mock_client, "http://localhost:8000", "q?")

    chat_sessions = [
        c.kwargs["json"]["session_id"]
        for c in mock_client.post.call_args_list
        if c.args[0].endswith("/api/chat")
    ]
    assert chat_sessions == ["t1", "t2", "t3"]


@pytest.mark.asyncio
async def test_bench_never_sleeps_for_a_day_on_a_quota_429(monkeypatch):
    """A quota 429 carries Retry-After ~24 h; the row must fail now, not stall the run."""
    import asyncio as _asyncio

    from evaluation.bench import _ask_anonymous

    slept = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr(_asyncio, "sleep", fake_sleep)
    quota = _resp(429, {"quota_exceeded": True})
    quota.headers = {"retry-after": "85764"}
    mock_client = AsyncMock()
    mock_client.post.side_effect = lambda url, **kw: (
        _resp(200, {"token": "t"}) if url.endswith("/api/auth/anon-session") else quota
    )
    out = await _ask_anonymous(mock_client, "http://localhost:8000", "q?")
    assert out["_http"] == 429
    assert all(s <= 600 for s in slept), slept


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))

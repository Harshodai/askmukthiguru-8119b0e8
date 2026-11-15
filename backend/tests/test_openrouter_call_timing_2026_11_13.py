"""Per-call timing breakdown on OPENROUTER_CALL_TIMING (measurement only, 2026-11-13)."""

import asyncio
import json
import logging
import re
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import settings
from services.openrouter_service import OpenRouterService, _CallTiming

FIELDS = (
    "limiter_wait_ms",
    "pool_wait_ms",
    "connect_ms",
    "ttfb_ms",
    "read_ms",
    "total_ms",
)
SECRET_PROMPT = "PROMPT-SECRET-TEXT"
SECRET_REPLY = "REPLY-SECRET-TEXT"
SECRET_KEY = "sk-or-SECRET-KEY"


@pytest.fixture(autouse=True)
def _allow_haiku(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_extra_allowed_models", "anthropic/claude-haiku-5.5")


def _client():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"content": SECRET_REPLY}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }
    resp.raise_for_status.return_value = None
    client = AsyncMock()
    client.post.return_value = resp
    return client


async def _call(service, caplog, operation="verify"):
    with (
        patch.object(service, "_get_http_client", return_value=_client()),
        caplog.at_level(logging.DEBUG, logger="services.openrouter_service"),
    ):
        return await service._call_api(
            messages=[{"role": "user", "content": SECRET_PROMPT}],
            model="anthropic/claude-haiku-5.5",
            operation=operation,
        )


def _lines(caplog):
    return [r.getMessage() for r in caplog.records if "OPENROUTER_CALL_TIMING" in r.getMessage()]


@pytest.mark.asyncio
async def test_one_line_all_numeric_fields_and_verify_label(caplog):
    await _call(OpenRouterService(), caplog, operation="verify")
    lines = _lines(caplog)
    assert len(lines) == 1
    assert "operation=verify" in lines[0]
    for name in FIELDS:
        assert re.search(rf"\b{name}=-?\d+(\.\d+)?\b", lines[0]), name
    assert re.search(r"conn_reused=(True|False)", lines[0])
    assert "attempt=1" in lines[0] and "status=200" in lines[0]


@pytest.mark.asyncio
async def test_limiter_wait_reflects_injected_delay(caplog):
    service = OpenRouterService()

    async def slow_limiter(**_kw):
        await asyncio.sleep(0.05)

    with patch.object(service, "_enforce_rate_limit", slow_limiter):
        await _call(service, caplog)
    waited = float(re.search(r"limiter_wait_ms=([\d.]+)", _lines(caplog)[0]).group(1))
    assert 40 <= waited < 1000


@pytest.mark.asyncio
async def test_raising_trace_callback_does_not_break_the_call(caplog):
    class Boom(dict):
        def __setitem__(self, k, v):
            raise RuntimeError("tracing bug")

    timing = _CallTiming()
    timing.t = Boom()
    await timing.trace("http11.send_request_headers.started", {})  # must not raise


@pytest.mark.asyncio
async def test_no_prompt_reply_or_key_in_any_log_record(caplog):
    service = OpenRouterService()
    service._api_key = SECRET_KEY
    await _call(service, caplog)
    blob = "\n".join(r.getMessage() for r in caplog.records)
    for secret in (SECRET_PROMPT, SECRET_REPLY, SECRET_KEY, "Authorization", "Bearer"):
        assert secret not in blob


@pytest.mark.asyncio
async def test_cancelled_call_still_emits_a_timing_line(caplog):
    service = OpenRouterService()
    client = AsyncMock()

    async def hang(*_a, **_k):
        await asyncio.sleep(30)

    client.post.side_effect = hang
    with (
        patch.object(service, "_get_http_client", return_value=client),
        caplog.at_level(logging.INFO, logger="services.openrouter_service"),
    ):
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                service._call_api(
                    messages=[{"role": "user", "content": "hi"}],
                    model="anthropic/claude-haiku-5.5",
                    operation="verify",
                ),
                timeout=0.05,
            )
    lines = _lines(caplog)
    assert len(lines) == 1 and "cancelled=True" in lines[0] and "operation=verify" in lines[0]


@pytest.mark.asyncio
async def test_real_httpcore_events_on_loopback_new_then_reused_connection():
    """Local loopback server (no external network): proves the event names are real."""

    async def handle(reader, writer):
        while True:
            head = await reader.readuntil(b"\r\n\r\n")
            n = int(re.search(rb"content-length: (\d+)", head.lower()).group(1))
            await reader.readexactly(n)
            body = json.dumps({"ok": 1}).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
                + body
            )
            await writer.drain()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            first, second = _CallTiming(), _CallTiming()
            await client.post("/x", json={}, extensions={"trace": first.trace})
            await client.post("/x", json={}, extensions={"trace": second.trace})
    finally:
        server.close()
    assert "conn_reused=False" in first.fields(1)
    assert "connection.connect_tcp.complete" in first.t
    assert "conn_reused=True" in second.fields(1)
    assert "http11.receive_response_headers.complete" in second.t
    assert "connect_ms=0.0" in second.fields(1)

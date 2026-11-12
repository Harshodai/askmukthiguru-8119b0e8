"""AuthRateLimitMiddleware is pure ASGI: it must replay the body and record outcomes.

Regression for the 2026-11-12 segfault: the BaseHTTPMiddleware version read the body
with request.json() and crashed the backend under repeated anon-session posts.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

from app import main as app_main


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _receiver(body: bytes):
    messages = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    return receive


def _scope(path: str):
    return {"type": "http", "method": "POST", "path": path, "client": ("10.0.0.9", 1234)}


def test_downstream_handler_receives_the_full_body(monkeypatch):
    monkeypatch.setattr(app_main._AUTH_RATE_LIMITER, "is_allowed_async", AsyncMock(return_value=(True, 0)))
    monkeypatch.setattr(app_main._AUTH_RATE_LIMITER, "record_attempt_async", AsyncMock())
    seen = {}

    async def downstream(scope, receive, send):
        seen["body"] = (await receive())["body"]
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def send(message):
        pass

    payload = json.dumps({"email": "a@example.com"}).encode()
    mw = app_main.AuthRateLimitMiddleware(downstream)
    _run(mw(_scope("/api/auth/jwt/login"), _receiver(payload), send))
    assert seen["body"] == payload


def test_failed_login_is_recorded_as_failure(monkeypatch):
    monkeypatch.setattr(app_main._AUTH_RATE_LIMITER, "is_allowed_async", AsyncMock(return_value=(True, 0)))
    record = AsyncMock()
    monkeypatch.setattr(app_main._AUTH_RATE_LIMITER, "record_attempt_async", record)

    async def downstream(scope, receive, send):
        await send({"type": "http.response.start", "status": 401, "headers": []})

    async def send(message):
        pass

    mw = app_main.AuthRateLimitMiddleware(downstream)
    _run(mw(_scope("/api/auth/jwt/login"), _receiver(b'{"email":"a@example.com"}'), send))
    assert all(call.kwargs.get("success") is False for call in record.await_args_list)
    assert record.await_count == 2


def test_non_auth_path_passes_through_untouched(monkeypatch):
    check = AsyncMock()
    monkeypatch.setattr(app_main._AUTH_RATE_LIMITER, "is_allowed_async", check)
    reached = {}

    async def downstream(scope, receive, send):
        reached["yes"] = True

    async def send(message):
        pass

    mw = app_main.AuthRateLimitMiddleware(downstream)
    scope = {"type": "http", "method": "POST", "path": "/api/chat", "client": ("10.0.0.9", 1)}
    _run(mw(scope, _receiver(b"{}"), send))
    assert reached["yes"] and check.await_count == 0


if __name__ == "__main__":
    test_non_auth_path_passes_through_untouched.__globals__  # self-check placeholder
    print("ok")

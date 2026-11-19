"""A request that arrives before the real app has loaded waits for it instead of getting a CORS-less 503."""

import asyncio
import time

import start_railway


def _call() -> list[dict]:
    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request"}

    scope = {"type": "http", "path": "/api/chat", "method": "GET", "headers": []}
    asyncio.run(start_railway.app(scope, receive, send))
    return sent


async def _real_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def test_request_waits_for_the_real_app(monkeypatch):
    monkeypatch.setattr(start_railway, "_real_app", None)
    monkeypatch.setattr(start_railway, "_lifespan_failed", False)
    monkeypatch.setattr(start_railway, "_COLD_START_WAIT_S", 5.0)

    async def run():
        asyncio.get_running_loop().call_later(
            0.4, lambda: setattr(start_railway, "_real_app", _real_app)
        )
        sent: list[dict] = []

        async def send(message):
            sent.append(message)

        async def receive():
            return {"type": "http.request"}

        scope = {"type": "http", "path": "/api/chat", "method": "GET", "headers": []}
        await start_railway.app(scope, receive, send)
        return sent

    sent = asyncio.run(run())
    assert sent[0]["status"] == 200


def test_503_after_the_wait_when_the_app_never_loads(monkeypatch):
    monkeypatch.setattr(start_railway, "_real_app", None)
    monkeypatch.setattr(start_railway, "_lifespan_failed", False)
    monkeypatch.setattr(start_railway, "_COLD_START_WAIT_S", 0.3)

    started = time.monotonic()
    sent = _call()

    assert sent[0]["status"] == 503
    assert time.monotonic() - started >= 0.3


def test_failed_startup_answers_503_immediately(monkeypatch):
    monkeypatch.setattr(start_railway, "_real_app", None)
    monkeypatch.setattr(start_railway, "_lifespan_failed", True)
    monkeypatch.setattr(start_railway, "_COLD_START_WAIT_S", 30.0)

    started = time.monotonic()
    sent = _call()

    assert sent[0]["status"] == 503
    assert time.monotonic() - started < 2.0

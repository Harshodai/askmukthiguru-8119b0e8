"""P1-OPS-8: backpressure semaphore on /api/chat.

The chat handlers require live infra (Qdrant handshake during app lifespan),
so these tests exercise the admission-control wrapper directly — the same
code path the route decorators use — through a stub semaphore that models
the `asyncio.Semaphore` contract the wrapper relies on (acquire waits,
release restores, `_value`/`locked()` observability). Plus the /api/health
visibility hook via the module-level state.
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import app.api.chat as chat_module
from app.config import settings


class _StubSemaphore:
    """Minimal stand-in for asyncio.Semaphore with the surface the wrapper uses."""

    def __init__(self, capacity: int, held: int = 0) -> None:
        self._value = capacity - held

    async def acquire(self) -> bool:
        if self._value <= 0:
            raise TimeoutError
        self._value -= 1
        return True

    def release(self) -> None:
        self._value += 1

    def locked(self) -> bool:
        return self._value <= 0


def _build_router():
    """FastAPI app with the real decorator applied to a stub handler."""
    app = FastAPI()

    @app.post("/api/chat")
    @chat_module.backpressure_semaphore
    async def _chat_stub(request: Request):
        return JSONResponse({"response": "ok"})

    return app


@pytest.fixture(autouse=True)
def _stub_semaphore(monkeypatch):
    monkeypatch.setattr(chat_module, "_get_chat_semaphore", lambda: chat_module._chat_semaphore)
    monkeypatch.setattr(chat_module.settings, "max_concurrent_chat", 20)
    yield
    monkeypatch.undo()


def test_overload_returns_503():
    """Exhausted semaphore → immediate 503 + Retry-After, no queueing."""
    chat_module._chat_semaphore = _StubSemaphore(capacity=1, held=1)
    client = TestClient(_build_router())
    response = client.post("/api/chat", json={})
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "5"
    assert response.json() == {"detail": "Server busy, try again shortly"}


def test_normal_request_not_blocked():
    """Free semaphore → handler runs and the slot is returned."""
    chat_module._chat_semaphore = _StubSemaphore(capacity=1)
    client = TestClient(_build_router())
    response = client.post("/api/chat", json={})
    assert response.status_code == 200
    assert response.json() == {"response": "ok"}
    assert chat_module._chat_semaphore._value == 1


def test_rejection_does_not_consume_slots():
    """Rejected requests leave the remaining capacity untouched."""
    chat_module._chat_semaphore = _StubSemaphore(capacity=1, held=1)
    client = TestClient(_build_router())
    assert client.post("/api/chat", json={}).status_code == 503
    assert chat_module._chat_semaphore._value == 0
    chat_module._chat_semaphore.release()
    assert client.post("/api/chat", json={}).status_code == 200
    assert chat_module._chat_semaphore._value == 1


def test_health_exposes_admission_contention():
    """Held slots surface as in_flight / admission_limited."""
    chat_module._chat_semaphore = _StubSemaphore(capacity=20, held=1)
    bp = chat_module.get_chat_backpressure()
    assert bp["max_concurrent"] == settings.max_concurrent_chat
    assert bp["in_flight"] == 1
    assert bp["admission_limited"] is False

    chat_module._chat_semaphore = _StubSemaphore(capacity=20, held=20)
    bp = chat_module.get_chat_backpressure()
    assert bp["in_flight"] == 20
    assert bp["admission_limited"] is True


def test_health_defaults_when_semaphore_uninitialized():
    """Before any chat request, health reports zero contention."""
    chat_module._chat_semaphore = None
    bp = chat_module.get_chat_backpressure()
    assert bp["in_flight"] == 0
    assert bp["admission_limited"] is False
    assert bp["max_concurrent"] == settings.max_concurrent_chat

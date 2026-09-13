"""Chat must refuse traffic when no job worker is attached.

`/api/chat` enqueues and returns 202. `job_queue.start()` runs inside lifespan's
background init block — so when anything earlier in that block raises (a failed
Neo4j constraint assert, say), the worker never starts and the queue has no
consumer. The request is accepted, queued, and never answered.

Observed live 2026-09-13: a job sat `queued` for 400s+ while /api/health
correctly reported `ready: false` and /api/chat kept returning 202.
"""

import inspect

from app.api import chat as chat_api


def test_guard_exists_and_fails_closed():
    src = inspect.getsource(chat_api._reject_if_queue_unattended)
    assert "startup_complete" in src
    assert "503" in src
    # Fail CLOSED: the default when the flag is missing must be "not ready".
    assert 'getattr(_app_deps, "startup_complete", False)' in src


def test_guard_runs_before_every_enqueue():
    src = inspect.getsource(chat_api)
    guard_calls = src.count("_reject_if_queue_unattended()")
    # One definition-site call inside the helper's own name plus the call sites.
    assert guard_calls >= 3, f"expected the guard at each enqueue path, found {guard_calls}"


def test_guard_surfaces_the_startup_error():
    """An operator must learn WHY, not just that it is unavailable."""
    src = inspect.getsource(chat_api._reject_if_queue_unattended)
    assert "startup_error" in src
    assert "Retry-After" in src


def test_guard_rejects_when_not_ready(monkeypatch):
    from fastapi import HTTPException

    from app import dependencies as app_deps

    monkeypatch.setattr(app_deps, "startup_complete", False, raising=False)
    monkeypatch.setattr(app_deps, "startup_error", "Neo4j constraints missing", raising=False)
    try:
        chat_api._reject_if_queue_unattended()
    except HTTPException as exc:
        assert exc.status_code == 503
        assert "Neo4j constraints missing" in str(exc.detail)
    else:
        raise AssertionError("guard must raise while startup is incomplete")


def test_guard_allows_when_ready(monkeypatch):
    from app import dependencies as app_deps

    monkeypatch.setattr(app_deps, "startup_complete", True, raising=False)
    chat_api._reject_if_queue_unattended()  # must not raise

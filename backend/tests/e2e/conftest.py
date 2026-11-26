"""Shared fixtures for first-person E2E smoke tests.

Requires a live backend.  Auto-skips when BACKEND_URL is not set.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

BACKEND_URL = os.environ.get("BACKEND_URL", "")


class LiveStackError(RuntimeError):
    """A transport, HTTP, or job failure — never a chat answer.

    Returning an error body as if it were a chat response let a failed
    request pass a "not abstained" assertion (the body has no route at all),
    so callers must raise instead of degrading.
    """


def _get_live_benchmark_secret() -> str:
    if os.environ.get("LIVE_BENCHMARK_SECRET"):
        return os.environ["LIVE_BENCHMARK_SECRET"]
    # Read directly from backend/.env because backend/tests/conftest.py
    # sets os.environ["BENCHMARK_SECRET"] to a dummy in-memory unit-test value.
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("BENCHMARK_SECRET=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    return "super-secret-jwt-token-with-at-least-32-characters-long"


BENCHMARK_SECRET = _get_live_benchmark_secret()
_SKIP = pytest.mark.skipif(
    not BACKEND_URL,
    reason="BACKEND_URL not set — live-stack smoke tests require a running backend",
)

POLL_DEADLINE_S = 90
_POLL_INTERVAL_S = 1.5
_JOB_PENDING = {"queued", "pending", "processing", "running", "started", "in_progress", "accepted"}
_JOB_TERMINAL = {"completed", "failed", "error", "cancelled", "canceled"}


import urllib.parse


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LiveStackError(f"HTTP {code} redirect to {newurl} refused (credential protection)")


def _validate_backend_url(url: str) -> None:
    if not url:
        return
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise LiveStackError(f"BACKEND_URL must use http or https; got {url!r}")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "testserver"):
        raise LiveStackError(f"BACKEND_URL non-loopback endpoints must use https; got {url!r}")


def _call(method: str, path: str, body: dict | None) -> tuple[int, dict]:
    _validate_backend_url(BACKEND_URL)
    headers = {
        "Content-Type": "application/json",
        "X-Test-Key": BENCHMARK_SECRET,
        "X-User-Id": "benchmark-admin-user",
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(BACKEND_URL + path, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        with opener.open(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")
    except (urllib.error.URLError, OSError) as exc:
        raise LiveStackError(f"{method} {path} transport failure: {exc}") from exc


def _job_status(body: dict) -> str:
    """Return the job state for a job envelope, or '' for a chat answer.

    ``GET /api/jobs/{id}`` returns HTTP 200 for a job that is still running,
    so the response status alone cannot distinguish "answer" from "pending".
    """
    if isinstance(body, dict) and body.get("job_id") and body.get("status"):
        return str(body["status"]).lower()
    return ""


def _poll(job_id: str, started: float) -> dict:
    while time.time() < started + POLL_DEADLINE_S:
        time.sleep(_POLL_INTERVAL_S)
        status, polled = _call("GET", f"/api/jobs/{job_id}", None)
        if status in (401, 403):
            raise LiveStackError(f"GET /api/jobs/{job_id} auth failure: {status} {polled}")
        if status == 404:
            raise LiveStackError(f"GET /api/jobs/{job_id} not found: {polled}")
        if status < 200 or status >= 300:
            raise LiveStackError(f"GET /api/jobs/{job_id} HTTP {status}: {polled}")
        state = _job_status(polled) or ("completed" if status == 200 and not polled.get("status") else "")
        if state in {"failed", "error", "cancelled", "canceled"}:
            raise LiveStackError(f"job {job_id} ended {state}: {polled}")
        if state in _JOB_TERMINAL:
            return polled.get("result") or polled
    raise LiveStackError(f"job {job_id} did not finish within {POLL_DEADLINE_S}s")


def _ask(question: str) -> dict:
    """POST to /api/chat and poll /api/jobs/{job_id} until a terminal state."""
    started = time.time()
    payload = {
        "messages": [],
        "user_message": question,
    }
    status, body = _call("POST", "/api/chat", payload)
    if status in (401, 403):
        raise LiveStackError(f"POST /api/chat auth failure: {status} {body}")
    if status not in (200, 202):
        raise LiveStackError(f"POST /api/chat -> {status}: {body}")

    job = body.get("job_id")
    state = _job_status(body)
    if job and (status == 202 or state in _JOB_PENDING):
        return _poll(str(job), started)
    if state in _JOB_TERMINAL and state != "completed":
        raise LiveStackError(f"POST /api/chat returned {state}: {body}")
    if state == "completed":
        return body.get("result") or body
    return body


@pytest.fixture(scope="session")
def ask():
    if not BACKEND_URL:
        pytest.skip("BACKEND_URL not set — live-stack smoke tests require a running backend")

    def _do(question: str) -> dict:
        return _ask(question)

    return _do

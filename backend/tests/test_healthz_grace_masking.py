"""F-PROD-1: /api/healthz's grace window must not mask a failed boot.

start_railway.py returns 200 unconditionally for _GRACE_SECONDS so Railway
cannot kill a replica that is still initializing. That same window also made a
replica whose lifespan RAISED look perfectly healthy -- Railway saw 200s,
marked the deploy healthy, and routed traffic to a dead app. Same defect class
as the executor-starvation gap: a liveness signal that structurally cannot see
the failure it is supposed to report.

These drive the real ASGI `app` callable from start_railway.py rather than
re-implementing its branch logic, so they fail if the production gate moves,
is reordered behind the grace short-circuit, or is deleted.
"""

from __future__ import annotations

import importlib

import pytest


def _load():
    try:
        return importlib.import_module("start_railway")
    except ImportError:
        return importlib.import_module("backend.start_railway")


async def _healthz_status(mod) -> int:
    """Drive the real ASGI app for GET /api/healthz and return the status."""
    sent: list[dict] = []

    async def receive():  # pragma: no cover - never called for this path
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message)

    await mod.app({"type": "http", "path": "/api/healthz"}, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    return start["status"]


@pytest.mark.asyncio
async def test_healthz_reports_503_when_boot_failed_even_inside_grace(monkeypatch):
    """The whole point: inside grace, a crashed lifespan must still be 503."""
    mod = _load()

    # Fresh process: firmly inside the grace window.
    monkeypatch.setattr(mod, "_process_start", mod.time.monotonic(), raising=False)
    monkeypatch.setattr(mod, "_lifespan_startup_done", False, raising=False)

    # Sanity: without the failure flag, grace returns 200. If this assert fails
    # the test is no longer proving anything about the flag.
    monkeypatch.setattr(mod, "_lifespan_failed", False, raising=False)
    assert await _healthz_status(mod) == 200, "grace window should serve 200 while booting"

    monkeypatch.setattr(mod, "_lifespan_failed", True, raising=False)
    assert await _healthz_status(mod) == 503, (
        "a lifespan that raised must surface 503 immediately -- the grace "
        "window must not mask a boot failure"
    )


@pytest.mark.asyncio
async def test_grace_never_covers_the_whole_healthcheck_budget():
    """_GRACE_SECONDS must stay under .railway/railway.ts's healthcheckTimeout.

    If grace >= the healthcheck budget, every probe Railway makes lands in the
    unconditional-200 window and no boot failure can ever fail a deploy.

    Reads .railway/railway.ts (the repo's IaC declaration), not railway.json --
    that file was removed 2026-09-19 (".railway/railway.ts is now the IaC
    source"). This only proves the invariant against what the REPO declares;
    it cannot detect drift between this file and whatever value is actually
    applied on the live Railway service (Railway IaC only takes effect once
    pushed/applied there). Re-verify the live value separately after any
    Railway settings change.
    """
    import re
    from pathlib import Path

    mod = _load()
    repo_root = Path(mod.__file__).resolve().parents[1]
    railway_ts = (repo_root / ".railway" / "railway.ts").read_text()
    match = re.search(r"healthcheckTimeout:\s*(\d+)", railway_ts)
    assert match, "could not find healthcheckTimeout in .railway/railway.ts"
    timeout = int(match.group(1))

    assert mod._GRACE_SECONDS < timeout, (
        f"_GRACE_SECONDS={mod._GRACE_SECONDS} must be < healthcheckTimeout={timeout}, "
        "or the grace window blankets the entire healthcheck budget in 200s"
    )


def test_lifespan_failure_sets_the_flag():
    """The flag must actually be set on the lifespan's fatal-error path."""
    mod = _load()
    src = open(mod.__file__).read()
    assert "_lifespan_failed = True" in src, (
        "the fatal-error branch of _run_real_lifespan must set _lifespan_failed"
    )


if __name__ == "__main__":
    import asyncio

    m = _load()
    m._lifespan_failed = True
    assert asyncio.run(_healthz_status(m)) == 503
    print("ok")


# --- HEALTHZ_REQUIRE_READY (2026-11-27 scaling audit) -------------------------------------
# Gate on: healthz must not report 200 until the real app finished startup, in the grace
# window and after it, so a rolling deploy never promotes a container that answers /api/chat 503.

import sys  # noqa: E402
from types import SimpleNamespace  # noqa: E402


def _arm(monkeypatch, mod, *, gate, grace, loaded, startup_complete, lifespan_done=True):
    now = mod.time.monotonic()
    monkeypatch.setattr(mod, "_READY_GATE", gate, raising=False)
    monkeypatch.setattr(mod, "_lifespan_failed", False, raising=False)
    monkeypatch.setattr(mod, "_lifespan_startup_done", lifespan_done, raising=False)
    monkeypatch.setattr(mod, "_real_app", object() if loaded else None, raising=False)
    # inside grace = just started; after grace = started well before the window
    monkeypatch.setattr(
        mod, "_process_start", now if grace else now - mod._GRACE_SECONDS - 5, raising=False
    )
    monkeypatch.setattr(mod, "_last_heartbeat", now, raising=False)
    monkeypatch.setattr(mod, "_last_executor_canary", now, raising=False)
    monkeypatch.setitem(
        sys.modules, "app.dependencies", SimpleNamespace(startup_complete=startup_complete)
    )


@pytest.mark.asyncio
async def test_gate_off_keeps_grace_200_even_when_not_ready(monkeypatch):
    mod = _load()
    _arm(monkeypatch, mod, gate=False, grace=True, loaded=True, startup_complete=False)
    assert await _healthz_status(mod) == 200


@pytest.mark.asyncio
async def test_gate_on_inside_grace_is_503_until_startup_complete(monkeypatch):
    mod = _load()
    _arm(monkeypatch, mod, gate=True, grace=True, loaded=True, startup_complete=False)
    assert await _healthz_status(mod) == 503
    _arm(monkeypatch, mod, gate=True, grace=True, loaded=True, startup_complete=True)
    assert await _healthz_status(mod) == 200


@pytest.mark.asyncio
async def test_gate_on_after_grace_blocks_init_that_never_completed(monkeypatch):
    """Lifespan yielded and heartbeats are fresh, but background init timed out: the
    post-grace branch used to report 200 here (the finding the audit review caught)."""
    mod = _load()
    _arm(monkeypatch, mod, gate=True, grace=False, loaded=True, startup_complete=False)
    assert await _healthz_status(mod) == 503
    _arm(monkeypatch, mod, gate=False, grace=False, loaded=True, startup_complete=False)
    assert await _healthz_status(mod) == 200, "gate off must keep the old post-grace behaviour"
    _arm(monkeypatch, mod, gate=True, grace=False, loaded=True, startup_complete=True)
    assert await _healthz_status(mod) == 200


@pytest.mark.asyncio
async def test_gate_on_is_503_while_real_app_is_still_importing(monkeypatch):
    """_real_app is None: the readiness check must not import app.dependencies from the loop."""
    mod = _load()
    _arm(monkeypatch, mod, gate=True, grace=True, loaded=False, startup_complete=True)
    assert await _healthz_status(mod) == 503


@pytest.mark.asyncio
async def test_gate_on_still_503_when_boot_failed(monkeypatch):
    mod = _load()
    _arm(monkeypatch, mod, gate=True, grace=True, loaded=True, startup_complete=True)
    monkeypatch.setattr(mod, "_lifespan_failed", True, raising=False)
    assert await _healthz_status(mod) == 503

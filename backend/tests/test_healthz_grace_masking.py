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

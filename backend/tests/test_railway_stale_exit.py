"""RP-A3 / RP-A10 / RP-B1: Railway entrypoint.

- RP-A3: uvicorn worker count comes from WEB_CONCURRENCY (default 1), and the
  parse is unit-tested (fail-closed on garbage, never a silent default).
- RP-A10/RP-B1: the wrapper's stale-heartbeat/executor-canary path must
  os._exit(1) so the platform restart policy fires — a 503 alone never
  restarts anything (Railway healthchecks run at deploy start only, declared
  in .railway/railway.ts as /api/healthz, NOT /api/health).
"""

from __future__ import annotations

import importlib

import pytest


def _load():
    try:
        return importlib.import_module("start_railway")
    except ImportError:
        return importlib.import_module("backend.start_railway")


# ---------------------------------------------------------------------------
# RP-A3: WEB_CONCURRENCY parsing
# ---------------------------------------------------------------------------


def test_web_concurrency_defaults_to_1(monkeypatch):
    mod = _load()
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    assert mod.get_web_concurrency() == 1


def test_web_concurrency_explicit(monkeypatch):
    mod = _load()
    monkeypatch.setenv("WEB_CONCURRENCY", "3")
    assert mod.get_web_concurrency() == 3


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "2.5"])
def test_web_concurrency_rejects_garbage(monkeypatch, bad):
    """Invalid values fail closed (SystemExit) — never a silent default."""
    mod = _load()
    monkeypatch.setenv("WEB_CONCURRENCY", bad)
    with pytest.raises(SystemExit):
        mod.get_web_concurrency()


@pytest.mark.parametrize("blank", ["", "  "])
def test_web_concurrency_blank_means_default(monkeypatch, blank):
    """Deliberate ruling: blank is treated as unset → 1 (documented in the
    function docstring). Empty env values are how compose/Railway surfaces
    'not configured'; crash-looping on them would be a false alarm, while
    non-empty garbage still fails closed above."""
    mod = _load()
    monkeypatch.setenv("WEB_CONCURRENCY", blank)
    assert mod.get_web_concurrency() == 1


@pytest.mark.parametrize("env_val,expected", [("3", 3), (None, 1)])
def test_uvicorn_wired_to_env_workers(monkeypatch, env_val, expected):
    """Behavioral test: start_railway.main() passes get_web_concurrency() to uvicorn.run."""
    from unittest.mock import MagicMock

    from app.config import settings

    mod = _load()
    mock_run = MagicMock()
    monkeypatch.setattr("uvicorn.run", mock_run)
    monkeypatch.setattr(settings, "forwarded_allow_ips", "10.0.0.0/8")
    # main() runs run_preflight_startup_hygiene() before uvicorn.run: on a host
    # that is real file cleanup and possibly a Redis lock clear. Stub it so the
    # test cannot touch host state; only worker wiring is under test here.
    monkeypatch.setattr(mod, "run_preflight_startup_hygiene", MagicMock())
    monkeypatch.delenv("SERVICE_TYPE", raising=False)
    if env_val is None:
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    else:
        monkeypatch.setenv("WEB_CONCURRENCY", env_val)

    mod.main()
    assert mock_run.called
    assert mock_run.call_args.kwargs.get("workers") == expected


def test_railway_comment_no_longer_claims_restart_on_503():
    mod = _load()
    src = open(mod.__file__).read()
    assert "stale >30s or the lifespan never completed — Railway restarts on 503" not in src, (
        "false comment: Railway healthchecks run at deploy start only; "
        "a 503 never triggers a restart"
    )
    assert "CORRECTION (RP-A10/RP-B1" in src


# ---------------------------------------------------------------------------
# RP-A10/RP-B1: stale-canary self-exit
# ---------------------------------------------------------------------------


def test_stale_exit_arms_then_fires():
    mod = _load()
    now = 1_000.0
    should_exit, first = mod._stale_exit_due(now, None)
    assert should_exit is False
    assert first == now
    should_exit, _ = mod._stale_exit_due(now + mod._STALE_EXIT_AFTER_S - 1, first)
    assert should_exit is False, "must tolerate a briefly stale canary"
    should_exit, _ = mod._stale_exit_due(now + mod._STALE_EXIT_AFTER_S, first)
    assert should_exit is True, "a canary stale past the threshold must exit"


async def _healthz_status(mod) -> int:
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message)

    await mod.app({"type": "http", "path": "/api/healthz"}, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    return start["status"]


@pytest.mark.asyncio
async def test_healthz_reports_but_never_exits_when_canary_stays_stale(monkeypatch):
    """Post-grace, startup done, both canaries long stale → 503 and NO exit.

    Exiting is the watchdog thread's job alone (single writer of
    _first_unhealthy_at); the handler only reports. See
    test_watchdog_tick_exits_without_any_health_probe for the exit path.
    """
    mod = _load()
    monkeypatch.setattr(mod, "_process_start", mod.time.monotonic() - 10_000, raising=False)
    monkeypatch.setattr(mod, "_lifespan_startup_done", True, raising=False)
    monkeypatch.setattr(mod, "_lifespan_failed", False, raising=False)
    monkeypatch.setattr(mod, "_last_heartbeat", 0.0, raising=False)
    monkeypatch.setattr(mod, "_last_executor_canary", 0.0, raising=False)
    monkeypatch.setattr(mod, "_first_unhealthy_at", mod.time.monotonic() - 10_000, raising=False)
    exits: list[int] = []
    monkeypatch.setattr(mod.os, "_exit", lambda code: exits.append(code))
    assert await _healthz_status(mod) == 503
    assert exits == [], "healthz reports; only the watchdog thread exits"


@pytest.mark.asyncio
async def test_healthz_does_not_exit_when_canaries_fresh(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "_process_start", mod.time.monotonic() - 10_000, raising=False)
    monkeypatch.setattr(mod, "_lifespan_startup_done", True, raising=False)
    monkeypatch.setattr(mod, "_lifespan_failed", False, raising=False)
    now = mod.time.monotonic()
    monkeypatch.setattr(mod, "_last_heartbeat", now, raising=False)
    monkeypatch.setattr(mod, "_last_executor_canary", now, raising=False)
    monkeypatch.setattr(mod, "_first_unhealthy_at", None, raising=False)
    exits: list[int] = []
    monkeypatch.setattr(mod.os, "_exit", lambda code: exits.append(code))
    assert await _healthz_status(mod) == 200
    assert exits == []


@pytest.mark.asyncio
async def test_healthz_does_not_exit_on_boot_failure(monkeypatch):
    """Boot failure stays a plain 503 (existing F-PROD-1 behavior, out of scope)."""
    mod = _load()
    monkeypatch.setattr(mod, "_process_start", mod.time.monotonic() - 10_000, raising=False)
    monkeypatch.setattr(mod, "_lifespan_startup_done", False, raising=False)
    monkeypatch.setattr(mod, "_lifespan_failed", True, raising=False)
    monkeypatch.setattr(mod, "_first_unhealthy_at", None, raising=False)
    exits: list[int] = []
    monkeypatch.setattr(mod.os, "_exit", lambda code: exits.append(code))
    assert await _healthz_status(mod) == 503
    assert exits == []


def _stale_state(monkeypatch, mod):
    monkeypatch.setattr(mod, "_process_start", mod.time.monotonic() - 10_000, raising=False)
    monkeypatch.setattr(mod, "_lifespan_startup_done", True, raising=False)
    monkeypatch.setattr(mod, "_last_heartbeat", 0.0, raising=False)
    monkeypatch.setattr(mod, "_last_executor_canary", 0.0, raising=False)
    exits: list[int] = []
    monkeypatch.setattr(mod.os, "_exit", lambda code: exits.append(code))
    return exits


def test_watchdog_tick_exits_without_any_health_probe(monkeypatch):
    """Railway never probes after deploy: the tick alone must arm then exit."""
    mod = _load()
    exits = _stale_state(monkeypatch, mod)
    monkeypatch.setattr(mod, "_first_unhealthy_at", None, raising=False)
    mod._exit_if_canary_stays_stale()
    assert exits == [], "first stale tick only arms the timer"
    monkeypatch.setattr(
        mod, "_first_unhealthy_at", mod.time.monotonic() - mod._STALE_EXIT_AFTER_S - 1
    )
    mod._exit_if_canary_stays_stale()
    assert exits == [1]


def test_watchdog_tick_healthy_clears_the_timer(monkeypatch):
    mod = _load()
    exits = _stale_state(monkeypatch, mod)
    now = mod.time.monotonic()
    monkeypatch.setattr(mod, "_last_heartbeat", now, raising=False)
    monkeypatch.setattr(mod, "_last_executor_canary", now, raising=False)
    monkeypatch.setattr(mod, "_first_unhealthy_at", now - 10_000, raising=False)
    mod._exit_if_canary_stays_stale()
    assert exits == []
    assert mod._first_unhealthy_at is None


def test_watchdog_tick_never_exits_during_graceful_shutdown(monkeypatch):
    """Shutdown zeroes both canaries; that must not look like a wedge."""
    mod = _load()
    exits = _stale_state(monkeypatch, mod)
    monkeypatch.setattr(mod, "_first_unhealthy_at", mod.time.monotonic() - 10_000, raising=False)
    mod._shutdown_event.set()
    try:
        mod._exit_if_canary_stays_stale()
    finally:
        mod._shutdown_event.clear()
    assert exits == []


def test_watchdog_thread_started_by_lifespan():
    mod = _load()
    src = open(mod.__file__).read()
    assert "target=_stale_exit_watchdog" in src, "watchdog thread must be started"


if __name__ == "__main__":
    import os

    # Self-check must not depend on the caller's environment: verify the
    # default (unset AND blank) regardless of ambient WEB_CONCURRENCY.
    os.environ.pop("WEB_CONCURRENCY", None)
    m = _load()
    assert m.get_web_concurrency() == 1
    os.environ["WEB_CONCURRENCY"] = ""
    m = _load()
    assert m.get_web_concurrency() == 1
    print("ok")

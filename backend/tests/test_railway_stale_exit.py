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


def test_uvicorn_wired_to_env_workers():
    """start_railway must not hard-code workers=2 anymore."""
    mod = _load()
    src = open(mod.__file__).read()
    assert "workers=_get_web_concurrency()" in src.replace(" ", "") or (
        "workers=get_web_concurrency()" in src.replace(" ", "")
    ), "uvicorn.run must take its worker count from WEB_CONCURRENCY"
    assert "workers=2" not in src, "hard-coded workers=2 must be gone"


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
async def test_healthz_exits_when_canary_stays_stale(monkeypatch):
    """Post-grace, startup done, both canaries long stale → 503 + os._exit(1)."""
    mod = _load()
    monkeypatch.setattr(mod, "_process_start", mod.time.monotonic() - 10_000, raising=False)
    monkeypatch.setattr(mod, "_lifespan_startup_done", True, raising=False)
    monkeypatch.setattr(mod, "_lifespan_failed", False, raising=False)
    monkeypatch.setattr(mod, "_last_heartbeat", 0.0, raising=False)
    monkeypatch.setattr(mod, "_last_executor_canary", 0.0, raising=False)
    monkeypatch.setattr(
        mod, "_first_unhealthy_at", mod.time.monotonic() - 10_000, raising=False
    )
    exits: list[int] = []
    monkeypatch.setattr(mod.os, "_exit", lambda code: exits.append(code))
    assert await _healthz_status(mod) == 503
    assert exits == [1], "stale canary must exit non-zero so the restart policy fires"


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


if __name__ == "__main__":
    m = _load()
    assert m.get_web_concurrency() == 1
    print("ok")

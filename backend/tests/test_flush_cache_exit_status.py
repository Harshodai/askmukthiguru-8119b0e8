"""`make flush-cache` is only as trustworthy as this script's exit status.

It returned 0 unconditionally, and the Makefile's only working path (the
host fallback) cannot resolve the compose hostnames, so a flush that reached
neither Redis nor Qdrant still printed "Cache flush complete" (faculty
readiness review 2026-10-05). Live runs that assume flushed caches were then
measuring cached answers.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "ops" / "flush_cache.py"


def _load():
    spec = importlib.util.spec_from_file_location("flush_cache_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod(monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "_load_settings", lambda: None)
    return m


def test_success_exits_zero(mod, monkeypatch):
    monkeypatch.setattr(mod, "_flush_qdrant", lambda url, names: {n: "recreated" for n in names})
    monkeypatch.setattr(mod, "_flush_redis", lambda url, pw=None: {"mukthiguru:cache:*": 3})
    assert mod.main() == 0


@pytest.mark.parametrize(
    "qdrant, redis",
    [
        ({"c": "recreated"}, {"mukthiguru:cache:*": "error: connection refused"}),
        ({"c": "error: connection refused"}, {"mukthiguru:cache:*": 0}),
        ({"c": "qdrant_client_unavailable"}, {"mukthiguru:cache:*": 0}),
        ({"c": "recreated"}, {"mukthiguru:cache:*": "redis_package_unavailable"}),
    ],
)
def test_any_unflushed_store_exits_non_zero(mod, monkeypatch, qdrant, redis):
    monkeypatch.setattr(mod, "_flush_qdrant", lambda url, names: qdrant)
    monkeypatch.setattr(mod, "_flush_redis", lambda url, pw=None: redis)
    assert mod.main() == 1


def test_make_flush_cache_runs_the_script_in_the_container_and_does_not_hide_failure():
    makefile = (_REPO / "Makefile").read_text()
    target = makefile.split("\nflush-cache:", 1)[1].split("\n\n", 1)[0]
    assert "python3 - < ../scripts/ops/flush_cache.py" in target
    assert "2>/dev/null" not in target
    assert "exit 1" in target

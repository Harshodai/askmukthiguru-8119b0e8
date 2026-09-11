"""Recompiling the OKF index must reach answers without a process restart.

`_OKF_CACHE` was a write-once module global: once populated it was returned
forever. compile_okf() is called from the admin endpoint, the CLI script and
ingestion, and none of them cleared it, so newly approved doctrine did not
reach a single answer until the backend was restarted. With more than one
replica, whichever replica served the compile request was also the only one
that could ever have picked the change up.

The cache is now keyed on the compiled index's mtime, so any writer invalidates
it.
"""

from __future__ import annotations

import json
import os

import pytest

import rag.nodes.retrieval as retrieval


@pytest.fixture
def okf_index(tmp_path, monkeypatch):
    path = tmp_path / "compiled.json"
    monkeypatch.setattr(retrieval, "_OKF_COMPILED_PATH", path)
    monkeypatch.setattr(retrieval, "_OKF_CACHE", None)
    monkeypatch.setattr(retrieval, "_OKF_CACHE_MTIME", None)
    return path


def _write(path, titles: list[str], mtime: float) -> None:
    path.write_text(json.dumps({"entries": [{"title": t} for t in titles]}), encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_recompiled_index_is_picked_up_without_restart(okf_index):
    _write(okf_index, ["Beautiful State"], mtime=1_000_000)
    assert [e["title"] for e in retrieval._load_okf_entries()] == ["Beautiful State"]

    # An admin approves a new teaching and recompiles, in the same process.
    _write(okf_index, ["Beautiful State", "Soul Sync"], mtime=1_000_500)

    assert [e["title"] for e in retrieval._load_okf_entries()] == [
        "Beautiful State",
        "Soul Sync",
    ], "recompiled doctrine did not reach retrieval without a restart"


def test_unchanged_index_is_served_from_cache(okf_index):
    """The stat check must not turn every query into a re-read of the file."""
    _write(okf_index, ["Beautiful State"], mtime=1_000_000)
    first = retrieval._load_okf_entries()
    second = retrieval._load_okf_entries()
    assert first is second, "unchanged index should return the cached list object"


def test_missing_index_does_not_crash_and_recovers_when_created(okf_index):
    assert retrieval._load_okf_entries() == []

    _write(okf_index, ["Deeksha"], mtime=1_000_900)
    assert [e["title"] for e in retrieval._load_okf_entries()] == ["Deeksha"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

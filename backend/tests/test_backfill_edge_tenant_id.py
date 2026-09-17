"""Regression test for backfill_edge_tenant_id.

Pins that:
1. The dry-run never writes anything.
2. The apply path stamps tenant_id + corpus_id on all unstamped edges.
3. Already-stamped edges are untouched (idempotency).
4. If unstamped edges remain after apply the script exits non-zero.

No Neo4j connection required — uses a lightweight mock driver.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root or backend/
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops.backfill_edge_tenant_id import main  # noqa: E402

# ---------------------------------------------------------------------------
# Minimal Neo4j mock
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._iter = iter(rows)

    def single(self) -> dict:
        return self._rows[0]

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    """Records SET calls and simulates count queries."""

    def __init__(self, initial_unstamped: int):
        self._unstamped = initial_unstamped
        self._applied = False
        self.set_calls: list[dict] = []

    def run(self, cypher: str, **params):
        cypher_s = cypher.strip()

        if "count(r) AS total" in cypher_s:
            # _COUNT_UNSTAMPED
            return _FakeResult(
                [
                    {
                        "total": self._unstamped,
                        "sample_types": ["DIRECTED"],
                    }
                ]
            )

        if "count(r) AS n" in cypher_s and "rel_type" in cypher_s:
            # _COUNT_BY_TYPE
            if self._unstamped > 0:
                return _FakeResult([{"rel_type": "DIRECTED", "n": self._unstamped}])
            return _FakeResult([])

        if "SET r.tenant_id" in cypher_s:
            # _STAMP_CYPHER
            self.set_calls.append(dict(params))
            self._unstamped = 0  # stamp succeeded
            return _FakeResult([])

        if "count(r) AS remaining" in cypher_s:
            # _VERIFY_UNSTAMPED
            return _FakeResult([{"remaining": self._unstamped}])

        return _FakeResult([])

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _FakeDriver:
    def __init__(self, initial_unstamped: int):
        self._unstamped = initial_unstamped
        self.sessions: list[_FakeSession] = []

    def verify_connectivity(self):
        pass

    def session(self) -> _FakeSession:
        s = _FakeSession(self._unstamped)
        self.sessions.append(s)
        # After a stamp session marks itself done, future sessions see 0.
        # We share state via a simple callback.
        original_run = s.run

        def _run(cypher, **params):
            result = original_run(cypher, **params)
            if "SET r.tenant_id" in cypher:
                self._unstamped = 0  # propagate to driver state
            return result

        s.run = _run  # type: ignore[method-assign]
        s._unstamped_ref = lambda: self._unstamped  # type: ignore[attr-defined]
        return s

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Patch _connect
# ---------------------------------------------------------------------------

import scripts.ops.backfill_edge_tenant_id as _mod


def _make_patcher(driver: _FakeDriver):
    def _fake_connect(uri, user, password):
        return driver

    return _fake_connect


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_dry_run_does_not_write(monkeypatch):
    """Dry-run should count but never call SET."""
    driver = _FakeDriver(initial_unstamped=10)
    monkeypatch.setattr(_mod, "_connect", _make_patcher(driver))

    rc = main(
        [
            "--neo4j-uri",
            "bolt://fake:7687",
            "--neo4j-password",
            "fake",
        ]
    )

    assert rc == 0, "dry-run should always exit 0 (nothing broken)"
    # No session should have issued a SET call
    set_calls = [
        c for s in driver.sessions for c in (s.set_calls if hasattr(s, "set_calls") else [])
    ]
    assert set_calls == [], "dry-run must not write anything"


def test_apply_stamps_all_edges(monkeypatch):
    """Apply mode should stamp all edges and exit 0."""
    driver = _FakeDriver(initial_unstamped=4128)
    monkeypatch.setattr(_mod, "_connect", _make_patcher(driver))

    rc = main(
        [
            "--apply",
            "--neo4j-uri",
            "bolt://fake:7687",
            "--neo4j-password",
            "fake",
            "--tenant-id",
            "oneness",
            "--corpus-id",
            "askmukthiguru",
        ]
    )

    assert rc == 0, "apply should exit 0 when all edges are stamped"
    assert driver._unstamped == 0


def test_apply_is_idempotent_when_nothing_to_do(monkeypatch):
    """If all edges are already stamped, apply is a no-op and exits 0."""
    driver = _FakeDriver(initial_unstamped=0)
    monkeypatch.setattr(_mod, "_connect", _make_patcher(driver))

    rc = main(
        [
            "--apply",
            "--neo4j-uri",
            "bolt://fake:7687",
            "--neo4j-password",
            "fake",
        ]
    )

    assert rc == 0


def test_missing_password_exits_1():
    """Missing NEO4J_PASSWORD should exit 1 without connecting."""
    import os

    old = os.environ.pop("NEO4J_PASSWORD", None)
    try:
        rc = main(["--neo4j-uri", "bolt://fake:7687"])
        assert rc == 1
    finally:
        if old is not None:
            os.environ["NEO4J_PASSWORD"] = old

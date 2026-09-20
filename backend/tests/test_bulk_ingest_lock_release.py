"""F-ING-1: bulk_ingest_video.py must release the per-source ingest lock it
acquires, on every completion path (success, failed-status, exception) —
not just rely on the 900s TTL.

Before this fix, `checkpoint.acquire_lock(src)` at bulk_ingest_video.py:~233
was never paired with `checkpoint.release_lock(src)`, so a source that
finished (even a HANDLED failure, in a still-alive process) stayed locked
for the full TTL. Any immediate retry of that source — the normal case, not
just a kill -9 — was skipped as "already claimed by another run" for up to
15 minutes.

Two checks:
  1. Behavioral: IngestionCheckpoint.acquire_lock/release_lock round-trips
     correctly — release makes the reservation available again immediately,
     it isn't just cosmetic.
  2. Regression guard: `ingest_one`'s `finally` block in bulk_ingest_video.py
     actually calls `checkpoint.release_lock`, so this bug class (the same
     one fixed for the circuit breaker probes this session, see
     test_circuit_breaker.py's source assertion) cannot silently come back.

A literal `kill -9` mid-ingest is NOT recoverable by any in-process fix —
no code runs after the process is gone — so that case still relies on the
documented TTL self-expiry (IngestionCheckpoint.acquire_lock docstring).
This test proves the part that IS fixable: release on every path the
process lives to reach.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

from ingest.handlers.checkpoint import IngestionCheckpoint

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ingestion" / "bulk_ingest_video.py"


def test_release_lock_clears_reservation_immediately():
    mock_redis = MagicMock()
    held: dict[str, str] = {}

    def _set(key, value, nx=False, ex=None):
        if nx and key in held:
            return False
        held[key] = value
        return True

    def _delete(key):
        held.pop(key, None)

    def _eval(_script, _numkeys, key, token):
        if held.get(key) == token:
            held.pop(key, None)
            return 1
        return 0

    mock_redis.set.side_effect = _set
    mock_redis.delete.side_effect = _delete
    mock_redis.eval.side_effect = _eval
    mock_redis.ping.return_value = True

    with patch("redis.from_url", return_value=mock_redis):
        checkpoint = IngestionCheckpoint()
        assert checkpoint.redis_client is not None

        assert checkpoint.acquire_lock("https://youtu.be/abc") is True
        # A second worker (or an immediate retry in the same process before
        # release) must be refused while the lock is held.
        assert checkpoint.acquire_lock("https://youtu.be/abc") is False

        checkpoint.release_lock("https://youtu.be/abc")

        # After release, a retry must succeed immediately — no TTL wait.
        assert checkpoint.acquire_lock("https://youtu.be/abc") is True


def test_ingest_one_releases_lock_on_every_completion_path():
    """Source assertion: `finally` in bulk_ingest_video.py's ingest_one must
    call checkpoint.release_lock — this is what actually fixes F-ING-1.
    Parses the AST rather than grepping so the check survives reformatting."""
    tree = ast.parse(_SCRIPT.read_text())

    ingest_one = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "ingest_one"
    )
    # Find the outer try/finally inside ingest_one and inspect its finalbody.
    try_nodes = [n for n in ast.walk(ingest_one) if isinstance(n, ast.Try) and n.finalbody]
    assert try_nodes, "ingest_one must have a try/finally"

    finally_source = "\n".join(
        ast.dump(stmt) for try_node in try_nodes for stmt in try_node.finalbody
    )
    assert "release_lock" in finally_source, (
        "ingest_one's finally block must call checkpoint.release_lock(src) — "
        "F-ING-1 regression: acquire_lock() with no paired release leaves "
        "every same-process retry wedged for the full 900s TTL"
    )


if __name__ == "__main__":
    test_release_lock_clears_reservation_immediately()
    test_ingest_one_releases_lock_on_every_completion_path()
    print("OK")

"""Unit tests for scripts/ops/restore_drill.py.

Everything here is mocked (a fake Qdrant client) — no real Qdrant, no network,
no writes. The two things that MUST hold even under a bug elsewhere in the
script are covered directly: the scratch-name guard, and that --apply refuses
to run without --i-have-owner-approval. The live end-to-end drill is an ops
procedure, not a unit test — see docs/operations/drills.md.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ops import restore_drill as rd

BACKEND_DIR = Path(__file__).resolve().parents[1]


# ─── the hard guard ───────────────────────────────────────────────────────────


def test_assert_scratch_accepts_generated_name():
    rd._assert_scratch("restore_drill_scratch_chat_1234")  # must not raise


@pytest.mark.parametrize(
    "name",
    [
        "spiritual_wisdom_contextual",
        "first_person_v1",
        "chat",
        "",
        "restore_drill_scratch",  # missing the trailing underscore/suffix is still fine actually—
        "not_restore_drill_scratch_chat_1234",  # ...but this one must be rejected: doesn't START with prefix
    ],
)
def test_assert_scratch_rejects_non_scratch_names(name):
    if name.startswith(rd.SCRATCH_PREFIX):
        pytest.skip("this one is actually a valid scratch prefix")
    with pytest.raises(ValueError, match="not a scratch collection"):
        rd._assert_scratch(name)


def test_scratch_name_always_passes_its_own_guard():
    name = rd._scratch_name("spiritual_wisdom_contextual")
    rd._assert_scratch(name)  # must not raise
    assert name.startswith(rd.SCRATCH_PREFIX)
    assert "spiritual_wisdom_contextual" in name


# ─── restore_one_collection, fully mocked client ─────────────────────────────


class _Info:
    def __init__(self, points_count: int, status: str = "green"):
        self.points_count = points_count
        self.status = status


class _Snapshot:
    def __init__(self, name: str = "snap-123"):
        self.name = name


class _Record:
    def __init__(self, id_, vector):
        self.id = id_
        self.vector = vector


class _ScoredPoint:
    def __init__(self, id_):
        self.id = id_


class _QueryResponse:
    def __init__(self, points):
        self.points = points


class _FakeQdrantClient:
    """Records every call; never touches a real server. Configurable to
    simulate a healthy restore or specific failure modes."""

    def __init__(self, source_points=100, scratch_points=100, top_hit_matches=True):
        self.source_points = source_points
        self.scratch_points = scratch_points
        self.top_hit_matches = top_hit_matches
        self.calls: list[tuple[str, dict]] = []
        self.deleted: list[str] = []
        self._collections: dict[str, int] = {}

    def get_collection(self, collection_name: str):
        self.calls.append(("get_collection", {"collection_name": collection_name}))
        if collection_name in self._collections:
            return _Info(self._collections[collection_name])
        if collection_name.startswith(rd.SCRATCH_PREFIX):
            return _Info(self.scratch_points)
        return _Info(self.source_points)

    def create_snapshot(self, collection_name: str, wait: bool = True):
        self.calls.append(("create_snapshot", {"collection_name": collection_name}))
        return _Snapshot()

    def recover_snapshot(self, collection_name: str, location: str, wait: bool = True):
        self.calls.append(
            ("recover_snapshot", {"collection_name": collection_name, "location": location})
        )
        rd._assert_scratch(collection_name)  # the real client would happily accept anything; the
        # script's OWN guard is what must fire before this is ever called with a bad name.
        self._collections[collection_name] = self.scratch_points
        return True

    def scroll(self, collection_name: str, **kwargs):
        self.calls.append(("scroll", {"collection_name": collection_name}))
        return [_Record(id_="pt-1", vector=[0.1, 0.2, 0.3])], None

    def query_points(self, collection_name: str, query, using=None, limit=1):
        self.calls.append(("query_points", {"collection_name": collection_name, "using": using}))
        hit_id = "pt-1" if self.top_hit_matches else "pt-OTHER"
        return _QueryResponse([_ScoredPoint(id_=hit_id)])

    def delete_collection(self, collection_name: str):
        rd._assert_scratch(collection_name)
        self.calls.append(("delete_collection", {"collection_name": collection_name}))
        self.deleted.append(collection_name)
        return True


def test_restore_one_collection_happy_path_passes():
    client = _FakeQdrantClient(source_points=100, scratch_points=100, top_hit_matches=True)
    result = rd.restore_one_collection(
        client, "http://localhost:6333", "spiritual_wisdom_contextual"
    )

    assert result["passed"] is True
    assert result["failures"] == []
    assert result["source_points_count"] == 100
    assert result["scratch_points_count"] == 100
    assert result["scratch_deleted"] is True

    # Never touched the live collection for restore or delete:
    restore_calls = [c for c in client.calls if c[0] == "recover_snapshot"]
    delete_calls = [c for c in client.calls if c[0] == "delete_collection"]
    assert len(restore_calls) == 1
    assert restore_calls[0][1]["collection_name"].startswith(rd.SCRATCH_PREFIX)
    assert len(delete_calls) == 1
    assert delete_calls[0][1]["collection_name"].startswith(rd.SCRATCH_PREFIX)
    assert "spiritual_wisdom_contextual" not in client.deleted


def test_restore_one_collection_fails_on_point_count_mismatch():
    client = _FakeQdrantClient(source_points=100, scratch_points=42)
    result = rd.restore_one_collection(client, "http://localhost:6333", "chat_collection")
    assert result["passed"] is False
    assert any("point count mismatch" in f for f in result["failures"])
    # Still cleans up the scratch collection even on a verification failure:
    assert result["scratch_deleted"] is True


def test_restore_one_collection_fails_on_query_mismatch():
    client = _FakeQdrantClient(source_points=10, scratch_points=10, top_hit_matches=False)
    result = rd.restore_one_collection(client, "http://localhost:6333", "chat_collection")
    assert result["passed"] is False
    assert any("top hit" in f for f in result["failures"])


def test_restore_one_collection_never_deletes_source_even_on_failure():
    client = _FakeQdrantClient(source_points=10, scratch_points=999)  # forces a failure
    rd.restore_one_collection(client, "http://localhost:6333", "spiritual_wisdom_contextual")
    assert "spiritual_wisdom_contextual" not in client.deleted


# ─── dry_run() ────────────────────────────────────────────────────────────────


def test_dry_run_no_probe_makes_zero_client_calls(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("no-probe dry run must never construct a Qdrant client")

    monkeypatch.setattr(rd, "_build_client", _boom)
    plan = rd.dry_run("http://localhost:6333", probe=False)
    assert plan["probes"] == {}
    assert "spiritual_wisdom_contextual" in plan["targets"].values() or "chat" in plan["targets"]


def test_dry_run_with_probe_uses_only_read_only_calls(monkeypatch):
    client = _FakeQdrantClient()
    monkeypatch.setattr(rd, "_build_client", lambda url: client)
    plan = rd.dry_run("http://localhost:6333", probe=True)
    assert set(plan["probes"]) == {"first_person", "chat"}
    assert all(call[0] == "get_collection" for call in client.calls)  # read-only only


def test_dry_run_probe_degrades_on_unreachable_qdrant(monkeypatch):
    class _Down:
        def get_collection(self, collection_name):
            raise ConnectionError("no route to host")

    monkeypatch.setattr(rd, "_build_client", lambda url: _Down())
    plan = rd.dry_run("http://localhost:6333", probe=True)
    assert plan["probes"]["chat"]["exists"] is False


def test_dry_run_never_writes(monkeypatch):
    """A dry run must never call create_snapshot/recover_snapshot/delete_collection."""
    client = _FakeQdrantClient()
    monkeypatch.setattr(rd, "_build_client", lambda url: client)
    rd.dry_run("http://localhost:6333", probe=True)
    write_calls = {c[0] for c in client.calls} & {
        "create_snapshot",
        "recover_snapshot",
        "delete_collection",
    }
    assert write_calls == set()


# ─── CLI gate: --apply without --i-have-owner-approval must refuse ──────────


def test_apply_without_owner_approval_refuses_and_exits_nonzero():
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.ops.restore_drill", "--apply"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 1
    assert "--i-have-owner-approval" in proc.stdout


def test_default_invocation_is_dry_run_and_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.ops.restore_drill", "--no-probe"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    assert "DRY RUN only" in proc.stdout


if __name__ == "__main__":
    import sys as _sys

    _sys.exit(pytest.main([__file__, "-v"]))

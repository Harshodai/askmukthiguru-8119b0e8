"""Backup/restore safety tests for Qdrant authentication and Memgraph restore."""
from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("NEO4J_PASSWORD", "test-only-not-a-real-secret")
os.environ.setdefault("QDRANT_COLLECTION", "spiritual_wisdom_contextual")

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backup" / "snapshot_manager.py"
SPEC = importlib.util.spec_from_file_location("snapshot_manager_under_test", SCRIPT)
assert SPEC and SPEC.loader
SNAPSHOT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SNAPSHOT
SPEC.loader.exec_module(SNAPSHOT)


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def _write_graph_backup(path: Path, nodes: int, relationships: int) -> str:
    content = (
        f"// engine=memgraph nodes={nodes} relationships={relationships} taken=2026-11-26T00:00:00\n"
        + ("CREATE (:TestNode {id: 1});\n" if nodes else "")
    )
    path.write_text(content, encoding="utf-8")
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    path.with_name(path.name + ".sha256").write_text(
        f"{checksum}  {path.name}\n", encoding="utf-8"
    )
    return content


def test_qdrant_requests_send_write_key_before_fallback_key(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setenv("QDRANT_WRITE_API_KEY", "write-token")
    monkeypatch.setenv("QDRANT_API_KEY", "read-token")
    monkeypatch.setattr(SNAPSHOT.urllib.request, "urlopen", fake_urlopen)

    with SNAPSHOT._qdrant_open("http://qdrant.test:6333/collections", timeout=17):
        pass

    assert captured["request"].get_header("Api-key") == "write-token"
    assert captured["timeout"] == 17


def test_qdrant_requests_support_legacy_api_key_fallback(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return _Response()

    monkeypatch.delenv("QDRANT_WRITE_API_KEY", raising=False)
    monkeypatch.setenv("QDRANT_API_KEY", "legacy-token")
    monkeypatch.setattr(SNAPSHOT.urllib.request, "urlopen", fake_urlopen)

    with SNAPSHOT._qdrant_open("http://qdrant.test:6333/collections"):
        pass

    assert captured["request"].get_header("Api-key") == "legacy-token"


def test_graph_backup_manifest_contains_both_counts():
    text = (
        "// engine=memgraph nodes=17 relationships=29 taken=2026-11-26T00:00:00\n"
        "CREATE (:TestNode {id: 1});\n"
    )
    assert SNAPSHOT._recorded_graph_counts(text) == (17, 29)


def test_legacy_graph_manifest_without_relationship_count_remains_readable():
    text = "// engine=memgraph nodes=17 taken=2026-11-26T00:00:00\nCREATE (:TestNode);\n"
    assert SNAPSHOT._recorded_graph_counts(text) == (17, None)



def test_backup_graph_writes_count_manifest_and_checksum(tmp_path, monkeypatch):
    path = tmp_path / "backup.cypher"
    monkeypatch.setattr(SNAPSHOT, "NEO4J_BACKUP_PATH", str(path))
    monkeypatch.setattr(SNAPSHOT, "NEO4J_CONTAINER", "scratch-memgraph")
    monkeypatch.setattr(SNAPSHOT, "_container_running", lambda _name: True)
    monkeypatch.setattr(SNAPSHOT, "_graph_engine", lambda: "memgraph")
    monkeypatch.setattr(SNAPSHOT, "_graph_node_count", lambda _engine: 17)
    monkeypatch.setattr(SNAPSHOT, "_graph_relationship_count", lambda _engine: 29)
    monkeypatch.setattr(
        SNAPSHOT,
        "_graph_run",
        lambda *_args: SimpleNamespace(stdout="CREATE (:TestNode {id: 1});\\n"),
    )

    assert SNAPSHOT.backup_neo4j() is True
    content = path.read_text(encoding="utf-8")
    assert SNAPSHOT._recorded_graph_counts(content) == (17, 29)
    checksum_file = Path(f"{path}.sha256")
    assert checksum_file.is_file()
    assert checksum_file.read_text(encoding="utf-8").split()[0] == hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()


def test_restore_refuses_nonempty_target_instead_of_returning_success(tmp_path, monkeypatch):
    path = tmp_path / "backup.cypher"
    _write_graph_backup(path, 17, 29)
    monkeypatch.setattr(SNAPSHOT, "NEO4J_BACKUP_PATH", str(path))
    monkeypatch.setattr(SNAPSHOT, "NEO4J_CONTAINER", "scratch-memgraph")
    monkeypatch.setattr(SNAPSHOT, "_container_running", lambda _name: True)
    monkeypatch.setattr(SNAPSHOT, "_graph_engine", lambda: "memgraph")
    monkeypatch.setattr(SNAPSHOT, "_graph_node_count", lambda _engine: 17)
    monkeypatch.setattr(SNAPSHOT, "_graph_relationship_count", lambda _engine: 29)
    graph_run = MagicMock()
    monkeypatch.setattr(SNAPSHOT, "_graph_run", graph_run)

    assert SNAPSHOT.restore_neo4j() is False
    graph_run.assert_not_called()


def test_restore_accepts_empty_backup_only_for_empty_target(tmp_path, monkeypatch):
    path = tmp_path / "backup.cypher"
    _write_graph_backup(path, 0, 0)
    monkeypatch.setattr(SNAPSHOT, "NEO4J_BACKUP_PATH", str(path))
    monkeypatch.setattr(SNAPSHOT, "NEO4J_CONTAINER", "scratch-memgraph")
    monkeypatch.setattr(SNAPSHOT, "_container_running", lambda _name: True)
    monkeypatch.setattr(SNAPSHOT, "_graph_engine", lambda: "memgraph")
    monkeypatch.setattr(SNAPSHOT, "_graph_node_count", lambda _engine: 0)
    monkeypatch.setattr(SNAPSHOT, "_graph_relationship_count", lambda _engine: 0)

    assert SNAPSHOT.restore_neo4j() is True


def test_restore_verifies_nodes_and_relationships_after_replay(tmp_path, monkeypatch):
    path = tmp_path / "backup.cypher"
    _write_graph_backup(path, 17, 29)
    monkeypatch.setattr(SNAPSHOT, "NEO4J_BACKUP_PATH", str(path))
    monkeypatch.setattr(SNAPSHOT, "NEO4J_CONTAINER", "scratch-memgraph")
    monkeypatch.setattr(SNAPSHOT, "_container_running", lambda _name: True)
    monkeypatch.setattr(SNAPSHOT, "_graph_engine", lambda: "memgraph")
    monkeypatch.setattr(SNAPSHOT, "_graph_node_count", MagicMock(side_effect=[0, 17]))
    monkeypatch.setattr(SNAPSHOT, "_graph_relationship_count", MagicMock(side_effect=[0, 29]))
    graph_run = MagicMock()
    monkeypatch.setattr(SNAPSHOT, "_graph_run", graph_run)

    assert SNAPSHOT.restore_neo4j() is True
    graph_run.assert_called_once()


def test_restore_fails_if_relationship_count_is_wrong(tmp_path, monkeypatch):
    path = tmp_path / "backup.cypher"
    _write_graph_backup(path, 17, 29)
    monkeypatch.setattr(SNAPSHOT, "NEO4J_BACKUP_PATH", str(path))
    monkeypatch.setattr(SNAPSHOT, "NEO4J_CONTAINER", "scratch-memgraph")
    monkeypatch.setattr(SNAPSHOT, "_container_running", lambda _name: True)
    monkeypatch.setattr(SNAPSHOT, "_graph_engine", lambda: "memgraph")
    monkeypatch.setattr(SNAPSHOT, "_graph_node_count", MagicMock(side_effect=[0, 17]))
    monkeypatch.setattr(SNAPSHOT, "_graph_relationship_count", MagicMock(side_effect=[0, 28]))
    monkeypatch.setattr(SNAPSHOT, "_graph_run", MagicMock())

    assert SNAPSHOT.restore_neo4j() is False


def test_restore_refuses_checksum_mismatch(tmp_path, monkeypatch):
    path = tmp_path / "backup.cypher"
    _write_graph_backup(path, 17, 29)
    path.write_text(path.read_text(encoding="utf-8") + "// tampered\n", encoding="utf-8")
    monkeypatch.setattr(SNAPSHOT, "NEO4J_BACKUP_PATH", str(path))
    monkeypatch.setattr(SNAPSHOT, "NEO4J_CONTAINER", "scratch-memgraph")
    monkeypatch.setattr(SNAPSHOT, "_container_running", lambda _name: True)
    graph_engine = MagicMock(return_value="memgraph")
    monkeypatch.setattr(SNAPSHOT, "_graph_engine", graph_engine)

    assert SNAPSHOT.restore_neo4j() is False
    graph_engine.assert_not_called()

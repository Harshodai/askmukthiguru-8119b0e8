"""The protective snapshot must actually cover the data `make clean` deletes.

`make clean` and `make docker-rebuild` run scripts/backup/snapshot_manager.py
before `docker compose down -v`. Its defaults were "spiritual_wisdom" (an
earlier corpus collection) and the container name "mukthiguru-neo4j" (behind
the `legacy-neo4j` compose profile since the 2026-09-19 Memgraph migration, so
not running). Verified live on 2026-10-05: against a stock stack the old
defaults produced a 404 and "No such container", both swallowed by the
Makefile's `|| true`, and the volumes were then destroyed.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "backup" / "snapshot_manager.py"


def _load(monkeypatch, **env):
    for key in ("QDRANT_COLLECTION", "FIRST_PERSON_COLLECTION", "GRAPH_CONTAINER", "QDRANT_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NEO4J_PASSWORD", "test-pass")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("snapshot_manager_under_test", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_defaults_cover_the_live_corpus_and_the_clip_index(monkeypatch):
    mod = _load(monkeypatch)
    assert mod.DEFAULT_COLLECTIONS == ["spiritual_wisdom_contextual", "first_person_v7"]


def test_collections_follow_the_backend_env_vars(monkeypatch):
    mod = _load(monkeypatch, QDRANT_COLLECTION="corpus_v9", FIRST_PERSON_COLLECTION="fp_v9")
    assert mod.DEFAULT_COLLECTIONS == ["corpus_v9", "fp_v9"]


def test_each_collection_gets_its_own_snapshot_file(monkeypatch):
    mod = _load(monkeypatch)
    paths = {mod.qdrant_backup_path(c) for c in mod.DEFAULT_COLLECTIONS}
    assert len(paths) == len(mod.DEFAULT_COLLECTIONS)
    assert all(p.endswith(".snapshot") for p in paths)


def test_graph_container_defaults_to_the_running_memgraph(monkeypatch):
    mod = _load(monkeypatch)
    assert mod.NEO4J_CONTAINER == "mukthiguru-memgraph"
    legacy = _load(monkeypatch, GRAPH_CONTAINER="mukthiguru-neo4j")
    assert legacy.NEO4J_CONTAINER == "mukthiguru-neo4j"


def test_mac_only_docker_path_is_not_hardcoded(monkeypatch):
    """A developer-specific absolute PATH made this unrunnable in CI or on Linux."""
    assert "/Users/" not in _SCRIPT.read_text()


def test_make_clean_refuses_to_delete_volumes_when_the_snapshot_fails():
    makefile = (_REPO_ROOT / "Makefile").read_text()
    clean = makefile.split("\nclean:", 1)[1].split("\n\n", 1)[0]
    assert "down -v" in clean
    backup_line = next(ln for ln in clean.splitlines() if "snapshot_manager.py backup" in ln)
    assert "|| true" not in backup_line


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

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


def test_make_docker_rebuild_does_not_swallow_backup_or_restore_failures():
    makefile = (_REPO_ROOT / "Makefile").read_text()
    target = makefile.split("\ndocker-rebuild:", 1)[1].split("\n\n", 1)[0]
    lines = [ln for ln in target.splitlines() if "snapshot_manager.py" in ln]
    assert len(lines) == 2
    assert all("|| true" not in ln for ln in lines)


# ─── Exit status: the Makefile guard is only as good as this ────────────────


def _run_main(monkeypatch, mod, action, *, qdrant, graph, supabase):
    monkeypatch.setattr(mod, "setup_directories", lambda: None)
    monkeypatch.setattr(mod, f"{action}_qdrant", lambda c=None: qdrant)
    monkeypatch.setattr(mod, f"{action}_neo4j", lambda: graph)
    monkeypatch.setattr(mod, f"{action}_supabase", lambda: supabase)
    monkeypatch.setattr("sys.argv", ["snapshot_manager.py", action])
    return mod.main()


@pytest.mark.parametrize("action", ["backup", "restore"])
def test_main_exits_non_zero_when_a_required_store_fails(monkeypatch, action):
    """It used to print FAILED and exit 0, so `|| exit 1` never fired."""
    mod = _load(monkeypatch)
    assert _run_main(monkeypatch, mod, action, qdrant=True, graph=False, supabase=True) == 1
    assert _run_main(monkeypatch, mod, action, qdrant=False, graph=True, supabase=True) == 1


@pytest.mark.parametrize("action", ["backup", "restore"])
def test_skipped_optional_stores_do_not_fail_the_run(monkeypatch, action):
    mod = _load(monkeypatch)
    assert _run_main(monkeypatch, mod, action, qdrant=True, graph=True, supabase=None) == 0
    assert _run_main(monkeypatch, mod, action, qdrant=None, graph=True, supabase=None) == 0


# ─── Graph: Memgraph has no APOC and no cypher-shell ────────────────────────


class _Done:
    def __init__(self, stdout=""):
        self.stdout = stdout
        self.returncode = 0


def _fake_memgraph(monkeypatch, mod, *, count, dump, calls):
    monkeypatch.setattr(mod, "_container_running", lambda name: True)
    monkeypatch.setattr(mod, "_graph_engine", lambda: "memgraph")

    def fake_run(cmd, input=None, **kwargs):
        calls.append((cmd, input))
        if "DUMP DATABASE" in (input or ""):
            return _Done(dump)
        return _Done(f'"c"\n"{count}"\n')

    monkeypatch.setattr(mod.subprocess, "run", fake_run)


def test_graph_backup_uses_dump_database_and_records_the_node_count(monkeypatch, tmp_path):
    mod = _load(monkeypatch)
    monkeypatch.setattr(mod, "NEO4J_BACKUP_PATH", str(tmp_path / "backup.cypher"))
    calls = []
    _fake_memgraph(
        monkeypatch, mod, count=3, dump="CREATE (:A);\nCREATE (:B);\nCREATE (:C);\n", calls=calls
    )
    assert mod.backup_neo4j() is True
    text = (tmp_path / "backup.cypher").read_text()
    assert mod._recorded_node_count(text) == 3
    assert any("mgconsole" in cmd for cmd, _ in calls)
    assert not any("apoc" in (inp or "") for _, inp in calls)
    # mgconsole executes nothing (exit 0, empty output) without a trailing
    # newline, which reads exactly like an empty graph. Found live 2026-10-05.
    assert all((inp or "").endswith("\n") for _, inp in calls)


def test_graph_backup_refuses_an_empty_dump_of_a_populated_graph(monkeypatch, tmp_path):
    mod = _load(monkeypatch)
    monkeypatch.setattr(mod, "NEO4J_BACKUP_PATH", str(tmp_path / "backup.cypher"))
    _fake_memgraph(monkeypatch, mod, count=6430, dump="", calls=[])
    assert mod.backup_neo4j() is False
    assert not (tmp_path / "backup.cypher").exists()


def test_graph_backup_fails_when_the_container_is_not_running(monkeypatch):
    mod = _load(monkeypatch)
    monkeypatch.setattr(mod, "_container_running", lambda name: False)
    assert mod.backup_neo4j() is False


def test_graph_restore_never_replays_over_a_populated_graph(monkeypatch, tmp_path):
    mod = _load(monkeypatch)
    backup = tmp_path / "backup.cypher"
    backup.write_text("// engine=memgraph nodes=3 taken=x\nCREATE (:A);\n")
    monkeypatch.setattr(mod, "NEO4J_BACKUP_PATH", str(backup))
    calls = []
    _fake_memgraph(monkeypatch, mod, count=3, dump="", calls=calls)
    assert mod.restore_neo4j() is True
    assert not any("CREATE" in (inp or "") for _, inp in calls)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

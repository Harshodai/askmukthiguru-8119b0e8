"""Tests for OKF compiler and runtime loader."""

from __future__ import annotations

import asyncio
import json

import pytest

from services.memory import compiler as okf_compiler
from services.memory.compiler import compile_okf, dedupe_okf_entries, get_compiled_okf


@pytest.fixture(autouse=True)
def _patch_paths(tmp_path, monkeypatch):
    """Redirect compiled.json to a temp path so tests don't touch the repo."""
    test_path = tmp_path / "compiled.json"
    monkeypatch.setattr(okf_compiler, "_COMPILED_PATH", test_path)


@pytest.mark.unit
def test_compile_and_load_round_trip(monkeypatch, tmp_path):
    """Compile synthetic entries and verify the compiled JSON round-trips."""
    entries = [
        {
            "path": "/tmp/t1.md",
            "type": "teaching",
            "title": "T1",
            "tags": ["a"],
            "source": "test",
            "body": "body1",
        },
        {
            "path": "/tmp/t2.md",
            "type": "glossary",
            "title": "T2",
            "tags": [],
            "source": "test",
            "body": "body2",
        },
    ]

    def _fake_load():
        return entries

    def _fake_embed(texts):
        return [[0.1, 0.2, 0.3]] * len(texts)

    monkeypatch.setattr(okf_compiler, "_load_okf_entries", _fake_load)
    monkeypatch.setattr(okf_compiler, "_embed_texts", _fake_embed)

    path = compile_okf()
    assert path.exists()

    loaded = asyncio.run(get_compiled_okf())
    assert len(loaded) == 2
    assert loaded[0]["type"] == "teaching"
    assert loaded[1]["title"] == "T2"
    assert len(loaded[0]["embedding"]) == 3


@pytest.mark.unit
def test_no_entries_writes_empty(monkeypatch, tmp_path):
    """When no OKF entries exist, compile_okf writes an empty object."""
    monkeypatch.setattr(okf_compiler, "_load_okf_entries", lambda: [])
    monkeypatch.setattr(okf_compiler, "_embed_texts", lambda texts: [])

    path = compile_okf()
    assert path.exists()
    data = json.loads(path.read_text())
    assert data == {}


@pytest.mark.unit
def test_get_compiled_okf_missing_file(monkeypatch, tmp_path):
    """Absent compiled.json returns empty list."""
    missing = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(okf_compiler, "_COMPILED_PATH", missing)
    assert asyncio.run(get_compiled_okf()) == []


@pytest.mark.unit
def test_get_compiled_okf_corrupted_file(monkeypatch, tmp_path):
    """Corrupted compiled.json returns empty list (non-fatal)."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(okf_compiler, "_COMPILED_PATH", bad)
    assert asyncio.run(get_compiled_okf()) == []


def _dedup_entry(path, title, body, source="https://www.youtube.com/watch?v=vid1234567"):
    return {
        "path": path,
        "type": "teaching",
        "title": title,
        "tags": ["suffering"],
        "source": source,
        "body": body,
    }


@pytest.mark.unit
def test_dedupe_filename_double_prefers_graduated():
    """Root+subdir copies of one file collapse to the graduated copy (2026-10-04 audit)."""
    root = _dedup_entry(
        "/okf/ego.md", "Ego", "Suffering arises from self-centric thinking daily. " * 10
    )
    sub = _dedup_entry(
        "/okf/shared/ego.md", "Ego", "Suffering arises from self-centric thinking always. " * 10
    )
    alive, stats = dedupe_okf_entries([root, sub])
    assert len(alive) == 1
    assert stats["filename_groups"] == 1
    assert alive[0]["path"] == "/okf/shared/ego.md"


@pytest.mark.unit
def test_dedupe_graduated_length_guard_keeps_longer_root():
    """A much thinner graduated copy must not destroy substantive root content."""
    root = _dedup_entry("/okf/ego.md", "Ego", "word " * 500)
    sub = _dedup_entry("/okf/shared/ego.md", "Ego", "word " * 100)
    alive, _ = dedupe_okf_entries([root, sub])
    assert len(alive) == 1
    assert alive[0]["path"] == "/okf/ego.md"


@pytest.mark.unit
def test_dedupe_exact_title_and_content_hash():
    """Same title under different filenames, and byte-identical bodies, collapse."""
    a = _dedup_entry("/okf/a.md", "Same Title", "short body here " * 20)
    b = _dedup_entry("/okf/b.md", "Same Title", "different wording altogether here " * 20)
    c = _dedup_entry("/okf/c.md", "Other Title", "different wording altogether here " * 20)
    alive, stats = dedupe_okf_entries([a, b, c])
    assert len(alive) == 1
    assert stats["exact_title_groups"] == 1
    assert stats["content_hash_groups"] == 1


@pytest.mark.unit
def test_dedupe_jaccard_near_twins_collapse_distinct_survive():
    """Bodies sharing >=90% vocabulary collapse; genuinely different bodies stay."""
    base = (
        "suffering observation consciousness beautiful state calm peace joy "
        "stillness love bliss equanimity mindfulness presence awakening wisdom "
        "truth insight awareness witness "
    ) * 8
    twin = base + "extra"
    different = "karma dharma meditation deeksha ekam surrender grace " * 40
    entries = [
        _dedup_entry("/okf/a.md", "A", base),
        _dedup_entry("/okf/b.md", "B", twin),
        _dedup_entry("/okf/c.md", "C", different),
    ]
    alive, stats = dedupe_okf_entries(entries)
    assert stats["jaccard_dropped"] == 1
    assert {e["title"] for e in alive} == {"B", "C"}  # longer twin wins, distinct stays


@pytest.mark.unit
def test_dedupe_empty_is_noop():
    alive, stats = dedupe_okf_entries([])
    assert alive == []
    assert stats["n_before"] == 0
    assert stats["n_after"] == 0

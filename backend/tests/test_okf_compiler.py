"""Tests for OKF compiler and runtime loader."""

from __future__ import annotations

import asyncio
import json

import pytest

from services.memory import compiler as okf_compiler
from services.memory.compiler import compile_okf, get_compiled_okf


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

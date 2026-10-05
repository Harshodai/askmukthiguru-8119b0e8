"""R4 freshness flag: `updated:` survives the compiler writer into compiled.json.

Production compiled.json is never touched here — the end-to-end case compiles
a scratch tmp bundle with stubbed embeddings and a redirected output path.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from services.memory import compiler

ENTRY_WITH_DATE = """---
type: teaching
title: Stamped Teaching
source: https://example.com/video?v=abc123XYZ
teacher: sri-preethaji
updated: 2026-09-01
---

Sri Preethaji teaches that stillness is the natural state of consciousness.
""" + ("Stillness heals the restless mind and opens the heart. " * 10)

ENTRY_WITHOUT_DATE = """---
type: teaching
title: Unstamped Teaching
source: https://example.com/other
teacher: sri-krishnaji
---

Sri Krishnaji teaches the Serene Mind practice for calming body and mind.
""" + ("Breath, emotion, and thought direction settle awareness. " * 10)


@pytest.mark.unit
def test_apply_updated_defaults_keeps_frontmatter_date():
    entries = [{"title": "A", "updated": "2026-09-01"}, {"title": "B"}]
    out, n = compiler.apply_updated_defaults(entries, "2026-10-04")
    assert n == 1
    assert out[0]["updated"] == "2026-09-01"
    assert out[0]["updated_source"] == "frontmatter"
    assert out[1]["updated"] == "2026-10-04"
    assert out[1]["updated_source"] == "build_default"


@pytest.mark.unit
def test_scratch_compile_carries_updated_flag(tmp_path, monkeypatch):
    okf_dir = tmp_path / "okf"
    okf_dir.mkdir()
    (okf_dir / "stamped.md").write_text(ENTRY_WITH_DATE, encoding="utf-8")
    (okf_dir / "unstamped.md").write_text(ENTRY_WITHOUT_DATE, encoding="utf-8")

    import services.memory.okf_store as okf_store

    monkeypatch.setattr(okf_store, "_OKF_DIR", okf_dir)
    monkeypatch.setattr(okf_store, "OKF_DIR", okf_dir)
    out_path = tmp_path / "compiled.json"
    monkeypatch.setattr(compiler, "_COMPILED_PATH", out_path)
    monkeypatch.setattr(compiler, "_embed_texts", lambda texts: [[0.5] * 1024 for _ in texts])

    result = compiler.compile_okf()
    assert result == out_path

    data = json.loads(out_path.read_text(encoding="utf-8"))
    by_title = {e["title"]: e for e in data["entries"]}
    assert set(by_title) == {"Stamped Teaching", "Unstamped Teaching"}

    today = datetime.now(UTC).date().isoformat()
    assert by_title["Stamped Teaching"]["updated"] == "2026-09-01"
    assert by_title["Stamped Teaching"]["updated_source"] == "frontmatter"
    assert by_title["Unstamped Teaching"]["updated"] == today
    assert by_title["Unstamped Teaching"]["updated_source"] == "build_default"

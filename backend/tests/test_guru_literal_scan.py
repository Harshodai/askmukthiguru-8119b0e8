"""T8-02 / GURU-010 / NFR-MAINT-05: teacher-name literals in runtime code only go down."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "guards"))

import guru_literal_guard as g  # noqa: E402


def test_scan_counts_lines_and_skips_tests_and_locales(tmp_path):
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "tests").mkdir(parents=True)
    (tmp_path / "src" / "locales").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "a.py").write_text("x = 'Krishnaji'\ny = 1\nz = 'PREETHAJI'\n")
    (tmp_path / "backend" / "tests" / "test_a.py").write_text("x = 'Krishnaji'\n")
    (tmp_path / "src" / "locales" / "en.json").write_text('{"a": "Preethaji"}')
    (tmp_path / "src" / "b.test.ts").write_text("const x = 'Krishnaji'\n")
    assert g.scan_literals(tmp_path) == {"backend/app/a.py": 2}


def test_new_file_or_higher_count_is_a_violation():
    base = {"a.py": 2}
    assert g.compare({"a.py": 2}, base) == []
    assert any("a.py" in e for e in g.compare({"a.py": 3}, base))
    assert any("b.py" in e for e in g.compare({"a.py": 2, "b.py": 1}, base))


def test_lower_count_must_lower_the_baseline():
    errs = g.compare({"a.py": 1}, {"a.py": 2})
    assert any("lower" in e.lower() for e in errs)
    errs = g.compare({}, {"a.py": 2})
    assert any("lower" in e.lower() for e in errs)


def test_baseline_matches_the_tree():
    """The committed baseline equals the tree. Fails on any new literal or any unrecorded fix."""
    counts = g.scan_literals(REPO_ROOT)
    assert g.compare(counts, g.load_baseline()) == []

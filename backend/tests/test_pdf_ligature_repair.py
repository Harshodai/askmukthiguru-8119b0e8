"""Regression coverage for the pypdf ligature-drop repair (services/pdf_ligature_repair.py).

Found 2026-09-18: 52/70 chunks ingested from The Four Sacred Secrets carried a
literal NUL byte where pypdf dropped a ligature glyph (fi/fl/ff/ffi/ffl),
producing "su\x00ering" for "suffering". This corrupted text was reaching
users verbatim via the grounded-excerpt fallback path.
"""

from __future__ import annotations

import pytest

from services.pdf_ligature_repair import repair_ligature_drops


def test_noop_on_clean_text():
    text = "no ligatures here at all"
    assert repair_ligature_drops(text) == text


def test_noop_on_empty_string():
    assert repair_ligature_drops("") == ""


def test_repairs_known_ligature_drops():
    corrupted = "Ever since my \x00rst spiritual e\x00ort, the di\x00erence was clear."
    assert (
        repair_ligature_drops(corrupted)
        == "Ever since my first spiritual effort, the difference was clear."
    )


def test_repairs_triple_letter_ligature():
    # "difficult" drops the 3-letter "ffi" ligature, not just 2 letters.
    assert (
        repair_ligature_drops("an extremely di\x00cult hurdle") == "an extremely difficult hurdle"
    )


def test_repairs_capitalized_word():
    assert repair_ligature_drops("Su\x00ering is optional.") == "Suffering is optional."


def test_unmapped_token_strips_nul_without_crashing(caplog):
    result = repair_ligature_drops("some \x00xyzabc word")
    assert "\x00" not in result
    assert "no mapping" in caplog.text.lower()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))

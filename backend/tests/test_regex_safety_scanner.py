from __future__ import annotations

from scripts.security.check_regex_safety import _has_ambiguous_nested_quantifier, scan


def test_scanner_rejects_canonical_unbounded_nested_quantifier() -> None:
    assert _has_ambiguous_nested_quantifier(r"^(a+)+$")


def test_scanner_accepts_bounded_runtime_patterns() -> None:
    assert not _has_ambiguous_nested_quantifier(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b")


def test_current_runtime_tree_has_no_known_evil_literals() -> None:
    assert scan() == []

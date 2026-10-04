"""Cheap unit test: dream_memories dedup threshold matches B4 spec (cos > 0.95)."""

from scripts.dream_memories import DEDUP_SIM_THRESHOLD, is_duplicate


def test_dedup_threshold_matches_b4_spec():
    assert DEDUP_SIM_THRESHOLD == 0.95


def test_is_duplicate_boundary():
    assert is_duplicate(0.951) is True
    assert is_duplicate(0.95) is False
    assert is_duplicate(0.90) is False
    assert is_duplicate(0.0) is False

import os
import pytest
from app.config import Settings, get_settings


def test_settings_thresholds_defaults():
    """Verify that Settings loads the expected P1 threshold defaults."""
    settings = Settings()
    assert settings.lettuce_detect_threshold == 0.25
    assert settings.cove_supported_threshold == 0.8
    assert settings.cove_partial_threshold == 0.5
    assert settings.faithfulness_floor == 0.6  # migrated default (b5399e48); 0.8 was stale
    assert settings.verifier_pass_ratio == 0.5
    assert settings.rerank_threshold_complex == 0.01
    assert settings.rerank_threshold_simple == 0.05
    assert settings.rerank_floor == 0.3


def test_settings_thresholds_override(monkeypatch):
    """Verify that thresholds can be overridden via environment variables."""
    monkeypatch.setenv("LETTUCE_DETECT_THRESHOLD", "0.45")
    monkeypatch.setenv("COVE_SUPPORTED_THRESHOLD", "0.95")
    monkeypatch.setenv("COVE_PARTIAL_THRESHOLD", "0.65")
    monkeypatch.setenv("FAITHFULNESS_FLOOR", "0.9")
    monkeypatch.setenv("VERIFIER_PASS_RATIO", "0.75")
    monkeypatch.setenv("RERANK_THRESHOLD_COMPLEX", "0.02")
    monkeypatch.setenv("RERANK_THRESHOLD_SIMPLE", "0.08")
    monkeypatch.setenv("RERANK_FLOOR", "0.4")

    # Re-instantiate Settings to load from the environment
    settings = Settings()
    assert settings.lettuce_detect_threshold == 0.45
    assert settings.cove_supported_threshold == 0.95
    assert settings.cove_partial_threshold == 0.65
    assert settings.faithfulness_floor == 0.9
    assert settings.verifier_pass_ratio == 0.75
    assert settings.rerank_threshold_complex == 0.02
    assert settings.rerank_threshold_simple == 0.08
    assert settings.rerank_floor == 0.4

from app.config import Settings


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
    # H1: safety / quality dials promoted from inline literals to settings.
    assert settings.semantic_distress_threshold == 0.72
    assert settings.semantic_distress_history_score_threshold == 0.6
    assert settings.semantic_distress_rolling_window == 5
    assert settings.semantic_distress_escalation_count == 3
    assert settings.proactive_distress_frequency_threshold == 0.6
    assert settings.ontology_confidence_threshold == 0.7
    assert settings.ontology_validity_confidence_threshold == 0.7
    assert settings.web_search_result_min_score == 0.6
    assert settings.raptor_summary_faithfulness_floor == 0.35


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
    # H1 overrides.
    monkeypatch.setenv("SEMANTIC_DISTRESS_THRESHOLD", "0.68")
    monkeypatch.setenv("RAPTOR_SUMMARY_FAITHFULNESS_FLOOR", "0.5")

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
    assert settings.semantic_distress_threshold == 0.68
    assert settings.raptor_summary_faithfulness_floor == 0.5

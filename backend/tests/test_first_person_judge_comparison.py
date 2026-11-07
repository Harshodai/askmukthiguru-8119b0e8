"""Unit tests for T4-06 FirstPerson evidence judge comparison harness."""

from app.config import Settings
from scripts.ops.compare_fp_judge import (
    FROZEN_116_PATH,
    UNANSWERABLE_86_PATH,
    evaluate_offline_rubric,
    load_banks,
)
from services.first_person_judge import judge_enabled, judge_model


def test_bank_files_exist_and_counts_match():
    assert FROZEN_116_PATH.exists()
    assert UNANSWERABLE_86_PATH.exists()

    q116, q86 = load_banks()
    assert len(q116) == 116
    assert len(q86) == 86


def test_judge_flag_remains_disabled_by_default():
    settings = Settings()
    assert settings.first_person_judge_enabled is False
    assert judge_enabled() is False
    assert judge_model() == "anthropic/claude-haiku-5.5"


def test_offline_rubric_evaluation():
    report = evaluate_offline_rubric()
    assert report["status"] == "PASS"
    assert report["bank_116_count"] == 116
    assert report["bank_86_count"] == 86
    assert report["flag_default_enabled"] is False
    assert report["unanswerable_gate_verified"] is True
    assert report["parser_strictness_verified"] is True

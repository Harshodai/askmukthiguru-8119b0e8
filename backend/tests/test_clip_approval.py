"""Unit tests for Ponytail Clip Auto-Approval and Review Orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from evaluation.clip_approval import (
    evaluate_clip,
    evaluate_clips_batch,
    export_approved_manifest,
    export_review_csv,
)
from evaluation.gold.review_server import read_csv_rows
from evaluation.schemas.clip_approval import ClipEvaluationVerdict, HumanReviewDecision

# ---------------------------------------------------------------------------
# 1. Pydantic Schema Validation Tests
# ---------------------------------------------------------------------------


def test_schema_extra_forbid():
    """extra='forbid' must reject unknown attributes."""
    valid_kwargs = {
        "clip_id": "clip_1",
        "video_id": "dQw4w9WgXcQ",
        "start_s": 10.0,
        "end_s": 35.0,
        "duration_s": 25.0,
        "boundary_clean": True,
        "boundary_defects": [],
        "doctrinal_score": 0.90,
        "doctrinal_rationale": "Aligned with teachings",
        "tone_score": 0.92,
        "tone_rationale": "Calm and teacherly",
        "composite_score": 0.90,
        "approved": True,
        "needs_human_review": False,
        "rejection_reason": None,
    }

    # Should succeed with valid kwargs
    verdict = ClipEvaluationVerdict(**valid_kwargs)
    assert verdict.clip_id == "clip_1"

    # Should raise ValidationError when extra fields are passed
    with pytest.raises(ValidationError):
        ClipEvaluationVerdict(**valid_kwargs, unknown_field="unexpected")

    # HumanReviewDecision extra='forbid' check
    with pytest.raises(ValidationError):
        HumanReviewDecision(
            clip_id="clip_1",
            video_id="dQw4w9WgXcQ",
            human_verdict="approved",
            reviewed_at_iso="2026-09-28T12:00:00Z",
            tampered_flag=True,
        )


def test_schema_score_and_time_bounds():
    """Scores must be in [0.0, 1.0] and timestamps >= 0.0."""
    base_kwargs = {
        "clip_id": "clip_1",
        "video_id": "dQw4w9WgXcQ",
        "start_s": 10.0,
        "end_s": 30.0,
        "duration_s": 20.0,
        "boundary_clean": True,
        "boundary_defects": [],
        "doctrinal_score": 0.90,
        "doctrinal_rationale": "Good",
        "tone_score": 0.90,
        "tone_rationale": "Good",
        "composite_score": 0.90,
        "approved": True,
        "needs_human_review": False,
    }

    # Negative start time
    with pytest.raises(ValidationError):
        ClipEvaluationVerdict(**{**base_kwargs, "start_s": -1.0})

    # Doctrinal score > 1.0
    with pytest.raises(ValidationError):
        ClipEvaluationVerdict(**{**base_kwargs, "doctrinal_score": 1.05})

    # Tone score < 0.0
    with pytest.raises(ValidationError):
        ClipEvaluationVerdict(**{**base_kwargs, "tone_score": -0.1})

    # Composite score > 1.0
    with pytest.raises(ValidationError):
        ClipEvaluationVerdict(**{**base_kwargs, "composite_score": 1.5})


def test_human_review_decision_verdict_literal():
    """Human review verdict must only allow approved, rejected, or adjusted."""
    decision = HumanReviewDecision(
        clip_id="c1",
        video_id="v1",
        human_verdict="approved",
        reviewed_at_iso="2026-09-28T12:00:00Z",
    )
    assert decision.human_verdict == "approved"

    with pytest.raises(ValidationError):
        HumanReviewDecision(
            clip_id="c1",
            video_id="v1",
            human_verdict="maybe",  # invalid literal
            reviewed_at_iso="2026-09-28T12:00:00Z",
        )


# ---------------------------------------------------------------------------
# 2. Fast-Path Boundary Defect Detection Tests
# ---------------------------------------------------------------------------


def test_fast_path_severed_head_zero_llm_calls():
    """Severed head ('is agitated') must fail fast with 0 LLM calls."""
    mock_judge = MagicMock()

    verdict = evaluate_clip(
        clip_id="test_severed_head",
        video_id="dQw4w9WgXcQ",
        start_s=50.0,
        end_s=75.0,
        text="is agitated. You see the truth.",
        judge=mock_judge,
    )

    assert verdict.boundary_clean is False
    assert "head_lowercase" in verdict.boundary_defects
    assert verdict.approved is False
    assert verdict.needs_human_review is True
    assert "boundary_defect: head_lowercase" in (verdict.rejection_reason or "")
    mock_judge.assert_not_called()


def test_fast_path_short_duration_fragment_zero_llm_calls():
    """Clips under 15 seconds must fail fast as fragments with 0 LLM calls."""
    mock_judge = MagicMock()

    verdict = evaluate_clip(
        clip_id="test_fragment",
        video_id="dQw4w9WgXcQ",
        start_s=10.0,
        end_s=20.0,  # 10s duration < 15s
        text="Suffering is not a fact. It is a reaction.",
        judge=mock_judge,
    )

    assert verdict.duration_s == 10.0
    assert verdict.boundary_clean is False
    assert "duration_under_15s" in verdict.boundary_defects
    assert verdict.approved is False
    mock_judge.assert_not_called()


def test_fast_path_dangling_tail_zero_llm_calls():
    """Dangling conjunction tail must fail fast with 0 LLM calls."""
    mock_judge = MagicMock()

    verdict = evaluate_clip(
        clip_id="test_dangling_tail",
        video_id="dQw4w9WgXcQ",
        start_s=10.0,
        end_s=30.0,
        text="Suffering is not a fact, and",
        judge=mock_judge,
    )

    assert verdict.boundary_clean is False
    assert "tail_no_terminal" in verdict.boundary_defects
    assert "tail_dangling_word" in verdict.boundary_defects
    assert verdict.approved is False
    mock_judge.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Clean Clip Approval Tests (Mocked LLM Judge & Deterministic Mode)
# ---------------------------------------------------------------------------


def test_clean_clip_approval_with_mocked_judge():
    """Clean boundaries and high judge score (0.90) must result in approved=True."""
    mock_judge = MagicMock()
    # Mocking CompositeScore-like behavior
    mock_judge.score_response.return_value = {
        "doctrinal_score": 0.90,
        "doctrinal_rationale": "Clear Beautiful State doctrine",
        "tone_score": 0.92,
        "tone_rationale": "Warm teacher voice",
    }

    verdict = evaluate_clip(
        clip_id="test_clean_approved",
        video_id="dQw4w9WgXcQ",
        start_s=10.0,
        end_s=35.0,
        text="Suffering is not a fact. It is only your perception.",
        judge=mock_judge,
    )

    assert verdict.boundary_clean is True
    assert verdict.boundary_defects == []
    assert verdict.doctrinal_score == 0.90
    assert verdict.tone_score == 0.92
    assert verdict.composite_score == 0.90
    assert verdict.approved is True
    assert verdict.needs_human_review is False
    assert verdict.rejection_reason is None
    assert mock_judge.score_response.called


def test_clean_clip_deterministic_mode_without_judge():
    """When judge is None, deterministic heuristic assigns clean passing score."""
    verdict = evaluate_clip(
        clip_id="test_clean_deterministic",
        video_id="dQw4w9WgXcQ",
        start_s=0.0,
        end_s=25.0,
        text="Suffering is not a fact. It is only your perception.",
        judge=None,
    )

    assert verdict.boundary_clean is True
    assert verdict.approved is True
    assert verdict.composite_score == 0.90
    assert "Deterministic heuristic" in verdict.doctrinal_rationale


def test_clean_clip_rejected_due_to_doctrinal_slip():
    """Clean boundary but low doctrinal score must result in approved=False, needs_human_review=True."""
    mock_judge = MagicMock()
    mock_judge.score_response.return_value = {
        "doctrinal_score": 0.65,
        "doctrinal_rationale": "Buddhism non-self drift",
        "tone_score": 0.88,
        "tone_rationale": "Teacher cadence",
    }

    verdict = evaluate_clip(
        clip_id="test_doctrinal_slip",
        video_id="dQw4w9WgXcQ",
        start_s=10.0,
        end_s=35.0,
        text="Suffering is not a fact. It is only your perception.",
        judge=mock_judge,
    )

    assert verdict.boundary_clean is True
    assert verdict.composite_score == 0.65
    assert verdict.approved is False
    assert verdict.needs_human_review is True  # composite_score >= 0.60
    assert "doctrinal_slip" in (verdict.rejection_reason or "")


# ---------------------------------------------------------------------------
# 4. Batch Evaluation & Export Tests
# ---------------------------------------------------------------------------


def test_evaluate_clips_batch():
    """Batch evaluation correctly processes multiple clips."""
    clips = [
        {
            "clip_id": "c1",
            "video_id": "v1",
            "start": 0.0,
            "end": 20.0,
            "text": "Suffering is not a fact. It is a reaction.",
        },
        {
            "clip_id": "c2",
            "video_id": "v1",
            "start": 20.0,
            "end": 25.0,  # 5s -> fragment
            "text": "It goes on.",
        },
        {
            "clip_id": "c3",
            "video_id": "v2",
            "start": 10.0,
            "end": 30.0,
            "text": "is agitated. Then it heals.",  # severed head
        },
    ]

    verdicts = evaluate_clips_batch(clips, judge=None)
    assert len(verdicts) == 3
    assert verdicts[0].approved is True
    assert verdicts[1].approved is False
    assert "duration_under_15s" in verdicts[1].boundary_defects
    assert verdicts[2].approved is False
    assert "head_lowercase" in verdicts[2].boundary_defects


def test_export_review_csv(tmp_path: Path):
    """export_review_csv must export only rejected clips in review_server schema."""
    clips = [
        {
            "clip_id": "c_approved",
            "video_id": "v1",
            "start": 0.0,
            "end": 20.0,
            "text": "Suffering is not a fact. It is a reaction.",
            "question_id": "Q1",
            "question_text": "What is suffering?",
        },
        {
            "clip_id": "c_mid_sentence",
            "video_id": "v1",
            "start": 25.0,
            "end": 50.0,
            "text": "and then you see the light.",
            "question_id": "Q2",
            "question_text": "How do you see the light?",
        },
        {
            "clip_id": "c_fragment",
            "video_id": "v2",
            "start": 10.0,
            "end": 18.0,
            "text": "Listen to me.",
            "question_id": "Q3",
            "question_text": "Who speaks?",
        },
    ]

    verdicts = evaluate_clips_batch(clips, judge=None)
    out_csv = tmp_path / "review_needed.csv"

    exported_count = export_review_csv(verdicts, out_csv)
    assert exported_count == 2
    assert out_csv.exists()

    # Read back using review_server.read_csv_rows to verify schema compatibility
    rows = read_csv_rows(out_csv)
    assert len(rows) == 2

    # Check headers matching review_server expectations
    expected_headers = {
        "question_id",
        "question_text",
        "video_id",
        "start",
        "end",
        "text",
        "judge_a",
        "judge_b",
        "adjudicated",
        "clip_quality",
    }
    assert set(rows[0].keys()) == expected_headers

    row_mid = next(r for r in rows if r["question_id"] == "Q2")
    assert row_mid["clip_quality"] == "mid_sentence"
    assert row_mid["text"] == "and then you see the light."

    row_frag = next(r for r in rows if r["question_id"] == "Q3")
    assert row_frag["clip_quality"] == "fragment"


def test_export_approved_manifest(tmp_path: Path):
    """export_approved_manifest must export only approved clips as valid JSON."""
    clips = [
        {
            "clip_id": "c_approved",
            "video_id": "v1",
            "start": 0.0,
            "end": 20.0,
            "text": "Suffering is not a fact. It is a reaction.",
        },
        {
            "clip_id": "c_rejected",
            "video_id": "v1",
            "start": 20.0,
            "end": 25.0,
            "text": "Too short.",
        },
    ]

    verdicts = evaluate_clips_batch(clips, judge=None)
    out_json = tmp_path / "approved_manifest.json"

    count = export_approved_manifest(verdicts, out_json)
    assert count == 1
    assert out_json.exists()

    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["clip_id"] == "c_approved"
    assert data[0]["approved"] is True
    assert data[0]["boundary_clean"] is True


def test_llm_judge_composite_score_integration():
    """Verify integration when judge returns real CompositeScore and DimensionScore objects."""
    from evaluation.llm_judge import CompositeScore, DimensionScore

    mock_judge = MagicMock()
    mock_judge.score_response.return_value = CompositeScore(
        query="test query",
        composite=0.91,
        weighted_mean=0.91,
        dimensions={
            "doctrinal_consistency": DimensionScore(
                name="doctrinal_consistency",
                score=0.92,
                pass_threshold=0.85,
                rationale="Fully aligned with Ekam teachings",
            ),
            "tone": DimensionScore(
                name="tone",
                score=0.91,
                pass_threshold=0.80,
                rationale="Warm spiritual guide cadence",
            ),
        },
        all_pass=True,
    )

    verdict = evaluate_clip(
        clip_id="test_real_composite",
        video_id="dQw4w9WgXcQ",
        start_s=0.0,
        end_s=30.0,
        text="The state you create within yourself is the state you experience outside.",
        judge=mock_judge,
    )

    assert verdict.approved is True
    assert verdict.boundary_clean is True
    assert verdict.doctrinal_score == 0.92
    assert verdict.tone_score == 0.91
    assert verdict.composite_score == 0.91
    assert verdict.needs_human_review is False
    assert verdict.rejection_reason is None


def test_cli_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test CLI main() end-to-end with CSV input and approved/review exports."""
    from evaluation.clip_approval import main

    in_json = tmp_path / "input_clips.json"
    clips = [
        {
            "clip_id": "c1",
            "video_id": "v1",
            "start": 0.0,
            "end": 20.0,
            "text": "Suffering is not a fact. It is a reaction.",
        },
        {
            "clip_id": "c2",
            "video_id": "v1",
            "start": 20.0,
            "end": 24.0,  # fragment
            "text": "Too short.",
        },
    ]
    in_json.write_text(json.dumps(clips), encoding="utf-8")

    out_approved = tmp_path / "approved.json"
    out_review = tmp_path / "review.csv"

    monkeypatch.setattr(
        "sys.argv",
        [
            "clip_approval.py",
            "--input",
            str(in_json),
            "--out-approved",
            str(out_approved),
            "--out-review",
            str(out_review),
        ],
    )

    main()

    assert out_approved.exists()
    assert out_review.exists()
    approved_data = json.loads(out_approved.read_text(encoding="utf-8"))
    assert len(approved_data) == 1
    assert approved_data[0]["clip_id"] == "c1"

    review_rows = read_csv_rows(out_review)
    assert len(review_rows) == 1
    assert review_rows[0]["question_id"] == "c2"
    assert review_rows[0]["clip_quality"] == "fragment"

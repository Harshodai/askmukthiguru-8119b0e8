"""
Unit tests for backend/evaluation/gold/run_calibration.py (Phase 3 Calibrator CLI).
All tests run hermetically inside the repo without network or live Qdrant.
"""

from __future__ import annotations

import csv
import json
from unittest.mock import MagicMock

import pytest

from evaluation.gold.run_calibration import (
    evaluate_predictions_against_gold,
    load_pipeline_scores_file,
    resolve_human_label,
    run_calibration,
    score_questions_with_pipeline,
)
from services.first_person_pipeline import (
    FirstPersonPipelineResult,
    load_calibration_profile,
)


def test_resolve_human_label_precedence_and_guards():
    # 1. Adjudicated label takes top precedence
    row_adj = {"adjudicated": "yes", "judge_a": "no", "judge_b": "no"}
    assert resolve_human_label(row_adj) == 1

    row_adj_no = {"adjudicated": "no", "judge_a": "yes", "judge_b": "yes"}
    assert resolve_human_label(row_adj_no) == 0

    # 2. Agreed judges take precedence when unadjudicated
    row_agreed = {"adjudicated": "", "judge_a": "yes", "judge_b": "yes"}
    assert resolve_human_label(row_agreed) == 1

    row_agreed_no = {"adjudicated": "", "judge_a": "no", "judge_b": "no"}
    assert resolve_human_label(row_agreed_no) == 0

    # 3. Disagreeing judges without adjudication -> disputed, returns None
    row_dispute = {"adjudicated": "", "judge_a": "yes", "judge_b": "no"}
    assert resolve_human_label(row_dispute) is None

    # 4. Single judge (by default rejected per B1 strict requirement)
    row_single = {"adjudicated": "", "judge_a": "yes", "judge_b": ""}
    assert resolve_human_label(row_single, allow_single_judge=False) is None
    # Allowed only with explicit pilot flag
    assert resolve_human_label(row_single, allow_single_judge=True) == 1

    # 5. Silver / AI contamination fails closed
    row_silver = {"adjudicated": "yes", "notes": "silver label from gpt-4"}
    with pytest.raises(ValueError, match="Forbidden AI/silver label"):
        resolve_human_label(row_silver)


def test_single_judge_pilot_mode_never_writes_loadable_profile(tmp_path):
    csv_file = tmp_path / "pilot.csv"
    fieldnames = [
        "question_id",
        "question_text",
        "clip_id",
        "video_id",
        "start",
        "end",
        "text",
        "judge_a",
        "judge_b",
        "adjudicated",
        "equivalent_group",
        "clip_quality",
    ]
    rows = [
        {
            "question_id": f"Q{i:03d}",
            "question_text": f"Question {i}?",
            "clip_id": f"clip_{i}",
            "video_id": "vidA",
            "start": "1.0",
            "end": "10.0",
            "text": "Teaching clip text",
            "judge_a": "yes",
            "judge_b": "",  # single judge only
            "adjudicated": "",
            "equivalent_group": "",
            "clip_quality": "clean",
        }
        for i in range(14)
    ]
    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    out_profile = tmp_path / "first_person_calibration.json"
    diag_file = tmp_path / "first_person_calibration.diagnostic.json"

    # Mock embedder and pipeline to avoid live models
    mock_embedder = MagicMock()
    mock_embedder.encode_single_full.return_value = {
        "dense": [0.1] * 1024,
        "sparse": {100: 1.0},
    }
    mock_pipeline = MagicMock()
    mock_pipeline.execute.return_value = FirstPersonPipelineResult(
        answer_text="Teaching clip text",
        citations=[
            {
                "confidence": 0.94,
                "point_id": "clip_0",
                "video_id": "vidA",
                "start_ms": 1000,
                "end_ms": 10000,
                "verbatim_text": "Teaching clip text",
            }
        ],
        status="weak_match",
        is_direct_answer=False,
        latency_ms=10.0,
    )

    # 1. Without --allow-single-judge-pilot, single-judge rows are ignored (0 valid samples)
    ret_default = run_calibration(
        csv_path=csv_file,
        collection="first_person_v1",
        output_path=out_profile,
        allow_single_judge_pilot=False,
        pipeline_instance=mock_pipeline,
        embedder_instance=mock_embedder,
    )
    assert ret_default == 1  # No evaluated samples available

    # 2. With --allow-single-judge-pilot: parses rows, but REFUSES to write a loadable profile (exit 2)
    ret_pilot = run_calibration(
        csv_path=csv_file,
        collection="first_person_v1",
        output_path=out_profile,
        diagnostic_path=diag_file,
        allow_single_judge_pilot=True,
        pipeline_instance=mock_pipeline,
        embedder_instance=mock_embedder,
    )
    assert ret_pilot == 2
    assert not out_profile.exists()  # MUST NOT WRITE loadable profile
    assert diag_file.exists()

    # Diagnostic file must NOT contain 'threshold' and must be rejected by load_calibration_profile
    diag_data = json.loads(diag_file.read_text(encoding="utf-8"))
    assert "threshold" not in diag_data
    assert diag_data["status"] == "single_judge_unadjudicated_pilot"
    assert load_calibration_profile(str(diag_file), "first_person_v1") is None


def test_score_questions_with_pipeline_passes_sparse_and_dense_to_execute():
    mock_embedder = MagicMock()
    mock_embedder.encode_single_full.return_value = {
        "dense": [0.5] * 1024,
        "sparse": {42: 0.8, 100: 0.9},
    }
    mock_pipeline = MagicMock()
    mock_pipeline.execute.return_value = FirstPersonPipelineResult(
        answer_text="Discourse text",
        citations=[
            {
                "confidence": 0.91,
                "point_id": "clip_xyz",
                "video_id": "vidX",
                "start_ms": 2000,
                "end_ms": 8000,
            }
        ],
        status="weak_match",
        is_direct_answer=False,
        latency_ms=12.0,
    )

    mock_pipeline._profile = {"threshold": 0.95}  # a previously fitted profile
    questions = [{"question_id": "Q1", "question_text": "What is awakening?"}]
    scored = score_questions_with_pipeline(
        questions=questions,
        collection="first_person_v1",
        pipeline=mock_pipeline,
        embedder=mock_embedder,
    )

    # Asserts embedder called with query text
    mock_embedder.encode_single_full.assert_called_once_with("What is awakening?")

    # Asserts pipeline.execute called with exact vectors and params
    mock_pipeline.execute.assert_called_once_with(
        query="What is awakening?",
        query_dense_vector=[0.5] * 1024,
        query_sparse_vector={"indices": [42, 100], "values": [0.8, 0.9]},
        teacher_id="both",
        max_clips=3,
    )

    # A re-fit must score the raw top clip, never through the old threshold.
    assert mock_pipeline._profile is None

    # Asserts top-1 clip confidence read from result citations
    assert len(scored) == 1
    assert scored[0]["score"] == 0.91
    assert scored[0]["top1_clip_id"] == "clip_xyz"
    assert scored[0]["top1_video_id"] == "vidX"
    assert scored[0]["top1_start"] == 2.0
    assert scored[0]["top1_end"] == 8.0


def test_evaluate_predictions_against_gold_equivalent_group():
    # Candidates with equivalence group
    candidates_by_q = {
        "Q1": [
            {
                "clip_id": "clip_orig",
                "video_id": "vid1",
                "start": 10.0,
                "end": 20.0,
                "label": 1,
                "equivalent_group": "group_peace",
            },
            {
                "clip_id": "clip_equiv",
                "video_id": "vid2",
                "start": 50.0,
                "end": 60.0,
                "label": 0,  # Unlabeled/unintended independently, but belongs to group_peace
                "equivalent_group": "group_peace",
            },
        ]
    }

    # Prediction returning the equivalent clip
    preds = [
        {
            "question_id": "Q1",
            "score": 0.88,
            "top1_clip_id": "clip_equiv",
            "top1_video_id": "vid2",
            "top1_start": 50.0,
            "top1_end": 60.0,
        }
    ]

    scores, labels = evaluate_predictions_against_gold(preds, candidates_by_q)
    assert scores == [0.88]
    assert labels == [1]  # Accepted because it matches equivalent_group


def test_run_calibration_success_with_300_samples(tmp_path):
    # 300 correct samples with high scores (0.92)
    scores_file = tmp_path / "scores.json"
    scores_data = {
        "collection": "first_person_v1",
        "score_kind": "dense_cosine",
        "scores": [{"score": 0.92, "label": 1} for _ in range(300)],
    }
    scores_file.write_text(json.dumps(scores_data), encoding="utf-8")

    dummy_csv = tmp_path / "dummy.csv"
    dummy_csv.write_text("question_id,question_text\n", encoding="utf-8")

    out_profile = tmp_path / "first_person_calibration.json"
    ret = run_calibration(
        csv_path=dummy_csv,
        collection="first_person_v1",
        output_path=out_profile,
        target_risk=0.01,
        delta=0.05,
        pipeline_scores_file=scores_file,
    )
    assert ret == 0
    assert out_profile.exists()

    profile = load_calibration_profile(str(out_profile), "first_person_v1")
    assert profile is not None
    assert profile["threshold"] == 0.92
    assert profile["score_kind"] == "dense_cosine"
    assert profile["collection"] == "first_person_v1"
    assert profile["n"] == 300
    assert profile["ucb_risk"] <= 0.01


def test_run_calibration_insufficient_samples_fails_closed(tmp_path):
    scores_file = tmp_path / "scores_14.json"
    scores_data = {
        "collection": "first_person_v1",
        "score_kind": "dense_cosine",
        "scores": [{"score": 0.95, "label": 1} for _ in range(14)],
    }
    scores_file.write_text(json.dumps(scores_data), encoding="utf-8")

    dummy_csv = tmp_path / "dummy.csv"
    dummy_csv.write_text("question_id,question_text\n", encoding="utf-8")

    out_profile = tmp_path / "first_person_calibration.json"
    diag_file = tmp_path / "first_person_calibration.diagnostic.json"

    ret = run_calibration(
        csv_path=dummy_csv,
        collection="first_person_v1",
        output_path=out_profile,
        diagnostic_path=diag_file,
        target_risk=0.01,
        delta=0.05,
        pipeline_scores_file=scores_file,
    )
    assert ret == 2
    assert not out_profile.exists()
    assert diag_file.exists()

    diag_data = json.loads(diag_file.read_text(encoding="utf-8"))
    assert "threshold" not in diag_data
    assert diag_data["status"] == "insufficient_samples"
    assert diag_data["n"] == 14
    assert load_calibration_profile(str(diag_file), "first_person_v1") is None


def test_pipeline_scores_validation_fails_on_collection_or_score_kind_mismatch(tmp_path):
    bad_col_file = tmp_path / "bad_col.json"
    bad_col_file.write_text(
        json.dumps(
            {
                "collection": "other_collection",
                "score_kind": "dense_cosine",
                "scores": [{"score": 0.9, "label": 1}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Collection mismatch"):
        load_pipeline_scores_file(bad_col_file, expected_collection="first_person_v1")

    bad_kind_file = tmp_path / "bad_kind.json"
    bad_kind_file.write_text(
        json.dumps(
            {
                "collection": "first_person_v1",
                "score_kind": "sparse_lexical",
                "scores": [{"score": 0.9, "label": 1}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="score_kind mismatch"):
        load_pipeline_scores_file(bad_kind_file, expected_collection="first_person_v1")


def test_target_risk_exceeding_product_bound_refused(tmp_path):
    dummy_csv = tmp_path / "dummy.csv"
    dummy_csv.write_text("question_id,question_text\n", encoding="utf-8")
    out_profile = tmp_path / "out.json"

    ret = run_calibration(
        csv_path=dummy_csv,
        collection="first_person_v1",
        output_path=out_profile,
        target_risk=0.05,
    )
    assert ret == 1
    assert not out_profile.exists()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))

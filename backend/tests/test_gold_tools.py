"""
Unit tests for gold evaluation tools: readiness_check, silver, and calibrator.
"""

import csv
import json
from pathlib import Path

from evaluation.gold.calibrator import SelectiveRiskCalibrator
from evaluation.gold.readiness_check import check_video_readiness, validate_gold_sheet
from evaluation.gold.silver import generate_silver_label_for_row
from services.transcript_verbatim import compute_verbatim_hash


def test_video_readiness_clean(tmp_path: Path):
    vid_dir = tmp_path / "vid123"
    vid_dir.mkdir()

    text = "The mind creates suffering through identification with thought."
    segs = [
        {"start": 0.0, "end": 10.0, "speaker": "Sri Preethaji", "text": text, "verbatim_text": text}
    ]
    h = compute_verbatim_hash(segs)

    canonical = {
        "transcript_hash": h,
        "verbatim_text": text,
        "segments": segs,
    }
    with open(vid_dir / "canonical_segments.json", "w", encoding="utf-8") as f:
        json.dump(canonical, f)

    res = check_video_readiness(vid_dir)
    assert res["ready"] is True
    assert len(res["issues"]) == 0


def test_video_readiness_detects_hash_mismatch_and_host_leak(tmp_path: Path):
    vid_dir = tmp_path / "vid123"
    vid_dir.mkdir()

    text = "Host: How do we achieve peace?"
    canonical = {
        "transcript_hash": "wrong_hash_" * 4,
        "verbatim_text": text,
        "segments": [
            {
                "start": 5.0,
                "end": 3.0,
                "speaker": "Sri Preethaji",
                "text": text,
            }  # end <= start + host leak
        ],
    }
    with open(vid_dir / "canonical_segments.json", "w", encoding="utf-8") as f:
        json.dump(canonical, f)

    res = check_video_readiness(vid_dir)
    assert res["ready"] is False
    assert any("hash mismatch" in issue.lower() for issue in res["issues"])
    assert any("end (3.0) <= start (5.0)" in issue for issue in res["issues"])
    assert any("host dialogue marker" in issue for issue in res["issues"])


def test_validate_gold_sheet_relevance(tmp_path: Path):
    csv_path = tmp_path / "relevance.csv"
    rows = [
        {
            "question_id": "Q1",
            "question_text": "What is love?",
            "clip_id": "c1",
            "video_id": "v1",
            "start": "0.0",
            "end": "10.0",
            "text": "Love is connection.",
            "judge_a": "yes",
            "judge_b": "yes",
            "adjudicated": "",
            "equivalent_group": "",
            "clip_quality": "perfect",
        }
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    res = validate_gold_sheet(csv_path, sheet_type="relevance")
    assert res["valid"] is True


def test_validate_gold_sheet_detects_max_questions_exceeded(tmp_path: Path):
    csv_path = tmp_path / "questions.csv"
    rows = [
        {
            "question_id": f"Q{i}",
            "author": "User",
            "question_text": f"Q text {i}",
            "type": "answerable",
            "intended_video_ids": "vid_overloaded",
            "notes": "",
        }
        for i in range(4)  # 4 questions on same video exceeds limit of 3
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    res = validate_gold_sheet(csv_path, sheet_type="question", max_questions_per_video=3)
    assert res["valid"] is False
    assert any("exceeds maximum allowed questions" in v for v in res["violations"])


def test_generate_silver_label():
    q = "What is the nature of suffering?"
    clip_yes = "Sri Preethaji speaks on the nature of suffering and emotional pain."
    clip_no = "Let us discuss the technique of deep abdominal breathing."

    res_yes = generate_silver_label_for_row(q, clip_yes)
    assert res_yes["silver_label"] == "yes"
    assert res_yes["status"] == "silver/unverified"

    res_no = generate_silver_label_for_row(q, clip_no)
    assert res_no["silver_label"] == "no"
    assert res_no["status"] == "silver/unverified"


def test_selective_risk_calibrator():
    # 350 predictions, top 300 are correct (1), bottom 50 are incorrect (0)
    scores = [0.9] * 300 + [0.2] * 50
    labels = [1] * 300 + [0] * 50

    calibrator = SelectiveRiskCalibrator(scores=scores, labels=labels)
    curve = calibrator.compute_precision_coverage_curve(delta=0.05)
    assert len(curve) > 0

    # With 300 correct and 0 errors, Clopper-Pearson upper bound should be <= 0.01 (1% risk)
    best_op = calibrator.find_operating_threshold(target_risk=0.01, delta=0.05)
    assert best_op is not None
    assert best_op["threshold"] == 0.9
    assert best_op["n_selected"] == 300
    assert best_op["precision"] == 1.0
    assert best_op["ucb_risk"] <= 0.01

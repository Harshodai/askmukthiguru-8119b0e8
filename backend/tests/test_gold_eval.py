"""Tests for backend/evaluation/gold/ (B1 human gold-set tooling)."""

from __future__ import annotations

from evaluation.gold.agreement import cohens_kappa, merge_adjudicated
from evaluation.gold.metrics import (
    abstention_rate,
    clopper_pearson_upper,
    coverage,
    precision_confident,
    topk_hit_rate,
    verbatim_mismatch_rate,
    wrong_speaker_rate,
)
from evaluation.gold.sheets import (
    QUESTION_COLUMNS,
    RELEVANCE_COLUMNS,
    build_question_sheet,
    build_relevance_sheet,
    pool_candidates,
)
from evaluation.gold.split import split_videos


def test_kappa_perfect_agreement():
    assert cohens_kappa(["yes"] * 10, ["yes"] * 10) == 1.0


def test_kappa_known_example():
    # Two-annotator binary set with one disagreement out of six -> po=5/6.
    a = ["yes", "no", "yes", "yes", "no", "no"]
    b = ["yes", "no", "yes", "no", "no", "no"]
    k = cohens_kappa(a, b)
    assert 0.6 < k < 1.0


def test_kappa_chance_agreement_is_zero():
    # Balanced, independent-looking labels: kappa should sit near 0, not 1.
    a = ["yes", "no", "yes", "no", "yes", "no", "yes", "no"]
    b = ["no", "yes", "no", "yes", "no", "yes", "no", "yes"]
    assert cohens_kappa(a, b) < -0.5  # perfectly anti-correlated on this pair


def test_adjudication_merge_requires_third_label_on_disagreement():
    rows = [
        {"judge_a": "yes", "judge_b": "yes"},
        {"judge_a": "yes", "judge_b": "no", "adjudicated": "no"},
    ]
    merged, summary = merge_adjudicated(rows)
    assert merged[0]["final_label"] == "yes"
    assert merged[1]["final_label"] == "no"
    assert summary["n_disagree"] == 1
    assert summary["cohens_kappa"] is not None


def test_clopper_pearson_matches_documented_sample_sizes():
    # docs/agent/first_person_research_2026-09-24.md section 8's table.
    assert clopper_pearson_upper(0, 299) <= 0.01
    assert (
        clopper_pearson_upper(0, 298) > 0.01
    )  # one fewer confident answer should not still clear it
    assert clopper_pearson_upper(2, 628) <= 0.01
    assert clopper_pearson_upper(2, 627) > 0.01


def test_clopper_pearson_monotonic_in_errors_and_n():
    assert clopper_pearson_upper(0, 500) < clopper_pearson_upper(2, 500)
    assert clopper_pearson_upper(0, 1000) < clopper_pearson_upper(0, 100)


def _synthetic_rows():
    return [
        {
            "id": "q1",
            "video_id": "v1",
            "group_id": None,
            "answerable": True,
            "confident": True,
            "top1_clip_id": "c1",
            "top1_video_id": "v1",
            "top1_start": 10.0,
            "top1_end": 20.0,
            "gold_ranges": [{"video_id": "v1", "start": 10.0, "end": 20.0}],
            "top1_speaker": "krishnaji",
            "gold_speaker": "krishnaji",
            "displayed_text": "an exact clip line",
            "gold_verbatim_text": "an exact clip line, in full",
        },
        {
            "id": "q2",
            "video_id": "v1",
            "group_id": None,
            "answerable": True,
            "confident": True,
            "top1_clip_id": "c2",
            "top1_video_id": "v1",
            "top1_start": 0.0,
            "top1_end": 5.0,
            "gold_ranges": [{"video_id": "v1", "start": 50.0, "end": 55.0}],  # wrong clip
            "top1_speaker": "host",
            "gold_speaker": "preethaji",
            "displayed_text": "fabricated line",
            "gold_verbatim_text": "a totally different line",
        },
        {
            "id": "q3",
            "video_id": "v2",
            "group_id": None,
            "answerable": True,
            "confident": False,
            "top1_clip_id": None,
            "top1_video_id": None,
            "top1_start": None,
            "top1_end": None,
            "gold_ranges": [{"video_id": "v2", "start": 0.0, "end": 5.0}],
            "top1_speaker": None,
            "gold_speaker": "preethaji",
            "displayed_text": None,
            "gold_verbatim_text": None,
        },
    ]


def test_metrics_on_synthetic_fixture():
    rows = _synthetic_rows()
    assert coverage(rows) == 2 / 3
    assert abs(abstention_rate(rows) - 1 / 3) < 1e-9
    prec = precision_confident(rows)
    assert prec["n_confident"] == 2 and prec["n_correct"] == 1  # q1 right clip, q2 wrong clip
    assert (
        wrong_speaker_rate(rows) == 0.5
    )  # q1's speaker matches, q2's doesn't, of 2 confident rows
    assert verbatim_mismatch_rate(rows) == 0.5  # q1 substring-matches, q2 doesn't
    top1 = topk_hit_rate(rows, 1)
    assert abs(top1["mean"] - 1 / 3) < 1e-3  # only q1 hits, out of 3 answerable rows


def test_split_is_deterministic_with_no_video_leakage():
    video_ids = [f"vid{i}" for i in range(300)]
    split_1 = split_videos(video_ids)
    split_2 = split_videos(video_ids)
    assert split_1 == split_2
    held = {v for v, side in split_1.items() if side == "held_out"}
    dev = {v for v, side in split_1.items() if side == "dev_pool"}
    assert held.isdisjoint(dev)
    assert held | dev == set(video_ids)
    assert 0.10 < len(held) / len(video_ids) < 0.30


def test_question_sheet_has_no_prediction_or_score_columns():
    rows = build_question_sheet([f"v{i}" for i in range(4)], n_questions=8)
    assert len(rows) == 8
    assert set(QUESTION_COLUMNS) == {
        "question_id",
        "author",
        "question_text",
        "type",
        "intended_video_ids",
        "notes",
    }
    assert not any(k in QUESTION_COLUMNS for k in ("prediction", "score", "rank", "model_answer"))
    assert all(r["question_text"] == "" for r in rows)  # never pre-filled


def test_relevance_sheet_is_blind():
    questions = [{"id": "q1", "question": "why does the mind resist stillness?"}]
    results = {
        "results": {
            "R0": {"q1": {"rank": ["c1", "c2"]}},
            "R1": {"q1": {"rank": ["c2"]}},
            "R2": {"q1": {"rank": []}},
        }
    }
    clip_meta = {
        "c1": {"video_id": "v0", "start": 0.0, "end": 1.0, "verbatim_text": "clip one"},
        "c2": {"video_id": "v0", "start": 1.0, "end": 2.0, "verbatim_text": "clip two"},
    }
    pooled = pool_candidates(questions, results, clip_meta)
    rows = build_relevance_sheet(questions, pooled)
    assert len(rows) == 2
    assert set(RELEVANCE_COLUMNS) == set(rows[0].keys())
    for forbidden in ("score", "rank", "model", "prediction"):
        assert forbidden not in RELEVANCE_COLUMNS
    assert all(
        r["judge_a"] == "" and r["adjudicated"] == "" and r["equivalent_group"] == "" for r in rows
    )


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))

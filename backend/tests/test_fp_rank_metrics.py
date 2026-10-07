"""Wave R-B eval-hardening tests (Q-rec#2/#10 + OKF R5). Pure logic + fixtures.

No Qdrant, no models, 0 LLM calls. Covers:
- fp_rank_metrics: recall@{5,10} + MRR + NDCG@10, per-class, abstention, legs
- harness score_ranked / dual_video_cover / summarize additive keys
- R5 slice datasets load under their SHA pins with the required schema
- gate-threshold replication: floors 0.12/0.0/0.0 still PASS and the
  golden25-gate.yml threshold envs are byte-untouched (additive metrics only)
"""

import json
import math
from pathlib import Path

from evaluation.first_person_harness import (
    GOLDEN_COMPARATIVE_PATH,
    GOLDEN_MULTILINGUAL_PATH,
    GOLDEN_OOC_PATH,
    dual_video_cover,
    load_questions,
    score_ranked,
    score_row,
    summarize,
)
from evaluation.fp_rank_metrics import (
    abstention_summary,
    legs_agreement_summary,
    ndcg_at_k,
    per_class_summary,
    recall_at_k,
    reciprocal_rank,
    summarize_rank_metrics,
)

RANGES = [{"video_id": "v1", "start": 10.0, "end": 30.0}]
RANGES2 = RANGES + [{"video_id": "v2", "start": 0.0, "end": 20.0}]

Q = {
    "id": "q1",
    "video_id": "v1",
    "answerable": True,
    "answer_ranges": RANGES,
}


def _cit(video="v1", start_s=12.0, end_s=28.0):
    return {
        "video_id": video,
        "start_ms": int(start_s * 1000),
        "end_ms": int(end_s * 1000),
        "speaker": "Sri Preethaji",
        "point_id": "p",
        "verbatim_text": "Suffering is resistance.",
    }


def _cand(video="v1", start=12.0, end=28.0):
    return {"video_id": video, "start": start, "end": end}


# --- pure metrics ------------------------------------------------------------


def test_recall_at_k():
    assert recall_at_k([False, True, False], 5) == 1.0
    assert recall_at_k([False] * 10, 5) == 0.0
    assert recall_at_k([False] * 10, 10) == 0.0
    assert recall_at_k([], 5) == 0.0


def test_reciprocal_rank():
    assert reciprocal_rank([True, False]) == 1.0
    assert abs(reciprocal_rank([False, False, True]) - 1 / 3) < 1e-9
    assert reciprocal_rank([False, False]) == 0.0


def test_ndcg_at_k_binary_single_ideal():
    assert ndcg_at_k([True]) == 1.0
    assert ndcg_at_k([False, True]) == round(1 / math.log2(3), 4)
    assert ndcg_at_k([False, False]) == 0.0


def test_summarize_rank_metrics_means_and_skips():
    rows = [
        {
            "answerable": True,
            "rank_metrics": {
                "recall_at_5": 1.0,
                "recall_at_10": 1.0,
                "reciprocal_rank": 1.0,
                "ndcg_at_10": 1.0,
            },
        },
        {
            "answerable": True,
            "rank_metrics": {
                "recall_at_5": 0.0,
                "recall_at_10": 1.0,
                "reciprocal_rank": 0.25,
                "ndcg_at_10": 0.5,
            },
        },
        {"answerable": True, "rank_metrics": None},  # no probe → excluded, not zero
        {"answerable": False, "rank_metrics": None},  # OOC never in rank pool
    ]
    out = summarize_rank_metrics(rows)
    assert out["n"] == 2
    assert out["n_skipped_no_probe"] == 1
    assert out["recall_at_5"] == 0.5
    assert out["recall_at_10"] == 1.0
    assert out["mrr"] == 0.625
    assert out["ndcg_at_10"] == 0.75


def test_summarize_rank_metrics_empty_is_honest_null():
    out = summarize_rank_metrics([{"answerable": True, "rank_metrics": None}])
    assert out == {
        "n": 0,
        "n_skipped_no_probe": 1,
        "recall_at_5": None,
        "recall_at_10": None,
        "mrr": None,
        "ndcg_at_10": None,
    }


# --- harness scoring ---------------------------------------------------------


def test_score_ranked_hit_and_miss():
    hit = score_ranked(Q, [_cand("v9"), _cand("v1", 12.0, 28.0)])
    assert hit["recall_at_5"] == 1.0
    assert hit["first_hit_rank"] == 2
    assert hit["reciprocal_rank"] == 0.5
    miss = score_ranked(Q, [_cand("v9"), _cand("v1", 100.0, 120.0)])
    assert miss["recall_at_5"] == 0.0
    assert miss["first_hit_rank"] is None
    assert miss["ndcg_at_10"] == 0.0


def test_score_ranked_unanswerable_is_all_miss():
    ooc = {"id": "o1", "video_id": "", "answerable": False, "answer_ranges": []}
    out = score_ranked(ooc, [_cand("v1")])
    assert out["recall_at_10"] == 0.0 and out["reciprocal_rank"] == 0.0


def test_dual_video_cover():
    q = {"gold_videos": ["v1", "v2"], "answer_ranges": RANGES2}
    both = dual_video_cover(q, [_cand("v1", 12.0, 28.0), _cand("v2", 1.0, 5.0)])
    assert both == {"n_gold_videos_covered": 2, "dual_present": True}
    one = dual_video_cover(q, [_cand("v1", 12.0, 28.0), _cand("v9")])
    assert one["dual_present"] is False


def test_summarize_additive_keys_leave_gated_keys_intact():
    rows = [
        score_row(Q, _cit()) | {"status": "weak_match", "rank_metrics": score_ranked(Q, [_cand()])},
        score_row(Q | {"id": "q2"}, None)
        | {"status": "error", "rank_metrics": score_ranked(Q, [_cand("v9")])},
    ]
    s = summarize(rows, [10.0, 20.0])
    # pre-R-B gated surface unchanged
    assert s["n_answerable"] == 2
    assert s["top1_hit"]["mean"] == 0.5
    assert s["n_errors"] == 1
    # R-B additive surface present
    assert s["rank_metrics"]["n"] == 2
    assert s["rank_metrics"]["recall_at_5"] == 0.5
    assert s["per_class"]["standard"]["n"] == 2
    assert s["per_class"]["standard"]["top1_hit_rate"] == 0.5
    assert s["abstention"]["n_answerable"] == 2
    assert s["legs"]["n_probed"] == 0


def test_per_class_and_abstention_and_legs():
    rows = [
        score_row(Q, _cit()) | {"status": "weak_match", "rank_metrics": score_ranked(Q, [_cand()])},
        score_row(
            {
                "id": "o1",
                "video_id": "",
                "answerable": False,
                "answer_ranges": [],
                "question_class": "unanswerable",
            },
            None,
        )
        | {"status": "abstained"},
        score_row(
            {
                "id": "m1",
                "video_id": "v1",
                "answerable": True,
                "answer_ranges": RANGES,
                "question_class": "multilingual",
            },
            _cit(),
        )
        | {"status": "weak_match", "legs": {"fused_dense_agree": True, "sparse_leg_active": True}},
    ]
    pc = per_class_summary(rows)
    assert set(pc) == {"standard", "unanswerable", "multilingual"}
    assert pc["unanswerable"]["abstain_rate_unanswerable"] == 1.0
    assert pc["unanswerable"]["top1_hit_rate"] is None
    ab = abstention_summary(rows)
    assert ab["n_unanswerable"] == 1
    assert ab["unanswerable_abstain_rate"] == 1.0
    assert ab["answerable_abstain_rate"] == 0.0
    legs = legs_agreement_summary(rows)
    assert legs["n_probed"] == 1
    assert legs["fused_dense_top1_agree_rate"] == 1.0
    assert legs["sparse_leg_active_rate"] == 1.0


# --- R5 slice datasets (pinned, 0 LLM) ---------------------------------------


def test_ooc_slice_loads_under_pin():
    qs = load_questions(GOLDEN_OOC_PATH)
    assert len(qs) == 8
    for q in qs:
        assert q["answerable"] is False
        assert q["answer_ranges"] == []
        assert q["question_class"] == "unanswerable"
        assert q["machine_made"] is True
        assert q["expected_non_direct"] is True
        assert q["query"] == q["question"]


def test_comparative_slice_spans_two_gold_videos():
    qs = load_questions(GOLDEN_COMPARATIVE_PATH)
    assert len(qs) == 6
    for q in qs:
        assert q["answerable"] is True
        assert q["question_class"] == "comparative"
        assert q["machine_made"] is True
        assert q["dual_present_expected"] is True
        assert len(q["gold_videos"]) == 2
        ranged_videos = {r["video_id"] for r in q["answer_ranges"]}
        assert set(q["gold_videos"]) <= ranged_videos
        for r in q["answer_ranges"]:
            assert r["start"] < r["end"]


def test_multilingual_slice_reuses_fixtures_zero_llm():
    qs = load_questions(GOLDEN_MULTILINGUAL_PATH)
    assert len(qs) == 3
    assert {q["language"] for q in qs} == {"te", "hi", "ta"}
    pri = json.loads((GOLDEN_MULTILINGUAL_PATH.parent / "priority_languages_v1.json").read_text())
    fixture_texts = {i["text"] for i in pri["items"]}
    for q in qs:
        assert q["answerable"] is True
        assert q["question_class"] == "multilingual"
        assert q["machine_made"] is True
        assert q["translation_source"] == "fixture_reuse_proxy"
        assert q["query"] in fixture_texts, "Indic query must be verbatim fixture reuse"
        assert q["retrieval_query"] and q["retrieval_query"] != q["query"]
        assert len(q["answer_ranges"]) > 0


# --- gate-threshold replication (floors untouched, additive only) -------------


def _gate_check(report: dict, top1_min: float, sv_min: float, sc_min: float):
    s = report["summary"]
    top1 = (s.get("top1_hit") or {}).get("mean")
    pcs = s.get("paraphrase_consistency") or {}
    checks = [
        top1 is not None and top1 >= top1_min,
        (pcs.get("same_video_rate") or 0) >= sv_min,
        (pcs.get("same_clip_rate") or 0) >= sc_min,
        s.get("n_errors") == 0,
    ]
    return all(checks)


def _synth_report(top1_mean: float):
    return {
        "answerability_gate": {"mode": "enabled", "llm_service": "openrouter"},
        "summary": {
            "n_questions": 25,
            "top1_hit": {"mean": top1_mean},
            "paraphrase_consistency": {"same_video_rate": 0.0, "same_clip_rate": 0.0},
            "n_errors": 0,
            "status_counts": {"weak_match": 25},
            # R-B additive keys present in the report — must not affect the verdict
            "rank_metrics": {
                "n": 25,
                "recall_at_5": 0.0,
                "recall_at_10": 0.04,
                "mrr": 0.01,
                "ndcg_at_10": 0.02,
            },
            "per_class": {"standard": {"n": 25}},
            "abstention": {"n_unanswerable": 0},
            "legs": {"n_probed": 25, "fused_dense_top1_agree_rate": 1.0},
        },
    }


def test_gate_floors_still_pass_with_new_metrics_present():
    # run1 0.12 / run2 0.16 shape (pre-ingest floors); new keys must not flip PASS
    assert _gate_check(_synth_report(0.12), 0.12, 0.0, 0.0) is True
    assert _gate_check(_synth_report(0.16), 0.12, 0.0, 0.0) is True
    # regression below floor still FAILs (gate alive)
    assert _gate_check(_synth_report(0.08), 0.12, 0.0, 0.0) is False


def test_golden25_gate_threshold_envs_untouched():
    yml = Path(__file__).resolve().parent.parent.parent / ".github/workflows/golden25-gate.yml"
    text = yml.read_text()
    assert "GOLDEN25_TOP1_MEAN_MIN: '0.12'" in text
    assert "GOLDEN25_SAME_VIDEO_MIN: '0.0'" in text
    assert "GOLDEN25_SAME_CLIP_MIN: '0.0'" in text
    # additive-metrics-only: the fail surface stays the original four checks
    enforce = text.split("Enforce measured thresholds", 1)[1]
    for gated in ("top1_hit.mean", "pcs.same_video_rate", "pcs.same_clip_rate", "n_errors"):
        assert gated in enforce


# --- probe regression (the missing-await bug class) ---------------------------


def test_probe_attaches_rank_and_legs_with_fake_store():
    import asyncio

    from evaluation.first_person_harness import _probe_rank_and_legs

    clips = [
        {"video_id": "v9", "start_ms": 0, "end_ms": 5000, "point_id": "p9", "score": 0.9},
        {"video_id": "v1", "start_ms": 12000, "end_ms": 28000, "point_id": "p1", "score": 0.8},
    ]

    class FakeStore:
        def __init__(self):
            self.calls = []

        def search_hybrid(self, query_dense_vector, query_sparse_vector=None, **kw):
            self.calls.append(query_sparse_vector)
            if len(self.calls) == 1:
                return clips  # fused probe: v9 then v1
            return [clips[0]]  # dense-only leg prefers v9

    row: dict = {}
    asyncio.run(_probe_rank_and_legs(row, Q, FakeStore(), {"dense": [0.1], "sparse": {}}, 5, True))
    assert row["rank_metrics"]["recall_at_5"] == 1.0
    assert row["rank_metrics"]["first_hit_rank"] == 2
    assert row["legs"]["fused_top1_video"] == "v9"
    assert row["legs"]["dense_top1_video"] == "v9"
    assert row["legs"]["fused_dense_agree"] is True
    assert row["legs"]["sparse_leg_active"] is False  # enc sparse empty
    assert row["legs"]["fused_scores"] == [0.9, 0.8]
    assert "probe_error" not in row


def test_probe_failure_never_fails_the_row():
    import asyncio

    from evaluation.first_person_harness import _probe_rank_and_legs

    class BadStore:
        def search_hybrid(self, *a, **k):
            raise RuntimeError("qdrant down")

    row: dict = {"id": "q1"}
    asyncio.run(_probe_rank_and_legs(row, Q, BadStore(), {"dense": [0.1]}, 5, True))
    assert "rank_metrics" not in row
    assert row["probe_error"].startswith("RuntimeError")

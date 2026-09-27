"""Pure-logic tests for the pinned first-person eval harness (no Qdrant, no model)."""

import json

import pytest

from evaluation.first_person_harness import (
    QUESTIONS_SHA256,
    HarnessError,
    load_questions,
    looks_host_like,
    mcnemar_exact,
    score_row,
    summarize,
)

Q = {"id": "q1", "video_id": "v1", "answerable": True, "answer_ranges": [{"video_id": "v1", "start": 10.0, "end": 30.0}]}


def _cit(video="v1", start_s=12.0, end_s=28.0, text="Suffering is resistance."):
    return {"video_id": video, "start_ms": int(start_s * 1000), "end_ms": int(end_s * 1000),
            "speaker": "Sri Preethaji", "point_id": "p", "verbatim_text": text}


def test_pinned_question_file_loads_and_has_fixed_denominator():
    qs = load_questions()
    assert len(qs) == 116
    assert sum(1 for q in qs if q["answerable"]) == 89


def test_changed_question_file_is_refused(tmp_path):
    p = tmp_path / "q.json"
    p.write_text(json.dumps({"questions": []}))
    with pytest.raises(HarnessError, match="refusing"):
        load_questions(p, QUESTIONS_SHA256)


def test_overlapping_clip_is_a_hit_other_video_is_a_miss():
    assert score_row(Q, _cit())["hit"] is True
    assert score_row(Q, _cit(video="v2"))["hit"] is False
    assert score_row(Q, _cit(start_s=100, end_s=120))["hit"] is False


def test_no_clip_is_a_miss_and_stays_in_the_denominator():
    rows = [score_row(Q, None) | {"status": "error"}, score_row(Q | {"id": "q2"}, _cit()) | {"status": "weak_match"}]
    s = summarize(rows, [10.0])
    assert s["n_answerable"] == 2
    assert s["top1_hit"]["mean"] == 0.5
    assert s["n_errors"] == 1


def test_host_like_heuristic():
    assert looks_host_like("So what do you mean by that?")
    assert not looks_host_like("Suffering is nothing but resistance to what is happening in your life right now.")


def test_mcnemar_exact_matches_hand_computed_binomial():
    # 5 discordant pairs, split 4 vs 1: two-sided p = 2 * (C(5,0)+C(5,1)) / 32 = 0.375
    a = [{"id": f"q{i}", "answerable": True, "hit": i == 0} for i in range(5)]
    b = [{"id": f"q{i}", "answerable": True, "hit": i != 0} for i in range(5)]
    out = mcnemar_exact(a, b)
    assert out["n_discordant"] == 5 and len(out["b_wins"]) == 4
    assert out["p_value_two_sided"] == 0.375


def test_mcnemar_refuses_different_question_sets():
    with pytest.raises(HarnessError):
        mcnemar_exact([{"id": "q1", "answerable": True, "hit": True}], [{"id": "q2", "answerable": True, "hit": True}])

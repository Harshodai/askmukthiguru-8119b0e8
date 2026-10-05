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

Q = {
    "id": "q1",
    "video_id": "v1",
    "answerable": True,
    "answer_ranges": [{"video_id": "v1", "start": 10.0, "end": 30.0}],
}


def _cit(video="v1", start_s=12.0, end_s=28.0, text="Suffering is resistance."):
    return {
        "video_id": video,
        "start_ms": int(start_s * 1000),
        "end_ms": int(end_s * 1000),
        "speaker": "Sri Preethaji",
        "point_id": "p",
        "verbatim_text": text,
    }


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
    rows = [
        score_row(Q, None) | {"status": "error"},
        score_row(Q | {"id": "q2"}, _cit()) | {"status": "weak_match"},
    ]
    s = summarize(rows, [10.0])
    assert s["n_answerable"] == 2
    assert s["top1_hit"]["mean"] == 0.5
    assert s["n_errors"] == 1


def test_host_like_heuristic():
    assert looks_host_like("So what do you mean by that?")
    assert not looks_host_like(
        "Suffering is nothing but resistance to what is happening in your life right now."
    )


def test_mcnemar_exact_matches_hand_computed_binomial():
    # 5 discordant pairs, split 4 vs 1: two-sided p = 2 * (C(5,0)+C(5,1)) / 32 = 0.375
    a = [{"id": f"q{i}", "answerable": True, "hit": i == 0} for i in range(5)]
    b = [{"id": f"q{i}", "answerable": True, "hit": i != 0} for i in range(5)]
    out = mcnemar_exact(a, b)
    assert out["n_discordant"] == 5 and len(out["b_wins"]) == 4
    assert out["p_value_two_sided"] == 0.375


def test_mcnemar_refuses_different_question_sets():
    with pytest.raises(HarnessError):
        mcnemar_exact(
            [{"id": "q1", "answerable": True, "hit": True}],
            [{"id": "q2", "answerable": True, "hit": True}],
        )


def test_paraphrase_consistency_is_none_without_groups_and_scores_with_them():
    from evaluation.first_person_harness import paraphrase_consistency

    assert paraphrase_consistency([score_row(Q, _cit())]) is None
    same = [score_row(Q | {"id": f"a{i}", "paraphrase_group": "g1"}, _cit()) for i in range(3)]
    split = [
        score_row(Q | {"id": "b1", "paraphrase_group": "g2"}, _cit()),
        score_row(
            Q | {"id": "b2", "paraphrase_group": "g2"}, _cit(video="v9") | {"point_id": "p9"}
        ),
    ]
    out = paraphrase_consistency(same + split)
    assert out == {"n_groups": 2, "same_video_rate": 0.5, "same_clip_rate": 0.5}


def test_golden_paraphrase_25_dataset_loads_and_verifies_schema():
    from evaluation.first_person_harness import (
        GOLDEN_PARAPHRASE_PATH,
        load_questions,
    )

    qs = load_questions(GOLDEN_PARAPHRASE_PATH)
    assert len(qs) == 25
    expected_themes = {
        "theme_1_suffering",
        "theme_2_competition_schooling",
        "theme_3_financial_fear",
        "theme_4_love_attachment",
        "theme_5_anger_resentment",
    }
    from collections import Counter

    groups = Counter(q["paraphrase_group"] for q in qs)
    assert set(groups.keys()) == expected_themes
    for theme, count in groups.items():
        assert count == 5, f"Theme {theme} has {count} variants, expected 5"

    for q in qs:
        assert q["answerable"] is True
        assert q["video_id"] in ("UlOt31lBhLY", "TqxxCYnAxo8", "hUmlujE6SN0", "HCs6I_BNtxo")
        assert q["query"] == q["question"]
        assert len(q["answer_ranges"]) > 0
        for r in q["answer_ranges"]:
            assert r["video_id"] == q["video_id"]
            assert r["start"] < r["end"]


def test_golden_paraphrase_25_pcs_calculation():
    from evaluation.first_person_harness import (
        GOLDEN_PARAPHRASE_PATH,
        load_questions,
        paraphrase_consistency,
        score_row,
    )

    qs = load_questions(GOLDEN_PARAPHRASE_PATH)
    assert len(qs) == 25

    # Case 1: All 5 groups retrieve consistent top-1 video and point_id
    perfect_rows = []
    for q in qs:
        cit = _cit(
            video=q["video_id"],
            start_s=q["answer_ranges"][0]["start"],
            end_s=q["answer_ranges"][0]["end"],
        )
        cit["point_id"] = f"pt_{q['paraphrase_group']}"
        perfect_rows.append(score_row(q, cit))

    pcs_perfect = paraphrase_consistency(perfect_rows)
    assert pcs_perfect is not None
    assert pcs_perfect["n_groups"] == 5
    assert pcs_perfect["same_video_rate"] == 1.0
    assert pcs_perfect["same_clip_rate"] == 1.0

    # Case 2: 3 groups consistent, 2 groups split on video
    mixed_rows = []
    for q in qs:
        group = q["paraphrase_group"]
        if group in (
            "theme_1_suffering",
            "theme_2_competition_schooling",
            "theme_3_financial_fear",
        ):
            cit = _cit(video=q["video_id"])
            cit["point_id"] = f"pt_{group}"
        elif group == "theme_4_love_attachment":
            # 4 out of 5 variants agree, 1 drifts
            vid = q["video_id"] if not q["id"].endswith("e") else "other_video"
            cit = _cit(video=vid)
            cit["point_id"] = f"pt_{group}" if vid == q["video_id"] else "other_pt"
        else:  # theme_5_anger_resentment: video agrees, point_id drifts
            cit = _cit(video=q["video_id"])
            cit["point_id"] = f"pt_{q['id']}"
        mixed_rows.append(score_row(q, cit))

    pcs_mixed = paraphrase_consistency(mixed_rows)
    assert pcs_mixed is not None
    assert pcs_mixed["n_groups"] == 5
    # theme_1, theme_2, theme_3, theme_5 have same video (4/5 = 0.8)
    assert pcs_mixed["same_video_rate"] == 0.8
    # only theme_1, theme_2, theme_3 have same clip (3/5 = 0.6)
    assert pcs_mixed["same_clip_rate"] == 0.6


def test_load_questions_pin_bypass_and_refusal(tmp_path):
    from evaluation.first_person_harness import (
        HarnessError,
        load_questions,
    )

    # Tampered golden paraphrase file without bypass is refused
    p = tmp_path / "first_person_golden_paraphrase_25.json"
    p.write_text(json.dumps({"questions": []}))
    with pytest.raises(HarnessError, match="refusing"):
        load_questions(p, pin_check=True)

    # With pin_check=False, tampered/custom file loads cleanly
    qs = load_questions(p, pin_check=False)
    assert qs == []


def test_cli_argument_parsing(monkeypatch, tmp_path):
    import evaluation.first_person_harness as harness
    from evaluation.first_person_harness import GOLDEN_PARAPHRASE_PATH, main

    captured = {}

    async def fake_run(
        collection, rerank, questions_path=None, pin_check=True, rank_depth=0, probe_legs=False
    ):
        captured["collection"] = collection
        captured["rerank"] = rerank
        captured["questions_path"] = questions_path
        captured["pin_check"] = pin_check
        captured["rank_depth"] = rank_depth
        captured["probe_legs"] = probe_legs
        return {
            "collection": collection,
            "rerank": rerank,
            "answerability_gate": {"mode": "enabled", "llm_service": "stub"},
            "summary": {},
        }

    monkeypatch.setattr(harness, "run", fake_run)

    out_file = tmp_path / "out.json"
    argv = [
        "run",
        "--collection",
        "first_person_v5",
        "--rerank",
        "--out",
        str(out_file),
        "--questions",
        str(GOLDEN_PARAPHRASE_PATH),
        "--no-pin-check",
    ]
    ret = main(argv)
    assert ret == 0
    assert captured["collection"] == "first_person_v5"
    assert captured["rerank"] is True
    assert captured["questions_path"] == GOLDEN_PARAPHRASE_PATH
    assert captured["pin_check"] is False
    assert captured["rank_depth"] == 0
    assert captured["probe_legs"] is False
    assert out_file.exists()

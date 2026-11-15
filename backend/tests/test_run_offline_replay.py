"""Unit and regression tests for offline replay validation harness (R4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops import run_offline_replay as ror


@pytest.fixture
def sample_served_row():
    return {
        "id": "q001",
        "question": "Why hasn't getting more money and success made me any happier?",
        "citations": [
            {
                "url": "https://www.youtube.com/watch?v=UlOt31lBhLY",
                "t": 101.0,
                "text": "We feel if we get more wealthier, we'll become more happier... but real fulfillment is an inner state.",
                "speaker": "Sri Krishnaji",
                "speaker_verified": True,
            }
        ],
    }


def test_clip_identity_key_hashing():
    citation = {"url": "https://www.youtube.com/watch?v=UlOt31lBhLY", "t": 101.0}
    key = ror.clip_identity_key(citation)
    assert key == "72082be68c"
    assert len(key) == 10


def test_load_served_rows_filters_citations(tmp_path: Path):
    rows_file = tmp_path / "rows.jsonl"
    rows = [
        {"id": "q1", "question": "Q1", "citations": [{"text": "Answer 1"}]},
        {"id": "q2", "question": "Q2", "citations": []},
        {"id": "q3", "question": "Q3"},
        {"id": "q4", "question": "Q4", "citations": [{"text": "Answer 4"}]},
    ]
    rows_file.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    served = ror.load_served_rows(rows_file)
    assert len(served) == 2
    assert [r["id"] for r in served] == ["q1", "q4"]


def test_load_negative_controls(tmp_path: Path):
    controls_file = tmp_path / "controls.jsonl"
    controls = [
        {
            "control_id": "neg_q001",
            "question_id": "q001",
            "question": "Q?",
            "clip_sha256_12": "abc",
        },
        {
            "control_id": "neg_q002",
            "question_id": "q002",
            "question": "Q2?",
            "clip_sha256_12": "def",
        },
    ]
    controls_file.write_text("\n".join(json.dumps(c) for c in controls) + "\n", encoding="utf-8")

    loaded = ror.load_negative_controls(controls_file)
    assert len(loaded) == 2
    assert loaded[0]["control_id"] == "neg_q001"


def test_replay_served_row_event_marker_elimination():
    promotional_row = {
        "id": "q022",
        "question": "Are the answers to why I have the family I have hidden somewhere inside me?",
        "citations": [
            {
                "url": "https://www.youtube.com/watch?v=19EEFd2ueiI",
                "t": 4.0,
                "text": "Ahead of us is Manifest family harmony. I will lead you into a deep process...",
                "speaker": "Sri Preethaji",
                "speaker_verified": True,
            }
        ],
    }
    result = ror.replay_served_row(promotional_row)
    assert not result.served_after
    assert result.verdict == "not_showable"
    assert "event_marker_gate" in result.reason
    assert "Ahead of us is" in result.reason


def test_replay_served_row_incomplete_enumeration_elimination():
    list_cutoff_row = {
        "id": "q010",
        "question": "I can never figure out what I actually want from life — why is that?",
        "citations": [
            {
                "url": "https://www.youtube.com/watch?v=sMgbjxyrgqw",
                "t": 1241.0,
                "text": "There are four levels of human seeking. First seeking is achievement... second seeking is love... third seeking is impact and giving.",
                "speaker": "Sri Preethaji",
                "speaker_verified": True,
            }
        ],
    }
    result = ror.replay_served_row(list_cutoff_row)
    assert not result.served_after
    assert result.verdict == "not_showable"
    assert "incomplete_enumeration" in result.reason


def test_replay_served_row_unconcluded_analogy_elimination():
    analogy_row = {
        "id": "q019",
        "question": "Why do people living under the same roof end up feeling like strangers?",
        "citations": [
            {
                "url": "https://www.youtube.com/watch?v=x-mTRlE0TC4",
                "t": 183.0,
                "text": "Everybody asked me this question. We live together but we don't feel together. It is like the cells in the human body...",
                "speaker": "Sri Krishnaji",
                "speaker_verified": True,
            }
        ],
    }
    result = ror.replay_served_row(analogy_row)
    assert not result.served_after
    assert result.verdict == "not_showable"
    assert "unconcluded_analogy" in result.reason


def test_replay_served_row_severed_argument_elimination():
    argument_cutoff_row = {
        "id": "q074",
        "question": "Why do people actually get sick, from a spiritual or Ayurvedic perspective?",
        "citations": [
            {
                "url": "https://www.youtube.com/watch?v=fdPQxZsPAwI",
                "t": 3.0,
                "text": "If you're not suffering you're not growing. But inner disturbance and stress leaves your body agitated.",
                "speaker": "Sri Preethaji",
                "speaker_verified": True,
            }
        ],
    }
    result = ror.replay_served_row(argument_cutoff_row)
    assert not result.served_after
    assert result.verdict == "not_showable"
    assert "severed_argument" in result.reason


def test_q070_resilient_parsing_recovery():
    q070_row = {
        "id": "q070",
        "question": "I keep trying to escape stress with entertainment or positive thinking — why doesn't that actually work long-term?",
        "citations": [
            {
                "url": "https://www.youtube.com/watch?v=HKjzpPlfvc8",
                "t": 0.0,
                "text": "To escape a Suffering State you get addicted to pleasurable fantasizing...",
                "speaker": "Sri Krishnaji",
                "speaker_verified": True,
            }
        ],
    }
    mock_grades = {
        "first": {"q070": {"verdict": "unsure", "reason": "grader_output_unparseable"}},
        "second": {"q070": {"verdict": "showable", "reason": "Direct and complete explanation"}},
    }
    result = ror.replay_served_row(q070_row, grades=mock_grades)
    assert result.served_after
    assert result.verdict == "showable"
    assert "R3 resilient parsing retry" in result.reason


def test_evaluate_hub_rule_resolution():
    # 3 rows on 72082be68c (q040 eliminated)
    passed_rows = [
        ror.RowReplayResult(
            "q001", "Q1", "url", 101.0, "72082be68c", True, True, "showable", "ok", False
        ),
        ror.RowReplayResult(
            "q026", "Q26", "url", 101.0, "72082be68c", True, True, "showable", "ok", False
        ),
        ror.RowReplayResult(
            "q042", "Q42", "url", 101.0, "72082be68c", True, True, "showable", "ok", False
        ),
        ror.RowReplayResult(
            "q002", "Q2", "url2", 63.0, "other_clip", True, True, "showable", "ok", False
        ),
    ]
    res = ror.evaluate_hub_rule(passed_rows)
    assert res["hub_clip_count_after"] == 3
    assert res["max_served_per_clip"] == 3
    assert res["pass"] is True


def test_evaluate_hub_rule_fails_if_four():
    passed_rows = [
        ror.RowReplayResult(
            "q001", "Q1", "url", 101.0, "72082be68c", True, True, "showable", "ok", False
        ),
        ror.RowReplayResult(
            "q026", "Q26", "url", 101.0, "72082be68c", True, True, "showable", "ok", False
        ),
        ror.RowReplayResult(
            "q040", "Q40", "url", 101.0, "72082be68c", True, True, "showable", "ok", False
        ),
        ror.RowReplayResult(
            "q042", "Q42", "url", 101.0, "72082be68c", True, True, "showable", "ok", False
        ),
    ]
    res = ror.evaluate_hub_rule(passed_rows)
    assert res["hub_clip_count_after"] == 4
    assert res["max_served_per_clip"] == 4
    assert res["pass"] is False


def test_replay_negative_control_abstains_on_mismatch():
    control = {
        "control_id": "neg_q001",
        "question_id": "q001",
        "question": "Why hasn't getting more money and success made me any happier?",
        "clip_sha256_12": "abc",
    }
    mismatched_clip = "We all experience challenges in our life. Pressure is always there. But suffering is something very different..."
    res = ror.replay_negative_control(control, mismatched_clip)
    assert res.verdict == "abstain"
    assert "insufficient_directness" in res.reason


def test_offline_replay_end_to_end_on_live_artifacts():
    if not ror.DEFAULT_ROWS.is_file() or not ror.DEFAULT_CONTROLS.is_file():
        pytest.skip("Attribution data artifacts not present in local test environment")

    result = ror.run_offline_replay(
        rows_path=ror.DEFAULT_ROWS,
        grades_path=ror.DEFAULT_GRADES,
        controls_path=ror.DEFAULT_CONTROLS,
    )

    assert result["status"] == "PASS"

    # 1. 40 served rows validation
    sr = result["served_rows"]
    assert sr["total"] == 40
    assert sr["passed_count"] == 31
    assert sr["eliminated_count"] == 9
    assert sr["target_flawed_eliminated"] is True
    assert sr["target_valid_preserved"] is True
    assert set(sr["eliminated_ids"]) == ror.TARGET_FLAWED_IDS
    assert set(sr["passed_ids"]) == ror.TARGET_VALID_IDS

    # 2. Hub Rule validation
    hr = result["hub_rule"]
    assert hr["pass"] is True
    assert hr["hub_clip_count_after"] == 3
    assert set(hr["hub_clip_rows_after"]) == {"q001", "q026", "q042"}
    assert hr["max_served_per_clip"] <= 3

    # 3. Negative Controls validation
    nc = result["negative_controls"]
    assert nc["total"] == 116
    assert nc["abstain_rate"] >= 0.95
    assert nc["pass"] is True


def test_cli_main_exit_code():
    if not ror.DEFAULT_ROWS.is_file() or not ror.DEFAULT_CONTROLS.is_file():
        pytest.skip("Attribution data artifacts not present in local test environment")
    exit_code = ror.main(["--strict"])
    assert exit_code == 0

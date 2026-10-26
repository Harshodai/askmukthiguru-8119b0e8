"""mine_seeker_questions pairs a real question with the teacher turn that answers it."""

import json

from scripts.ops.mine_seeker_questions import classify, is_seeker_question, main, mine


def _t(video, start, end, role, text):
    return {"video_id": video, "start_ms": start, "end_ms": end, "speaker_role": role, "text": text}


def test_host_question_is_paired_with_following_guru_turns():
    turns = [
        _t("v1", 0, 5000, "host", "Welcome everyone."),
        _t("v1", 6000, 12000, "host", "How do I stop worrying about my children all the time?"),
        _t("v1", 13000, 30000, "guru", "Worry is love that has lost its way."),
        _t("v1", 30500, 50000, "guru", "Return to the breath first."),
        _t("v1", 51000, 55000, "host", "Thank you."),
    ]
    rows = list(mine(turns))
    assert len(rows) == 1
    row = rows[0]
    assert row["question"].startswith("How do I stop worrying")
    assert row["answer_start_ms"] == 13000 and row["answer_end_ms"] == 50000
    assert "Return to the breath" in row["answer_text"]
    assert row["use"] == "test_input_only_never_served" and row["reviewed"] is False
    assert row["type_guess"] == "relationship"


def test_question_without_a_timely_teacher_answer_is_dropped():
    turns = [
        _t("v1", 0, 5000, "host", "What does it mean to live in the Beautiful State?"),
        _t("v1", 90000, 99000, "guru", "Much later the teacher speaks."),
    ]
    assert list(mine(turns)) == []


def test_teacher_questions_and_statements_are_not_mined():
    assert not is_seeker_question(_t("v", 0, 1, "guru", "Do you see how the mind works here?"))
    assert not is_seeker_question(_t("v", 0, 1, "host", "That was lovely."))
    assert not is_seeker_question(_t("v", 0, 1, "host", "Why?"))  # too short to stand alone


def test_videos_do_not_leak_into_each_other():
    turns = [
        _t("a", 0, 5000, "guest", "How can I forgive my father after all these years?"),
        _t("b", 6000, 20000, "guru", "An answer in a different video."),
    ]
    assert list(mine(turns)) == []


def test_classify_stratifies_by_keyword():
    assert classify("How do I practice Soul Sync every morning?") == "practice"
    assert classify("What is the Beautiful State?") == "concept"
    assert classify("Why is the sky blue today for everyone?") == "other"


def test_cli_writes_pairs_and_summary(tmp_path):
    turns = tmp_path / "turns.jsonl"
    rows = [
        _t("v1", 0, 6000, "guest", "I lost my mother last year, how do I carry this grief?"),
        _t("v1", 7000, 40000, "guru", "Grief is love with nowhere to go."),
    ]
    turns.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out, summary = tmp_path / "pairs.jsonl", tmp_path / "summary.json"
    assert main([str(turns), "--out", str(out), "--summary", str(summary)]) == 0
    pairs = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(pairs) == 1 and pairs[0]["type_guess"] == "grief"
    assert json.loads(summary.read_text(encoding="utf-8"))["candidates"] == 1


def test_long_first_teacher_turn_is_kept_as_the_answer():
    """A first teacher turn longer than MAX_ANSWER_MS must not drop the question."""
    from scripts.ops.mine_seeker_questions import MAX_ANSWER_MS

    turns = [
        _t("v1", 0, 5000, "host", "How do I stay present when my mind races?"),
        _t("v1", 6000, 6000 + MAX_ANSWER_MS + 30_000, "guru", "A long unbroken teaching on presence."),
        _t("v1", 6000 + MAX_ANSWER_MS + 31_000, 6000 + MAX_ANSWER_MS + 40_000, "guru", "A later turn."),
    ]
    rows = list(mine(turns))
    assert len(rows) == 1
    # The first turn is the answer; the second would grow it past the cap.
    assert "A long unbroken teaching" in rows[0]["answer_text"]
    assert "A later turn" not in rows[0]["answer_text"]


def test_short_first_turn_still_stops_before_the_cap():
    from scripts.ops.mine_seeker_questions import MAX_ANSWER_MS

    turns = [
        _t("v1", 0, 5000, "host", "How do I stay present?"),
        _t("v1", 6000, 20_000, "guru", "Start with the breath."),
        _t("v1", 21_000, 21_000 + MAX_ANSWER_MS, "guru", "Then a very long continuation."),
    ]
    rows = list(mine(turns))
    assert len(rows) == 1
    assert rows[0]["answer_text"] == "Start with the breath."

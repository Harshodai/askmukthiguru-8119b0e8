"""
Regression tests for gold-set readiness hard-failure gates and silver-label
word-boundary matching (B1 protocol). Kept separate from test_gold_tools.py
per task-assignment (that file is also being edited for the calibrator by
another worker in this session).
"""

import csv
import json
from pathlib import Path

from evaluation.gold.readiness_check import check_video_readiness, validate_gold_sheet
from evaluation.gold.silver import generate_silver_file, generate_silver_label_for_row
from services.transcript_verbatim import compute_verbatim_hash


def _write_relevance_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_forbidden_host_speaker_label_is_hard_failure(tmp_path: Path):
    """A segment whose own speaker label names the host/questioner is host
    content leaked into a teacher-only corpus — must be a hard `issue`
    (ready=False), not silently accepted."""
    vid_dir = tmp_path / "vid_host_leak"
    vid_dir.mkdir()

    text = "How do we achieve peace?"
    segs = [{"start": 0.0, "end": 5.0, "speaker": "Host", "text": text, "verbatim_text": text}]
    h = compute_verbatim_hash(segs)
    canonical = {"transcript_hash": h, "segments": segs}
    (vid_dir / "canonical_segments.json").write_text(json.dumps(canonical), encoding="utf-8")

    res = check_video_readiness(vid_dir)
    assert res["ready"] is False
    assert any("forbidden host speaker label" in issue.lower() for issue in res["issues"])


def test_clean_teacher_speaker_label_is_not_flagged(tmp_path: Path):
    """Sanity: a normal teacher-attributed segment must not trip the new
    forbidden-label check (guards against an overly broad regex/set)."""
    vid_dir = tmp_path / "vid_clean"
    vid_dir.mkdir()

    text = "The mind creates suffering through identification with thought."
    segs = [{"start": 0.0, "end": 10.0, "speaker": "Sri Preethaji", "text": text, "verbatim_text": text}]
    h = compute_verbatim_hash(segs)
    canonical = {"transcript_hash": h, "segments": segs}
    (vid_dir / "canonical_segments.json").write_text(json.dumps(canonical), encoding="utf-8")

    res = check_video_readiness(vid_dir)
    assert res["ready"] is True
    assert res["issues"] == []


def test_unadjudicated_disagreement_is_hard_failure(tmp_path: Path):
    """judge_a/judge_b disagree, adjudicated is blank -> must be a
    `violation` (readiness failure), never just a `warning` a pipeline could
    silently skip past into calibration."""
    csv_path = tmp_path / "relevance.csv"
    rows = [
        {
            "question_id": "Q1", "question_text": "What is love?", "clip_id": "c1", "video_id": "v1",
            "start": "0.0", "end": "10.0", "text": "Love is connection.",
            "judge_a": "yes", "judge_b": "no", "adjudicated": "",
            "equivalent_group": "", "clip_quality": "",
        }
    ]
    _write_relevance_csv(csv_path, rows)

    res = validate_gold_sheet(csv_path, sheet_type="relevance")
    assert res["valid"] is False
    assert any("requires adjudication" in v for v in res["violations"])


def test_adjudicated_disagreement_is_valid(tmp_path: Path):
    """Same disagreement, but adjudicated: no longer a failure of any kind."""
    csv_path = tmp_path / "relevance.csv"
    rows = [
        {
            "question_id": "Q1", "question_text": "What is love?", "clip_id": "c1", "video_id": "v1",
            "start": "0.0", "end": "10.0", "text": "Love is connection.",
            "judge_a": "yes", "judge_b": "no", "adjudicated": "yes",
            "equivalent_group": "", "clip_quality": "",
        }
    ]
    _write_relevance_csv(csv_path, rows)

    res = validate_gold_sheet(csv_path, sheet_type="relevance")
    assert res["valid"] is True
    assert res["violations"] == []


def test_silver_label_uses_word_boundary_not_substring():
    """"love" must not match inside "glove" — silver.py previously used
    plain substring `in` matching."""
    res = generate_silver_label_for_row("What is love?", "She put on a warm glove.")
    assert res["evidence"]["matched_keywords"] == []
    assert res["silver_label"] == "no"


def test_silver_label_matches_real_word_occurrence():
    res = generate_silver_label_for_row("What is love?", "Love is the deepest connection.")
    assert "love" in res["evidence"]["matched_keywords"]
    assert res["silver_label"] == "yes"


def test_silver_never_writes_judge_columns(tmp_path: Path):
    """Silver output is a strictly separate JSON file and must never carry
    judge_a/judge_b/adjudicated keys (blind protocol)."""
    relevance_rows = [
        {"question_id": "Q1", "question_text": "What is love?", "clip_id": "c1", "video_id": "v1",
         "start": "0.0", "end": "10.0", "text": "Love is the deepest connection."}
    ]
    out_path = tmp_path / "silver.json"
    results = generate_silver_file(relevance_rows, out_path)

    for row in results:
        assert "judge_a" not in row
        assert "judge_b" not in row
        assert "adjudicated" not in row

    written = json.loads(out_path.read_text())
    for row in written["silver_rows"]:
        assert "judge_a" not in row
        assert "judge_b" not in row
        assert "adjudicated" not in row
    assert written["silver_rows"][0]["status"] == "silver/unverified"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))

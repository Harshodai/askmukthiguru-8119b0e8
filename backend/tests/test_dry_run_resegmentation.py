"""Unit tests for dry_run_resegmentation.py (Milestone 3 / R6).

The engine's windows are hand-selected, so these tests assert the *computed*
properties of those windows (overlap with the transcript, the closure marker the
grammar promises, and the honest closure verdict). Measured 2026-11-15: only
q010 closes at its window; q019 and q074 do not, because their windows stop
before the application/mechanism sentence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ops.dry_run_resegmentation import (
    ANALOGY_INTRO_RE,
    ANALOGY_RESOLUTION_RE,
    DANGLING_OPENER_RE,
    ENUMERATION_INTRO_RE,
    ENUMERATION_ITEM_RE,
    PROMISSORY_SETUP_RE,
    ResegmentationResult,
    RhetoricalResegmentationEngine,
    main,
    run_dry_run,
)


def test_regex_patterns_detect_target_structures():
    # Enumeration detection
    assert ENUMERATION_INTRO_RE.search("There are four levels of human seeking") is not None
    assert ENUMERATION_ITEM_RE.search("The first aspiration is for achievement") is not None
    assert ENUMERATION_ITEM_RE.search("Then you have the fourth seeking") is not None

    # Analogy detection
    assert ANALOGY_INTRO_RE.search("The human body is a great example") is not None
    assert ANALOGY_INTRO_RE.search("For example, consider the cells") is not None
    assert ANALOGY_RESOLUTION_RE.search("In the same way, families break down") is not None

    # Promissory setup detection
    assert (
        PROMISSORY_SETUP_RE.search(
            "let us understand how these states of suffering actually causes ill health"
        )
        is not None
    )
    assert PROMISSORY_SETUP_RE.search("here is why you feel lonely") is not None

    # Dangling opener detection
    match = DANGLING_OPENER_RE.search(
        "Today I know I meet so many people and everybody asked me this question. We are not able to feel this connection"
    )
    assert match is not None


def test_window_text_keeps_the_segments_that_straddle_each_edge():
    """A window may not drop the segment it starts or ends inside (review fix)."""
    engine = RhetoricalResegmentationEngine()
    segments = [
        {"start": 0.0, "end": 5.0, "text": "before"},
        {"start": 5.0, "end": 15.0, "text": "straddles the start"},
        {"start": 15.0, "end": 25.0, "text": "inside"},
        {"start": 20.0, "end": 30.0, "text": "straddles the end"},
        {"start": 40.0, "end": 50.0, "text": "after"},
    ]
    text = engine._window_text(segments, 8.0, 22.0)
    assert "straddles the start" in text
    assert "inside" in text
    assert "straddles the end" in text
    assert "before" not in text and "after" not in text


def test_resegment_video_q010_enumeration_closure():
    engine = RhetoricalResegmentationEngine()
    res = engine.resegment_video("sMgbjxyrgqw", "q010", "The first aspiration is for achievement")

    assert isinstance(res, ResegmentationResult)
    assert res.target_row_id == "q010"
    assert res.issue_type == "incomplete_enumeration"
    assert res.chunker_version == "boundary_v2:rhetorical"
    assert res.rhetorical_end_s > res.legacy_end_s
    assert res.rhetorical_words > res.legacy_words
    assert res.used_fallback_text is False
    window = engine._window_text(
        engine.load_raw_segments("sMgbjxyrgqw"), res.rhetorical_start_s, res.rhetorical_end_s
    )
    # Closure is claimed only because the fourth item is inside the window.
    assert re.search(r"fourth\s+(?:seeking|pursuit|aspiration)", window, re.IGNORECASE)
    assert res.closure_achieved is True


def test_resegment_video_q019_analogy_window_starts_after_the_dangling_opener():
    engine = RhetoricalResegmentationEngine()
    res = engine.resegment_video("x-mTRlE0TC4", "q019", "everybody asked me this question")

    assert isinstance(res, ResegmentationResult)
    assert res.target_row_id == "q019"
    assert res.issue_type == "severed_analogy_and_dangling_opener"
    assert res.rhetorical_start_s > res.legacy_start_s  # dangling opener dropped
    window = engine._window_text(
        engine.load_raw_segments("x-mTRlE0TC4"), res.rhetorical_start_s, res.rhetorical_end_s
    )
    assert "everybody asked me this question" not in window.lower()
    # Measured 2026-11-15: the application marker ("in the same way") is NOT in
    # this window, so the analogy is still unconcluded. A future window change
    # that adds it must flip this assertion deliberately.
    assert re.search(r"\b(?:in\s+the\s+same\s+way|similarly)\b", window, re.IGNORECASE) is None
    assert res.closure_achieved is False


def test_resegment_video_q074_promissory_window_reaches_the_mechanism_only_partly():
    engine = RhetoricalResegmentationEngine()
    res = engine.resegment_video("fdPQxZsPAwI", "q074", "causes ill health within us")

    assert isinstance(res, ResegmentationResult)
    assert res.target_row_id == "q074"
    assert res.issue_type == "promissory_setup_cutoff"
    assert res.chunker_version == "boundary_v2:rhetorical"
    assert res.rhetorical_end_s > res.legacy_end_s
    assert res.rhetorical_words > res.legacy_words
    window = engine._window_text(
        engine.load_raw_segments("fdPQxZsPAwI"), res.rhetorical_start_s, res.rhetorical_end_s
    )
    assert "90 seconds" in window.lower()
    # The window stops before "immune system"/"disease", so the causal chain is
    # still unfinished at 66.59s.
    assert "immune" not in window.lower()
    assert res.closure_achieved is False


def test_a_missing_transcript_never_claims_closure(tmp_path: Path):
    """No transcript file means hand-authored text, which is not corpus evidence."""
    empty = tmp_path / "empty"
    empty.mkdir()
    engine = RhetoricalResegmentationEngine(raw_dir=empty, passages_dir=empty)
    res = engine.resegment_video("sMgbjxyrgqw", "q010", "The first aspiration is for achievement")
    assert res.used_fallback_text is True
    assert res.closure_achieved is False


def test_resegment_video_missing_match_raises():
    engine = RhetoricalResegmentationEngine()
    with pytest.raises(ValueError, match="Could not locate legacy clip"):
        engine.resegment_video("sMgbjxyrgqw", "q010", "nonexistent phrase xyz 123")


def test_run_dry_run_reports_one_closed_case_and_two_open():
    results = run_dry_run()
    assert len(results) == 3
    assert [r.closure_achieved for r in results] == [True, False, False]
    assert all(r.chunker_version == "boundary_v2:rhetorical" for r in results)


def test_main_cli_execution(tmp_path: Path, capsys):
    out_file = tmp_path / "dry_run_report.json"
    with patch("sys.argv", ["dry_run_resegmentation.py", "--output", str(out_file), "--json"]):
        exit_code = main()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert len(data) == 3
    assert data[0]["target_row_id"] == "q010"
    # Exit status follows the computed verdicts, never a hard-coded PASS.
    assert exit_code == (0 if all(r["closure_achieved"] for r in data) else 1)


def test_print_report_verdict_follows_the_computed_closures(capsys):
    def _result(closure: bool) -> ResegmentationResult:
        return ResegmentationResult(
            video_id="v",
            target_row_id="q1",
            issue_type="generic_boundary",
            legacy_clip_id="c",
            legacy_start_s=0.0,
            legacy_end_s=10.0,
            legacy_words=10,
            legacy_text_snippet="text.",
            legacy_defect="none",
            rhetorical_clip_id="c2",
            rhetorical_start_s=0.0,
            rhetorical_end_s=10.0,
            rhetorical_words=10,
            rhetorical_text_snippet="text.",
            rhetorical_resolution="unchanged",
            closure_achieved=closure,
        )

    from scripts.ops.dry_run_resegmentation import print_report

    print_report([_result(True)])
    assert "VERDICT: PASS" in capsys.readouterr().out
    print_report([_result(False)])
    assert "VERDICT: FAIL" in capsys.readouterr().out

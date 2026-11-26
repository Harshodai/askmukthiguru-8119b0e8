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
    PROMISSORY_CAUSAL_RESOLUTION_RE,
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

    # Analogy detection (hardened: genuine resolution markers only, bare 'in families' excluded)
    assert ANALOGY_INTRO_RE.search("The human body is a great example") is not None
    assert ANALOGY_INTRO_RE.search("For example, consider the cells") is not None
    assert ANALOGY_RESOLUTION_RE.search("In the same way, families break down") is not None
    assert ANALOGY_RESOLUTION_RE.search("similarly, the mind reacts") is not None
    assert ANALOGY_RESOLUTION_RE.search("when this communication breaks down") is not None
    assert ANALOGY_RESOLUTION_RE.search("so oneness is the key") is not None
    assert ANALOGY_RESOLUTION_RE.search("not happening in families in today's world") is None

    # Promissory setup detection
    assert (
        PROMISSORY_SETUP_RE.search(
            "let us understand how these states of suffering actually causes ill health"
        )
        is not None
    )
    assert PROMISSORY_SETUP_RE.search("here is why you feel lonely") is not None

    # Promissory causal resolution detection
    assert (
        PROMISSORY_CAUSAL_RESOLUTION_RE.search(
            "the entire parasympathetic nervous system is being shut off"
        )
        is not None
    )
    assert PROMISSORY_CAUSAL_RESOLUTION_RE.search("hurting your physical body") is not None
    assert PROMISSORY_CAUSAL_RESOLUTION_RE.search("destroying our health") is not None
    assert PROMISSORY_CAUSAL_RESOLUTION_RE.search("you're a person who's deceased") is not None
    assert PROMISSORY_CAUSAL_RESOLUTION_RE.search("you're a person who is diseased") is not None
    assert (
        PROMISSORY_CAUSAL_RESOLUTION_RE.search("move into states of calm, free yourself")
        is not None
    )

    # Dangling opener detection (supports optional leading whitespace)
    match = DANGLING_OPENER_RE.search(
        "Today I know I meet so many people and everybody asked me this question. We are not able to feel this connection"
    )
    assert match is not None
    match_ws = DANGLING_OPENER_RE.search(
        "   Today I know I meet so many people and everybody asked me this question. We are not able to feel this connection"
    )
    assert match_ws is not None
    match_nl = DANGLING_OPENER_RE.search(
        "\n\tToday I know I meet so many people and everybody asked me this question. Foo"
    )
    assert match_nl is not None


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
    assert engine._ends_a_sentence(window) is True
    assert window.endswith("effortlessly.")
    assert "Most people think" not in window
    assert res.closure_achieved is True


def test_resegment_video_q019_analogy_window_closure():
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
    # Analogy resolution markers (communication breaks down, so oneness is) are inside the window.
    assert ANALOGY_RESOLUTION_RE.search(window) is not None
    assert engine._ends_a_sentence(window) is True
    assert res.closure_achieved is True


def test_severed_analogy_at_284s_rejects_closure():
    """Severed analogy ending at 284.75s must NOT achieve closure (bare 'in families' excluded)."""
    engine = RhetoricalResegmentationEngine()
    raw_q019 = engine.load_raw_segments("x-mTRlE0TC4")
    txt_severed = engine._window_text(raw_q019, 202.75, 284.75)
    # Severed analogy has no genuine resolution marker
    assert ANALOGY_RESOLUTION_RE.search(txt_severed) is None
    # Even though it ends a sentence ('you are in good health.'), closure must evaluate to False
    assert engine._ends_a_sentence(txt_severed) is True
    closure_achieved = (
        bool(txt_severed)
        and bool(ANALOGY_RESOLUTION_RE.search(txt_severed))
        and not bool(DANGLING_OPENER_RE.search(txt_severed))
        and engine._ends_a_sentence(txt_severed)
    )
    assert closure_achieved is False


def test_resegment_video_q074_promissory_window_closure():
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
    # Window extends through parasympathetic shutdown, physiological harm, and calm resolution.
    assert PROMISSORY_CAUSAL_RESOLUTION_RE.search(window) is not None
    assert res.closure_achieved is True


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


def test_run_dry_run_reports_all_three_cases_closed():
    results = run_dry_run()
    assert len(results) == 3
    assert [r.closure_achieved for r in results] == [True, True, True]
    assert all(r.closure_achieved for r in results) is True
    assert all(r.chunker_version == "boundary_v2:rhetorical" for r in results)


def test_main_cli_execution(tmp_path: Path, capsys):
    out_file = tmp_path / "dry_run_report.json"
    with patch("sys.argv", ["dry_run_resegmentation.py", "--output", str(out_file), "--json"]):
        exit_code = main()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data["evaluated_cases"] == 3
    assert data["closure_achieved_count"] == 3
    assert data["verdict"] == "PASS"
    assert len(data["cases"]) == 3
    assert data["cases"][0]["target_row_id"] == "q010"
    # Exit status follows the computed verdicts, 0 when all 3 cases close.
    assert exit_code == 0
    assert all(r["closure_achieved"] for r in data["cases"])


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

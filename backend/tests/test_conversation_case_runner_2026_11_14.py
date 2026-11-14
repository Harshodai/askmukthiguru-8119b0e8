"""Pins for `scripts/ops/run_conversation_cases.py` (open-work row T-E7, 2026-11-14).

The 24 draft conversation rows had no runner, so they changed no measurement. The runner exists
now; these pins hold the parts that make its output trustworthy:

* both row shapes are executed (multi-turn `turns`, single-turn `question`);
* a draft row is never scored as a pass or a fail — the summary says so in words;
* the spend guard refuses before any network call;
* the overlap hint is arithmetic, and an uncited turn is `None`, not `0.0`.

No server is contacted: the executing path is only entered with both flags, which the refusal test
proves it never reaches.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "run_conversation_cases.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_conversation_cases", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rcc = _load()


def test_every_draft_row_is_reachable_including_single_turn_ones() -> None:
    cases = rcc.load_cases()
    assert len(cases) == 24
    kinds = {len(rcc.case_turns(c)) for c in cases}
    assert kinds == {1, 2}, kinds
    assert sum(len(rcc.case_turns(c)) for c in cases) == 30


def test_the_header_row_is_not_a_case() -> None:
    assert all(not c.get("_header") for c in rcc.load_cases())


def test_dry_run_sends_nothing_and_says_so(capsys) -> None:
    assert rcc.main(["--dry-run"]) == 0
    captured = capsys.readouterr()
    assert '"dry_run": true' in captured.out
    assert "nothing was sent" in captured.err


def test_execute_without_the_spend_guard_is_refused() -> None:
    assert rcc.main(["--execute"]) == 2


def test_overlap_hint_is_arithmetic_and_absence_is_not_zero() -> None:
    turns = [
        {"citation_videos": ["a", "b"]},
        {"citation_videos": ["b", "c"]},
        {"citation_videos": []},
    ]
    assert rcc.overlap_with_previous(turns, 1) == 0.5
    assert rcc.overlap_with_previous(turns, 2) is None
    assert rcc.overlap_with_previous(turns, 0) is None


def test_summary_never_reads_as_a_verdict() -> None:
    records = [
        {
            "turn": 1,
            "grounding": "grounded",
            "fp_served": True,
            "latency_ms": 1000,
            "citation_videos": ["a"],
        },
        {
            "turn": 2,
            "grounding": "abstained",
            "fp_served": False,
            "latency_ms": None,
            "citation_videos": [],
            "turn2_citation_overlap": None,
        },
    ]
    summary = rcc.summarize(records, {"cases": 1, "turns": 2, "categories": ["x"]})
    assert summary["row_status"] == "draft_needs_owner_review"
    assert "DRAFT" in summary["note"] and "not a pass/fail verdict" in summary["note"]
    assert summary["served_turns"] == 1
    assert summary["p95_latency_ms"] == 1000  # a missing latency is skipped, not counted as 0
    markdown = rcc.render_markdown(summary, "run-x")
    assert "draft_needs_owner_review" in markdown


def test_no_answer_or_citation_text_is_recorded() -> None:
    """The wire record keeps ids and counts. A routing measurement does not need the text."""
    case = {"id": "mt01", "category": "multi_turn_followup"}
    result = {
        "route_decision": "first_person",
        "grounding_state": "grounded",
        "route_metadata": {"fp_served": True},
        "citations": [
            {
                "video_id": "CZ_r5sYeTyY",
                "text": "teacher words",
                "url": "https://x/watch?v=CZ_r5sYeTyY",
            }
        ],
        "response": "answer text",
        "latency_ms": 12,
    }
    record = rcc.build_turn_record(case, 0, 200, result, 0.5)
    assert record["citation_videos"] == ["CZ_r5sYeTyY"]
    assert "teacher words" not in json.dumps(record)
    assert "answer text" not in json.dumps(record)

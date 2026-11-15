"""Deterministic perturbation checks for the standalone gate. No LLM calls.

Known-good clips (graded-6 served set) are broken in known ways; the gate must refuse
each broken clip. Measured 2026-11-13 before the fix: truncation refused 14 of 40, "So " prefix 0 of 40.
The "So " rule is now a general discourse-opener rule and passes. Truncation stays strict xfail: it
conflicts with a documented invariant (see the xfail reason).
"""

import json
from pathlib import Path

import pytest

from services.first_person_evidence_policy import _standalone_problem

_ROWS = Path(
    "/Users/harshodaikolluru/mukthiguru_attribution_data/graded_runs/20261112-graded-6/rows.jsonl"
)


def _good_clips():
    if not _ROWS.exists():
        return []
    rows = [
        json.loads(line) for line in _ROWS.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    texts = [
        r["citations"][0]["text"]
        for r in rows
        if r.get("citations") and r["citations"][0].get("text")
    ]
    return [t for t in texts if _standalone_problem(t) is None]


def _truncate(text: str) -> str:
    words = text.split()
    return " ".join(words[: max(12, len(words) * 2 // 3)])


def _so_prefix(text: str) -> str:
    # Resumptive "So what" class only (generic "So <any>" is valid: see test_so_opener_is_a_fine_opener).
    return "So what, " + text[0].lower() + text[1:]


GOOD = _good_clips()


@pytest.mark.skipif(not GOOD, reason="graded-6 rows not present on this machine")
@pytest.mark.xfail(
    strict=True,
    reason="CONFLICT: punctuation-free truncation is indistinguishable from a valid ASR ending; "
    "lessons/invariant: a judge-approved clip ends without punctuation. Not fixed by design (2026-11-13).",
)
def test_truncated_clips_are_refused():
    assert all(_standalone_problem(_truncate(t)) for t in GOOD)


@pytest.mark.skipif(not GOOD, reason="graded-6 rows not present on this machine")
def test_resumptive_so_prefixed_clips_are_refused():
    assert all(_standalone_problem(_so_prefix(t)) for t in GOOD)

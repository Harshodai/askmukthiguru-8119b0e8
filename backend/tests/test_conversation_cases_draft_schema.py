"""Offline schema checks for the draft conversation cases.

Structure only: no network, no LLM, no judgement of system behaviour.
The dataset is AI-authored and must never be used as calibration gold.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

DATASET = (
    Path(__file__).resolve().parents[2]
    / "evals"
    / "first_person"
    / "conversation_cases_draft.jsonl"
)

CATEGORIES = {
    "multi_turn_followup",
    "ambiguous",
    "apparent_contradiction",
    "plain_fact_preferred",
}
EXPECTED_VALUES = {
    "resolve_followup_then_serve_or_abstain",
    "treat_turn2_as_new_topic",
    "clarify_or_abstain",
    "serve_clip_or_abstain",
    "no_premise_confirmation",
    "no_teacher_clip",
}
ALLOWED_EXPECTED_BY_CATEGORY = {
    "multi_turn_followup": {
        "resolve_followup_then_serve_or_abstain",
        "treat_turn2_as_new_topic",
    },
    "ambiguous": {"clarify_or_abstain"},
    "apparent_contradiction": {"serve_clip_or_abstain", "no_premise_confirmation"},
    "plain_fact_preferred": {"no_teacher_clip"},
}
MUST_NOT_VALUES = {
    "generated_teaching_text",
    "teacher_voice_without_citation",
    "confirm_unverified_attribution",
    "merge_with_prior_turn",
    "silently_pick_one_reading",
    "discourse_clip_for_logistics",
}
REQUIRED_BY_CATEGORY = {
    "multi_turn_followup": {"turns", "turn2_must_use_history", "expected", "must_not"},
    "ambiguous": {"question", "readings", "expected", "must_not"},
    "apparent_contradiction": {"question", "premise_type", "expected", "must_not"},
    "plain_fact_preferred": {"question", "expected", "must_not"},
}
COMMON_FIELDS = {"id", "category", "expected", "status", "authored_by", "must_not"}
FORBIDDEN_KEYS = {"answer", "gold_clip", "video_id", "answer_ranges"}
QUOTED_SPAN = re.compile(r'"([^"]*)"')
MAX_QUOTED_SPAN = 40


def _load() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = [line for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    header = json.loads(lines[0])
    rows = [json.loads(line) for line in lines[1:]]
    return header, rows


def _walk(value: Any):
    """Yield every (key, string value) pair in a nested row."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, None
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, str):
        yield None, value


def test_first_line_is_draft_header_not_gold() -> None:
    header, _ = _load()
    assert header.get("_header") is True
    assert "draft_needs_owner_review" in header["note"]
    assert "NOT calibration gold" in header["note"]


def test_row_count_and_unique_ids() -> None:
    _, rows = _load()
    assert len(rows) == 24
    ids = [row["id"] for row in rows]
    assert len(set(ids)) == len(ids)


def test_six_rows_per_category() -> None:
    _, rows = _load()
    counts = Counter(row["category"] for row in rows)
    assert counts == {category: 6 for category in CATEGORIES}


def test_common_fields_status_and_closed_sets() -> None:
    _, rows = _load()
    for row in rows:
        assert COMMON_FIELDS <= set(row), row["id"]
        assert row["status"] == "draft_needs_owner_review", row["id"]
        assert row["authored_by"] == "ai", row["id"]
        assert row["category"] in CATEGORIES, row["id"]
        assert row["expected"] in EXPECTED_VALUES, row["id"]
        assert row["expected"] in ALLOWED_EXPECTED_BY_CATEGORY[row["category"]], row["id"]
        assert row["must_not"], row["id"]
        assert set(row["must_not"]) <= MUST_NOT_VALUES, row["id"]


def test_required_fields_per_category() -> None:
    _, rows = _load()
    for row in rows:
        assert REQUIRED_BY_CATEGORY[row["category"]] <= set(row), row["id"]


def test_multi_turn_rows_have_two_turns_and_consistent_history_flag() -> None:
    _, rows = _load()
    multi = [row for row in rows if row["category"] == "multi_turn_followup"]
    for row in multi:
        assert isinstance(row["turns"], list) and len(row["turns"]) == 2, row["id"]
        assert all(isinstance(t, str) and t.strip() for t in row["turns"]), row["id"]
        assert isinstance(row["turn2_must_use_history"], bool), row["id"]
        resolves = row["expected"] == "resolve_followup_then_serve_or_abstain"
        assert row["turn2_must_use_history"] is resolves, row["id"]
        assert ("merge_with_prior_turn" in row["must_not"]) is (not resolves), row["id"]
    assert sum(1 for row in multi if not row["turn2_must_use_history"]) == 2


def test_ambiguous_rows_list_at_least_two_readings() -> None:
    _, rows = _load()
    for row in rows:
        if row["category"] != "ambiguous":
            continue
        readings = row["readings"]
        assert isinstance(readings, list) and len(readings) >= 2, row["id"]
        assert all(isinstance(r, str) and r.strip() for r in readings), row["id"]
        assert "silently_pick_one_reading" in row["must_not"], row["id"]


def test_contradiction_rows_mark_unverified_premises() -> None:
    _, rows = _load()
    contradictions = [row for row in rows if row["category"] == "apparent_contradiction"]
    premise_types = Counter(row["premise_type"] for row in contradictions)
    assert set(premise_types) <= {"perceived_tension", "unverified_attribution"}
    assert premise_types["unverified_attribution"] == 2
    for row in contradictions:
        unverified = row["premise_type"] == "unverified_attribution"
        assert (row["expected"] == "no_premise_confirmation") is unverified, row["id"]
        assert ("confirm_unverified_attribution" in row["must_not"]) is unverified, row["id"]


def test_plain_fact_rows_expect_no_teacher_clip() -> None:
    _, rows = _load()
    for row in rows:
        if row["category"] == "plain_fact_preferred":
            assert row["expected"] == "no_teacher_clip", row["id"]
            assert "discourse_clip_for_logistics" in row["must_not"], row["id"]


def test_no_fabricated_attribution_fields_or_long_quotes() -> None:
    _, rows = _load()
    for row in rows:
        for key, text in _walk(row):
            if key is not None:
                assert key not in FORBIDDEN_KEYS, (row["id"], key)
            if text is not None:
                for match in QUOTED_SPAN.finditer(text):
                    assert len(match.group(1)) <= MAX_QUOTED_SPAN, (row["id"], match.group(1))

"""Schema and pairing rules for the first-person negative-control set (no LLM, no clip text)."""

import json
import re
from pathlib import Path

import pytest

_FILE = Path(__file__).resolve().parents[2] / "evals" / "first_person" / "negative_controls.jsonl"


def _controls():
    return [
        json.loads(line) for line in _FILE.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_file_exists_and_has_one_control_per_frozen_question():
    controls = _controls()
    assert len(controls) == 116
    assert len({c["question_id"] for c in controls}) == 116


def test_no_control_pairs_a_question_with_its_own_clip():
    for c in _controls():
        assert c["clip_source_question_id"] != c["question_id"], c["control_id"]


def test_every_control_expects_abstain_and_records_its_seed():
    for c in _controls():
        assert c["expected"] == "abstain"
        assert c["seed"] == 20261113


def test_clip_hashes_are_twelve_hex_chars_and_no_clip_text_is_stored():
    for c in _controls():
        assert re.fullmatch(r"[0-9a-f]{12}", c["clip_sha256_12"]), c["control_id"]
        assert set(c) == {
            "control_id",
            "question_id",
            "question",
            "clip_source_question_id",
            "clip_sha256_12",
            "expected",
            "seed",
        }


@pytest.mark.parametrize("field", ["control_id", "question", "clip_source_question_id"])
def test_fields_are_non_empty(field):
    for c in _controls():
        assert c[field], c["control_id"]

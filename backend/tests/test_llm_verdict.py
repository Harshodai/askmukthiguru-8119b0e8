"""Typed LLM verdict parsing.

Every provider used to parse verdicts with substring tests, which produced three
concrete bugs:

* ``"yes" in content.lower()`` treats "yesterday" as a yes;
* ``"faithful" in result.lower()`` accepts "not faithful" — the check was
  therefore always true;
* three copies of the CRAG line parser drifted, and a reply with no verdict
  silently kept the top document as if it had been graded.

These tests pin the contract: explicit token or JSON field, otherwise
indeterminate — never a guess, and never an implicit yes.
"""

from __future__ import annotations

import pytest

from services.llm_verdict import (
    grade_documents,
    parse_faithfulness,
    parse_numbered_verdicts,
    parse_verdict,
    strip_model_noise,
)

# ---------------------------------------------------------------------------
# Single verdict
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw", ["yes", "Yes", "YES.", "yes, because the clip names it", "true", "1"]
)
def test_affirmative_verdicts(raw):
    assert parse_verdict(raw).value is True


@pytest.mark.parametrize("raw", ["no", "No.", "false", "0", "no, the clip is off topic"])
def test_negative_verdicts(raw):
    assert parse_verdict(raw).value is False


@pytest.mark.parametrize(
    "raw",
    [
        "yesterday it rained",
        "not sure, yes maybe",
        "",
        "   ",
        None,
        "I'm currently experiencing a temporary connection issue",
    ],
)
def test_non_verdicts_are_indeterminate(raw):
    verdict = parse_verdict(raw)
    assert verdict.value is None
    assert verdict.indeterminate is True


def test_first_token_only_so_an_ambiguous_sentence_is_not_a_yes():
    assert parse_verdict("yes but also no").value is True
    assert parse_verdict("maybe yes").value is None


def test_a_leading_no_is_a_negative_verdict_even_when_hedged():
    # "no idea" / "no, off topic" are the grader saying no. Only the leading token
    # is evidence, so the hedge after it cannot turn a no into a pass.
    assert parse_verdict("no idea").value is False
    assert parse_verdict("No, I cannot tell").value is False


def test_json_verdict_in_any_wrapping_is_read():
    assert parse_verdict('{"verdict": "no"}').value is False
    assert parse_verdict('```json\n{"answerable": true}\n```').value is True
    assert parse_verdict('Sure: {"relevant": "yes"}').value is True


def test_json_without_a_verdict_field_falls_back_to_the_token():
    assert parse_verdict('{"score": 3}').value is None


# ---------------------------------------------------------------------------
# Noise stripping
# ---------------------------------------------------------------------------


def test_think_blocks_and_fences_are_stripped():
    assert strip_model_noise("<think>maybe</think>yes") == "yes"
    assert strip_model_noise("<thinking>no</thinking> no") == "no"
    assert strip_model_noise("```\nyes\n```") == "yes"
    assert parse_verdict("<think>reasoning</think>no").value is False


# ---------------------------------------------------------------------------
# Numbered CRAG verdicts
# ---------------------------------------------------------------------------


def test_numbered_verdicts_parse_the_common_formats():
    assert parse_numbered_verdicts("1: yes - on topic\n2: no - off topic") == {
        0: (True, "on topic"),
        1: (False, "off topic"),
    }
    assert parse_numbered_verdicts("1. no") == {0: (False, "Irrelevant content")}
    assert parse_numbered_verdicts("**1:** yes (good match)")[0][0] is True
    assert parse_numbered_verdicts("1 - yes (reason here)")[0][0] is True


def test_numbered_verdicts_read_a_json_array():
    parsed = parse_numbered_verdicts(
        '[{"index": 1, "relevant": true, "reason": "a"}, {"index": 2, "verdict": "no"}]'
    )
    assert parsed[0] == (True, "a")
    assert parsed[1][0] is False


def test_unparseable_numbered_reply_yields_nothing():
    assert parse_numbered_verdicts("I cannot grade these documents.") == {}
    assert parse_numbered_verdicts("") == {}


@pytest.mark.parametrize("raw", ["", "I cannot grade these documents.", "Sure thing!"])
def test_grade_documents_keeps_the_top_document_but_marks_it_indeterminate(raw):
    results = grade_documents(raw, 3)
    assert len(results) == 3
    assert results[0]["relevant"] is True
    assert results[0]["indeterminate"] is True
    assert "unparseable" in results[0]["reason"].lower()
    assert all(result["relevant"] is False for result in results[1:])


def test_grade_documents_reports_an_explicit_all_no():
    results = grade_documents("1: no - a\n2: no - b", 2)
    assert [r["relevant"] for r in results] == [False, False]
    assert all("indeterminate" not in r for r in results)


def test_grade_documents_zero_documents():
    assert grade_documents("1: yes - x", 0) == []


# ---------------------------------------------------------------------------
# Faithfulness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw", ["Faithful", "true", "The answer is fully supported by the context."]
)
def test_faithfulness_affirmative(raw):
    assert parse_faithfulness(raw) is True


@pytest.mark.parametrize(
    "raw",
    [
        "Not faithful: the second claim is unsupported",
        "unfaithful",
        "The answer is not supported by the context",
        '{"verdict": false}',
    ],
)
def test_faithfulness_negation_is_checked_before_affirmation(raw):
    assert parse_faithfulness(raw) is False


@pytest.mark.parametrize("raw", ["no idea", "", None, "I cannot evaluate this"])
def test_unparseable_faithfulness_is_not_a_pass(raw):
    assert parse_faithfulness(raw) is None

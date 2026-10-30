"""Grader logic: selection of the strong-model pass, agreement, and the PROPOSED bar label."""

from __future__ import annotations

import json

from scripts.ops.grade_served_answers import (
    agreement,
    evaluate_bar,
    grade_rows,
    parse_grade,
    select_for_second_pass,
)


def _g(verdict, harmful=False):
    return {"verdict": verdict, "harmful": harmful, "reasons": []}


def test_unparseable_reply_is_unsure_never_a_pass():
    assert parse_grade("sorry I cannot")["verdict"] == "unsure"
    assert parse_grade('{"verdict": "great"}')["verdict"] == "unsure"


def test_parse_accepts_fenced_json():
    out = parse_grade('```json\n{"verdict": "showable", "harmful": false, "reasons": ["ok"]}\n```')
    assert out["verdict"] == "showable"


def test_every_fail_and_unsure_goes_to_second_pass_plus_sample():
    first = {f"s{i}": _g("showable") for i in range(10)}
    first["f1"] = _g("not_showable")
    first["u1"] = _g("unsure")
    chosen = select_for_second_pass(first, 0.2, seed=1)
    assert {"f1", "u1"} <= set(chosen)
    assert len([c for c in chosen if c.startswith("s")]) == 2  # 20% of 10 showable


def test_sample_is_reproducible_for_a_seed():
    first = {f"s{i}": _g("showable") for i in range(30)}
    assert select_for_second_pass(first, 0.2, 7) == select_for_second_pass(first, 0.2, 7)


def test_agreement_counts_only_rows_both_graded():
    first = {"a": _g("showable"), "b": _g("showable"), "c": _g("unsure")}
    second = {"a": _g("showable"), "b": _g("not_showable")}
    out = agreement(first, second)
    assert out["compared"] == 2 and out["agree"] == 1 and out["agreement_rate"] == 0.5
    assert out["disagreements"] == [{"id": "b", "first": "showable", "second": "not_showable"}]


def test_unapproved_bar_is_labelled_proposed_even_when_met():
    final = {f"s{i}": _g("showable") for i in range(10)}
    out = evaluate_bar(final, {"approved": False, "min_showable_rate": 0.85, "max_harmful": 0})
    assert out["status"] == "PROPOSED" and out["result_if_bar_applied"] == "PASS"


def test_approved_bar_fails_on_one_harmful_answer():
    final = {f"s{i}": _g("showable") for i in range(10)}
    final["s0"] = _g("showable", harmful=True)
    out = evaluate_bar(final, {"approved": True, "min_showable_rate": 0.85, "max_harmful": 0})
    assert out["status"] == "FAIL"


def test_empty_input_never_passes():
    out = evaluate_bar({}, {"approved": True, "min_showable_rate": 0.0, "max_harmful": 0})
    assert out["status"] == "FAIL"


def test_strong_model_overrides_cheap_model_in_final():
    rows = [{"id": "x", "question": "q", "answer": "a", "citations": []}]
    first = json.dumps({"verdict": "showable", "harmful": False, "reasons": []})
    second = json.dumps({"verdict": "not_showable", "harmful": True, "reasons": ["bad"]})
    out = grade_rows(rows, lambda s, u: first, lambda s, u: second, sample_fraction=1.0)
    assert out["final"]["x"]["verdict"] == "not_showable"
    assert out["final"]["x"]["graded_by"] == "second"

"""U4 harness trust: rubric hash (H-19), per-grader showable, kappa, per-set. Synthetic data only."""

from __future__ import annotations

import hashlib

from scripts.ops.grade_served_answers import RUBRIC, grader_meta
from scripts.ops.graded_registered_report import bar_showable, cohen_kappa, grader_trust


def test_kappa_perfect_and_chance():
    a = [True, True, False, False]
    assert cohen_kappa(a, a) == 1.0
    # independent labels with identical marginals: observed agreement == chance agreement
    assert cohen_kappa([True, True, False, False], [True, False, True, False]) == 0.0
    assert cohen_kappa([], []) is None
    assert cohen_kappa([True, True], [True, True]) is None  # undefined, not 1.0


def test_known_kappa():
    # po=0.8, pa=pb=0.5 -> pe=0.5 -> kappa 0.6
    a = [True] * 5 + [False] * 5
    b = [True] * 4 + [False] + [True] + [False] * 4
    assert cohen_kappa(a, b) == 0.6


def test_grader_meta_hash():
    m = grader_meta({"first": "m1", "second": "m2"})
    assert m["rubric_sha256"] == hashlib.sha256(RUBRIC.encode()).hexdigest()
    assert (m["first_model"], m["second_model"]) == ("m1", "m2")
    assert grader_meta(None)["first_model"] is None


def _g(ids, showable):
    return {i: {"verdict": "showable" if i in showable else "not_showable"} for i in ids}


def test_trust_and_bar_unchanged():
    ids = ["q1", "q2", "q3", "q4"]
    rows = [
        {"id": i, "set": "frozen116", "citations": [{"video_id": "v", "start_ms": 0}]} for i in ids
    ]
    grades = {
        "first": _g(ids, {"q1", "q2", "q3"}),
        "second": _g(ids, {"q1", "q2"}),
        "models": {"first": "anthropic/a", "second": "google/b"},
        "grader_meta": grader_meta({"first": "anthropic/a", "second": "google/b"}),
    }
    t = grader_trust(rows, grades)
    assert t["per_grader_showable"]["first"] == {"k": 3, "n": 4}
    assert t["agreement"] == 0.75 and t["rows_graded_by_both"] == 4
    assert t["showable_by_set"]["frozen116"]["second"] == {"k": 2, "n": 4}
    assert t["held_out_set_label_present"] is False
    assert t["rubric_sha256"] == grades["grader_meta"]["rubric_sha256"]
    bar, _ = bar_showable(rows, grades)
    assert bar["status"] == "failed" and bar["k"] == 2 and bar["n"] == 4


def test_trust_missing_grades():
    assert grader_trust([], None)["status"] == "not_measured"

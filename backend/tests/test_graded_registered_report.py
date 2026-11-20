"""Registered-bar report (graded-7 criteria). Synthetic runs only; no real answer text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.graded_registered_report import evaluate, wilson_interval

FLAGS = {
    k: "x"
    for k in (
        "FIRST_PERSON_ACTIVE_COLLECTION",
        "FIRST_PERSON_CONTEXT_USE_SPARSE",
        "FIRST_PERSON_JUDGE_ENABLED",
        "FIRST_PERSON_JUDGE_MODEL",
        "FIRST_PERSON_RELEVANCE_MIN_SCORE",
        "FIRST_PERSON_RELEVANCE_MODEL",
        "FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED",
    )
}


def make_run(
    tmp_path: Path,
    *,
    n=20,
    clips=None,
    latency=3000,
    crisis_ok=True,
    ua_served=False,
    models=("anthropic/claude-sonnet-5.5", "google/gemini-3.6-flash"),
    not_showable=0,
    second_all=True,
) -> Path:
    rows = []
    for i in range(n):
        c = clips[i] if clips else i
        rows.append(
            {
                "id": f"q{i}",
                "set": "frozen116",
                "answerable": True,
                "citations": [{"url": f"u{c}", "t": c}],
                "latency_ms": latency,
                "query_class": "conceptual",
            }
        )
    for i in range(50):  # unanswerable core
        served = ua_served and i == 0
        rows.append(
            {
                "id": f"ua{i}",
                "set": "unanswerable86",
                "expected": "abstain_no_teacher_clip",
                "scoring_group": "core",
                "citations": [{"url": "z", "t": 0}] if served else [],
            }
        )
    ids = [f"q{i}" for i in range(n)]

    def v(i: str) -> dict:
        return {
            "verdict": "not_showable" if int(i[1:]) < not_showable else "showable",
            "harmful": False,
        }

    first = {i: v(i) for i in ids}
    second = {i: v(i) for i in (ids if second_all else ids[:5])}
    (tmp_path / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (tmp_path / "grades.json").write_text(
        json.dumps(
            {
                "first": first,
                "second": second,
                "models": {"first": models[0], "second": models[1]},
                "warnings": [],
            }
        )
    )
    n_core = 50
    passed = n_core - (1 if ua_served else 0)
    (tmp_path / "unanswerable.json").write_text(
        json.dumps(
            {
                "core_abstain_rate": passed / n_core,
                "core_n": n_core,
                "crisis_route": {"n": 7, "passed": 7 if crisis_ok else 6, "served_clip": 0},
                "groups": {"core": {"n": n_core, "passed": passed, "served_clip": n_core - passed}},
            }
        )
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "r",
                "sha": "s",
                "valid": True,
                "flags": FLAGS,
                "collection_fingerprint": {"points": 1},
                "spend_before": {"day": 1.0, "month": 2.0},
                "spend_after": {"day": 2.5, "month": 3.5},
            }
        )
    )
    return tmp_path


def test_wilson_matches_known_values():
    lo, hi = wilson_interval(35, 43)
    assert (round(lo, 3), round(hi, 3)) == (0.674, 0.903)
    assert wilson_interval(0, 0) is None


def test_all_bars_met(tmp_path):
    rep = evaluate(make_run(tmp_path, n=60))
    st = {k: b["status"] for k, b in rep["bars"].items()}
    assert rep["run_valid"] and rep["invalid_reasons"] == []
    assert all(s == "met" for k, s in st.items() if not k.startswith("10")), st
    assert st["10_strict_reader_answers"] == "not_measured"
    assert rep["manifest"]["spend_delta_usd"] == {"day": 1.5, "month": 1.5}


def test_lower_bound_below_bar_fails_even_with_high_point_estimate(tmp_path):
    rep = evaluate(make_run(tmp_path, n=20))  # 20/20 -> lower ~0.84
    b = rep["bars"]["1_showable_both_graders"]
    assert b["estimate"] == 1.0 and b["status"] == "failed" and b["inconclusive"] is True


def test_shared_judge_makes_joint_bar_not_measured_and_run_invalid(tmp_path):
    m = "anthropic/claude-sonnet-5.5"
    rep = evaluate(make_run(tmp_path, n=60, models=(m, m)))
    assert rep["bars"]["1_showable_both_graders"]["status"] == "not_measured"
    assert any("shared judge" in r for r in rep["invalid_reasons"]) and not rep["run_valid"]
    assert rep["bars"]["4_harmful_zero"]["status"] == "not_measured"


def test_rows_graded_by_one_family_only_are_invalid(tmp_path):
    rep = evaluate(make_run(tmp_path, n=60, second_all=False))
    assert any("one family only" in r for r in rep["invalid_reasons"])


def test_hub_clip_serving_four_questions_fails(tmp_path):
    rep = evaluate(make_run(tmp_path, n=60, clips=[0, 0, 0, 0] + list(range(1, 57))))
    hub = rep["bars"]["8_hub_rule"]
    assert hub["status"] == "failed" and hub["max_questions_per_clip"] == 4
    assert len(hub["clips_over_limit"]) == 1


def test_missing_latency_never_passes(tmp_path):
    d = make_run(tmp_path, n=60)
    rows = [json.loads(x) for x in (d / "rows.jsonl").read_text().splitlines()]
    rows[0]["latency_ms"] = None
    (d / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    lat = evaluate(d)["bars"]["3_p95_latency"]
    assert lat["status"] == "failed" and lat["missing_ids"] == ["q0"]


def test_misrouted_crisis_row_fails(tmp_path):
    assert (
        evaluate(make_run(tmp_path, n=60, crisis_ok=False))["bars"]["7_crisis_routing"]["status"]
        == "failed"
    )


def test_served_unanswerable_row_fails_bars_5_and_6(tmp_path):
    rep = evaluate(make_run(tmp_path, n=60, ua_served=True))
    assert rep["bars"]["5_unanswerable_set"]["served_clip_ids"] == ["ua0"]
    assert rep["bars"]["5_unanswerable_set"]["status"] == "failed"
    assert rep["bars"]["6_core_abstain_rate"]["status"] == "met"  # 49/50 = 0.98 >= 0.95


def test_disagreements_are_listed_by_id(tmp_path):
    d = make_run(tmp_path, n=60)
    g = json.loads((d / "grades.json").read_text())
    g["second"]["q3"]["verdict"] = "not_showable"
    (d / "grades.json").write_text(json.dumps(g))
    assert evaluate(d)["9_grader_disagreements"]["ids"] == ["q3"]


REAL = Path.home() / "mukthiguru_attribution_data/graded_runs/20261112-graded-6"


@pytest.mark.skipif(not REAL.exists(), reason="graded-6 artifacts not on this machine")
def test_real_graded_6_directory_parses():
    rep = evaluate(REAL)
    assert rep["rows"] == 202 and "8_hub_rule" in rep["bars"]


def test_unanswerable_group_with_missing_counts_is_failing_not_passing():
    """Review finding 2026-11-13: `None != None` is false, so a group whose counts were
    missing used to count as passing."""
    from scripts.ops.graded_registered_report import bar_unanswerable

    una = {"groups": {"core": {"passed": None, "n": None, "rate": None}}}
    bar = bar_unanswerable([], una)
    assert bar["status"] == "failed"
    assert bar["failing_groups"] == ["core"]


def _mark_crisis_transport_failure(run: Path, *, flag: bool) -> None:
    """Add one crisis probe that came back HTTP 429; the scorer counted it a failed crisis route."""
    row = {
        "id": "ua_crisis",
        "set": "unanswerable86",
        "expected": "crisis_support_route_no_teacher_clip",
        "scoring_group": "core",
        "http": 429,
        "citations": [],
    }
    if flag:
        row["transport_failed"] = True
    with (run / "rows.jsonl").open("a") as f:
        f.write("\n" + json.dumps(row))
    una = json.loads((run / "unanswerable.json").read_text())
    una["crisis_route"] = {"n": 7, "passed": 6, "served_clip": 0}
    una["failures"] = [{"id": "ua_crisis", "group": "core"}]
    una["groups"]["core"]["n"] += 1
    una["core_n"] += 1
    una["core_abstain_rate"] = una["groups"]["core"]["passed"] / una["groups"]["core"]["n"]
    (run / "unanswerable.json").write_text(json.dumps(una))


@pytest.mark.parametrize("flag", [True, False])  # False: a run captured before the field existed
def test_transport_failed_crisis_row_is_not_measured_not_failed(tmp_path, flag):
    run = make_run(tmp_path, n=60)
    _mark_crisis_transport_failure(run, flag=flag)
    rep = evaluate(run)
    b7 = rep["bars"]["7_crisis_routing"]
    assert b7["status"] == "not_measured" and b7["not_measured_ids"] == ["ua_crisis"]
    assert "not measured for 1 rows" in b7["reason"]
    assert rep["bars"]["5_unanswerable_set"]["status"] == "met"
    assert rep["bars"]["6_core_abstain_rate"]["status"] == "met"
    assert rep["run_valid"] is False
    assert any("ua_crisis" in r for r in rep["invalid_reasons"])
    assert rep["overall"] == "INCOMPLETE"  # never PASS for an invalid run


def test_capture_marked_invalid_run_never_reads_pass(tmp_path):
    run = make_run(tmp_path, n=60)
    m = json.loads((run / "manifest.json").read_text())
    m.update(valid=False, reasons=["1 rows failed at transport after retries: ua85"])
    (run / "manifest.json").write_text(json.dumps(m))
    rep = evaluate(run)
    assert rep["run_valid"] is False and rep["overall"] != "PASS"

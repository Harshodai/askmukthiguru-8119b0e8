"""NEW-LOAD-1 / NEW-LOAD-2: staging load harness. No network, no live system."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO / "scripts" / "ops"))

import load_run_report as R  # noqa: E402

from benchmarks import fp_staging_load as L  # noqa: E402

LOCUSTFILE = BACKEND / "benchmarks" / "locustfile_fp_staging.py"


# ---- pools and mix --------------------------------------------------------------------


def test_pools_load_from_the_eval_files_with_expected_sizes():
    pools = L.load_pools(REPO)
    assert len(pools["on_topic"]) >= 150
    assert len(pools["abstain"]) >= 60
    assert len(pools["crisis"]) == 5
    assert all(isinstance(q, str) and q for q in pools["on_topic"])


def test_s5_mix_matches_the_plan_and_sums_to_100():
    assert L.S5_MIX == {
        "on_topic_cold": 55,
        "cache_hit": 15,
        "out_of_corpus": 20,
        "greeting_off_topic": 5,
        "crisis": 1,
        "other": 4,
    }
    assert sum(L.S5_MIX.values()) == 100


def test_every_stage_has_a_tag_and_the_locustfile_parses():
    assert set(L.STAGE_TAGS) == {"s0", "s1", "s2", "s3", "s4", "s5", "s6"}
    tree = ast.parse(LOCUSTFILE.read_text())
    assert any(isinstance(n, ast.ClassDef) for n in tree.body)


# ---- response classification ----------------------------------------------------------


def test_classify_shed_needs_retry_after():
    assert L.classify(503, {"Retry-After": "7"}, "Server busy, try again shortly") == "shed"
    assert L.classify(503, {}, "boom") == "error"
    assert L.classify(500, {}, "") == "error"
    assert L.classify(429, {}, "") == "rate_limited"


def test_classify_200_bodies():
    served = {"route_decision": "first_person_bridge", "citations": [{"video_id": "v"}]}
    assert L.classify(200, {}, served) == "served"
    assert L.classify(200, {}, {"grounding_state": "abstained", "citations": []}) == "abstain"
    assert L.classify(200, {}, {"intent": "DISTRESS", "citations": []}) == "crisis"
    assert L.classify(200, {}, {"grounding_state": "safety_redirect"}) == "crisis"
    assert L.classify(200, {}, {"route_decision": "general_generated"}) == "general_generated"
    assert L.classify(200, {}, {"response": "hello"}) == "abstain"


def test_expected_outcomes_per_kind():
    assert L.violation("crisis", "served") is not None
    assert L.violation("crisis", "crisis") is None
    assert L.violation("out_of_corpus", "served") is not None
    assert L.violation("out_of_corpus", "abstain") is None
    assert L.violation("on_topic", "general_generated") is not None
    assert L.violation("on_topic", "shed") is None  # shedding is judged by the rules, not a failure


# ---- abort rules ----------------------------------------------------------------------


def test_ab6_crisis_not_crisis_aborts():
    rules = L.AbortRules()
    assert rules.observe("crisis", "served", now=0.0) == "AB-6"


def test_ab5_ooc_leak_aborts_that_stage():
    assert L.AbortRules().observe("out_of_corpus", "served", now=0.0) == "AB-5"


def test_ab3_five_percent_5xx_over_two_minutes():
    rules = L.AbortRules()
    out = None
    for i in range(100):
        out = rules.observe("on_topic", "error" if i < 10 else "served", now=float(i)) or out
    assert out == "AB-3"
    quiet = L.AbortRules()
    assert all(quiet.observe("on_topic", "served", now=float(i)) is None for i in range(100))


def test_ab1_has_no_default_cap():
    # Owner removed the default cap 2026-11-07. Without SPEND_CAP_USD nothing stops the run.
    assert L.spend_exceeded(10_000.0) is False
    assert not hasattr(L, "TEST_CAP_USD")


def test_ab1_spend_stops_at_80_percent_of_an_explicit_cap():
    assert L.spend_exceeded(19.99, cap_usd=25.0) is False
    assert L.spend_exceeded(20.0, cap_usd=25.0) is True


# ---- safety: never aim at production --------------------------------------------------


@pytest.mark.parametrize(
    "host",
    [
        "https://askmukthiguru-8119b0e8-production.up.railway.app",
        "https://example.com/production",
    ],
)
def test_production_hosts_are_refused(host):
    assert L.host_refusal(host, confirm="yes") is not None


def test_staging_needs_explicit_confirmation():
    assert L.host_refusal("https://staging.example.test", confirm="") is not None
    assert L.host_refusal("https://staging.example.test", confirm="yes") is None


# ---- metrics parsing and the report (NEW-LOAD-2) --------------------------------------

SAMPLE_BEFORE = """\
# HELP guru_answer_outcome_total x
guru_answer_outcome_total{lane="teaching",outcome="served"} 10
guru_answer_outcome_total{lane="teaching",outcome="abstained"} 4
guru_provider_reported_cost_usd_total{provider="openrouter"} 1.5
guru_openrouter_cost_unknown_total{model="m",operation="chat"} 0
guru_answer_latency_seconds_bucket{lane="teaching",outcome="served",le="1"} 2
guru_answer_latency_seconds_bucket{lane="teaching",outcome="served",le="10"} 10
guru_answer_latency_seconds_bucket{lane="teaching",outcome="served",le="+Inf"} 10
"""
SAMPLE_AFTER = """\
guru_answer_outcome_total{lane="teaching",outcome="served"} 40
guru_answer_outcome_total{lane="teaching",outcome="abstained"} 14
guru_answer_outcome_total{lane="teaching",outcome="crisis"} 1
guru_provider_reported_cost_usd_total{provider="openrouter"} 2.7
guru_openrouter_cost_unknown_total{model="m",operation="chat"} 2
guru_answer_latency_seconds_bucket{lane="teaching",outcome="served",le="1"} 12
guru_answer_latency_seconds_bucket{lane="teaching",outcome="served",le="10"} 40
guru_answer_latency_seconds_bucket{lane="teaching",outcome="served",le="+Inf"} 40
"""


def test_parse_metrics_text_reads_labels_and_values():
    rows = R.parse_metrics(SAMPLE_BEFORE)
    assert (
        "guru_answer_outcome_total",
        {"lane": "teaching", "outcome": "served"},
        10.0,
    ) in rows


def test_report_computes_deltas_cost_and_unknown_cost():
    rep = R.build_report(R.parse_metrics(SAMPLE_BEFORE), R.parse_metrics(SAMPLE_AFTER))
    assert rep["outcomes"]["served"] == 30
    assert rep["outcomes"]["abstained"] == 10
    assert rep["outcomes"]["crisis"] == 1
    assert rep["cost_usd"] == pytest.approx(1.2)
    assert rep["unknown_cost_calls"] == 2
    assert rep["cost_per_request_usd"] == pytest.approx(1.2 / 41)
    assert rep["cost_per_served_usd"] == pytest.approx(1.2 / 30)
    # 30 new served requests; 10 of them <= 1 s, all <= 10 s
    assert rep["latency_p50_upper_bound_s"] == 10.0


def test_useful_cost_needs_an_external_share():
    base = R.build_report(R.parse_metrics(SAMPLE_BEFORE), R.parse_metrics(SAMPLE_AFTER))
    assert base["cost_per_useful_usd"] is None
    with_share = R.build_report(
        R.parse_metrics(SAMPLE_BEFORE), R.parse_metrics(SAMPLE_AFTER), useful_share=0.5
    )
    assert with_share["cost_per_useful_usd"] == pytest.approx(1.2 / (30 * 0.5))


def test_markdown_table_has_no_secrets_and_names_the_unknowns():
    rep = R.build_report(R.parse_metrics(SAMPLE_BEFORE), R.parse_metrics(SAMPLE_AFTER))
    md = R.to_markdown(rep, stage="S2")
    assert "S2" in md and "unknown-cost" in md.lower()
    assert "Bearer" not in md


def test_report_script_only_reads_metrics():
    src = (REPO / "scripts" / "ops" / "load_run_report.py").read_text()
    assert ".post(" not in src and 'method="POST"' not in src
    assert "/internal/metrics" in src

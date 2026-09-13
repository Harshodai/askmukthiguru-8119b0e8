"""A3 guard: slo_latency_seconds observed at wall-time with per-tier thresholds.

Root cause: single 8s SLO mismatches measured distribution
(backend/benchmarks/reports/isolated_latency_2026-09-06.json):
fast/casual ~0.02-0.1s, warm doctrine ~1.5-2.1s, Hindi ~10s,
comparative 14-65s. Per-tier SLOs required (Google SRE multi-tier practice).
"""
import pathlib
import subprocess


def test_slo_latency_observed():
    src = pathlib.Path("app/metrics.py").read_text()
    assert "_SLO_CHAT_LATENCY" in src, "raw SLO histogram must be private to metrics.py"
    assert "slo_latency_seconds" in src
    assert "def observe_slo_latency" in src
    out = subprocess.run(
        ["grep", "-rn", "observe_slo_latency", "app", "rag", "--include=*.py"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    # At least one callsite outside metrics.py must route through the helper
    # at wall-time (so the P2 violation counter cannot be bypassed).
    lines = [ln for ln in out.stdout.splitlines() if "metrics.py" not in ln]
    assert any("observe_slo_latency(" in ln for ln in lines), "no callsite routes through observe_slo_latency"
    # The raw histogram must never be observed directly outside metrics.py.
    raw = subprocess.run(
        ["grep", "-rn", "SLO_CHAT_LATENCY", "app", "rag", "--include=*.py"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    raw_lines = [ln for ln in raw.stdout.splitlines() if "metrics.py" not in ln]
    assert not any(".observe(" in ln for ln in raw_lines), "raw SLO histogram observed outside metrics.py"


def test_slo_violation_counted_when_over_threshold():
    from app import metrics as m

    before = m.SLO_LATENCY_VIOLATIONS_TOTAL.labels(tier="fast")._value.get()
    m.observe_slo_latency("fast", m.SLO_THRESHOLDS["fast"] + 1.0)
    after = m.SLO_LATENCY_VIOLATIONS_TOTAL.labels(tier="fast")._value.get()
    assert after == before + 1, "over-threshold request must increment violation counter"


def test_slo_violation_silent_when_under_threshold():
    from app import metrics as m

    before = m.SLO_LATENCY_VIOLATIONS_TOTAL.labels(tier="standard")._value.get()
    m.observe_slo_latency("standard", 0.01)
    after = m.SLO_LATENCY_VIOLATIONS_TOTAL.labels(tier="standard")._value.get()
    assert after == before, "under-threshold request must not increment violation counter"


def test_slo_violation_unknown_tier_normalizes_to_standard():
    from app import metrics as m

    before = m.SLO_LATENCY_VIOLATIONS_TOTAL.labels(tier="standard")._value.get()
    m.observe_slo_latency("bogus-tier", m.SLO_THRESHOLDS["standard"] + 5.0)
    after = m.SLO_LATENCY_VIOLATIONS_TOTAL.labels(tier="standard")._value.get()
    assert after == before + 1, "unknown tier must normalize to standard before comparing"


def test_coordinator_path_counts_violation_when_over_threshold():
    """PipelineCoordinator routes through observe_slo_latency, so an
    over-threshold coordinator-path request increments the P2 violation
    counter (R3/S2: direct-histogram bypass closed)."""
    import pathlib

    src = pathlib.Path("app/pipeline/pipeline_coordinator.py").read_text()
    assert "observe_slo_latency(" in src, "coordinator must call observe_slo_latency"
    assert "SLO_CHAT_LATENCY" not in src, "coordinator must not touch the raw histogram"

    from app import metrics as m
    import app.pipeline.pipeline_coordinator as pc

    assert pc.observe_slo_latency is m.observe_slo_latency
    before = m.SLO_LATENCY_VIOLATIONS_TOTAL.labels(tier="fast")._value.get()
    pc.observe_slo_latency("fast", m.SLO_THRESHOLDS["fast"] + 1.0)
    after = m.SLO_LATENCY_VIOLATIONS_TOTAL.labels(tier="fast")._value.get()
    assert after == before + 1, "coordinator-path over-threshold request must increment violation counter"


def test_slo_per_tier_thresholds():
    src = pathlib.Path("app/metrics.py").read_text()
    # Per-tier thresholds derived from isolated_latency_2026-09-06.json.
    for tier in ("fast", "standard", "hindi", "comparative"):
        assert tier in src, f"tier {tier} missing from metrics.py"
    assert "SLO_THRESHOLDS" in src, "SLO_THRESHOLDS dict missing"
    slo = pathlib.Path("../docs/SLO.md").read_text()
    for tier in ("fast", "standard", "hindi", "comparative"):
        assert tier in slo.lower(), f"tier {tier} missing from docs/SLO.md"

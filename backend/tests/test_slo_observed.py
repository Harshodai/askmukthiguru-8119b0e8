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
    assert "SLO_CHAT_LATENCY" in src
    assert "slo_latency_seconds" in src
    out = subprocess.run(
        ["grep", "-rn", "SLO_CHAT_LATENCY", "app", "rag", "--include=*.py"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    # At least one callsite outside metrics.py must observe at wall-time.
    lines = [ln for ln in out.stdout.splitlines() if "metrics.py" not in ln]
    assert any(".observe(" in ln for ln in lines), "SLO_CHAT_LATENCY never observed"


def test_slo_per_tier_thresholds():
    src = pathlib.Path("app/metrics.py").read_text()
    # Per-tier thresholds derived from isolated_latency_2026-09-06.json.
    for tier in ("fast", "standard", "hindi", "comparative"):
        assert tier in src, f"tier {tier} missing from metrics.py"
    assert "SLO_THRESHOLDS" in src, "SLO_THRESHOLDS dict missing"
    slo = pathlib.Path("../docs/SLO.md").read_text()
    for tier in ("fast", "standard", "hindi", "comparative"):
        assert tier in slo.lower(), f"tier {tier} missing from docs/SLO.md"

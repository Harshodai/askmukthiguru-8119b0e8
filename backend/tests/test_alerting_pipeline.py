"""NEW-OPS-1 (OPS-001, OPS-002, OPS-003): the alert pipeline can actually fire.

Static checks on `infrastructure/prometheus/`. Three failures the audit found:

1. Rules used severities `warning` and `info`, but Alertmanager routes only
   `critical`, `page` and `warn`. The root receiver is the pager, so an unrouted
   alert paged the on-call person (or, for `info`, paged for nothing).
2. Rules read metrics that no code emits, so they evaluated against an empty
   series and could never fire (`BackupStale` fires always; the others never).
3. `prometheus.prod.yml` scraped `/api/metrics` and `/metrics`. Both answer 401
   to a static bearer token. The scrape path is `/internal/metrics`.

Nothing here runs Prometheus or Alertmanager. `promtool` and `amtool` are not
available in this environment, so these checks are static. A live
`promtool check rules` run stays an owner step (UNPROVEN until it is run).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROM_DIR = REPO_ROOT / "infrastructure" / "prometheus"
BACKEND_DIR = REPO_ROOT / "backend"

ALERTMANAGER_FILES = (
    "alertmanager.yml",
    "alertmanager.template.yml",
    "alertmanager.local.yml",
)

# Metrics the rules read that are emitted OUTSIDE the backend process. Each entry
# names the task that closes it. This set may only shrink: when the emitter
# lands, delete the entry. Never add a name to make a rule pass.
EXTERNAL_METRICS: dict[str, str] = {
    "backup_last_success_timestamp_seconds": "scripts/ops/backup_metrics.py (textfile or Pushgateway)",
    "qdrant_collection_points_count": "NEW-OPS-3 (backend scrape-time gauge)",
}

_PROMQL_WORDS = {
    "sum", "rate", "increase", "delta", "abs", "histogram_quantile", "absent",
    "time", "by", "without", "on", "ignoring", "and", "or", "unless", "le",
    "avg", "max", "min", "count", "irate", "avg_over_time", "max_over_time",
    "min_over_time", "sum_over_time", "clamp_min", "clamp_max", "bool", "offset",
    "group_left", "group_right", "vector", "scalar", "round", "ceil", "floor",
}  # fmt: skip


def _rules() -> list[dict]:
    data = yaml.safe_load((PROM_DIR / "alerting-rules.yml").read_text(encoding="utf-8"))
    return [r for g in data["groups"] for r in g.get("rules", []) if "alert" in r]


def _metric_names_in(expr: str) -> set[str]:
    """Metric names in a PromQL expression (label names and functions removed)."""
    text = re.sub(r'"[^"]*"', '""', expr)  # drop string values
    text = re.sub(r"\{[^}]*\}", "", text)  # drop label matchers
    text = re.sub(r"\[[^\]]*\]", "", text)  # drop range selectors
    text = re.sub(r"\b(by|without|on|ignoring)\s*\([^)]*\)", "", text)
    names = re.findall(r"(?<![\w.:])[a-zA-Z_:][\w:]*", text)
    return {n for n in names if n not in _PROMQL_WORDS}


def _emitted_metric_names() -> set[str]:
    """Names declared with prometheus_client in backend code (tests excluded)."""
    declared: set[str] = set()
    pattern = re.compile(r"""\b(Counter|Gauge|Histogram|Summary)\(\s*["']([A-Za-z_:][\w:]*)["']""")
    for path in BACKEND_DIR.rglob("*.py"):
        parts = set(path.relative_to(BACKEND_DIR).parts)
        if parts & {"tests", ".venv", "venv", "node_modules"}:
            continue
        for kind, name in pattern.findall(path.read_text(encoding="utf-8", errors="ignore")):
            declared.add(name)
            if kind == "Counter":
                declared.add(name if name.endswith("_total") else f"{name}_total")
            if kind == "Histogram":
                declared.update({f"{name}_bucket", f"{name}_sum", f"{name}_count"})
            if kind == "Summary":
                declared.update({f"{name}_sum", f"{name}_count"})
    return declared


def _route_severities(node: dict) -> set[str]:
    found: set[str] = set()
    for route in node.get("routes", []):
        match = route.get("match") or {}
        if "severity" in match:
            found.add(match["severity"])
        found |= _route_severities(route)
    return found


def test_every_rule_severity_has_a_route_in_every_alertmanager_file():
    severities = {r["labels"]["severity"] for r in _rules()}
    assert severities, "no rules found"
    for name in ALERTMANAGER_FILES:
        text = (PROM_DIR / name).read_text(encoding="utf-8")
        # The template and prod files hold ${VAR} placeholders; YAML keeps them as text.
        config = yaml.safe_load(text)
        routed = _route_severities(config["route"])
        missing = severities - routed
        assert not missing, (
            f"{name}: severities with no route (would hit the root pager): {missing}"
        )


def test_info_alerts_do_not_page():
    """`info` must route to Slack, never to the pager receiver."""
    for name in ("alertmanager.yml", "alertmanager.template.yml"):
        config = yaml.safe_load((PROM_DIR / name).read_text(encoding="utf-8"))
        info = [
            r for r in config["route"]["routes"] if (r.get("match") or {}).get("severity") == "info"
        ]
        assert info, f"{name}: no info route"
        assert all(r["receiver"] == "oncall-slack" for r in info), name


def test_every_metric_read_by_a_rule_is_emitted_or_explicitly_external():
    emitted = _emitted_metric_names()
    problems: list[str] = []
    for rule in _rules():
        for metric in _metric_names_in(rule["expr"]):
            if metric in emitted or metric in EXTERNAL_METRICS:
                continue
            problems.append(f"{rule['alert']}: {metric}")
    assert not problems, "rules read metrics no code emits (they could never fire):\n" + "\n".join(
        problems
    )


def test_external_metric_allowlist_only_holds_metrics_a_rule_still_reads():
    """Ratchet: an entry with no reader, or one the backend now emits, is stale."""
    read: set[str] = set()
    for rule in _rules():
        read |= _metric_names_in(rule["expr"])
    emitted = _emitted_metric_names()
    stale = {m for m in EXTERNAL_METRICS if m not in read or m in emitted}
    assert not stale, f"remove from EXTERNAL_METRICS: {sorted(stale)}"


def test_relevance_indeterminate_alert_reads_the_real_counter():
    rule = next(r for r in _rules() if r["alert"] == "FirstPersonRelevanceIndeterminateSpike")
    assert "fp_relevance_scorer_total" not in rule["expr"]
    assert "first_person_requests_total" in rule["expr"]
    assert 'reason="relevance_indeterminate"' in rule["expr"]


def test_integrity_breach_pages():
    rule = next(r for r in _rules() if r["alert"] == "FirstPersonIntegrityBreach")
    assert "guru_integrity_breach_total" in rule["expr"]
    assert "increase(" in rule["expr"]
    assert rule["labels"]["severity"] == "page"
    assert rule["annotations"]["runbook"].startswith("docs/runbooks/ALERTING.md#")


@pytest.mark.parametrize("name", ["prometheus.prod.yml", "prometheus.yml"])
def test_every_scrape_job_uses_the_internal_metrics_path(name):
    config = yaml.safe_load((PROM_DIR / name).read_text(encoding="utf-8"))
    jobs = config["scrape_configs"]
    assert jobs, name
    for job in jobs:
        assert job.get("metrics_path") == "/internal/metrics", (name, job["job_name"])
        assert job.get("authorization", {}).get("type") == "Bearer", (name, job["job_name"])


def test_prod_scrape_token_is_the_backend_scrape_token():
    text = (PROM_DIR / "prometheus.prod.yml").read_text(encoding="utf-8")
    assert "${METRICS_SCRAPE_TOKEN}" in text
    assert "PROMETHEUS_BEARER_TOKEN" not in text

"""NEW-OPS-9 (OPS-004): an alert that fires must lead to a page that exists.

Static checks on `infrastructure/prometheus/alerting-rules.yml` and
`docs/runbooks/`. They prove the links resolve. They do not prove the steps in a
runbook work: that needs a drill (UNPROVEN until one is run and logged).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOKS = REPO_ROOT / "docs" / "runbooks"
RULES = REPO_ROOT / "infrastructure" / "prometheus" / "alerting-rules.yml"


def _rules() -> list[dict]:
    data = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return [r for g in data["groups"] for r in g.get("rules", []) if "alert" in r]


def _anchors(path: Path) -> set[str]:
    return {a.lower() for a in re.findall(r'<a name="([^"]+)"', path.read_text(encoding="utf-8"))}


def test_every_alert_runbook_link_resolves_to_an_anchor():
    anchors = _anchors(RUNBOOKS / "ALERTING.md")
    broken = []
    for rule in _rules():
        link = rule["annotations"].get("runbook", "")
        match = re.fullmatch(r"docs/runbooks/ALERTING\.md#([a-z0-9_-]+)", link)
        if not match or match.group(1) not in anchors:
            broken.append((rule["alert"], link))
    assert not broken, f"alerts whose runbook link does not resolve: {broken}"


def test_inventory_table_lists_every_alert():
    text = (RUNBOOKS / "ALERTING.md").read_text(encoding="utf-8")
    table = text.split("## Alert inventory", 1)[1].split("\n## ", 1)[0]
    missing = [r["alert"] for r in _rules() if f"`{r['alert']}`" not in table]
    assert not missing, f"alerts missing from the inventory table: {missing}"


def test_inventory_severity_matches_the_rule():
    text = (RUNBOOKS / "ALERTING.md").read_text(encoding="utf-8")
    for rule in _rules():
        row = next(ln for ln in text.splitlines() if f"| `{rule['alert']}` |" in ln)
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells[1] == rule["labels"]["severity"], (rule["alert"], cells[1])


def test_incident_response_runbooks_rb1_to_rb10_have_anchors():
    path = RUNBOOKS / "INCIDENT_RUNBOOKS.md"
    anchors = _anchors(path)
    for n in range(1, 11):
        assert f"rb-{n}" in anchors, f"RB-{n} anchor missing"


def test_rb_alert_names_are_real_or_marked_planned():
    """A runbook must not name an alert that does not exist as if it did."""
    real = {r["alert"] for r in _rules()}
    text = (RUNBOOKS / "INCIDENT_RUNBOOKS.md").read_text(encoding="utf-8")
    code_like = {  # classes and services named in the text, not alerts
        "AnonQuotaRedisAdapter", "CircuitBreakerStage", "FirstPersonPipeline",
    }  # fmt: skip
    problems = []
    for match in re.finditer(r"`([A-Z][A-Za-z0-9]{11,})`", text):
        name = match.group(1)
        if name in real or name in code_like or sum(c.isupper() for c in name) < 3:
            continue
        if "(planned)" not in text[match.end() : match.end() + 14]:
            problems.append(name)
    assert not problems, f"names that are not defined alerts and not marked (planned): {problems}"


def test_incident_log_exists_and_forbids_seeker_text():
    text = (RUNBOOKS / "INCIDENT_LOG.md").read_text(encoding="utf-8")
    assert "seeker text" in text.lower()
    assert "append" in text.lower()


def test_oncall_and_alerting_point_at_the_scrape_path_not_api_metrics():
    for name in ("ONCALL.md", "ALERTING.md", "SECRET_ROTATION.md"):
        text = (RUNBOOKS / name).read_text(encoding="utf-8")
        assert "GET /api/metrics" not in text, name
    assert "/internal/metrics" in (RUNBOOKS / "ONCALL.md").read_text(encoding="utf-8")

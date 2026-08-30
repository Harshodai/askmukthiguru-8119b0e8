import pytest
from fastapi import FastAPI

from app import observability
from app.tracing import trace_rag_node


def test_observability_respects_disabled_env(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "false")
    monkeypatch.setattr(observability, "_INITIALIZED", False)

    assert observability.init_observability(FastAPI()) is False


def test_observability_is_idempotent(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setattr(observability, "_INITIALIZED", True)

    assert observability.init_observability(FastAPI()) is True


class _BoomError(ValueError):
    """Distinct exception type, message deliberately contains 'span'."""


def test_trace_rag_node_propagates_original_exception_once():
    """Regression for #13/#14: a real exception must propagate as its exact
    type/message, and the wrapped function must run exactly once even when
    the exception message contains the literal word 'span'."""
    call_count = 0

    @trace_rag_node("boom_node")
    async def boom(state):
        nonlocal call_count
        call_count += 1
        raise _BoomError("this span setup blew up")

    with pytest.raises(_BoomError, match="this span setup blew up"):
        import asyncio

        asyncio.run(boom({}))

    assert call_count == 1


def test_alertmanager_config_validity():
    """Verify infrastructure/prometheus/alertmanager.yml syntax and required receivers."""
    import pathlib
    import yaml

    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    alertmanager_path = repo_root / "infrastructure" / "prometheus" / "alertmanager.yml"
    assert alertmanager_path.exists(), f"Missing alertmanager config at {alertmanager_path}"

    content = alertmanager_path.read_text(encoding="utf-8")
    config = yaml.safe_load(content)

    assert "route" in config
    assert "receivers" in config
    assert "inhibit_rules" in config

    receiver_names = {r["name"] for r in config["receivers"]}
    assert "oncall-pager" in receiver_names
    assert "oncall-slack" in receiver_names

    pager_receiver = next(r for r in config["receivers"] if r["name"] == "oncall-pager")
    assert "pagerduty_configs" in pager_receiver
    assert "slack_configs" in pager_receiver
    assert "webhook_configs" in pager_receiver

    slack_receiver = next(r for r in config["receivers"] if r["name"] == "oncall-slack")
    assert "slack_configs" in slack_receiver


def test_prometheus_prod_config_validity():
    """Verify infrastructure/prometheus/prometheus.prod.yml syntax, Bearer auth, and remote_write."""
    import pathlib
    import yaml

    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    prom_prod_path = repo_root / "infrastructure" / "prometheus" / "prometheus.prod.yml"
    assert prom_prod_path.exists(), f"Missing prometheus.prod.yml at {prom_prod_path}"

    content = prom_prod_path.read_text(encoding="utf-8")
    config = yaml.safe_load(content)

    assert "global" in config
    assert "scrape_configs" in config
    assert "remote_write" in config
    assert "rule_files" in config
    assert "alerting-rules.yml" in config["rule_files"]

    scrape_jobs = {job["job_name"]: job for job in config["scrape_configs"]}
    assert "askmukthiguru-backend-prod-api" in scrape_jobs
    assert "askmukthiguru-backend-prod-system" in scrape_jobs

    api_job = scrape_jobs["askmukthiguru-backend-prod-api"]
    assert api_job.get("metrics_path") == "/api/metrics"
    assert api_job.get("scheme") == "https"
    assert api_job.get("authorization", {}).get("type") == "Bearer"
    assert "${PROMETHEUS_BEARER_TOKEN}" in api_job.get("authorization", {}).get("credentials", "")

    # Validate remote write for Grafana Cloud
    assert len(config["remote_write"]) > 0
    rw = config["remote_write"][0]
    assert "${GRAFANA_CLOUD_PROMETHEUS_URL}" in rw["url"]
    assert "${GRAFANA_CLOUD_INSTANCE_ID}" in rw.get("basic_auth", {}).get("username", "")


def test_hallucination_anomaly_workflow_validity():
    """Verify .github/workflows/hallucination-anomaly.yml syntax and structure."""
    import pathlib
    import yaml

    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    workflow_path = repo_root / ".github" / "workflows" / "hallucination-anomaly.yml"
    assert workflow_path.exists(), f"Missing workflow at {workflow_path}"

    content = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(content)

    assert "name" in workflow
    # Test cron schedule
    triggers = workflow.get(True if True in workflow else "on") or workflow.get("on")
    assert "schedule" in triggers
    schedules = [s.get("cron") for s in triggers["schedule"]]
    assert "0 4 * * *" in schedules

    # Verify steps
    job = workflow["jobs"]["anomaly-detection"]
    step_names = [s.get("name", "") for s in job["steps"]]
    assert any("Hallucination Anomaly Check" in name for name in step_names)
    assert any("Job Summary" in name for name in step_names)
    assert any("Alert on Threshold Breach" in name for name in step_names)


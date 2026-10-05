import os

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


def test_alertmanager_local_config_is_startable():
    """The config compose actually mounts must not need secrets to load.

    AMK-F-001: compose used to mount `alertmanager.yml`, the production artifact,
    which still contains `${PD_SERVICE_KEY}` / `${SLACK_WEBHOOK_URL}` until
    envsubst renders it. Alertmanager validates receiver URLs when it loads its
    config, so that mount could never have started the container. The service was
    also profile-gated and never launched, so it went unnoticed for as long as it
    existed. This pins the file compose mounts, not the one prod renders.
    """
    import pathlib

    import yaml

    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    local_path = repo_root / "infrastructure" / "prometheus" / "alertmanager.local.yml"
    assert local_path.exists(), f"Missing local alertmanager config at {local_path}"

    raw = local_path.read_text(encoding="utf-8")
    body = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("#"))
    assert "${" not in body, (
        "the mounted alertmanager config contains an unrendered placeholder; "
        "Alertmanager will refuse to start"
    )

    config = yaml.safe_load(raw)
    assert "route" in config and "receivers" in config and "inhibit_rules" in config
    receiver_names = {r["name"] for r in config["receivers"]}
    assert config["route"]["receiver"] in receiver_names
    for route in config["route"].get("routes", []):
        assert route["receiver"] in receiver_names, f"route points at unknown receiver: {route}"


def test_compose_mounts_the_startable_alertmanager_config():
    """Guard the wiring itself, not just the file's contents."""
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    compose = (repo_root / "backend" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "alertmanager.local.yml:/etc/alertmanager/alertmanager.yml" in compose, (
        "compose must mount the secret-free local config, not the prod artifact"
    )


def test_first_person_alerting_rules_valid():
    """First-person verbatim route (N6) must alert on: any quarantine (an
    integrity-gate failure means corrupt data reached serving), p95 latency
    breach, and an elevated error rate. See root CLAUDE.md's SPOF/Redis
    Degradation invariant -- these three are the route's only production
    signals besides the request-count-by-status metric itself."""
    import pathlib

    import yaml

    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    rules_path = repo_root / "infrastructure" / "prometheus" / "alerting-rules.yml"
    assert rules_path.exists(), f"Missing alerting rules at {rules_path}"

    config = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    all_rules = [rule for group in config["groups"] for rule in group["rules"]]
    rules_by_name = {rule["alert"]: rule for rule in all_rules if "alert" in rule}

    quarantine = rules_by_name["FirstPersonQuarantineDetected"]
    assert "first_person_quarantined_total" in quarantine["expr"]
    assert quarantine["labels"]["severity"] == "warning"

    latency = rules_by_name["FirstPersonLatencySLOBreach"]
    assert "first_person_latency_seconds" in latency["expr"]
    assert latency["labels"]["severity"] == "warning"
    assert latency["for"] == "10m"

    error_rate = rules_by_name["FirstPersonErrorRateHigh"]
    assert "first_person_requests_total" in error_rate["expr"]
    assert 'status="error"' in error_rate["expr"]
    assert error_rate["labels"]["severity"] == "critical"
    assert error_rate["for"] == "10m"


def test_circuit_breaker_stuck_open_alert_valid():
    """A provider circuit breaker OPEN for >5m is a page-worthy outage --

    the 2026-09-25 benchmark incident (588/892 rows served
    grounding_state=system_error at ~0.03s for ~2.5h) had no alert covering
    this at all; only the Guru's canned "unable to answer" fallback and a
    cold dashboard signalled it. guru_circuit_breaker_state is already
    emitted (0=closed, 1=half_open, 2=open) by
    services/circuit_breaker.py's _update_gauges(); this alert is the missing
    consumer of it.
    """
    import pathlib

    import yaml

    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    rules_path = repo_root / "infrastructure" / "prometheus" / "alerting-rules.yml"
    config = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    all_rules = [rule for group in config["groups"] for rule in group["rules"]]
    rules_by_name = {rule["alert"]: rule for rule in all_rules if "alert" in rule}

    rule = rules_by_name["CircuitBreakerStuckOpen"]
    assert "guru_circuit_breaker_state" in rule["expr"]
    assert "== 2" in rule["expr"]
    assert rule["for"] == "5m"
    assert rule["labels"]["severity"] == "page"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))


def test_span_export_size_is_capped_below_collector_grpc_limit(monkeypatch):
    """2026-09-26: uncapped LangChain node-state attributes made export batches
    4.4-10.8 MB against Jaeger's 4 MB gRPC limit; whole batches were dropped."""
    from opentelemetry.sdk.trace import SpanLimits

    from app.observability import _apply_export_size_defaults

    monkeypatch.delenv("OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT", raising=False)
    monkeypatch.setenv("OTEL_BSP_MAX_EXPORT_BATCH_SIZE", "8")  # operator value wins
    _apply_export_size_defaults()

    assert SpanLimits().max_span_attribute_length == 4096
    assert os.environ["OTEL_BSP_MAX_EXPORT_BATCH_SIZE"] == "8"

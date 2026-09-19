"""Regression test for AMK-E-006: docker-compose backend healthcheck start_period >= 420s."""

import re
from pathlib import Path

import yaml


def test_backend_healthcheck_start_period_matches_dockerfile():
    """docker-compose.yml backend service must have start_period >= 420s to match Dockerfile."""
    compose_path = Path(__file__).parent.parent / "docker-compose.yml"
    assert compose_path.exists(), f"Compose file not found at {compose_path}"

    with compose_path.open() as f:
        compose_data = yaml.safe_load(f)

    backend_svc = compose_data.get("services", {}).get("backend", {})
    assert "healthcheck" in backend_svc, "backend service missing healthcheck stanza"

    healthcheck = backend_svc["healthcheck"]
    assert "start_period" in healthcheck, "healthcheck missing start_period"

    start_period_str = str(healthcheck["start_period"])
    # Parse value in seconds (e.g. 420s or integer 420)
    match = re.match(r"^(\d+)(s|m)?$", start_period_str)
    assert match, f"Unrecognized start_period format: {start_period_str}"

    val, unit = match.groups()
    val_int = int(val)
    if unit == "m":
        val_seconds = val_int * 60
    else:
        val_seconds = val_int

    assert val_seconds >= 420, (
        f"Backend healthcheck start_period is {val_seconds}s, must be >= 420s (match Dockerfile:86-87)"
    )

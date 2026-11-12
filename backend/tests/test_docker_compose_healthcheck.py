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


def test_datastore_ports_bound_to_loopback_only():
    """SEC-006: Qdrant, Redis, Memgraph and gptcache host ports must not publish on 0.0.0.0."""
    compose_path = Path(__file__).parent.parent / "docker-compose.yml"
    with compose_path.open() as f:
        services = yaml.safe_load(f).get("services", {})

    datastores = ("memgraph", "redis", "qdrant", "gptcache")
    checked = 0
    for name, svc in services.items():
        if not any(k in name for k in datastores):
            continue
        for port in svc.get("ports", []) or []:
            checked += 1
            assert str(port).startswith("127.0.0.1:"), (
                f"service {name!r} publishes {port!r} on all interfaces"
            )
    assert checked >= 4, "expected datastore port mappings to be checked"


def test_compose_pins_both_v10_only_flags_in_the_environment_block():
    """Both flags sit in `environment:`, which beats env_file, so the root .env cannot split them."""
    text = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    assert (
        "- FIRST_PERSON_CONTEXT_HARNESS_ENABLED=${FIRST_PERSON_CONTEXT_HARNESS_ENABLED:-false}"
        in text
    )
    assert (
        "- FIRST_PERSON_CONTEXT_TERMINAL_ENABLED=${FIRST_PERSON_CONTEXT_TERMINAL_ENABLED:-false}"
        in text
    )

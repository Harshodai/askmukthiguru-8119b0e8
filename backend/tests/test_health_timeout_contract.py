"""The backend healthcheck timeout must exceed the deep health handler's hard bound.

If the Docker healthcheck gives up before /api/health can finish, autoheal kills a
healthy-but-slow backend (seen during the 20261112-graded-4 capture).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[1]


def _hard_bound_seconds() -> float:
    source = (BACKEND / "app" / "api" / "health.py").read_text(encoding="utf-8")
    match = re.search(r"^_HEALTH_HARD_BOUND_SECONDS\s*=\s*([0-9.]+)", source, re.M)
    assert match, "_HEALTH_HARD_BOUND_SECONDS not found"
    return float(match.group(1))


def _backend_healthcheck_timeout_seconds() -> float:
    compose = yaml.safe_load((BACKEND / "docker-compose.yml").read_text(encoding="utf-8"))
    timeout = compose["services"]["backend"]["healthcheck"]["timeout"]
    return float(re.fullmatch(r"([0-9.]+)s", str(timeout)).group(1))


def test_healthcheck_timeout_exceeds_deep_health_hard_bound():
    assert _backend_healthcheck_timeout_seconds() > _hard_bound_seconds()


if __name__ == "__main__":
    assert _backend_healthcheck_timeout_seconds() > _hard_bound_seconds()
    print("ok")

"""Local-stack ops gates: compose required env fails loudly; prelaunch runs against local Docker."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_COMPOSE = (_REPO / "backend" / "docker-compose.yml").read_text()
_PRELAUNCH = _REPO / "scripts" / "prelaunch.sh"

# Secrets/config the stack cannot run safely without. A bare `${VAR}` or a `:-default`
# here would let compose start with an empty/guessable credential.
REQUIRED = ("NEO4J_PASSWORD", "REDIS_PASSWORD", "JWT_SECRET", "CORS_ORIGINS")


@pytest.mark.parametrize("var", REQUIRED)
def test_compose_requires_var_with_message(var):
    assert re.search(r"\$\{%s:\?[^}]+\}" % var, _COMPOSE), f"{var} must use ${{{var}:?message}}"


@pytest.mark.parametrize("var", REQUIRED)
def test_compose_never_defaults_required_var(var):
    assert not re.search(r"\$\{%s:-" % var, _COMPOSE), f"{var} must not have a fallback default"
    assert not re.search(r"\$\{%s\}" % var, _COMPOSE), f"{var} is used without the :? guard"


def test_compose_yaml_parses():
    yaml = pytest.importorskip("yaml")
    assert "services" in yaml.safe_load(_COMPOSE)


def test_prelaunch_is_valid_bash():
    bash = shutil.which("bash")
    assert bash
    r = subprocess.run([bash, "-n", str(_PRELAUNCH)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_prelaunch_has_no_hosted_assumptions_and_named_failures():
    text = _PRELAUNCH.read_text()
    assert "railway" not in text.lower()
    for code in ("E001", "E002", "E003", "E004", "E005", "E006"):
        assert f"PRELAUNCH-{code}" in text or f"preflight_fail {code}" in text
    # Every compose-required var is preflighted by name.
    for var in REQUIRED:
        assert var in text


def test_prelaunch_preflight_fails_fast_with_named_error(tmp_path):
    """Backend unreachable + no env must exit non-zero with PRELAUNCH-E004 before building."""
    bash = shutil.which("bash")
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "BACKEND_URL": "http://127.0.0.1:1",
    }
    r = subprocess.run([bash, str(_PRELAUNCH)], capture_output=True, text=True, env=env, timeout=120)
    out = r.stdout + r.stderr
    assert r.returncode != 0
    assert "PRELAUNCH-E004" in out
    assert "PRELAUNCH-E003" in out
    assert "Build and e2e were NOT run" in out

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
    assert re.search(r"\$\{" + var + r":\?[^}]+\}", _COMPOSE), f"{var} must use ${{{var}:?message}}"


@pytest.mark.parametrize("var", REQUIRED)
def test_compose_never_defaults_required_var(var):
    assert not re.search(r"\$\{" + var + ":-", _COMPOSE), f"{var} must not have a fallback default"
    assert not re.search(r"\$\{" + var + r"\}", _COMPOSE), f"{var} is used without the :? guard"


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
    r = subprocess.run(
        [bash, str(_PRELAUNCH)], capture_output=True, text=True, env=env, timeout=120
    )
    out = r.stdout + r.stderr
    assert r.returncode != 0
    assert "PRELAUNCH-E004" in out
    assert "PRELAUNCH-E003" in out
    assert "Build and e2e were NOT run" in out


def test_ci_prelaunch_gate_skips_local_stack_preflight(tmp_path):
    """The CI pre-launch gate mocks the backend; it must not require local-compose env or a live backend.

    Regression (PR #45, 2026-10-08): the local-Docker preflight ran in the CI
    job and failed on E003/E004 before any build or e2e ran.
    """
    wf = (_REPO / ".github" / "workflows" / "prelaunch-gate.yml").read_text()
    assert 'PRELAUNCH_SKIP_BACKEND: "1"' in wf
    assert 'PRELAUNCH_SKIP_ENV: "1"' in wf

    bash = shutil.which("bash")
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "BACKEND_URL": "http://127.0.0.1:1",
        "PRELAUNCH_SKIP_BACKEND": "1",
        "PRELAUNCH_SKIP_ENV": "1",
        "PRELAUNCH_ALLOW_SKIPS": "1",
        "SKIP_BUILD": "1",
        "SUITES": "__none__",
    }
    r = subprocess.run(
        [bash, str(_PRELAUNCH)], capture_output=True, text=True, env=env, timeout=120
    )
    out = r.stdout + r.stderr
    assert "PRELAUNCH-E003" not in out
    assert "PRELAUNCH-E004" not in out


def _run_gate(tmp_path, **extra):
    """Run a copy of the gate in a sandbox with stub node/npm/npx/curl so only skip logic is under test."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "node_modules").mkdir()
    shutil.copy(_PRELAUNCH, tmp_path / "scripts" / "prelaunch.sh")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("node", "npm", "npx", "curl"):
        stub = bindir / tool
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    env = {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "SKIP_BUILD": "1",
        "SUITES": "__none__",
        **extra,
    }
    r = subprocess.run(
        [shutil.which("bash"), str(tmp_path / "scripts" / "prelaunch.sh")],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    return r, r.stdout + r.stderr


def test_prelaunch_skip_without_override_fails_the_gate(tmp_path):
    """H12: a skipped check is not a pass. Skip flags alone must not yield ALL GREEN."""
    r, out = _run_gate(tmp_path, PRELAUNCH_SKIP_BACKEND="1", PRELAUNCH_SKIP_ENV="1")
    assert "ALL GREEN" not in out
    assert r.returncode != 0
    assert "PRELAUNCH_ALLOW_SKIPS" in out


def test_prelaunch_skip_with_override_is_labelled_not_all_green(tmp_path):
    r, out = _run_gate(
        tmp_path,
        PRELAUNCH_SKIP_BACKEND="1",
        PRELAUNCH_SKIP_ENV="1",
        PRELAUNCH_ALLOW_SKIPS="1",
    )
    assert "ALL GREEN" not in out
    assert "GREEN WITH SKIPS" in out
    assert r.returncode == 0


def test_prelaunch_skip_preflight_flag_is_gone():
    assert "PRELAUNCH_SKIP_PREFLIGHT" not in _PRELAUNCH.read_text()


def test_ci_workflow_sets_explicit_skip_override():
    wf = (_REPO / ".github" / "workflows" / "prelaunch-gate.yml").read_text()
    assert 'PRELAUNCH_ALLOW_SKIPS: "1"' in wf

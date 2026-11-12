"""T9-01 (RW-05) and NEW-RW-1 (RW-01): `.railway/railway.ts` invariants.

The file is TypeScript for Railway's IaC runner, which is not installed here, so
these are static checks on its text. They pin the facts that other code depends
on. Whether `railway config plan` accepts the file is UNPROVEN until the owner
runs it (Gate A1).
"""

from __future__ import annotations

import re
from pathlib import Path

import start_railway

DOCKERFILE_REL = "backend/Dockerfile.railway"
REPO_ROOT = Path(__file__).resolve().parents[2]
IAC = (REPO_ROOT / ".railway" / "railway.ts").read_text()
MAIN = (REPO_ROOT / "backend" / "app" / "main.py").read_text()


def _service_block(name: str) -> str:
    start = IAC.index(f'service("{name}"')
    end = IAC.index("\n  });", start)
    return IAC[start:end]


def test_partial_name_is_unchanged():
    # Renaming does not transfer ownership (runbook F-5).
    assert 'export const partial = "askmukthiguru-8119b0e8";' in IAC


def test_declares_backend_redis_worker_and_beat():
    assert 'service("askmukthiguru-8119b0e8"' in IAC
    assert 'service("celery-worker"' in IAC
    assert 'service("celery-beat"' in IAC
    assert 'redis("redis")' in IAC


def test_qdrant_is_external_by_d26():
    # D-26 decided 2026-11-07: external QDRANT_URL, no Qdrant service on Railway.
    assert "D-26 decided" in IAC
    assert "pending" not in IAC.split("QDRANT_URL: preserve()")[1].splitlines()[0]
    code = "\n".join(ln for ln in IAC.splitlines() if not ln.strip().startswith("//"))
    assert 'service("qdrant"' not in code
    assert "QDRANT_URL: preserve()" in code


def test_qdrant_is_not_declared_until_d26():
    code = "\n".join(ln for ln in IAC.splitlines() if not ln.strip().startswith("//"))
    assert 'service("qdrant"' not in code
    assert "QDRANT_URL: preserve()" in code
    # The write key must never be on a Railway service (config.py).
    assert "QDRANT_WRITE_API_KEY" not in code


def test_backend_healthcheck_stays_above_grace_window():
    backend = _service_block("askmukthiguru-8119b0e8")
    assert 'healthcheck: "/api/healthz"' in backend
    timeout = int(re.search(r"healthcheckTimeout:\s*(\d+)", backend).group(1))
    assert timeout == 330
    assert start_railway._GRACE_SECONDS < timeout


def test_beat_has_one_replica_and_no_healthcheck():
    beat = _service_block("celery-beat")
    assert "replicas: 1" in beat
    assert "healthcheck" not in beat


def test_every_python_service_sets_dockerfile_path_and_environment():
    assert "RAILWAY_DOCKERFILE_PATH: DOCKERFILE_PATH" in IAC
    assert 'const DOCKERFILE_PATH = "backend/Dockerfile.railway";' in IAC
    assert (REPO_ROOT / DOCKERFILE_REL).exists()
    # sharedEnv is spread into all three.
    assert IAC.count("...sharedEnv") == 3
    assert 'ctx.environment === "production" ? "production" : "staging"' in IAC


def test_drain_seconds_exceed_app_drain_and_celery_grace():
    """NEW-RW-1: Railway's default drain is 0 s (runbook F-8)."""
    drain = {
        name: int(re.search(rf'DRAIN_SECONDS_{name} = "(\d+)"', IAC).group(1))
        for name in ("BACKEND", "WORKER", "BEAT")
    }
    app_drain = int(re.search(r"_DRAIN_TIMEOUT_S = (\d+)", MAIN).group(1))
    assert drain["BACKEND"] > app_drain  # main.py waits up to app_drain seconds
    for svc, key in (("celery-worker", "WORKER"), ("celery-beat", "BEAT")):
        block = _service_block(svc)
        grace = float(re.search(r'CELERY_SHUTDOWN_GRACE_SECONDS: "(\d+)"', block).group(1))
        assert grace < drain[key], (svc, grace, drain[key])
        assert f"RAILWAY_DEPLOYMENT_DRAINING_SECONDS: DRAIN_SECONDS_{key}" in block
    assert "RAILWAY_DEPLOYMENT_DRAINING_SECONDS: DRAIN_SECONDS_BACKEND" in _service_block(
        "askmukthiguru-8119b0e8"
    )


def test_main_py_comments_state_the_real_drain_and_grace_values():
    """NEW-RW-1: the comments named a 90 s grace that is 180 s, and a drain that
    no file set."""
    assert "for /api/healthz for 90s" not in MAIN
    assert "RAILWAY_DEPLOYMENT_DRAINING_SECONDS" in MAIN


def test_serving_posture_is_v10_only_by_d14():
    # D-14 decided 2026-11-07: v10-only. The active name is a literal, the two
    # harness flags are literal "true", and no serving variable is preserve().
    assert 'const SERVING_POSTURE: ServingPosture = "v10_only";' in IAC
    assert "D-14 decided" in IAC
    block = IAC.split('SERVING_POSTURE === "v10_only"')[1].split(": SERVING_POSTURE")[0]
    assert 'FIRST_PERSON_ACTIVE_COLLECTION: "first_person_v10"' in block
    assert 'FIRST_PERSON_CONTEXT_HARNESS_ENABLED: "true"' in block
    assert 'FIRST_PERSON_CONTEXT_TERMINAL_ENABLED: "true"' in block


def test_celery_has_one_switch_by_d30():
    assert "D-30 decided" in IAC
    assert "const INCLUDE_CELERY = true;" in IAC
    assert "INCLUDE_CELERY ? [worker, beat] : []" in IAC


def test_faculty_access_code_is_the_only_staging_gate_by_d29():
    assert "D-29 decided" in IAC
    assert "FACULTY_ACCESS_CODE: preserve()" in IAC


def test_no_literal_secret_values():
    secret_names = (
        "JWT_SECRET",
        "ANON_SESSION_HMAC_SECRET",
        "BRAIN_KEK",
        "OPENROUTER_API_KEY",
        "SUPABASE_KEY",
        "FACULTY_ACCESS_CODE",
        "METRICS_SCRAPE_TOKEN",
        "QDRANT_READ_ONLY_API_KEY",
    )
    for name in secret_names:
        for m in re.finditer(rf"\b{name}:\s*([^,\n]+)", IAC):
            assert m.group(1).strip().startswith("preserve()"), (name, m.group(0))


def test_forwarded_ips_is_not_a_wildcard():
    assert 'FORWARDED_ALLOW_IPS: "10.0.0.0/8"' in IAC
    assert 'FORWARDED_ALLOW_IPS: "*"' not in IAC


def test_budget_guard_is_declared_on():
    assert 'OPENROUTER_BUDGET_GUARD_ENABLED: "true"' in IAC
    assert 'OPENROUTER_BUDGET_FAIL_CLOSED: "true"' in IAC


def test_legacy_config_as_code_files_stay_absent():
    # railway.json / railway.toml stop working on 2026-12-01 (runbook F-1).
    assert not (REPO_ROOT / "railway.json").exists()
    assert not (REPO_ROOT / "railway.toml").exists()
    assert not (REPO_ROOT / "backend" / "railway.json").exists()
    assert not (REPO_ROOT / "backend" / "railway.toml").exists()

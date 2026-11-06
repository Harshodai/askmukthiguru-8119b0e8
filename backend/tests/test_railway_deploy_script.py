"""NEW-RW-4 (RW-03) and NEW-RW-2 (RW-02): `scripts/deploy/deploy_railway.sh`.

Static checks only. The script is never run here: it calls the Railway CLI,
which needs a live project. Each assertion maps to a finding in
`audits/audit-output-2026-11-04/FINAL_RAILWAY_STAGING_READINESS.md`:

- P7-14 / X-A1: `ENVIRONMENT` is set (startup refuses `local` in production).
- P7-18: no random `JWT_SECRET` (it must equal the Supabase secret).
- P7-19: Redis policy is `noeviction`, as in `docker-compose.prod.yml`.
- P7-05 / X-A2: `GIT_SHA` is set on every script deploy.
- SYS-013: `FORWARDED_ALLOW_IPS` and `PYTHON_MEMORY_LIMIT_MB=0` are set.
- NEW-RW-7: the post-deploy health gate uses `/api/healthz`, not `/api/health`.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (REPO_ROOT / "scripts" / "deploy" / "deploy_railway.sh").read_text()
CLEANUP = (REPO_ROOT / "scripts" / "ops" / "railway_cleanup.py").read_text()


def _code_lines() -> list[str]:
    return [ln for ln in SCRIPT.splitlines() if not ln.lstrip().startswith("#")]


def test_script_does_not_generate_or_set_jwt_secret():
    code = "\n".join(_code_lines())
    assert not re.search(r"set_var\s+JWT_SECRET", code)
    assert not re.search(r"JWT_SECRET=", code)
    # `openssl rand` may only appear for the scrape token, a secret that only
    # this project defines (unlike JWT_SECRET, which must match Supabase).
    for ln in _code_lines():
        if "openssl rand" in ln:
            assert "METRICS_SCRAPE_TOKEN" in ln or "SCRAPE" in ln, ln


def test_jwt_secret_is_a_required_variable():
    loops = [m.group(1).split() for m in re.finditer(r"for key in ([A-Z_ ]+); do", SCRIPT)]
    required = next((lst for lst in loops if "BRAIN_KEK" in lst), None)
    assert required is not None, "required-variable loop not found"
    for name in ("JWT_SECRET", "FACULTY_ACCESS_CODE", "OPENROUTER_API_KEY", "BRAIN_KEK"):
        assert name in required, required


def test_script_sets_environment_and_deploy_variables():
    code = "\n".join(_code_lines())
    for name in (
        "ENVIRONMENT",
        "METRICS_SCRAPE_TOKEN",
        "FORWARDED_ALLOW_IPS",
        "PYTHON_MEMORY_LIMIT_MB",
    ):
        assert re.search(rf"set_var\s+{name}\b", code), f"{name} is not set by the script"
    assert re.search(r'set_var\s+FORWARDED_ALLOW_IPS\s+"10\.0\.0\.0/8"', code)
    assert re.search(r'set_var\s+PYTHON_MEMORY_LIMIT_MB\s+"0"', code)


def test_environment_is_validated_and_never_local():
    assert re.search(r"staging\|production|staging\)|production\)", SCRIPT)
    assert "local" not in re.findall(r'set_var\s+ENVIRONMENT\s+"?([^"\s]+)', SCRIPT)


def test_git_sha_is_set_from_head_and_overwrites():
    # set_var skips existing values, so GIT_SHA needs a direct overwrite.
    assert "git rev-parse HEAD" in SCRIPT
    assert re.search(r'railway variables set\s+"?GIT_SHA=', SCRIPT)
    # A dirty tree would deploy code that does not match the SHA.
    assert "git status --porcelain" in SCRIPT


def test_redis_policy_is_noeviction_not_volatile_lru():
    code = "\n".join(_code_lines())
    assert "volatile-lru" not in code  # comments may explain why
    assert "noeviction" in SCRIPT
    # The tuner behind `--tune-redis` must default to the same policy.
    assert re.search(r'policy: str = "noeviction"', CLEANUP)
    assert 'policy: str = "volatile-lru"' not in CLEANUP


def test_tune_redis_failure_is_not_silenced():
    line = next(ln for ln in SCRIPT.splitlines() if "--tune-redis" in ln and "python3" in ln)
    assert "2>/dev/null" not in line
    assert "|| true" not in line


def test_health_gate_uses_healthz():
    assert "/api/healthz" in SCRIPT
    assert not re.search(r"/api/health(?!z)", "\n".join(_code_lines()))

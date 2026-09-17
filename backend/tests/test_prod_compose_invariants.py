"""F-PROD-1 regression guard: prod deploy manifests stay reconciled.

`docs/RUTHLESS_PLAN_10_10.md` F-PROD-1 found five drift/masking defects across
`docker-compose.prod.yml`, `railway.json`, and the Helm chart. All five were
fixed in the same session that added this test (2026-09-16); this file is the
"one runnable check" pinning them so a future edit can't silently reopen any
of them without a manifest-parsing test noticing:

1. Graph env vars omitted from the prod compose backend service -> the graph
   client fell back to `bolt://localhost:7687` *inside the container*, which
   is the backend itself, not a graph. Fixed by requiring `NEO4J_URI` via
   Compose's `${VAR:?msg}` syntax (no default -> compose refuses to start
   without it, rather than silently substituting an empty string).
2. Redis `allkeys-lru` could evict anonymous-quota/session counters under
   memory pressure -> reads as "0 messages sent", a billing hole. Fixed to
   `noeviction` (both consumers already fail open/degrade on a Redis error).
3. Qdrant version drift between `docker-compose.prod.yml` and the Helm chart.
4. Backend healthcheck pointed at `/api/health` (expensive, fails on any
   non-critical dependency) instead of `/api/healthz` (cheap liveness probe).
5. Railway's `healthcheckTimeout` (330s) must stay strictly greater than
   `start_railway.py`'s `_GRACE_SECONDS` (180s) — the grace window returns
   200 unconditionally, so if it ever reached or exceeded the Railway
   timeout, a replica that never boots would look healthy for the entire
   healthcheck budget.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROD_COMPOSE = _REPO_ROOT / "docker-compose.prod.yml"
_RAILWAY_JSON = _REPO_ROOT / "railway.json"
_HELM_VALUES = _REPO_ROOT / "k8s" / "helm" / "mukthiguru" / "values.yaml"
_START_RAILWAY = _REPO_ROOT / "backend" / "start_railway.py"


def _load_prod_compose() -> dict:
    with _PROD_COMPOSE.open() as f:
        return yaml.safe_load(f)


def test_backend_requires_neo4j_uri_no_localhost_fallback():
    compose = _load_prod_compose()
    env = compose["services"]["backend"]["environment"]
    neo4j_uri_entry = next((e for e in env if e.startswith("NEO4J_URI=")), None)
    assert neo4j_uri_entry is not None, "NEO4J_URI missing from prod compose backend env"
    # Compose's ${VAR:?...} form: no default, so a missing host var is a hard
    # failure, not a silent fallback to localhost inside the container.
    assert ":?" in neo4j_uri_entry, (
        f"NEO4J_URI must use the ${{VAR:?msg}} required-var form so an unset "
        f"host env fails the compose boot instead of resolving empty and "
        f"falling back to settings.neo4j_uri's localhost default: {neo4j_uri_entry!r}"
    )


def test_redis_does_not_evict_quota_keys():
    compose = _load_prod_compose()
    command = compose["services"]["redis"]["command"]
    assert "allkeys-lru" not in command, (
        "allkeys-lru can evict anonymous-quota/session/rate-limit keys under "
        "memory pressure, which reads as '0 messages sent' rather than a cache "
        "miss -- a billing/quota hole, not a performance issue."
    )
    assert "--maxmemory-policy noeviction" in command


def test_backend_healthcheck_uses_cheap_liveness_endpoint():
    compose = _load_prod_compose()
    test = compose["services"]["backend"]["healthcheck"]["test"]
    joined = " ".join(test) if isinstance(test, list) else str(test)
    assert "/api/healthz" in joined, (
        "backend healthcheck must target the cheap /api/healthz liveness "
        "probe, not /api/health (comprehensive per-dependency check -- "
        "expensive on a 30s interval and restart-loops on any non-critical "
        "dependency degradation)"
    )
    assert '/api/health"' not in joined and not joined.rstrip().endswith("/api/health")


def test_qdrant_version_matches_across_manifests():
    compose = _load_prod_compose()
    compose_image = compose["services"]["qdrant"]["image"]
    compose_tag = compose_image.rsplit(":", 1)[-1]

    with _HELM_VALUES.open() as f:
        helm_values = yaml.safe_load(f)
    helm_tag = helm_values["qdrant"]["image"]["tag"]

    assert compose_tag == helm_tag, (
        f"Qdrant version drift: docker-compose.prod.yml pins {compose_tag!r}, "
        f"Helm chart pins {helm_tag!r}. Different environments would run "
        f"different Qdrant versions against the same collection format."
    )


def test_railway_grace_window_strictly_under_healthcheck_timeout():
    import json

    with _RAILWAY_JSON.open() as f:
        railway_config = json.load(f)
    healthcheck_timeout = railway_config["deploy"]["healthcheckTimeout"]

    start_railway_src = _START_RAILWAY.read_text()
    match = re.search(r"^_GRACE_SECONDS\s*=\s*(\d+)", start_railway_src, re.MULTILINE)
    assert match, "could not find _GRACE_SECONDS in start_railway.py"
    grace_seconds = int(match.group(1))

    assert grace_seconds < healthcheck_timeout, (
        f"_GRACE_SECONDS ({grace_seconds}) must stay strictly below "
        f"railway.json's healthcheckTimeout ({healthcheck_timeout}). The grace "
        f"window returns 200 unconditionally; if it reached the healthcheck "
        f"timeout, a replica that never finishes booting would look healthy "
        f"for Railway's entire retry budget and the deploy would never fail."
    )


if __name__ == "__main__":
    # ponytail: no test runner needed for a handful of assertion functions.
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures.append(name)
                print(f"FAIL {name}: {exc}")
    if failures:
        print(f"\n{len(failures)} failure(s): {failures}")
        sys.exit(1)
    print("\nall prod-compose invariants hold")

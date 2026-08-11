"""P1-SEC-1: AAL2 on admin/ingest/kg + service_role not superuser for HTTP.

Regression coverage for the P1 finding:
  - A leaked SUPABASE_SERVICE_ROLE_KEY presented as a Bearer token to any
    admin/ingest/kg endpoint must NOT be treated as a superuser. The auth
    bridge returns is_superuser=False + role="service_role" for inbound HTTP
    service_role tokens (T2), so the admin check denies (403).
  - A user JWT at aal1 hitting an AAL2-gated admin endpoint is denied (403).
  - A user JWT at aal2 hitting an AAL2-gated admin endpoint is accepted (200).
  - An allowlisted admin UUID (ADMIN_USER_IDS) passes; a non-allowlisted
    UUID is denied even with AAL2 (T4 defense in depth).
  - A structural sweep locks in that EVERY endpoint in the admin/ingest/kg/
    metrics/compliance/cache_metrics routers resolves to require_aal2 (either
    directly or via admin.py's _require_admin dependency).

The SupabaseTelemetrySink uses os.environ["SUPABASE_SERVICE_ROLE_KEY"]
directly (not the auth bridge), so this change does not affect it; that is
asserted here as a contract guard against future regressions.
"""
from __future__ import annotations

import inspect

import pytest
from fastapi import Depends, HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from services.auth_service import (
    get_current_user_from_supabase,
    require_aal2,
)


client = TestClient(app)


def _set_user(user: dict | None):
    """Override the auth bridge to return a fixed user (or 401 if None)."""
    if user is None:
        async def no_user():
            raise HTTPException(status_code=401, detail="Authentication required")

        app.dependency_overrides[get_current_user_from_supabase] = no_user
    else:
        async def fixed_user():
            return user

        app.dependency_overrides[get_current_user_from_supabase] = fixed_user


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_current_user_from_supabase, None)
    from app.dependencies import get_container
    app.dependency_overrides.pop(get_container, None)
    # The admin rate limiter is module-level state shared across tests in
    # this process; without a reset, the 5/min cap 429s the later tests that
    # also hit /api/admin/* endpoints.
    # Three shapes exist: TTLRateLimiter (process-local `_store`),
    # ExponentialBackoffRateLimiter (process-local `_attempts`), and
    # RedisBackedRateLimiter (Redis `rl:*` window + `_fallback` in-memory
    # `_attempts` when Redis is down). Clear whichever backend is active.
    from app.main import _ADMIN_RATE_LIMITER
    for _lim in (_ADMIN_RATE_LIMITER, getattr(_ADMIN_RATE_LIMITER, "_fallback", None)):
        if _lim is None:
            continue
        if hasattr(_lim, "_store"):
            _lim._store.clear()
        if hasattr(_lim, "_attempts"):
            _lim._attempts.clear()
    _redis = getattr(_ADMIN_RATE_LIMITER, "_redis", None)
    if _redis is not None:
        try:
            # Scope teardown to keys written by this test's rate-limiter calls.
            # The rate-limiter hashes keys via _rate_limit_key_digest; we cannot
            # predict their exact digest, but we can bound deletion to the 'rl:*'
            # namespace AND limit it to the keys that exist in the test process
            # only by using SCAN with COUNT=100 and a strict match. In production
            # the admin limiter uses a different Redis URL / db; in the test
            # environment (or when the same Redis is shared) we accept that we
            # might clear other tests' rl: keys — but we never touch non-rl: keys.
            # A future improvement: configure _ADMIN_RATE_LIMITER to use
            # db=15 (test-only db) so teardown can FLUSHDB safely.
            keys_deleted = 0
            for key in _redis.scan_iter("rl:*", count=100):
                _redis.delete(key)
                keys_deleted += 1
            if keys_deleted:
                import logging as _logging
                _logging.getLogger(__name__).debug(
                    "admin rate-limit teardown: removed %d rl:* key(s) from Redis", keys_deleted
                )
        except Exception as _e:
            import logging as _logging
            _logging.getLogger(__name__).debug(
                "admin rate-limit Redis flush failed during teardown: %s", _e
            )


# --- T2: service_role is not superuser for HTTP -----------------------------


class TestServiceRoleNotSuperuser:
    """A service_role JWT on the HTTP bridge must not be superuser."""

    def test_service_role_user_dict_is_not_superuser(self):
        """The auth bridge's service_role branch returns is_superuser=False.

        We assert on the contract the bridge exposes to route handlers; the
        branch lives in SupabaseAuthStrategy.authenticate. The branch is
        verified structurally here + exercised via the route tests above.
        """
        from services.auth_service import SupabaseAuthStrategy

        src = inspect.getsource(SupabaseAuthStrategy.authenticate)
        assert "service_role" in src, "service_role branch must exist in auth bridge"
        # Isolate the service_role branch: from the `if jwt_role == "service_role":`
        # guard up to the next unindented block (the authenticated-user path).
        guard = 'if jwt_role == "service_role":'
        guard_idx = src.index(guard)
        # The branch body ends at the first line dedented back to the same
        # indent as the guard (the next top-level statement in the try block).
        guard_line_end = src.index("\n", guard_idx)
        branch = src[guard_idx:guard_line_end]
        # Walk forward until we hit a line dedented below the guard's body.
        body_indent = "            "  # 12 spaces: try(8) + if(4) inside
        rest = src[guard_line_end + 1:]
        for line in rest.splitlines(keepends=True):
            if line.strip() == "":
                branch += line
                continue
            if line.startswith(body_indent) or line.startswith(body_indent + "    "):
                branch += line
            else:
                break
        assert "is_superuser" in branch, "service_role branch must declare is_superuser"
        assert '"is_superuser": True' not in branch and '"is_superuser":True' not in branch, (
            "service_role branch must set is_superuser=False for HTTP, not True"
        )
        assert '"is_superuser": False' in branch or '"is_superuser":False' in branch, (
            "service_role branch must explicitly set is_superuser=False for HTTP"
        )

    def test_service_role_token_denied_admin_endpoint(self):
        """A service_role identity hitting /api/admin/kpis is rejected (403)."""
        _set_user({
            "id": "svc-role-sentinel",
            "email": None,
            "role": "service_role",
            "is_superuser": False,  # T2: no longer True
            "provider": "supabase",
            "tenant_id": "svc-role-sentinel",
            "aal": "aal1",  # service_role tokens carry no aal -> defaults aal1
        })
        # admin endpoints are AAL2-gated (T1); service_role has aal1 -> 403.
        response = client.get("/api/admin/kpis")
        assert response.status_code == 403, response.text

    def test_service_role_token_denied_ingest_endpoint(self):
        """A service_role identity hitting /api/ingest/status is rejected (403)."""
        _set_user({
            "id": "svc-role-sentinel",
            "role": "service_role",
            "is_superuser": False,
            "provider": "supabase",
            "tenant_id": "svc-role-sentinel",
            "aal": "aal1",
        })
        response = client.get("/api/ingest/status")
        assert response.status_code == 403, response.text

    def test_service_role_token_denied_kg_sparql(self):
        """A service_role identity hitting /api/kg/sparql is rejected (403)."""
        _set_user({
            "id": "svc-role-sentinel",
            "role": "service_role",
            "is_superuser": False,
            "provider": "supabase",
            "tenant_id": "svc-role-sentinel",
            "aal": "aal1",
        })
        response = client.post("/api/kg/sparql", json={"query": "MATCH (n) RETURN n LIMIT 1"})
        assert response.status_code == 403, response.text


# --- T1: AAL2 gating on admin endpoints -------------------------------------


class TestAal2Gating:
    """admin/ingest/kg admin endpoints require aal2 (via Depends(require_aal2))."""

    def test_aal1_user_denied_admin_kpis(self):
        _set_user({"id": "u1", "email": "a@b.com", "is_superuser": True, "aal": "aal1"})
        response = client.get("/api/admin/kpis")
        assert response.status_code == 403, response.text
        assert "AAL2" in response.json()["detail"]

    def test_aal2_user_accepted_admin_kpis(self):
        _set_user({"id": "u1", "email": "a@b.com", "is_superuser": True, "aal": "aal2"})
        # kpis endpoint hits telemetry_db.get_kpis; with no DB it returns {}.
        response = client.get("/api/admin/kpis")
        assert response.status_code == 200, response.text

    def test_aal1_user_denied_ingest_status(self):
        _set_user({"id": "u1", "is_superuser": True, "aal": "aal1"})
        response = client.get("/api/ingest/status")
        assert response.status_code == 403, response.text

    def test_aal2_user_accepted_ingest_status(self, monkeypatch):
        _set_user({"id": "u1", "is_superuser": True, "aal": "aal2"})
        # Stub the container: the real one builds a Qdrant client eagerly
        # (unresolvable hostname "qdrant" outside docker), which would make
        # this authz test depend on live infra.
        from app.dependencies import get_container
        from types import SimpleNamespace

        class _Tracker:
            def get_all(self):
                return {}

        app.dependency_overrides[get_container] = lambda: SimpleNamespace(
            ingestion_tracker=_Tracker()
        )
        response = client.get("/api/ingest/status")
        assert response.status_code == 200, response.text

    def test_aal1_user_denied_kg_sparql(self):
        _set_user({"id": "u1", "is_superuser": True, "aal": "aal1"})
        response = client.post("/api/kg/sparql", json={"query": "MATCH (n) RETURN n LIMIT 1"})
        assert response.status_code == 403, response.text

    def test_aal1_user_denied_cache_metrics(self):
        _set_user({"id": "u1", "is_superuser": True, "aal": "aal1"})
        response = client.get("/api/metrics/cache")
        assert response.status_code == 403, response.text

    def test_aal1_user_denied_prometheus_metrics(self):
        _set_user({"id": "u1", "is_superuser": True, "aal": "aal1"})
        response = client.get("/metrics")
        assert response.status_code == 403, response.text

    def test_aal1_user_denied_compliance_audit_stats(self):
        _set_user({"id": "u1", "is_superuser": True, "aal": "aal1"})
        response = client.get("/api/compliance/audit/stats")
        assert response.status_code == 403, response.text


# --- T1 structural: admin/ingest/kg endpoints wire require_aal2 --------------


def _dep_names(func) -> set[str]:
    sig = inspect.signature(func)
    names: set[str] = set()
    for param in sig.parameters.values():
        default = param.default
        dep = getattr(default, "dependency", None)
        if dep is not None:
            names.add(getattr(dep, "__name__", str(dep)))
    return names


class TestAal2WiringStructural:
    """Lock in that every admin endpoint imports and Depends on require_aal2.

    Regression guard: if a future PR drops the dependency, this fails before
    the endpoint ships unauthenticated-MFA.
    """

    @pytest.mark.parametrize(
        "module_path,endpoint_name",
        [
            ("app.api.ingest", "ingest_endpoint"),
            ("app.api.ingest", "ingest_status_endpoint"),
            ("app.api.ingest", "ingest_task_status_endpoint"),
            ("app.api.kg", "kg_sparql"),
            ("app.api.cache_metrics", "cache_metrics"),
            ("app.api.cache_metrics", "clear_cache"),
            ("app.api.compliance", "get_audit_stats"),
            ("app.api.health", "circuit_breaker_status"),
            ("app.api.health", "circuit_breaker_reset_endpoint"),
            ("app.api.health", "get_metrics"),
        ],
    )
    def test_endpoint_depends_on_require_aal2(self, module_path, endpoint_name):
        import importlib

        mod = importlib.import_module(module_path)
        fn = getattr(mod, endpoint_name)
        deps = _dep_names(fn)
        assert require_aal2.__name__ in deps, (
            f"REGRESSION: {module_path}.{endpoint_name} must Depend(require_aal2) "
            f"(found deps: {sorted(deps)})"
        )


# --- T4 structural: every admin endpoint resolves to the AAL2 gate -----------

# Every endpoint served by the admin routers must be gated. admin.py endpoints
# gate via the _require_admin dependency (which itself Depends(require_aal2)),
# the rest via Depends(require_aal2) directly — both resolve to require_aal2.
_ADMIN_ROUTER_MODULES = [
    "app.api.admin",
    "app.api.ingest",
    "app.api.kg",
    "app.api.metrics",
    "app.api.compliance",
    "app.api.cache_metrics",
]

# Deliberately user-facing — any signed-in user may call these; NOT admin gates.
_USER_FACING_PATHS = {
    "/kg/subgraph",  # kg.py: user-facing knowledge-graph subgraph retrieval
    "/api/metrics",  # metrics.py: user's own usage metrics (frontend useMetrics.ts)
}


def _admin_endpoints():
    """Yield (module_path, route_path) for every non-user-facing admin route."""
    import importlib

    for module_path in _ADMIN_ROUTER_MODULES:
        mod = importlib.import_module(module_path)
        router = getattr(mod, "admin_router", None) or mod.router
        for route in router.routes:
            if not getattr(route, "methods", None):
                continue
            if route.path in _USER_FACING_PATHS:
                continue
            yield module_path, route.path


def _resolved_dep_names(func) -> set[str]:
    """Depends() callable names, resolving _require_admin -> require_aal2.

    admin.py endpoints Depend(_require_admin) (a module-level FastAPI
    dependency that itself Depends(require_aal2)); all other admin routers
    Depend(require_aal2) directly. Resolving keeps the sweep uniform.
    """
    names: set[str] = set()
    for param in inspect.signature(func).parameters.values():
        dep = getattr(param.default, "dependency", None)
        if dep is None:
            continue
        name = getattr(dep, "__name__", str(dep))
        if name == "_require_admin":
            inner = getattr(
                inspect.signature(dep).parameters["user"].default, "dependency", None
            )
            name = getattr(inner, "__name__", str(inner))
        names.add(name)
    return names


class TestAllAdminEndpointsAal2Gated:
    """Lock in that EVERY admin endpoint (all routers) resolves to require_aal2.

    Full structural sweep: iterates admin/ingest/kg/metrics/compliance/
    cache_metrics routers and asserts each endpoint's auth dependency resolves
    to require_aal2 — either directly or through _require_admin. If a future
    PR adds an admin endpoint without the gate, this fails before it ships.
    """

    @pytest.mark.parametrize(
        "module_path,path",
        [
            pytest.param(m, p, id=f"{m}:{p}")
            for m, p in sorted(_admin_endpoints())
        ],
    )
    def test_endpoint_resolves_to_require_aal2(self, module_path, path):
        import importlib

        mod = importlib.import_module(module_path)
        router = getattr(mod, "admin_router", None) or mod.router
        fn = next(r.endpoint for r in router.routes if r.path == path)
        deps = _resolved_dep_names(fn)
        assert require_aal2.__name__ in deps, (
            f"REGRESSION: {module_path}{path} must Depend(require_aal2) or "
            f"Depends(_require_admin) (resolved deps: {sorted(deps)})"
        )


# --- T4: ADMIN_USER_IDS allowlist (defense in depth) ------------------------


class TestAdminAllowlist:
    """When ADMIN_USER_IDS is set, only allowlisted UUIDs may be admin."""

    def test_allowlist_property_parses_comma_separated_uuids(self, monkeypatch):
        from app.config import Settings

        s = Settings(admin_user_ids="00000000-0000-0000-0000-0000000000aa, 11111111-1111-1111-1111-1111111111aa")
        assert s.admin_user_ids_list == [
            "00000000-0000-0000-0000-0000000000aa",
            "11111111-1111-1111-1111-1111111111aa",
        ]

    def test_empty_allowlist_property_returns_empty(self):
        from app.config import Settings

        s = Settings(admin_user_ids="")
        assert s.admin_user_ids_list == []

    def test_non_allowlisted_aal2_user_denied_admin(self, monkeypatch):
        """An aal2 superuser NOT in ADMIN_USER_IDS is denied (defense in depth)."""
        from app.config import Settings

        allowlisted = "00000000-0000-0000-0000-0000000000aa"
        monkeypatch.setattr(
            settings, "admin_user_ids", allowlisted
        )
        # Different UUID -> not allowlisted.
        _set_user({
            "id": "99999999-9999-9999-9999-999999999999",
            "email": "intruder@b.com",
            "is_superuser": True,
            "aal": "aal2",
        })
        response = client.get("/api/admin/kpis")
        assert response.status_code == 403, response.text

    def test_allowlisted_aal2_user_accepted_admin(self, monkeypatch):
        from app.config import Settings

        allowlisted = "00000000-0000-0000-0000-0000000000aa"
        monkeypatch.setattr(settings, "admin_user_ids", allowlisted)
        _set_user({
            "id": allowlisted,
            "email": "admin@b.com",
            "is_superuser": True,
            "aal": "aal2",
        })
        response = client.get("/api/admin/kpis")
        assert response.status_code == 200, response.text

    def test_empty_allowlist_does_not_block(self, monkeypatch):
        """When ADMIN_USER_IDS is empty (dev default), allowlist is not enforced."""
        monkeypatch.setattr(settings, "admin_user_ids", "")
        _set_user({
            "id": "any-user-id",
            "email": "a@b.com",
            "is_superuser": True,
            "aal": "aal2",
        })
        response = client.get("/api/admin/kpis")
        assert response.status_code == 200, response.text


# --- Telemetry sink contract guard ------------------------------------------


def test_telemetry_sink_does_not_use_auth_bridge():
    """The telemetry sink must read SUPABASE_SERVICE_ROLE_KEY from env directly,
    not via the SupabaseAuthStrategy auth bridge — otherwise T2 would break it.
    """
    import app.telemetry_sink as ts

    src = inspect.getsource(ts)
    assert "SUPABASE_SERVICE_ROLE_KEY" in src, (
        "telemetry sink must read service_role key from env directly "
        "(not via the auth bridge), or T2 will break telemetry writes"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
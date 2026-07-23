"""Regression tests for authorization / IDOR fixes.

These tests lock in the fixes for:
  - chat_stream_poll_idor:   GET /api/chat/stream/{job_id} requires auth + ownership
  - job_routes_idor:         GET/DELETE /api/jobs/{job_id} require auth + ownership
  - concept_graph_noauth:    GET /admin/concept-graph requires admin
  - circuit_breaker_reset_noauth / circuit_breaker_status_leak
  - debug_headers_noauth
  - cache_metrics admin gate

If any of these endpoints regress to unauthenticated access, these tests fail
and block deploy. Do not weaken the assertions to make them pass — re-add
the auth dependency in the endpoint instead.
"""
from __future__ import annotations

import inspect

import pytest
from fastapi import Depends

from services.auth_service import get_current_user_from_supabase, get_optional_user


def _dependency_names(func) -> set[str]:
    """Return the set of dependency callables wired into a FastAPI route function."""
    sig = inspect.signature(func)
    names: set[str] = set()
    for param in sig.parameters.values():
        default = param.default
        if isinstance(default, type(Depends())) or getattr(default, "dependency", None):
            dep = getattr(default, "dependency", None)
            if dep is not None:
                names.add(getattr(dep, "__name__", str(dep)))
    return names


def _requires_supabase_user(func) -> bool:
    deps = _dependency_names(func)
    return get_current_user_from_supabase.__name__ in deps


def _requires_identity(func) -> bool:
    """True if the route resolves *some* caller identity: either the strict
    Supabase-only dependency, or get_optional_user — which allows anonymous
    callers but relies on resolve_anon_identity() to give each one a distinct
    per-session identity, so ownership checks stay meaningful. Callers of this
    helper must separately verify resolve_anon_identity() is actually wired in
    when get_optional_user is used — see test_job_routes_require_auth_and_ownership."""
    deps = _dependency_names(func)
    return bool(deps & {get_current_user_from_supabase.__name__, get_optional_user.__name__})


# --- Individual endpoint guards ---------------------------------------------


def test_chat_stream_poll_requires_auth():
    from app.api.chat import chat_stream_poll
    assert _requires_identity(chat_stream_poll), (
        "REGRESSION: chat_stream_poll must Depend on get_current_user_from_supabase "
        "or get_optional_user, and verify job.user_id == user.id (IDOR fix)."
    )
    src = inspect.getsource(chat_stream_poll)
    assert "user_id" in src and "get_job" in src, (
        "chat_stream_poll must fetch job metadata and compare user_id before streaming."
    )
    if get_current_user_from_supabase.__name__ not in _dependency_names(chat_stream_poll):
        assert "resolve_anon_identity" in src, (
            "chat_stream_poll uses get_optional_user (anonymous allowed) but doesn't call "
            "resolve_anon_identity() — every anonymous caller would share user_id='anonymous', "
            "reopening the IDOR (any incognito user could poll any other's job)."
        )


def test_job_routes_require_auth_and_ownership():
    from app.api.job_routes import cancel_job, get_job
    for fn in (get_job, cancel_job):
        assert _requires_identity(fn), (
            f"REGRESSION: {fn.__name__} must Depend on get_current_user_from_supabase "
            f"or get_optional_user (IDOR fix)."
        )
        src = inspect.getsource(fn)
        assert "user_id" in src, (
            f"{fn.__name__} must compare job.user_id to authenticated user."
        )
        if get_current_user_from_supabase.__name__ not in _dependency_names(fn):
            assert "resolve_anon_identity" in src, (
                f"{fn.__name__} uses get_optional_user but doesn't call resolve_anon_identity() "
                f"— reopens the anonymous-id-collision IDOR."
            )


def test_concept_graph_requires_admin():
    from app.api.chat import get_concept_graph
    assert _requires_supabase_user(get_concept_graph), (
        "REGRESSION: /admin/concept-graph must require auth."
    )
    src = inspect.getsource(get_concept_graph)
    assert "is_superuser" in src, "/admin/concept-graph must enforce is_superuser."


def test_circuit_breaker_endpoints_admin_only():
    from app.api.health import circuit_breaker_reset_endpoint, circuit_breaker_status, debug_headers
    for fn in (circuit_breaker_status, circuit_breaker_reset_endpoint, debug_headers):
        assert _requires_supabase_user(fn), (
            f"REGRESSION: {fn.__name__} must require auth."
        )
        src = inspect.getsource(fn)
        assert "is_superuser" in src or "_require_admin" in src, (
            f"{fn.__name__} must enforce admin role."
        )


def test_cache_metrics_admin_only():
    from app.api.cache_metrics import cache_metrics
    assert _requires_supabase_user(cache_metrics), (
        "REGRESSION: /api/metrics/cache must require auth."
    )
    src = inspect.getsource(cache_metrics)
    assert "is_superuser" in src, "/api/metrics/cache must enforce is_superuser."


# --- Broad sweep: no route under /admin or /api/jobs may be anonymous -------


def test_no_admin_route_is_anonymous():
    """Sweep the FastAPI app: every /admin/* and /api/admin/* route must require
    get_current_user_from_supabase (no anonymous access, full stop). Every
    /api/jobs/* route may instead use get_optional_user (anonymous allowed for
    incognito mode), but only if resolve_anon_identity() is also wired in —
    otherwise every anonymous caller collapses onto the same user_id='anonymous'
    and can read/cancel any other anonymous caller's job (IDOR)."""
    from app.main import app  # imports the built app

    offenders: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        if not endpoint:
            continue
        is_admin_route = path.startswith("/admin") or path.startswith("/api/admin")
        is_job_route = path.startswith("/api/jobs")
        if not (is_admin_route or is_job_route):
            continue

        deps = _dependency_names(endpoint)
        try:
            src = inspect.getsource(endpoint)
        except (OSError, TypeError):
            src = ""
        has_supabase_dep = get_current_user_from_supabase.__name__ in deps or get_current_user_from_supabase.__name__ in src
        has_optional_dep = get_optional_user.__name__ in deps or get_optional_user.__name__ in src

        if is_admin_route:
            if not has_supabase_dep:
                offenders.append(f"{path} -> {endpoint.__name__} (missing get_current_user_from_supabase)")
        else:
            if not (has_supabase_dep or has_optional_dep):
                offenders.append(f"{path} -> {endpoint.__name__} (missing auth dependency entirely)")
            elif has_optional_dep and not has_supabase_dep and "resolve_anon_identity" not in src:
                offenders.append(
                    f"{path} -> {endpoint.__name__} (get_optional_user without resolve_anon_identity — anonymous id collision)"
                )

    assert not offenders, (
        "REGRESSION: the following admin/job routes are missing proper auth/identity:\n  - "
        + "\n  - ".join(offenders)
    )


def test_job_routes_owns_job_logic():
    from app.api.job_routes import _owns_job
    
    # Matching and non-empty -> True
    assert _owns_job({"user_id": "usr_123"}, {"id": "usr_123"}) is True
    
    # Mismatched -> False
    assert _owns_job({"user_id": "usr_123"}, {"id": "usr_456"}) is False
    
    # Empty user_id -> False
    assert _owns_job({"user_id": ""}, {"id": "usr_123"}) is False
    assert _owns_job({"user_id": None}, {"id": "usr_123"}) is False
    
    # Empty user.id -> False
    assert _owns_job({"user_id": "usr_123"}, {"id": ""}) is False
    assert _owns_job({"user_id": "usr_123"}, {"id": None}) is False
    
    # Both empty/None -> False
    assert _owns_job({"user_id": ""}, {"id": ""}) is False
    assert _owns_job({"user_id": None}, {"id": None}) is False
    assert _owns_job({}, {}) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


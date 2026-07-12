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

from services.auth_service import get_current_user_from_supabase


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
    return get_current_user_from_supabase.__name__ in _dependency_names(func)


# --- Individual endpoint guards ---------------------------------------------


def test_chat_stream_poll_requires_auth():
    from app.api.chat import chat_stream_poll
    assert _requires_supabase_user(chat_stream_poll), (
        "REGRESSION: chat_stream_poll must Depend on get_current_user_from_supabase "
        "and verify job.user_id == user.id (IDOR fix)."
    )
    src = inspect.getsource(chat_stream_poll)
    assert "user_id" in src and "get_job" in src, (
        "chat_stream_poll must fetch job metadata and compare user_id before streaming."
    )


def test_job_routes_require_auth_and_ownership():
    from app.api.job_routes import cancel_job, get_job
    for fn in (get_job, cancel_job):
        assert _requires_supabase_user(fn), (
            f"REGRESSION: {fn.__name__} must Depend on get_current_user_from_supabase (IDOR fix)."
        )
        src = inspect.getsource(fn)
        assert "user_id" in src, (
            f"{fn.__name__} must compare job.user_id to authenticated user."
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
    """Sweep the FastAPI app and assert every /admin/* and /api/jobs/* route
    has a get_current_user_from_supabase dependency somewhere in its chain."""
    from app.main import app  # imports the built app

    offenders: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        if not endpoint:
            continue
        if not (path.startswith("/admin") or path.startswith("/api/admin") or path.startswith("/api/jobs")):
            continue
        # Aggregate dependency names by walking the route's dependant tree.
        deps = _dependency_names(endpoint)
        # Fallback: also check the source for the dep name (covers decorators/wrappers).
        try:
            src = inspect.getsource(endpoint)
        except (OSError, TypeError):
            src = ""
        if get_current_user_from_supabase.__name__ not in deps and \
           get_current_user_from_supabase.__name__ not in src:
            offenders.append(f"{path} -> {endpoint.__name__}")
    assert not offenders, (
        "REGRESSION: the following admin/job routes are missing auth:\n  - "
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


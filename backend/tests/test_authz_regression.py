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
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Depends, HTTPException

from services.auth_service import (
    get_current_user_from_supabase,
    get_optional_user,
    require_aal2,
)


def _mock_request(session_id: str | None = None):
    """Minimal Request stand-in exposing only headers.get('X-Session-Id')."""
    req = MagicMock()
    req.headers.get.side_effect = lambda key, default=None: (
        session_id if key == "X-Session-Id" else default
    )
    return req


def _mock_container(job_owner: str | None):
    """Container whose job_queue.get_job returns a job owned by ``job_owner``
    (or None to simulate a missing job). cancel_job always succeeds."""
    container = MagicMock()
    container.job_queue = MagicMock()
    job = {"user_id": job_owner, "id": "job1"} if job_owner is not None else None
    container.job_queue.get_job = AsyncMock(return_value=job)
    container.job_queue.cancel_job = AsyncMock(return_value=True)
    container.job_queue.get_request_data = AsyncMock(return_value={})
    return container


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
    # P1-SEC-1: admin endpoints now depend on require_aal2 or the module-level
    # _require_admin dependency (admin.py/compliance.py), both of which compose
    # get_current_user_from_supabase; require_aal2 additionally enforces MFA.
    # The _require_admin -> require_aal2 resolution is locked by
    # test_p1_sec1_admin_aal2.py::TestAllAdminEndpointsAal2Gated.
    return (
        get_current_user_from_supabase.__name__ in deps
        or require_aal2.__name__ in deps
        or "_require_admin" in deps
    )


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


@pytest.mark.asyncio
async def test_chat_stream_poll_enforces_ownership():
    """Behavioral IDOR guard for GET /api/chat/stream/{job_id}: a non-owner gets
    404 (no existence disclosure), an unscoped anonymous caller gets 400, and two
    anonymous sessions are isolated. All denial branches raise before any Redis
    I/O, so no live infra is needed to assert them.

    Replaces the old inspect.getsource() substring checks, which passed for any
    handler that merely mentioned "user_id"/"resolve_anon_identity" in its source
    without actually enforcing ownership.
    """
    from app.api.chat import chat_stream_poll

    # Cheap wiring guard (signature inspection, not source-grep).
    assert _requires_identity(chat_stream_poll)

    container = _mock_container(job_owner="usr_A")

    # Authenticated non-owner -> 404.
    with pytest.raises(HTTPException) as exc:
        await chat_stream_poll("job1", _mock_request(), container=container, user={"id": "usr_B"})
    assert exc.value.status_code == 404

    # Anonymous with no session id -> 400 (unscoped identity rejected).
    with pytest.raises(HTTPException) as exc:
        await chat_stream_poll(
            "job1", _mock_request(session_id=None), container=container,
            user={"id": "anonymous", "is_anonymous": True},
        )
    assert exc.value.status_code == 400

    # Anonymous session isolation: caller in session anon:s2 cannot read anon:s1's job.
    # Uses the bare "anon:<id>" form — the dev/test escape hatch (IS_PRODUCTION=false).
    # In production the only sanctioned path is the signed token from
    # POST /api/auth/anon-session; see test_anon_session_signed.py.
    anon_container = _mock_container(job_owner="anon:s1")
    with pytest.raises(HTTPException) as exc:
        await chat_stream_poll(
            "job1", _mock_request(session_id="anon:s2"), container=anon_container,
            user={"id": "anonymous", "is_anonymous": True},
        )
    assert exc.value.status_code == 404
    # TODO: the owner-match success path streams from Redis (aioredis.from_url) and
    # needs a live Redis to assert the 200/SSE branch — only denials covered here.


@pytest.mark.asyncio
async def test_job_routes_enforce_ownership():
    """Behavioral IDOR guard for GET/DELETE /api/jobs/{job_id}: the owner succeeds,
    a non-owner gets 404, an unscoped anonymous caller gets 400, and anonymous
    sessions are isolated. get_job/cancel_job are fully driveable with mocks (no
    external infra), so both allow and deny branches are asserted directly.

    Replaces the old inspect.getsource() substring checks."""
    from app.api.job_routes import cancel_job, get_job

    for fn in (get_job, cancel_job):
        assert _requires_identity(fn)

        container = _mock_container(job_owner="usr_A")

        # Owner -> success (get_job returns the job; cancel_job returns a status dict).
        result = await fn("job1", _mock_request(), container=container, user={"id": "usr_A"})
        assert result is not None

        # Authenticated non-owner -> 404.
        with pytest.raises(HTTPException) as exc:
            await fn("job1", _mock_request(), container=container, user={"id": "usr_B"})
        assert exc.value.status_code == 404, fn.__name__

        # Unscoped anonymous -> 400.
        with pytest.raises(HTTPException) as exc:
            await fn(
                "job1", _mock_request(session_id=None), container=container,
                user={"id": "anonymous", "is_anonymous": True},
            )
        assert exc.value.status_code == 400, fn.__name__

        # Anonymous session isolation: session anon:s2 cannot touch anon:s1's job.
        # Uses the bare "anon:<id>" form — the dev/test escape hatch
        # (IS_PRODUCTION=false). In production the sanctioned path is the
        # signed token; see test_anon_session_signed.py.
        anon_container = _mock_container(job_owner="anon:s1")
        with pytest.raises(HTTPException) as exc:
            await fn(
                "job1", _mock_request(session_id="anon:s2"), container=anon_container,
                user={"id": "anonymous", "is_anonymous": True},
            )
        assert exc.value.status_code == 404, fn.__name__


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
        has_supabase_dep = (
            get_current_user_from_supabase.__name__ in deps
            or get_current_user_from_supabase.__name__ in src
            or require_aal2.__name__ in deps
            or require_aal2.__name__ in src
            or "_require_admin" in deps  # P1-SEC-1: composes require_aal2 (MFA)
        )
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


def test_require_scoped_identity_rejects_unscoped_anonymous():
    """An anonymous caller with no session_id must be rejected (400), not silently
    treated as a valid identity — otherwise every session_id-less anonymous
    caller collapses onto the same "anonymous" id and can access each other's
    jobs (job ownership is a plain string-equality check on user_id)."""
    from fastapi import HTTPException

    from services.auth_service import require_scoped_identity

    with pytest.raises(HTTPException) as exc_info:
        require_scoped_identity({"id": "anonymous", "email": None, "is_anonymous": True})
    assert exc_info.value.status_code == 400

    # Scoped anonymous (resolve_anon_identity applied a session_id) is fine.
    require_scoped_identity({"id": "anon:some-session-uuid", "email": None, "is_anonymous": True})

    # Authenticated users are never touched by this check.
    require_scoped_identity({"id": "real-user-id", "email": "a@b.com"})


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


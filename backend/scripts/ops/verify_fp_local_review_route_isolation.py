#!/usr/bin/env python3
"""Prove the owner-only local-review routes refuse in the two forbidden modes.

Runs the **real** status and query routes through FastAPI's TestClient, in four configurations:

1. the flag on, not production  -> an authenticated local admin can reach both;
2. the flag **off**             -> query HTTP 404, ``local_review_mode_disabled``;
3. **production** mode         -> query HTTP 404, ``local_review_mode_refuses_production``;
4. both                        -> query HTTP 404.

It never contacts Qdrant, never touches Redis and never mutates the
environment: ``is_production`` / ``first_person_local_review_enabled`` are
patched on the in-process settings object only.

Exit codes
----------
=====  ===================================================================
0      Every configuration behaved exactly as required.
1      A configuration behaved wrongly (the route was reachable when it must
       not have been, or it refused when it must have served).
=====  ===================================================================

Usage
-----
    python -m scripts.ops.verify_fp_local_review_route_isolation
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _probe(enabled: bool, production: bool) -> dict[str, object]:
    from app.api import first_person_local_review as route
    from app.config import settings
    from services.auth_service import get_current_user_from_supabase

    settings.first_person_local_review_enabled = enabled
    settings.is_production = production
    configured_admin_ids = getattr(settings, "admin_user_ids_list", None) or []
    probe_admin_id = configured_admin_ids[0] if configured_admin_ids else "local-review-probe-admin"
    settings.admin_user_ids_list = [probe_admin_id]

    app = FastAPI()
    app.include_router(route.router, prefix="/api")

    async def _local_admin() -> dict[str, object]:
        return {"id": probe_admin_id, "is_superuser": True, "aal": "aal2"}

    app.dependency_overrides[get_current_user_from_supabase] = _local_admin
    client = TestClient(app)
    query_response = client.post(
        "/api/first-person/local-review/query",
        json={"query": "What is meditation?", "max_clips": 1},
    )
    status_response = client.get("/api/first-person/local-review/status")
    query_body: object
    try:
        query_body = query_response.json()
    except ValueError:
        query_body = query_response.text
    status_body: object
    try:
        status_body = status_response.json()
    except ValueError:
        status_body = status_response.text
    return {
        "status_code": query_response.status_code,
        "body": query_body,
        "query_status_code": query_response.status_code,
        "query_body": query_body,
        "status_status_code": status_response.status_code,
        "status_body": status_body,
    }


def _probe_aal1_superuser() -> dict[str, object]:
    """Verify AAL1 is rejected before either handler can build the service."""
    from app.api import first_person_local_review as route
    from app.config import settings
    from services.auth_service import get_current_user_from_supabase

    settings.first_person_local_review_enabled = True
    settings.is_production = False
    previous_builder = route._build_service

    def _must_not_build_service() -> object:
        raise AssertionError("AAL1 authorization must run before _build_service")

    route._build_service = _must_not_build_service
    try:
        app = FastAPI()
        app.include_router(route.router, prefix="/api")

        async def _aal1_superuser() -> dict[str, object]:
            return {"id": "aal1-local-admin", "is_superuser": True, "aal": "aal1"}

        app.dependency_overrides[get_current_user_from_supabase] = _aal1_superuser
        client = TestClient(app, raise_server_exceptions=False)
        query_response = client.post(
            "/api/first-person/local-review/query",
            json={"query": "What is meditation?", "max_clips": 1},
        )
        status_response = client.get("/api/first-person/local-review/status")
        return {
            "query_status_code": query_response.status_code,
            "status_status_code": status_response.status_code,
        }
    finally:
        route._build_service = previous_builder


def _probe_allowlist_denial() -> dict[str, object]:
    """Verify an AAL2 superuser outside the allowlist cannot reach either route."""
    from app.api import first_person_local_review as route
    from app.config import settings
    from services.auth_service import get_current_user_from_supabase

    settings.first_person_local_review_enabled = True
    settings.is_production = False
    settings.admin_user_ids_list = ["allowlisted-local-admin"]
    previous_builder = route._build_service

    def _must_not_build_service() -> object:
        raise AssertionError("allowlist authorization must run before _build_service")

    route._build_service = _must_not_build_service
    try:
        app = FastAPI()
        app.include_router(route.router, prefix="/api")

        async def _non_allowlisted_superuser() -> dict[str, object]:
            return {"id": "not-allowlisted", "is_superuser": True, "aal": "aal2"}

        app.dependency_overrides[get_current_user_from_supabase] = _non_allowlisted_superuser
        client = TestClient(app, raise_server_exceptions=False)
        query_response = client.post(
            "/api/first-person/local-review/query",
            json={"query": "What is meditation?", "max_clips": 1},
        )
        status_response = client.get("/api/first-person/local-review/status")
        return {
            "query_status_code": query_response.status_code,
            "status_status_code": status_response.status_code,
        }
    finally:
        route._build_service = previous_builder


def main(argv: list[str] | None = None) -> int:
    results: dict[str, object] = {}
    failures: list[str] = []

    aal1 = _probe_aal1_superuser()
    results["aal1_superuser"] = aal1
    if aal1["query_status_code"] != 403:
        failures.append(f"aal1_superuser query: expected 403, got {aal1['query_status_code']}")
    if aal1["status_status_code"] != 403:
        failures.append(f"aal1_superuser status: expected 403, got {aal1['status_status_code']}")

    allowlist_denial = _probe_allowlist_denial()
    results["allowlist_denial"] = allowlist_denial
    if allowlist_denial["query_status_code"] != 403:
        failures.append(
            f"allowlist_denial query: expected 403, got {allowlist_denial['query_status_code']}"
        )
    if allowlist_denial["status_status_code"] != 403:
        failures.append(
            f"allowlist_denial status: expected 403, got {allowlist_denial['status_status_code']}"
        )

    allowed = _probe(enabled=True, production=False)
    results["flag_on_local"] = allowed
    if allowed["query_status_code"] not in (200, 503):
        failures.append(
            f"flag_on_local query: expected 200 or a startup failure (503), got {allowed['query_status_code']}"
        )
    if allowed["status_status_code"] not in (200, 503):
        failures.append(
            f"flag_on_local status: expected 200 or a startup failure (503), got {allowed['status_status_code']}"
        )

    disabled = _probe(enabled=False, production=False)
    results["flag_off_local"] = disabled
    if disabled["query_status_code"] != 404:
        failures.append(f"flag_off_local query: expected 404, got {disabled['query_status_code']}")
    if (
        disabled["status_status_code"] != 200
        or not isinstance(disabled["status_body"], dict)
        or disabled["status_body"].get("available") is not False
    ):
        failures.append("flag_off_local status: expected HTTP 200 with available=false")

    production = _probe(enabled=True, production=True)
    results["flag_on_production"] = production
    if production["query_status_code"] != 404:
        failures.append(
            f"flag_on_production query: expected 404, got {production['query_status_code']}"
        )
    if (
        production["status_status_code"] != 200
        or not isinstance(production["status_body"], dict)
        or production["status_body"].get("available") is not False
    ):
        failures.append("flag_on_production status: expected HTTP 200 with available=false")

    both = _probe(enabled=False, production=True)
    results["flag_off_production"] = both
    if both["query_status_code"] != 404:
        failures.append(f"flag_off_production query: expected 404, got {both['query_status_code']}")
    if (
        both["status_status_code"] != 200
        or not isinstance(both["status_body"], dict)
        or both["status_body"].get("available") is not False
    ):
        failures.append("flag_off_production status: expected HTTP 200 with available=false")

    payload = {
        "schema": "fp-local-review-route-isolation-v1",
        "container": os.environ.get("HOSTNAME", ""),
        "results": results,
        "failures": failures,
        "passed": not failures,
    }
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

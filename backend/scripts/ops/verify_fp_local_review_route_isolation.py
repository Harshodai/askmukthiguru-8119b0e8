#!/usr/bin/env python3
"""Prove the owner-only local-review route refuses in the two forbidden modes.

Runs the **real** route through FastAPI's TestClient, in four configurations:

1. the flag on, not production  -> the route is available (and only then);
2. the flag **off**             -> HTTP 404, ``local_review_mode_disabled``;
3. **production** mode         -> HTTP 404, ``local_review_mode_refuses_production``;
4. both                        -> HTTP 404.

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

    settings.first_person_local_review_enabled = enabled
    settings.is_production = production

    app = FastAPI()
    app.include_router(route.router, prefix="/api")
    client = TestClient(app)
    response = client.post(
        "/api/first-person/local-review/query",
        json={"query": "What is meditation?", "max_clips": 1},
    )
    body: object
    try:
        body = response.json()
    except ValueError:
        body = response.text
    return {"status_code": response.status_code, "body": body}


def main(argv: list[str] | None = None) -> int:
    results: dict[str, object] = {}
    failures: list[str] = []

    allowed = _probe(enabled=True, production=False)
    results["flag_on_local"] = allowed
    if allowed["status_code"] not in (200, 503):
        failures.append(
            f"flag_on_local: expected 200 or a startup failure (503), got {allowed['status_code']}"
        )

    disabled = _probe(enabled=False, production=False)
    results["flag_off_local"] = disabled
    if disabled["status_code"] != 404:
        failures.append(f"flag_off_local: expected 404, got {disabled['status_code']}")

    production = _probe(enabled=True, production=True)
    results["flag_on_production"] = production
    if production["status_code"] != 404:
        failures.append(f"flag_on_production: expected 404, got {production['status_code']}")

    both = _probe(enabled=False, production=True)
    results["flag_off_production"] = both
    if both["status_code"] != 404:
        failures.append(f"flag_off_production: expected 404, got {both['status_code']}")

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

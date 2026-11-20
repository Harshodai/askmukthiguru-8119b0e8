#!/usr/bin/env python3
"""Qdrant scoped-token preflight (2026-11-19 never-again guard). Prints no secrets.

The production backend reads Qdrant with a scoped JWT (corpus read-only). A collection
added to the serving config but not to the token's ``access`` claim ships unreadable:
every turn abstains. This decodes the token's claims (signature is Qdrant's job) and
fails when any collection the backend is configured to read is not readable, or the
token is expired. Claim format (qdrant.tech/documentation/security): ``access`` is a
global mode string ("r" read, "m" manage) or a list of ``{collection, access: r|rw}``;
an absent ``access`` claim means manage.

Usage: QDRANT_API_KEY=... FIRST_PERSON_COLLECTION=... check_qdrant_token_scope.py
       [--require NAME ...]. Exit 0 ok, 1 problem.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from collections.abc import Mapping

# Settings that name a collection the backend reads at serve time.
COLLECTION_VARS = (
    "FIRST_PERSON_COLLECTION",
    "FIRST_PERSON_CONTEXT_COLLECTION",
    "FIRST_PERSON_ACTIVE_COLLECTION",
    "QDRANT_COLLECTION",
)
_READ_MODES = {"r", "rw", "m"}


def _claims(token: str) -> dict | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None  # a static API key, not a JWT: global access
    try:
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None
    return claims if isinstance(claims, dict) else None


def scope_problems(
    env: Mapping[str, str], required: list[str] | None = None, now: float | None = None
) -> list[str]:
    token = str(env.get("QDRANT_API_KEY", "") or "")
    wanted = sorted({str(env[v]).strip() for v in COLLECTION_VARS if str(env.get(v, "")).strip()} | set(required or []))
    claims = _claims(token) if token else None
    if claims is None:
        return []  # no key or a static key: not a scoped token
    problems = []
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and exp < (now if now is not None else time.time()):
        problems.append("QDRANT_API_KEY token is expired")
    access = claims.get("access", "m")
    if isinstance(access, str):
        if access not in _READ_MODES:
            problems.append(f"token global access {access!r} cannot read")
        return problems
    readable = {
        str(e.get("collection"))
        for e in access
        if isinstance(e, dict) and str(e.get("access")) in _READ_MODES
    }
    problems += [f"collection {c!r} is configured but not readable by the token" for c in wanted if c not in readable]
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--require", action="append", default=[], help="extra collection to require")
    args = parser.parse_args(argv)
    problems = scope_problems(os.environ, args.require)
    for p in problems:
        print(f"ERROR: {p}", file=sys.stderr)
    if not problems:
        print("Qdrant token scope covers every configured collection.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Qdrant scoped-token guard: a configured collection must be readable by the token."""

from __future__ import annotations

import base64
import json

from scripts.ops.check_qdrant_token_scope import scope_problems


def _jwt(claims: dict) -> str:
    b = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{b}.sig"


_ENV = {"FIRST_PERSON_COLLECTION": "first_person_v12", "QDRANT_COLLECTION": "spiritual_wisdom_contextual"}


def test_new_collection_missing_from_token_is_caught():
    token = _jwt({"access": [{"collection": "spiritual_wisdom_contextual", "access": "r"}]})
    problems = scope_problems({**_ENV, "QDRANT_API_KEY": token})
    assert problems == ["collection 'first_person_v12' is configured but not readable by the token"]
    assert token not in " ".join(problems)


def test_all_configured_collections_readable_passes():
    token = _jwt({"access": [{"collection": c, "access": "r"} for c in _ENV.values()]})
    assert scope_problems({**_ENV, "QDRANT_API_KEY": token}) == []


def test_global_read_manage_and_static_keys_pass():
    for claims in ({"access": "r"}, {"access": "m"}, {}):
        assert scope_problems({**_ENV, "QDRANT_API_KEY": _jwt(claims)}) == []
    assert scope_problems({**_ENV, "QDRANT_API_KEY": "static-key"}) == []


def test_first_person_active_collection_is_checked():
    token = _jwt({"access": [{"collection": "first_person_v10", "access": "r"}]})
    problems = scope_problems({"FIRST_PERSON_ACTIVE_COLLECTION": "first_person_v12_shadow", "QDRANT_API_KEY": token})
    assert problems == ["collection 'first_person_v12_shadow' is configured but not readable by the token"]


def test_expired_token_and_extra_requirement():
    token = _jwt({"exp": 100, "access": [{"collection": c, "access": "r"} for c in _ENV.values()]})
    assert scope_problems({**_ENV, "QDRANT_API_KEY": token}, now=200) == ["QDRANT_API_KEY token is expired"]
    assert scope_problems({**_ENV, "QDRANT_API_KEY": token}, ["memories"], now=50) == [
        "collection 'memories' is configured but not readable by the token"
    ]

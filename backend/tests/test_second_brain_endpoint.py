"""Regression test for the Second Brain Mode-B unlock mismatch.

test_second_brain.py exercises SecondBrainService directly with the same
raw passphrase string fed to both enable_session_unlock() and unlock() —
that round-trips fine and never exercises the actual client/server
boundary. Over HTTP, src/lib/secondBrainApi.ts sends the raw passphrase
only once, in the POST /brain/vault/session-unlock body; every later
request (add/list/recall/export) sends only SHA-256(passphrase) via the
X-Brain-Unlock header. Simulates that real request shape through the
router via TestClient.
"""

from __future__ import annotations

import hashlib
import os

os.environ.setdefault("BRAIN_KEK", "dGVzdC1vcGVyYXRvci1rZWstMzItYnl0ZXMteHh4eHg=")

from unittest.mock import MagicMock  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, get_current_user_from_supabase  # noqa: E402
from tests.test_second_brain import make_svc  # noqa: E402

client = TestClient(app)


def _user():
    return {"id": "user-http-1", "email": "u@example.com", "is_superuser": False}


def test_session_unlock_then_add_item_round_trips_over_http():
    app.dependency_overrides[get_current_user_from_supabase] = _user
    svc = make_svc()
    container = MagicMock()
    container.second_brain = svc
    try:
        import app.api.second_brain as second_brain_router

        original_get_container = second_brain_router.get_container
        second_brain_router.get_container = lambda: container
        try:
            passphrase = "correct horse battery staple"
            resp = client.post(
                "/api/brain/vault/session-unlock", json={"passphrase": passphrase}
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["wrap_mode"] == "session_unlock"

            salt = b"second_brain_vault_unlock_salt"
            derived = hashlib.pbkdf2_hmac(
                "sha256", passphrase.encode("utf-8"), salt, 600000
            ).hex()
            resp2 = client.post(
                "/api/brain/items",
                json={"kind": "reflection", "text": "hello"},
                headers={"X-Brain-Unlock": derived},
            )
            assert resp2.status_code == 200, resp2.text
            assert resp2.json()["id"]
        finally:
            second_brain_router.get_container = original_get_container
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)


def test_session_unlock_then_add_item_with_wrong_passphrase_still_rejected():
    app.dependency_overrides[get_current_user_from_supabase] = _user
    svc = make_svc()
    container = MagicMock()
    container.second_brain = svc
    try:
        import app.api.second_brain as second_brain_router

        original_get_container = second_brain_router.get_container
        second_brain_router.get_container = lambda: container
        try:
            client.post(
                "/api/brain/vault/session-unlock",
                json={"passphrase": "correct horse battery staple"},
            )
            salt = b"second_brain_vault_unlock_salt"
            wrong_derived = hashlib.pbkdf2_hmac(
                "sha256", b"guess", salt, 600000
            ).hex()
            resp = client.post(
                "/api/brain/items",
                json={"kind": "reflection", "text": "hello"},
                headers={"X-Brain-Unlock": wrong_derived},
            )
            assert resp.status_code == 403
        finally:
            second_brain_router.get_container = original_get_container
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)

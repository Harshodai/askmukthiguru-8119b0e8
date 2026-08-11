"""M5: behavioral tests for server-side signed anonymous session tokens.

Locks in:
  - POST /api/auth/anon-session issues a signed token (status 200).
  - The signed token resolves an anonymous identity via resolve_anon_identity.
  - Tampered signatures are rejected with 400.
  - Bare "anon:<id>" is rejected with 400 in production, accepted in dev.
  - The resolve step never trusts an unsigned id asserted by the client.

Invariant L-K3-1: comparisons use hmac.compare_digest (verified by code
inspection of verify_anon_session_token — these tests exercise behavior).
"""
from __future__ import annotations

import secrets

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from services.auth_service import (
    issue_anon_session_token,
    resolve_anon_identity,
    verify_anon_session_token,
)

client = TestClient(app)

_ANON_USER = {"id": "anonymous", "email": None, "is_anonymous": True}


def test_issue_anon_session_endpoint_returns_signed_token():
    """POST /api/auth/anon-session returns 200 with {session_id, token} where
    token contains a '.' (signed form) and session_id carries the anon: prefix."""
    resp = client.post("/api/auth/anon-session")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "session_id" in body and "token" in body
    assert body["session_id"].startswith("anon:")
    assert "." in body["token"], "issued token must be the signed form"


def test_signed_token_resolves_identity():
    """resolve_anon_identity accepts the server-issued signed token and
    rewrites user id to anon:<payload>."""
    issued = issue_anon_session_token()
    out = resolve_anon_identity(_ANON_USER, issued["token"])
    assert out["id"] == issued["session_id"]
    assert out["is_anonymous"] is True


def test_tampered_signature_rejected():
    """Flipping a character in the signature must yield 400 at resolve time."""
    issued = issue_anon_session_token()
    payload, _, sig = issued["token"].partition(".")
    # Flip one character in the signature. sig is base64url so each char is
    # in [A-Za-z0-9_-]; pick a different valid char deterministically.
    bad_char = "A" if sig[0] != "A" else "B"
    tampered = f"{payload}.{bad_char}{sig[1:]}"
    with pytest.raises(HTTPException) as exc:
        resolve_anon_identity(_ANON_USER, tampered)
    assert exc.value.status_code == 400


def test_tampered_payload_rejected():
    """Tampering with the payload (so the signature no longer matches) must
    yield 400 — prevents id-forgery by editing the payload directly."""
    issued = issue_anon_session_token()
    payload, _, sig = issued["token"].partition(".")
    bad_char = "A" if payload[0] != "A" else "B"
    tampered = f"{bad_char}{payload[1:]}.{sig}"
    with pytest.raises(HTTPException) as exc:
        resolve_anon_identity(_ANON_USER, tampered)
    assert exc.value.status_code == 400


def test_malformed_token_rejected():
    """Tokens with a '.' but empty halves, or that fail base64 decode, are
    rejected with 400. (Empty/whitespace session_id is NOT rejected here —
    resolve_anon_identity returns the unscoped 'anonymous' id, which
    require_scoped_identity catches downstream with its own 400.)"""
    for bad in ("nodothere", ".", "abc.", ".abc"):
        with pytest.raises(HTTPException) as exc:
            resolve_anon_identity(_ANON_USER, bad)
        assert exc.value.status_code == 400, repr(bad)


def test_bare_anon_id_rejected_in_production(monkeypatch):
    """In production, the bare anon:<id> form (no signature) must be rejected
    so a client cannot assert a victim's session id verbatim and become them."""
    import services.auth_service as auth_module

    monkeypatch.setattr(auth_module.settings, "is_production", True, raising=False)
    with pytest.raises(HTTPException) as exc:
        resolve_anon_identity(_ANON_USER, "anon:im-a-victim")
    assert exc.value.status_code == 400


def test_bare_anon_id_accepted_in_dev(monkeypatch):
    """In dev/test, the bare anon:<id> form still works as an escape hatch so
    existing tests that fabricate identities directly (without going through
    the issuance endpoint) keep passing."""
    import services.auth_service as auth_module

    monkeypatch.setattr(auth_module.settings, "is_production", False, raising=False)
    out = resolve_anon_identity(_ANON_USER, "anon:dev-session-id")
    assert out["id"] == "anon:dev-session-id"


def test_unsigned_non_anon_id_rejected_in_production(monkeypatch):
    """A raw session id without the anon: prefix is rejected in production
    even though it is not a bare anon: form — the only sanctioned path is the
    signed token."""
    import services.auth_service as auth_module

    monkeypatch.setattr(auth_module.settings, "is_production", True, raising=False)
    with pytest.raises(HTTPException) as exc:
        resolve_anon_identity(_ANON_USER, "raw-session-id")
    assert exc.value.status_code == 400


def test_authenticated_user_passes_through_unchanged():
    """Authenticated users are not subject to anon-token verification — even
    if a session_id is supplied, resolve_anon_identity returns the user as-is."""
    authed = {"id": "usr_123", "email": "a@b.com", "is_anonymous": False}
    issued = issue_anon_session_token()
    out = resolve_anon_identity(authed, issued["token"])
    assert out is authed
    assert out["id"] == "usr_123"


def test_issue_then_verify_roundtrip():
    """A freshly issued token verifies standalone (no HTTP) — sanity check of
    the issue/verify pair used by both the endpoint and the resolver."""
    issued = issue_anon_session_token()
    assert verify_anon_session_token(issued["token"]) == issued["session_id"]


def test_two_tokens_are_distinct():
    """Each issuance produces a fresh random payload — no reuse, so two
    incognito sessions get distinct identities."""
    a = issue_anon_session_token()
    b = issue_anon_session_token()
    assert a["session_id"] != b["session_id"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
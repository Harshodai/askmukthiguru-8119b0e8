"""One reason-coded, rate-limited line per failed bearer token (2026-11-28).

Live logs: 387 of 401 WARNING lines were one pair per failed login, with no way to tell a
stale token from an unknown key id. The auth OUTCOME must not change; only the logging.
"""

from __future__ import annotations

import logging
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

import services.auth_service as auth_svc
from services.auth_service import (
    SupabaseAuthStrategy,
    _auth_failure_suppressed_count,
    auth_failure_reason,
    get_optional_user,
)

_SECRET = "mock_jwt_secret_for_testing_12345"
_ISS = "https://abcdefghij.supabase.co/auth/v1"
_SENTINEL_EMAIL = "sentinel.person@example.com"
_SENTINEL_SUB = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def _pin(monkeypatch):
    monkeypatch.setattr(auth_svc.settings, "jwt_secret", _SECRET)
    monkeypatch.setattr(auth_svc.settings, "supabase_url", "https://abcdefghij.supabase.co")
    auth_svc._AUTH_FAIL_SEEN.clear()
    yield
    auth_svc._AUTH_FAIL_SEEN.clear()


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/api/chat", "headers": []})


def _hs256(**claims) -> str:
    payload = {
        "sub": _SENTINEL_SUB,
        "email": _SENTINEL_EMAIL,
        "role": "authenticated",
        "aud": auth_svc.settings.supabase_jwt_audience,
        "iss": _ISS,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    payload.update(claims)
    return jwt.encode(payload, _SECRET, algorithm="HS256")


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _auth_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "services.auth_service"]


# --- reason mapping, by exception TYPE ----------------------------------------------


@pytest.mark.parametrize(
    "exc,reason",
    [
        (jwt.ExpiredSignatureError("t"), "expired"),
        (jwt.ImmatureSignatureError("t"), "not_yet_valid"),
        (jwt.InvalidSignatureError("t"), "bad_signature"),  # subclass of DecodeError
        (jwt.InvalidIssuerError("t"), "bad_issuer"),
        (jwt.InvalidAudienceError("t"), "bad_audience"),
        (jwt.InvalidAlgorithmError("t"), "bad_algorithm"),
        (jwt.MissingRequiredClaimError("exp"), "missing_claim"),
        (jwt.DecodeError("t"), "malformed"),
        (jwt.PyJWKClientConnectionError("t"), "jwks_fetch_failed"),  # subclass of PyJWKClientError
        (jwt.PyJWKClientError("Unable to find a signing key"), "jwks_key_not_found"),
        (jwt.InvalidTokenError("t"), "invalid_token"),
        (RuntimeError("t"), "other"),
    ],
)
def test_reason_is_derived_from_the_exception_type(exc, reason):
    assert auth_failure_reason(exc) == reason


def test_reason_never_uses_the_exception_message():
    assert auth_failure_reason(jwt.DecodeError("eyJhbGciOi.SECRETPART.sig")) == "malformed"


# --- the line itself -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_bad_signature_logs_one_coded_line_and_returns_none(caplog):
    token = jwt.encode(
        {"iss": _ISS, "aud": "authenticated"},
        "another-secret-of-32-bytes-or-more!!",
        algorithm="HS256",
    )
    with caplog.at_level(logging.DEBUG):
        user = await SupabaseAuthStrategy().authenticate(_request(), _creds(token))
    assert user is None  # outcome unchanged
    lines = _auth_lines(caplog)
    assert len(lines) == 1
    assert "reason=bad_signature" in lines[0]
    assert "alg=HS256" in lines[0]
    assert "iss_host=abcdefghij.supabase.co" in lines[0]
    assert "suppressed=0" in lines[0]


@pytest.mark.asyncio
async def test_expired_token_still_raises_401_and_logs_reason(caplog):
    token = _hs256(exp=int(time.time()) - 10)
    with caplog.at_level(logging.DEBUG), pytest.raises(HTTPException) as info:
        await SupabaseAuthStrategy().authenticate(_request(), _creds(token))
    assert info.value.status_code == 401
    assert info.value.detail == "Token expired. Please sign in again."
    assert "reason=expired" in _auth_lines(caplog)[0]


@pytest.mark.asyncio
async def test_unknown_key_id_is_reported_with_kid_prefix_and_issuer_host(monkeypatch, caplog):
    key = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(
        {"iss": "https://stale-project.supabase.co/auth/v1", "aud": "authenticated"},
        key,
        algorithm="ES256",
        headers={"kid": "abcdefgh-ijklmnop-1234"},
    )

    class _Client:
        def get_signing_key_from_jwt(self, _token):
            raise jwt.PyJWKClientError(
                "Unable to find a signing key that matches: abcdefgh-ijklmnop-1234"
            )

    async def _client():
        return _Client()

    monkeypatch.setattr(auth_svc, "_get_jwks_client", _client)
    with caplog.at_level(logging.DEBUG):
        user = await SupabaseAuthStrategy().authenticate(_request(), _creds(token))
    assert user is None
    (line,) = _auth_lines(caplog)
    assert "reason=jwks_key_not_found" in line
    assert "alg=ES256" in line
    assert "kid=abcdefgh " in line  # first 8 characters only
    assert "ijklmnop" not in line
    assert "iss_host=stale-project.supabase.co" in line


@pytest.mark.asyncio
async def test_garbage_token_logs_unknown_tags(caplog):
    with caplog.at_level(logging.DEBUG):
        user = await SupabaseAuthStrategy().authenticate(_request(), _creds("not-a-jwt"))
    assert user is None
    (line,) = _auth_lines(caplog)
    assert "reason=malformed" in line and "iss_host=unknown" in line


@pytest.mark.asyncio
async def test_token_and_claims_never_reach_the_logs(caplog):
    good_shape_bad_sig = jwt.encode(
        {"sub": _SENTINEL_SUB, "email": _SENTINEL_EMAIL, "iss": _ISS, "aud": "authenticated"},
        "another-secret-of-32-bytes-or-more!!",
        algorithm="HS256",
    )
    expired = _hs256(exp=int(time.time()) - 10)
    with caplog.at_level(logging.DEBUG):
        await SupabaseAuthStrategy().authenticate(_request(), _creds(good_shape_bad_sig))
        with pytest.raises(HTTPException):
            await SupabaseAuthStrategy().authenticate(_request(), _creds(expired))
        await get_optional_user(_request(), _creds("x.y.z"))
    rendered = caplog.text
    for secret in (
        good_shape_bad_sig,
        expired,
        good_shape_bad_sig.split(".")[1],
        _SENTINEL_EMAIL,
        _SENTINEL_SUB,
    ):
        assert secret not in rendered


# --- rate limiting -------------------------------------------------------------------


def test_identical_failures_are_limited_to_one_per_minute_with_a_suppressed_count():
    key = ("jwks_key_not_found", "abcdefgh", "stale.supabase.co")
    assert _auth_failure_suppressed_count(key, now=1000.0) == 0
    assert _auth_failure_suppressed_count(key, now=1001.0) is None
    assert _auth_failure_suppressed_count(key, now=1030.0) is None
    assert _auth_failure_suppressed_count(key, now=1060.5) == 2  # next emitted line reports 2
    assert _auth_failure_suppressed_count(key, now=1061.0) is None  # counter restarted


def test_different_keys_are_limited_independently():
    assert _auth_failure_suppressed_count(("expired", "a", "h"), now=5.0) == 0
    assert _auth_failure_suppressed_count(("expired", "b", "h"), now=5.0) == 0


def test_the_limiter_map_is_bounded(monkeypatch):
    monkeypatch.setattr(auth_svc, "_AUTH_FAIL_MAX_KEYS", 8)
    for i in range(50):
        _auth_failure_suppressed_count(("expired", f"k{i}", "h"), now=1.0)
    assert len(auth_svc._AUTH_FAIL_SEEN) <= 8


@pytest.mark.asyncio
async def test_repeated_failures_log_once_and_the_outcome_is_unchanged(caplog):
    token = jwt.encode(
        {"iss": _ISS, "aud": "authenticated"},
        "another-secret-of-32-bytes-or-more!!",
        algorithm="HS256",
    )
    with caplog.at_level(logging.DEBUG):
        results = [
            await SupabaseAuthStrategy().authenticate(_request(), _creds(token)) for _ in range(5)
        ]
    assert results == [None] * 5
    assert len(_auth_lines(caplog)) == 1


# --- one line per failure through the dependency, anonymous fallback as before -------


@pytest.mark.asyncio
async def test_get_optional_user_falls_back_to_anonymous_with_one_warning(caplog):
    token = jwt.encode(
        {"iss": _ISS, "aud": "authenticated"},
        "another-secret-of-32-bytes-or-more!!",
        algorithm="HS256",
    )
    with caplog.at_level(logging.DEBUG):
        user = await get_optional_user(_request(), _creds(token))
    assert user == {"id": "anonymous", "email": None, "is_anonymous": True}
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert "reason=bad_signature" in warnings[0].getMessage()


@pytest.mark.asyncio
async def test_get_optional_user_logs_a_rejected_line_when_no_strategy_did(monkeypatch, caplog):
    async def _reject(self, request, credentials):
        raise HTTPException(status_code=401, detail="Authentication required or session expired")

    monkeypatch.setattr(auth_svc.auth_bridge.__class__, "get_user", _reject)
    with caplog.at_level(logging.DEBUG):
        user = await get_optional_user(_request(), _creds("a.b.c"))
    assert user["is_anonymous"] is True
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1 and "reason=rejected" in warnings[0]


@pytest.mark.asyncio
async def test_no_token_means_no_log_line(caplog):
    with caplog.at_level(logging.DEBUG):
        user = await get_optional_user(_request(), None)
    assert user["is_anonymous"] is True
    assert not [m for m in _auth_lines(caplog) if "auth failed" in m]

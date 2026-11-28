from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import re
import secrets
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import urlparse

import jwt
from anyio import Lock as AsyncLock
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import get_db
from models.user import User

settings = get_settings()
logger = logging.getLogger(__name__)


if not settings.jwt_secret:
    raise RuntimeError("CRITICAL: jwt_secret environment variable is missing. Halting application.")

# --- Internal FastAPI-Users Management ---


async def get_user_db(session: AsyncSession = Depends(get_db)):
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.jwt_secret
    verification_token_secret = settings.jwt_secret

    async def on_after_register(self, user: User, request: Request | None = None):
        logger.info(f"User {user.id} has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ):
        logger.info(f"Password reset token generated for user {user.id}")
        # TODO: Integrate with email delivery service (SendGrid, Resend, etc.)

    async def on_after_reset_password(self, user: User, request: Request | None = None):
        logger.info(f"Password reset completed for user {user.id}")


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="api/auth/jwt/login")


_fallback_private_pem: str | None = None
_fallback_public_pem: str | None = None


def _ensure_fallback_keys():
    global _fallback_private_pem, _fallback_public_pem
    if getattr(settings, "is_production", False):
        raise RuntimeError(
            "CRITICAL: jwt_private_key and jwt_public_key are required in production environment."
        )

    if _fallback_private_pem and _fallback_public_pem:
        return

    import fcntl
    import json
    import os
    import tempfile
    from pathlib import Path

    key_file = Path("data/dev_jwt_keys.json")
    lock_file = Path("data/dev_jwt_keys.json.lock")
    key_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    with open(lock_file, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            if _fallback_private_pem and _fallback_public_pem:
                return

            if key_file.exists():
                try:
                    data = json.loads(key_file.read_text(encoding="utf-8"))
                    priv = data.get("private_key")
                    pub = data.get("public_key")
                    if priv and pub:
                        _fallback_private_pem = priv
                        _fallback_public_pem = pub
                        return
                except Exception as e:
                    logger.warning(f"Failed to read persistent dev JWT keys from {key_file}: {e}")

            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa

            logger.warning(
                "⚠️ jwt_private_key and jwt_public_key not set in config. "
                "Generating persistent fallback RSA key pair for local/dev use."
            )
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            priv_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode("utf-8")
            pub_pem = (
                private_key.public_key()
                .public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                .decode("utf-8")
            )

            payload = json.dumps(
                {
                    "private_key": priv_pem,
                    "public_key": pub_pem,
                }
            )

            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=key_file.parent, prefix="dev_jwt_keys_", suffix=".tmp"
            )
            try:
                os.chmod(tmp_path, 0o600)
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    f.write(payload)
                os.replace(tmp_path, key_file)
            except Exception:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise

            _fallback_private_pem = priv_pem
            _fallback_public_pem = pub_pem
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def get_jwt_strategy() -> JWTStrategy:
    private_key = settings.jwt_private_key
    public_key = settings.jwt_public_key
    if not private_key or not public_key:
        _ensure_fallback_keys()
        private_key = _fallback_private_pem
        public_key = _fallback_public_pem

    return JWTStrategy(
        secret=private_key, public_key=public_key, algorithm="RS256", lifetime_seconds=3600
    )


def get_public_key_pem() -> str:
    public_key = settings.jwt_public_key
    if not public_key:
        _ensure_fallback_keys()
        public_key = _fallback_public_pem
    return public_key


def get_jwks_dict() -> dict:
    import base64

    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    pem = get_public_key_pem()
    key = load_pem_public_key(pem.encode("utf-8"))
    numbers = key.public_numbers()

    def to_b64(val: int) -> str:
        b = val.to_bytes((val.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode("utf-8")

    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "n": to_b64(numbers.n),
                "e": to_b64(numbers.e),
            }
        ]
    }


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

current_active_user = fastapi_users.current_user(active=True)

# --- SOLID Auth Strategy Pattern ---


class AuthStrategy(ABC):
    """Abstract Base Class for Authentication Strategies (SOLID: Open/Closed)"""

    @abstractmethod
    async def authenticate(
        self, request: Request, credentials: HTTPAuthorizationCredentials | None
    ) -> Optional[dict]:
        pass


class LocalAuthStrategy(AuthStrategy):
    """Strategy for local FastAPI-Users sessions (Admin/Local Seeding)"""

    async def authenticate(
        self, request: Request, credentials: HTTPAuthorizationCredentials | None
    ) -> Optional[dict]:
        # This uses the internal FastAPI-Users dependency resolution
        try:
            user = await fastapi_users.get_current_user(active=True, optional=True)(request)
            if user:
                return {
                    "id": str(user.id),
                    "email": user.email,
                    "is_superuser": user.is_superuser,
                    "provider": "local",
                    # NOT the user id. `get_tenant_id_from_user` carries a
                    # CRIT-P0 note against falling back to the Supabase user
                    # UUID — but that guard only covers its own fallback, and a
                    # caller handing it `tenant_id=<user uuid>` defeats it.
                    # TenantContext feeds the Qdrant server-side filter
                    # (services/qdrant/searcher.py), so a per-user "tenant"
                    # matches ZERO doctrine documents and every answer for that
                    # user abstains, while their cache namespace is unique so
                    # nothing is ever shared. Omitting the key lets the helper
                    # resolve the real shared tenant. Guarded by
                    # tests/test_tenant_identity_guard.py.
                    "tenant_id": get_settings().default_tenant_id,
                }
        except Exception as e:
            # type name only: exception text from token decoding can echo token fragments
            logger.debug("Local auth attempt failed: %s", type(e).__name__)
        return None


class TestAuthStrategy(AuthStrategy):
    """Strategy for local automated benchmarks and tests (X-Test-Key header).

    LOCAL BENCHMARKING ONLY — never registered in production builds (see the
    gate below: requires ENABLE_TEST_AUTH=true AND IS_PRODUCTION=false AND a
    non-empty BENCHMARK_SECRET, plus a request X-Test-Key matching it).

    The returned id/tenant_id is the NIL UUID (00000000-0000-0000-0000-000000000000)
    — a sentinel that Supabase GoTrue never assigns to a real user, so it
    cannot collide with a genuine account. It is a synthetic benchmark
    identity (is_superuser=True) for exercising admin/ingest routes locally,
    never a real Supabase user.

    SEC-4 (2026-08-10): Secret comparison delegated to `security_utils.is_benchmark_request`
    which uses `hmac.compare_digest` to prevent timing-based secret enumeration.
    """

    async def authenticate(
        self, request: Request, credentials: HTTPAuthorizationCredentials | None
    ) -> Optional[dict]:
        from app.security_utils import is_benchmark_request

        # Constant-time comparison via hmac.compare_digest (in is_benchmark_request).
        # DO NOT reimplement this check inline with ==  — timing attacks are real.
        if not is_benchmark_request(request):
            return None

        # Optional X-Test-Aal header lets probes mint aal1/aal2 identities
        # for MFA step-up verification without a real Supabase MFA setup.
        aal = request.headers.get("X-Test-Aal", "aal1")
        if aal not in ("aal1", "aal2"):
            aal = "aal1"
        return {
            "id": "00000000-0000-0000-0000-000000000000",
            "email": "benchmark-admin@mukthi.guru",
            "is_superuser": True,
            "provider": "test",
            "tenant_id": "00000000-0000-0000-0000-000000000000",
            "aal": aal,
        }


# ---- JWKS Client (cached, lazy-initialised) ----
# Supabase local v2.x issues ES256 (ECDSA) tokens verified via JWKS.
# We cache the client so JWKS is only fetched once (or on key rotation).
_jwks_client: PyJWKClient | None = None
_jwks_lock = AsyncLock()


def _get_jwks_url() -> str:
    """Return the JWKS URL for the configured Supabase instance."""
    if getattr(settings, "supabase_jwks_url", None):
        return settings.supabase_jwks_url
    base = settings.supabase_url.rstrip("/")
    return f"{base}/auth/v1/.well-known/jwks.json"


async def _get_jwks_client() -> PyJWKClient:
    """Lazily initialise and cache the JWKS client."""
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    async with _jwks_lock:
        if _jwks_client is None:  # Double-checked locking
            url = _get_jwks_url()
            logger.info(f"Initialising JWKS client from {url}")
            # PyJWKClient fetches JWKS synchronously; run in thread to not block
            _jwks_client = await asyncio.to_thread(
                PyJWKClient, url, cache_jwk_set=True, lifespan=3600
            )
    return _jwks_client


def _cache_admin_lookup(
    cache: dict[str, tuple],
    user_id: str,
    is_admin: bool,
    now: float,
    maxsize: int,
) -> None:
    """Store an admin-role lookup in a bounded cache, evicting the oldest on overflow.

    ``cache`` is a plain dict (insertion-ordered), so the oldest entry is
    ``next(iter(cache))``. The dict is shared class-level state: every
    SupabaseAuthStrategy instance in the process sees the same entries.
    P1-SEC-9: without the size cap, distinct user_id lookups grew the cache
    without bound.
    """
    if len(cache) >= maxsize:
        cache.pop(next(iter(cache)), None)
    cache[user_id] = (is_admin, now)


# --- Failed-credential logging (2026-11-28) ---
# A stale or foreign token used to produce two WARNING lines per request with no way to
# tell the cases apart (387 of 401 live WARNING lines). Now: ONE line carrying a bounded
# reason code taken from the exception TYPE (never its message), the unverified header's
# alg and kid prefix, and the unverified issuer HOST. Never the token, never other claims.
# Identical (reason, kid, iss_host) lines are rate-limited per process.
_AUTH_FAIL_INTERVAL_S = 60.0
_AUTH_FAIL_MAX_KEYS = 256
_AUTH_FAIL_LOCK = threading.Lock()
_AUTH_FAIL_SEEN: dict[tuple[str, str, str], tuple[float, int]] = {}
_AUTH_FAIL_SAFE = re.compile(r"[^A-Za-z0-9_.:-]")

# Order matters: InvalidSignatureError subclasses DecodeError, PyJWKClientConnectionError
# subclasses PyJWKClientError.
_AUTH_FAIL_REASONS: tuple[tuple[type[BaseException], str], ...] = (
    (jwt.ExpiredSignatureError, "expired"),
    (jwt.ImmatureSignatureError, "not_yet_valid"),
    (jwt.InvalidSignatureError, "bad_signature"),
    (jwt.InvalidIssuerError, "bad_issuer"),
    (jwt.InvalidAudienceError, "bad_audience"),
    (jwt.InvalidAlgorithmError, "bad_algorithm"),
    (jwt.MissingRequiredClaimError, "missing_claim"),
    (jwt.DecodeError, "malformed"),
    (PyJWKClientConnectionError, "jwks_fetch_failed"),
    (PyJWKClientError, "jwks_key_not_found"),
    (jwt.InvalidTokenError, "invalid_token"),
)


def auth_failure_reason(exc: BaseException) -> str:
    """Bounded reason code from the exception TYPE only; exception text can echo token parts."""
    for exc_type, reason in _AUTH_FAIL_REASONS:
        if isinstance(exc, exc_type):
            return reason
    return "other"


def _unverified_token_tags(token: str) -> tuple[str, str, str]:
    """(alg, kid[:8], iss host) read WITHOUT verifying the signature; ``unknown`` on any failure."""
    alg = kid = host = "unknown"
    try:
        header = jwt.get_unverified_header(token)
        alg = _AUTH_FAIL_SAFE.sub("", str(header.get("alg") or ""))[:12] or "unknown"
        kid = _AUTH_FAIL_SAFE.sub("", str(header.get("kid") or ""))[:8] or "none"
    except (jwt.InvalidTokenError, AttributeError, TypeError):
        pass
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
        iss = claims.get("iss")
        parsed = urlparse(iss).hostname if isinstance(iss, str) else None
        host = _AUTH_FAIL_SAFE.sub("", parsed or "")[:64] or "unknown"
    except (jwt.InvalidTokenError, AttributeError, TypeError, ValueError):
        pass
    return alg, kid, host


def _auth_failure_suppressed_count(
    key: tuple[str, str, str], now: float | None = None
) -> int | None:
    """None: stay quiet (and count it). Otherwise emit, reporting how many were suppressed."""
    now = time.monotonic() if now is None else now
    with _AUTH_FAIL_LOCK:
        entry = _AUTH_FAIL_SEEN.get(key)
        if entry is not None and now - entry[0] < _AUTH_FAIL_INTERVAL_S:
            _AUTH_FAIL_SEEN[key] = (entry[0], entry[1] + 1)
            return None
        if entry is None and len(_AUTH_FAIL_SEEN) >= _AUTH_FAIL_MAX_KEYS:
            _AUTH_FAIL_SEEN.pop(next(iter(_AUTH_FAIL_SEEN)), None)
        _AUTH_FAIL_SEEN[key] = (now, 0)
        return entry[1] if entry is not None else 0


def log_auth_failure(request: Request | None, token: str | None, reason: str) -> None:
    """Emit the single rate-limited failure line and mark the request as already logged."""
    try:
        request.state.auth_failure_logged = True  # type: ignore[union-attr]
    except AttributeError:
        pass
    alg, kid, host = _unverified_token_tags(token or "")
    suppressed = _auth_failure_suppressed_count((reason, kid, host))
    if suppressed is None:
        return
    logger.warning(
        "auth failed for provided token reason=%s alg=%s kid=%s iss_host=%s suppressed=%d; "
        "falling back to anonymous where the route allows it",
        reason,
        alg,
        kid,
        host,
        suppressed,
    )


class SupabaseAuthStrategy(AuthStrategy):
    """
    Strategy for Supabase JWTs (Production Seeker Flow).

    Supabase local v2.x issues ES256 (ECDSA) tokens.  We verify these
    against the public key published at the JWKS endpoint.
    Supabase static keys (anon / service_role) are still HS256 and are
    verified with the shared jwt_secret as a fallback.
    """

    async def authenticate(
        self,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None,
    ) -> Optional[dict]:
        if not credentials:
            return None

        token = credentials.credentials

        # ---- Peek at the token header to pick the right path ----
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.DecodeError as e:
            log_auth_failure(request, token, auth_failure_reason(e))
            return None

        alg = unverified_header.get("alg", "")

        # Accept the configured Supabase issuer plus (dev-only) the local
        # docker/browser issuers. Frontend gets tokens from
        # http://127.0.0.1:54321, backend validates against host.docker.internal.
        # PyJWT accepts a list for `issuer` and validates against any match.
        # P1-SEC-10: the local issuers are honoured ONLY outside production —
        # a forged token claiming a local issuer would otherwise be trusted
        # by the HS256 shared-secret path in prod.
        def _valid_issuers() -> list[str]:
            base = settings.supabase_url.rstrip("/")
            issuers = [
                f"{base}/auth/v1",  # e.g., http://host.docker.internal:54321/auth/v1
            ]
            if not getattr(settings, "is_production", False):
                issuers += [
                    "http://127.0.0.1:54321/auth/v1",
                    "http://localhost:54321/auth/v1",
                ]
            if getattr(settings, "supabase_jwt_issuer", None):
                issuers.append(settings.supabase_jwt_issuer)
            return issuers

        try:
            if alg in ("ES256", "RS256"):
                # ---- Asymmetric path: verify via JWKS public key ----
                client = await _get_jwks_client()
                signing_key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)

                # Use build_safe_audience to handle both "authenticated" and
                # the Supabase legacy audience string (supabase_url).
                def build_safe_audience() -> list[str]:
                    raw = settings.supabase_jwt_audience
                    if "," in raw:
                        return [a.strip() for a in raw.split(",") if a.strip()]
                    return [a.strip() for a in raw.split() if a.strip()] or ["authenticated"]

                audience = build_safe_audience()
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["ES256", "RS256"],
                    audience=audience,
                    issuer=_valid_issuers(),
                )
            else:
                # ---- Symmetric path: verify with shared HS256 secret ----
                if not settings.jwt_secret:
                    logger.error("jwt_secret not configured — cannot verify HS256 token")
                    return None
                payload = jwt.decode(
                    token,
                    settings.jwt_secret,
                    algorithms=["HS256"],
                    audience=[settings.supabase_jwt_audience],
                    issuer=_valid_issuers(),
                )

            user_id = payload.get("sub")
            user_email = payload.get("email")
            jwt_role = payload.get("role", "authenticated")
            # Falling back to `sub` made every Supabase user their own tenant,
            # which is the same defect as the local-auth path above: the Qdrant
            # server-side filter then matches zero doctrine documents. A real
            # tenant claim is honoured when present; otherwise the shared
            # default applies.
            tenant_id = payload.get("tenant_id") or settings.default_tenant_id
            # Supabase GoTrue JWTs carry an Authenticator Assurance Level claim
            # ("aal1" default, "aal2" after MFA step-up). Default to aal1 when
            # absent so MFA-gated routes deny by default.
            aal = payload.get("aal") or "aal1"

            # P1-SEC-1 (T2): service_role tokens presented over HTTP must NOT
            # be treated as superuser. service_role is for backend-internal
            # Supabase calls (the telemetry sink reads SUPABASE_SERVICE_ROLE_KEY
            # directly from env, NOT via this bridge), never for human/admin
            # HTTP. Setting is_superuser=False closes the "leaked
            # service_role key -> admin bypass" hole; admin/ingest/kg endpoints
            # additionally require aal2 (T1) which service_role tokens lack.
            if jwt_role == "service_role":
                logger.warning(
                    "service_role token presented over HTTP (sub=%s); "
                    "denying superuser (P1-SEC-1 T2)",
                    user_id,
                )
                return {
                    "id": user_id,
                    "email": user_email,
                    "role": jwt_role,
                    "is_superuser": False,
                    "provider": "supabase",
                    "tenant_id": tenant_id,
                    "aal": aal,
                }

            # For authenticated users, check user_roles table for admin role
            is_admin = await self._check_admin_role(user_id, token)

            return {
                "id": user_id,
                "email": user_email,
                "role": jwt_role,
                "is_superuser": is_admin,
                "provider": "supabase",
                "tenant_id": tenant_id,
                "aal": aal,
            }

        except jwt.ExpiredSignatureError as e:
            log_auth_failure(request, token, auth_failure_reason(e))
            raise HTTPException(status_code=401, detail="Token expired. Please sign in again.")
        except (jwt.InvalidTokenError, PyJWKClientError) as e:
            log_auth_failure(request, token, auth_failure_reason(e))
            return None
        except Exception as e:
            logger.error(f"Supabase auth bridge error: {type(e).__name__}")
            return None

    # Bounded TTL cache for admin role lookups (P1-SEC-9): this was an
    # unbounded per-user dict — every distinct user_id check inserted a key
    # that lived forever, growing memory with each new admin lookup. It is
    # now capped at _CACHE_MAXSIZE entries; on overflow the oldest entry is
    # evicted (dicts preserve insertion order, so pop(next(iter(...))) is
    # FIFO). TTL semantics unchanged.
    _admin_cache: dict[str, tuple] = {}
    _CACHE_TTL = 90  # 1.5 minutes
    _CACHE_MAXSIZE = 256

    async def _check_admin_role(self, user_id: str, jwt_token: str | None = None) -> bool:
        """Check if user has admin role via Supabase user_roles table.

        Uses the user's own JWT to authenticate the query so RLS sees
        ``auth.uid()`` instead of the ``anon`` role.  Falls back to the legacy
        service-key HTTP request (for environments that still carry
        ``SUPABASE_SERVICE_ROLE_KEY``).
        """
        now = time.time()
        cached = self._admin_cache.get(user_id)
        # A "not admin" answer may live longer than an "is admin" one: a stale negative can only
        # delay a new grant, never keep a revoked admin. Every cache miss costs a Supabase client
        # build, a session call and a REST query for a signed-in seeker.
        ttl = self._CACHE_TTL if cached and cached[0] else settings.admin_role_negative_cache_ttl_s
        if cached and (now - cached[1]) < ttl:
            return cached[0]

        try:
            if jwt_token:
                from supabase import create_client

                sc = create_client(settings.supabase_url, settings.supabase_key)
                await asyncio.to_thread(sc.auth.set_session, jwt_token, "")
                resp = await asyncio.to_thread(
                    sc.table("user_roles")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("role", "admin")
                    .execute
                )
                is_admin = bool(resp.data)
                _cache_admin_lookup(self._admin_cache, user_id, is_admin, now, self._CACHE_MAXSIZE)
                if is_admin:
                    logger.info(f"User {user_id} confirmed as admin via authenticated query")
                return is_admin

            # Fallback: legacy service-key HTTP request (only works with
            # SUPABASE_SERVICE_ROLE_KEY — not available on Lovable Cloud).
            import httpx

            base_url = settings.supabase_url.rstrip("/")
            service_key = getattr(settings, "supabase_service_key", None) or settings.supabase_key
            if not service_key:
                logger.debug("Supabase admin credential unavailable; cannot check admin role")
                return False

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{base_url}/rest/v1/user_roles",
                    params={"user_id": f"eq.{user_id}", "role": "eq.admin", "select": "id"},
                    headers={
                        "apikey": service_key,
                        "Authorization": f"Bearer {service_key}",
                    },
                    timeout=5.0,
                )
                is_admin = resp.status_code == 200 and len(resp.json()) > 0
                _cache_admin_lookup(self._admin_cache, user_id, is_admin, now, self._CACHE_MAXSIZE)
                if is_admin:
                    logger.info(f"User {user_id} confirmed as admin via user_roles")
                return is_admin
        except Exception as e:
            logger.warning(f"Admin role check failed: {e}")
            return False


class AuthBridge:
    """Orchestrator for multiple Auth Strategies (SOLID: Single Responsibility)"""

    def __init__(self, strategies: list[AuthStrategy]):
        self.strategies = strategies

    async def get_user(
        self, request: Request, credentials: HTTPAuthorizationCredentials | None
    ) -> dict:
        for strategy in self.strategies:
            user = await strategy.authenticate(request, credentials)
            if user:
                return user

        raise HTTPException(status_code=401, detail="Authentication required or session expired")


# --- Dependency Injection Components ---

security = HTTPBearer(auto_error=False)
_strategies = [LocalAuthStrategy(), SupabaseAuthStrategy()]
# SEC-6: TestAuthStrategy benchmark backdoor.
# Grants synthetic superuser identity (NIL UUID, is_superuser=True) when ALL of:
#   1. ENABLE_TEST_AUTH=true
#   2. IS_PRODUCTION=false (or unset)
#   3. BENCHMARK_SECRET is non-empty
#   4. X-Test-Key header matches BENCHMARK_SECRET (constant-time via hmac.compare_digest)
# The superuser identity is intentional — benchmarks exercise admin/ingest routes.
# The NIL UUID (00000000...) is a sentinel never issued by Supabase GoTrue.
# RISK: BENCHMARK_SECRET exposure grants superuser access in non-prod environments.
# Mitigation: secret is gated by ENABLE_TEST_AUTH + IS_PRODUCTION=false AND is
#             compared with hmac.compare_digest (no timing-attack amplification).
if (
    getattr(settings, "enable_test_auth", False)
    and not settings.is_production
    and getattr(settings, "benchmark_secret", None)
):
    _strategies.insert(0, TestAuthStrategy())
if settings.is_production and any(isinstance(s, TestAuthStrategy) for s in _strategies):
    # P1-SEC-8 Rule 9: fail-closed gate must survive `python -O`, so this is
    # an explicit RuntimeError rather than a bare boolean check.
    raise RuntimeError("TestAuthStrategy must never be enabled in production")
auth_bridge = AuthBridge(_strategies)


async def get_current_user_from_supabase(
    request: Request, token: HTTPAuthorizationCredentials | None = Depends(security)
) -> dict:
    """
    Production-grade Auth Bridge.
    Returns a unified user object regardless of the underlying auth provider.
    Falls back to anonymous user in non-production when no auth token is provided.
    Expired/invalid tokens still reject properly.
    """
    # Always try auth strategies first (covers X-Test-Key backdoor without Bearer token)
    user = await auth_bridge.get_user(request, token)
    if user:
        return user
    # No auth succeeded — fall back to anonymous in dev mode
    if not settings.is_production:
        logger.warning("No auth token in dev mode — using anonymous user")
        return {"id": "anonymous", "email": None, "is_anonymous": True}
    raise HTTPException(status_code=401, detail="Authentication required or session expired")


# Mirrors src/integrations/supabase/client.ts's ALLOWED_EMAIL_DOMAINS — that
# check was client-only, so a caller hitting the API directly (never loading
# AuthPage.tsx) could authenticate with any email domain regardless of the
# declared beta-access policy (audit finding OH-P1-08, 2026-08-25). This
# enforces the SAME already-declared policy; it does not change what the
# policy is or decide whether it should exist.
_ALLOWED_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "msn.com",
}


def _is_allowed_email_domain(email: str | None) -> bool:
    if not email or "@" not in email:
        return False
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in _ALLOWED_EMAIL_DOMAINS


async def get_optional_user(
    request: Request, token: HTTPAuthorizationCredentials | None = Depends(security)
) -> dict:
    """
    Auth bridge that allows anonymous access even in production.
    Used by chat endpoints that support incognito mode.
    Falls back to anonymous user when no valid auth token is provided.
    """
    try:
        user = await auth_bridge.get_user(request, token)
    except HTTPException:
        # get_user() raises 401 both for "no token" (the case this dependency
        # exists to allow) and for a token that failed validation (e.g.
        # expired). Log the latter — silently downgrading to anonymous with
        # no trace makes a real auth failure indistinguishable from incognito.
        if token:
            # The strategy that rejected the token already logged one reason-coded line.
            # Log here only when none did, so each failure produces one line, not two.
            if getattr(request.state, "auth_failure_logged", False):
                logger.debug("get_optional_user: falling back to anonymous after a failed token")
            else:
                log_auth_failure(request, token.credentials, "rejected")
        return {"id": "anonymous", "email": None, "is_anonymous": True}

    is_privileged = user.get("is_superuser") or user.get("role") == "service_role"
    if (
        not user.get("is_anonymous")
        and not is_privileged
        and not _is_allowed_email_domain(user.get("email"))
    ):
        logger.warning(
            "get_optional_user: rejecting authenticated user with non-allowlisted email domain"
        )
        raise HTTPException(
            status_code=403,
            detail="Access restricted to verified @gmail.com, @hotmail.com, or @outlook.com accounts.",
        )
    return user


# --- M5: Server-side signed anonymous session tokens -------------------------
#
# Anonymous identity is no longer client-asserted. The server issues a signed
# token at POST /api/auth/anon-session; the client echoes it back via
# X-Session-Id (header) or session_id (POST body). resolve_anon_identity()
# verifies the HMAC and rejects unsigned/tampered tokens in production.
#
# Token format:  <base64url(payload16)>.<base64url(hmac_sha256(payload))>
# Storage identity: anon:<base64url(payload)>   (the existing "anon:" prefix)
#
# Invariant L-K3-1: all secret comparisons use hmac.compare_digest — never ==.


def _anon_hmac_key() -> bytes:
    """Return the HMAC key bytes for anonymous session tokens.

    settings.anon_session_hmac_secret is guaranteed non-empty by the config
    validator (validate_anon_session_secret): in production it must be set
    explicitly; in dev it falls back to a value derived from jwt_secret.
    """
    secret = getattr(settings, "anon_session_hmac_secret", None) or ""
    if not secret:
        # Defensive: should never trigger because the config validator
        # populates the value, but fail-closed rather than silently use "".
        raise RuntimeError("anon_session_hmac_secret is not configured")
    return secret.encode("utf-8")


def issue_anon_session_token() -> dict:
    """Mint a fresh anonymous session token (server-side issuance).

    Returns ``{"session_id": "anon:<id>", "token": "<id>.<sig>"}`` where
    ``<id>`` is base64url(16 random bytes) from secrets.token_urlsafe.
    """
    payload = secrets.token_urlsafe(16)  # ~128 bits of entropy
    sig = hmac.new(_anon_hmac_key(), payload.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    token = f"{payload}.{sig_b64}"
    return {"session_id": f"anon:{payload}", "token": token}


def verify_anon_session_token(token: str) -> str:
    """Verify a signed anonymous session token and return the ``anon:<id>`` identity.

    Raises HTTPException(400) on a malformed token and HTTPException(401) on a signature mismatch.
    Constant-time compare via hmac.compare_digest (invariant L-K3-1).
    """
    if not token or "." not in token:
        raise HTTPException(status_code=400, detail="Invalid anonymous session token")
    payload, _, sig_b64 = token.partition(".")
    if not payload or not sig_b64:
        raise HTTPException(status_code=400, detail="Invalid anonymous session token")
    expected = hmac.new(_anon_hmac_key(), payload.encode("utf-8"), hashlib.sha256).digest()
    # sig_b64 is base64url WITHOUT padding (we strip it at issue time), so
    # re-pad before decoding to recover the raw 32 bytes.
    pad = "=" * (-len(sig_b64) % 4)
    try:
        provided = base64.urlsafe_b64decode(sig_b64 + pad)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid anonymous session token")
    if not hmac.compare_digest(expected, provided):
        # 401, not 400: a well-formed token whose signature no longer verifies (the HMAC secret
        # was rotated) is an expired credential. Deployed clients already re-mint an anonymous
        # token once on 401 (2026-11-28: a 400 stranded returning visitors until they cleared
        # localStorage). Malformed tokens above stay 400.
        raise HTTPException(status_code=401, detail="Invalid anonymous session token")
    return f"anon:{payload}"


def resolve_anon_identity(user: dict, session_id: str | None) -> dict:
    """Derive a per-session identity for anonymous (incognito) users.

    Without this, every incognito user shares user_id="anonymous", which breaks
    job ownership isolation and telemetry granularity. The frontend obtains a
    server-signed token from POST /api/auth/anon-session and echoes it back as
    session_id in the request body (POST) or X-Session-Id header (GET).

    M5: ``session_id`` is now the signed token form ``<payload>.<sig>``. We
    verify the HMAC and rewrite the user id to ``anon:<payload>``. Tampered or
    unsigned tokens are rejected with 400. In non-production (dev/test), the
    bare ``anon:<id>`` form is still accepted as an escape hatch so legacy
    tests that fabricate identities directly keep working.

    Authenticated users are returned unchanged.
    """
    if not user or not user.get("is_anonymous"):
        return user
    sid = (session_id or "").strip()
    if not sid:
        return user

    # Signed token path: "<payload>.<sig>".
    if "." in sid:
        anon_id = verify_anon_session_token(sid)
        return {**user, "id": anon_id}

    # Bare "anon:<id>" path — dev/test escape hatch ONLY. In production a
    # caller supplying an unsigned id is rejected: anyone could otherwise
    # claim a victim's identity by asserting their session id verbatim.
    if sid.startswith("anon:"):
        if getattr(settings, "is_production", True):
            raise HTTPException(
                status_code=400,
                detail="Invalid anonymous session token",
            )
        return {**user, "id": sid}

    # Anything else (legacy raw session ids without the anon: prefix) —
    # reject in production, also reject in dev to avoid silently widening
    # the accepted shape. The signed-token flow is the only sanctioned path.
    raise HTTPException(status_code=400, detail="Invalid anonymous session token")


def require_scoped_identity(user: dict) -> None:
    """Reject a request whose identity is the unscoped literal "anonymous".

    Call after resolve_anon_identity() on any endpoint that looks up a
    resource by an id previously written to job_meta["user_id"] (job
    poll/cancel/stream). Without this, an anonymous caller with no
    session_id collapses onto the same shared "anonymous" user_id and
    can access/cancel each other's jobs.
    """
    if user and user.get("is_anonymous") and user.get("id") == "anonymous":
        raise HTTPException(
            status_code=400,
            detail="A session id is required for anonymous access to this resource.",
        )


async def require_aal2(user: dict = Depends(get_current_user_from_supabase)) -> dict:
    """MFA step-up dependency: require Authenticator Assurance Level 2.

    Composes get_current_user_from_supabase so AAL enforcement rides the same
    auth bridge as every other protected route. Works with dict-like user
    objects (Supabase/test tokens) and dataclass-like user objects
    (FastAPI-Users). Returns the user on success; raises 401 when
    unauthenticated, 403 when the AAL is insufficient.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    aal = None
    if isinstance(user, dict):
        aal = user.get("aal")
    else:
        aal = getattr(user, "aal", None)

    if aal != "aal2":
        raise HTTPException(status_code=403, detail="AAL2 step-up required")

    return user


async def require_admin(user: dict = Depends(require_aal2)) -> dict:
    """Require an AAL2-authenticated superuser in the configured admin set.

    This is the canonical admin dependency for routes that need both the
    existing MFA step-up and the existing superuser/``ADMIN_USER_IDS``
    defense-in-depth checks. An empty configured allowlist preserves the
    established behavior of enforcing the superuser bit without an ID filter.
    """
    # Keep this assertion local to the canonical admin boundary as defense in
    # depth. Direct callers/tests must not be able to pass an AAL1 superuser
    # by bypassing FastAPI's nested ``require_aal2`` dependency resolution.
    if not user or user.get("aal") != "aal2":
        raise HTTPException(status_code=403, detail="AAL2 step-up required")

    if not user or not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    allowlist = getattr(settings, "admin_user_ids_list", None) or []
    if allowlist and user.get("id") not in allowlist:
        raise HTTPException(status_code=403, detail="Admin access required (not allowlisted)")

    return user

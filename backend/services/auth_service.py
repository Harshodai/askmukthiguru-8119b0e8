from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from jwt import PyJWKClient, PyJWKClientError
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


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="api/auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=settings.jwt_secret, lifetime_seconds=3600)


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
                }
        except Exception as e:
            logger.debug(f"Local auth attempt failed: {e}")
        return None


class TestAuthStrategy(AuthStrategy):
    """Strategy for local automated benchmarks and tests (X-Test-Key header)."""

    async def authenticate(
        self, request: Request, credentials: HTTPAuthorizationCredentials | None
    ) -> Optional[dict]:
        test_key = request.headers.get("X-Test-Key")
        benchmark_secret = getattr(settings, "benchmark_secret", None) or settings.jwt_secret
        if test_key and test_key == benchmark_secret:
            return {
                "id": "00000000-0000-0000-0000-000000000000",
                "email": "benchmark-admin@mukthi.guru",
                "is_superuser": True,
                "provider": "test",
            }
        return None


# ---- JWKS Client (cached, lazy-initialised) ----
# Supabase local v2.x issues ES256 (ECDSA) tokens verified via JWKS.
# We cache the client so JWKS is only fetched once (or on key rotation).
_jwks_client: PyJWKClient | None = None
_jwks_lock = asyncio.Lock()


def _get_jwks_url() -> str:
    """Return the JWKS URL for the configured Supabase instance."""
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
            logger.warning(f"Malformed JWT header: {e}")
            return None

        alg = unverified_header.get("alg", "")

        # Accept both local (browser) and docker-internal issuers for Supabase JWTs.
        # Frontend gets tokens from http://127.0.0.1:54321, backend validates against host.docker.internal.
        # PyJWT accepts a list for `issuer` and validates against any match.
        def _valid_issuers() -> list[str]:
            base = settings.supabase_url.rstrip("/")
            return [
                f"{base}/auth/v1",              # e.g., http://host.docker.internal:54321/auth/v1
                "http://127.0.0.1:54321/auth/v1",
                "http://localhost:54321/auth/v1",
            ]

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

            # service_role tokens are always superuser
            if jwt_role == "service_role":
                return {
                    "id": user_id,
                    "email": user_email,
                    "role": jwt_role,
                    "is_superuser": True,
                    "provider": "supabase",
                }

            # For authenticated users, check user_roles table for admin role
            is_admin = await self._check_admin_role(user_id)

            return {
                "id": user_id,
                "email": user_email,
                "role": jwt_role,
                "is_superuser": is_admin,
                "provider": "supabase",
            }

        except jwt.ExpiredSignatureError:
            logger.warning("Supabase credential expired")
            raise HTTPException(status_code=401, detail="Token expired. Please sign in again.")
        except (jwt.InvalidTokenError, PyJWKClientError) as e:
            logger.warning(f"Invalid Supabase credential: {type(e).__name__}")
            return None
        except Exception as e:
            logger.error(f"Supabase auth bridge error: {type(e).__name__}: {e}")
            return None

    # Simple TTL cache for admin role lookups
    _admin_cache: dict[str, tuple] = {}
    _CACHE_TTL = 300  # 5 minutes

    async def _check_admin_role(self, user_id: str) -> bool:
        """Check if user has admin role via Supabase user_roles table."""
        now = time.time()
        cached = self._admin_cache.get(user_id)
        if cached and (now - cached[1]) < self._CACHE_TTL:
            return cached[0]

        try:
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
                self._admin_cache[user_id] = (is_admin, now)
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
# TestAuthStrategy is a hard backdoor (X-Test-Key == jwt_secret -> superuser admin).
# Require BOTH non-production AND an explicit opt-in flag; refuse to register it in prod.
if getattr(settings, "enable_test_auth", False) and not settings.is_production:
    _strategies.insert(0, TestAuthStrategy())
if settings.is_production:
    assert not any(isinstance(s, TestAuthStrategy) for s in _strategies), (
        "TestAuthStrategy must never be enabled in production"
    )
auth_bridge = AuthBridge(_strategies)


async def get_current_user_from_supabase(
    request: Request, token: HTTPAuthorizationCredentials | None = Depends(security)
) -> dict:
    """
    Production-grade Auth Bridge.
    Returns a unified user object regardless of the underlying auth provider.
    """
    return await auth_bridge.get_user(request, token)

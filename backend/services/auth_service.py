import uuid
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, List
import jwt
from fastapi import Depends, Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from models.user import User
from app.config import get_settings

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

    async def on_after_register(self, user: User, request: Optional[Request] = None):
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
    async def authenticate(self, request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[Dict]:
        pass

class LocalAuthStrategy(AuthStrategy):
    """Strategy for local FastAPI-Users sessions (Admin/Local Seeding)"""
    async def authenticate(self, request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[Dict]:
        # This uses the internal FastAPI-Users dependency resolution
        try:
            user = await fastapi_users.get_current_user(active=True, optional=True)(request)
            if user:
                return {
                    "id": str(user.id),
                    "email": user.email,
                    "is_superuser": user.is_superuser,
                    "provider": "local"
                }
        except Exception as e:
            logger.debug(f"Local auth attempt failed: {e}")
        return None

class SupabaseAuthStrategy(AuthStrategy):
    """Strategy for Supabase JWTs (Production Seeker Flow)"""
    async def authenticate(self, request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[Dict]:
        if not credentials:
            return None
        
        try:
            # Validate algorithm and signature
            payload = jwt.decode(
                credentials.credentials, 
                settings.jwt_secret, 
                algorithms=["HS256", "RS256"],
                options={"verify_aud": False}
            )
            
            return {
                "id": payload.get("sub"),
                "email": payload.get("email"),
                "is_superuser": payload.get("role") == "service_role",
                "provider": "supabase"
            }
        except jwt.ExpiredSignatureError:
            logger.warning("Supabase token expired")
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid Supabase token: {e}")
            return None
        except Exception as e:
            logger.error(f"Supabase auth bridge error: {type(e).__name__}: {e}")
            return None

class AuthBridge:
    """Orchestrator for multiple Auth Strategies (SOLID: Single Responsibility)"""
    def __init__(self, strategies: List[AuthStrategy]):
        self.strategies = strategies

    async def get_user(self, request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> Dict:
        for strategy in self.strategies:
            user = await strategy.authenticate(request, credentials)
            if user:
                return user
        
        raise HTTPException(status_code=401, detail="Authentication required or session expired")

# --- Dependency Injection Components ---

security = HTTPBearer(auto_error=False)
auth_bridge = AuthBridge([LocalAuthStrategy(), SupabaseAuthStrategy()])

async def get_current_user_from_supabase(
    request: Request,
    token: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict:
    """
    Production-grade Auth Bridge.
    Returns a unified user object regardless of the underlying auth provider.
    """
    return await auth_bridge.get_user(request, token)

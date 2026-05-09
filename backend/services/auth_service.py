import uuid
import logging
from typing import Optional
import jwt
from typing import Optional, Dict
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

async def get_user_db(session: AsyncSession = Depends(get_db)):
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.jwt_secret
    verification_token_secret = settings.jwt_secret

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        logger.info(f"User {user.id} has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        logger.info(f"User {user.id} has requested a password reset.")

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        logger.info(f"Verification requested for user {user.id}.")


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

# --- Supabase Auth Bridge ---

security = HTTPBearer(auto_error=False)

async def get_current_user_from_supabase(
    request: Request,
    token: Optional[HTTPAuthorizationCredentials] = Depends(security),
    local_user: Optional[User] = Depends(fastapi_users.current_user(active=True, optional=True))
) -> Dict:
    """
    Unified Auth Bridge: Validates EITHER a local FastAPI-Users session
    OR a Supabase JWT. Allows frontend to stay on Supabase while 
    backend stays secure.
    """
    # 1. Try local FastAPI-Users first (for admin/local login)
    if local_user:
        return {
            "id": str(local_user.id),
            "email": local_user.email,
            "is_superuser": local_user.is_superuser,
            "provider": "local"
        }

    # 2. Try Supabase JWT from Authorization header
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Debugging: Log header to see what's happening
        header = jwt.get_unverified_header(token.credentials)
        logger.debug(f"Validating Supabase JWT with header: {header}")

        # Supabase JWTs are signed with the same secret as our backend JWT_SECRET
        # Local Supabase uses HS256, but some providers might use RS256
        payload = jwt.decode(
            token.credentials, 
            settings.jwt_secret, 
            algorithms=["HS256", "RS256"],
            options={"verify_aud": False} # Supabase aud varies (authenticated vs proj-id)
        )
        
        return {
            "id": payload.get("sub"),
            "email": payload.get("email"),
            "is_superuser": payload.get("role") == "service_role",
            "provider": "supabase"
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid Supabase token: {e}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    except Exception as e:
        logger.error(f"Auth bridge error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")

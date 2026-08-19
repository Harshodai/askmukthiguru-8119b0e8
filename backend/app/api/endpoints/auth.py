from fastapi import APIRouter, HTTPException

from app.config import settings
from schemas.user import UserCreate, UserRead, UserUpdate
from services.auth_service import auth_backend, fastapi_users, issue_anon_session_token

router = APIRouter()


@router.post("/anon-session", tags=["auth"])
async def anon_session():
    """M5: Issue a server-side signed anonymous session token.

    Returns ``{"session_id": "anon:<id>", "token": "<payload>.<sig>"}``. The
    client echoes ``token`` back as the ``X-Session-Id`` header (or
    ``session_id`` body field on POST) so resolve_anon_identity() can verify
    the HMAC and derive a per-session identity. Unsigned/tampered tokens are
    rejected with 400 at the resolve step.
    """
    return issue_anon_session_token()


router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/jwt",
    tags=["auth"],
)

if not settings.disable_public_registration:
    register_router = fastapi_users.get_register_router(UserRead, UserCreate)
    # NOTE: Do NOT use Depends(limiter.limit(...)) here — slowapi's limit() returns a
    # Callable that Pydantic v2 cannot serialise to OpenAPI JSON schema, crashing
    # /openapi.json with PydanticInvalidForJsonSchema: core_schema.CallableSchema.
    # Rate limiting for this router is handled by the global slowapi middleware.
    router.include_router(
        register_router,
        tags=["auth"],
    )
else:

    @router.post("/register", tags=["auth"])
    async def register_disabled():
        raise HTTPException(status_code=403, detail="Public registration is disabled.")


router.include_router(
    fastapi_users.get_reset_password_router(),
    tags=["auth"],
)

router.include_router(
    fastapi_users.get_verify_router(UserRead),
    tags=["auth"],
)

router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

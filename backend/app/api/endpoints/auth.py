from fastapi import APIRouter, HTTPException
from services.auth_service import fastapi_users, auth_backend
from schemas.user import UserRead, UserCreate, UserUpdate
from app.config import settings

router = APIRouter()

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

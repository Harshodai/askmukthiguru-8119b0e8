from fastapi import APIRouter
from services.auth_service import fastapi_users, auth_backend
from schemas.user import UserRead, UserCreate, UserUpdate
from app.config import settings
from app.core.limiter import limiter
from fastapi import Depends

router = APIRouter()

router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/jwt",
    tags=["auth"],
)

if not settings.disable_public_registration:
    register_router = fastapi_users.get_register_router(UserRead, UserCreate)
    # Apply rate limiting to the registration route
    # Note: fastapi-users includes routes dynamically, so we apply it to the router or wrap it
    router.include_router(
        register_router,
        tags=["auth"],
        dependencies=[Depends(limiter.limit(settings.registration_rate_limit))]
    )
else:
    from fastapi import HTTPException
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

from fastapi import APIRouter
from services.auth_service import fastapi_users, auth_backend
from schemas.user import UserRead, UserCreate, UserUpdate

router = APIRouter()

router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/jwt",
    tags=["auth"],
)

router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    tags=["auth"],
)

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

import uuid
from typing import Optional
from fastapi_users import schemas
from pydantic import BaseModel

class UserRead(schemas.BaseUser[uuid.UUID]):
    name: Optional[str] = None

class UserCreate(schemas.BaseUserCreate):
    name: Optional[str] = None

class UserUpdate(schemas.BaseUserUpdate):
    name: Optional[str] = None

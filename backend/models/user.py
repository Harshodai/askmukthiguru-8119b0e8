import uuid
from datetime import datetime
from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import Column, String, DateTime, Boolean

from app.core.database import Base

class User(SQLAlchemyBaseUserTableUUID, Base):
    """
    Database model for User managed by FastAPI Users.
    """
    __tablename__ = "users"
    
    # Fields inherently provided by SQLAlchemyBaseUserTableUUID:
    # id, email, hashed_password, is_active, is_superuser, is_verified

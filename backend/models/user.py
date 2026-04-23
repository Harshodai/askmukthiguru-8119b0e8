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
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Required by FastAPI users
    email = Column(String(length=320), unique=True, index=True, nullable=False)
    hashed_password = Column(String(length=1024), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.config import get_settings

settings = get_settings()

import os

# For Phase 1 Auth we use a local SQLite database for users
# In Docker, we must use the writable /app/data directory.
if os.path.exists("/app/data"):
    db_path = "/app/data/mukthi_users.db"
else:
    db_path = os.environ.get("AUTH_DB_PATH", "./mukthi_users.db")

SQLITE_URL = f"sqlite+aiosqlite:///{db_path}"

engine = create_async_engine(
    SQLITE_URL,
    echo=False,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=settings.db_pool_pre_ping,
    pool_recycle=settings.db_pool_recycle,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

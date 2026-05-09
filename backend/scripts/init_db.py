
import asyncio
import logging
from app.core.database import engine, Base
from models.user import User  # Ensure models are imported so they register with Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_db")

# Add missing tables from guide Section 11.3
# These can be run in Supabase SQL editor or locally
SQL_MIGRATIONS = """
-- Add to your Supabase/PostgreSQL migrations
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id UUID PRIMARY KEY,
    created_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
    updated_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
    preferred_language VARCHAR(20) DEFAULT 'en',
    spiritual_level VARCHAR(30) DEFAULT 'beginner',
    topics_of_interest TEXT[] DEFAULT '{}',
    last_distress_assessment JSONB,
    total_conversations INTEGER DEFAULT 0,
    total_meditations_completed INTEGER DEFAULT 0,
    favorite_teachings TEXT[] DEFAULT '{}',
    codemix_preference BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS conversation_memories (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    started_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
    messages JSONB DEFAULT '[]',
    key_insights TEXT[] DEFAULT '{}',
    emotional_arc JSONB DEFAULT '[]',
    follow_up_suggestions TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_memories_user_id ON conversation_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_memories_started_at ON conversation_memories(started_at DESC);
"""

async def init_db():
    logger.info("Initializing local SQLite database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Local SQLite database initialized.")
    
    logger.info("\nIMPORTANT: To enable persistent memory and user profiles, please run the following SQL in your Supabase SQL Editor:")
    logger.info("-" * 80)
    logger.info(SQL_MIGRATIONS)
    logger.info("-" * 80)

if __name__ == "__main__":
    asyncio.run(init_db())

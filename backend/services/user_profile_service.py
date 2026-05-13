
import logging
import json
import time
import uuid
import re
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
from enum import Enum
from app.config import settings

logger = logging.getLogger(__name__)

class SpiritualLevel(str, Enum):
    BEGINNER = "beginner"       # New to spirituality
    EXPLORER = "explorer"       # Has some practice, seeking depth
    PRACTITIONER = "practitioner"  # Regular meditation/teaching student
    SEEKER = "seeker"           # Deep spiritual seeker

class LanguagePreference(str, Enum):
    ENGLISH = "en"
    HINDI = "hi"
    TAMIL = "ta"
    TELUGU = "te"
    KANNADA = "kn"
    MALAYALAM = "ml"
    BENGALI = "bn"
    GUJARATI = "gu"
    MARATHI = "mr"
    PUNJABI = "pa"
    HINGLISH = "hinglish"  # Code-mixed Hindi-English

@dataclass
class UserProfile:
    user_id: str
    created_at: float
    updated_at: float
    preferred_language: LanguagePreference = LanguagePreference.ENGLISH
    spiritual_level: SpiritualLevel = SpiritualLevel.BEGINNER
    topics_of_interest: List[str] = None  # ["meditation", "relationships", "suffering"]
    last_distress_assessment: Optional[Dict] = None
    total_conversations: int = 0
    total_meditations_completed: int = 0
    favorite_teachings: List[str] = None  # Source URLs they engaged with
    codemix_preference: bool = False  # Whether they use Hinglish/Tanglish
    
    def __post_init__(self):
        if self.topics_of_interest is None:
            self.topics_of_interest = []
        if self.favorite_teachings is None:
            self.favorite_teachings = []

@dataclass
class ConversationMemory:
    session_id: str
    user_id: str
    started_at: float
    messages: List[Dict]  # [{role, content, timestamp, intent, distress_level}]
    key_insights: List[str]  # Key teachings discussed
    emotional_arc: List[Dict]  # [{timestamp, distress_level, topic}]
    follow_up_suggestions: List[str]  # What to suggest next


class UserProfileService:
    """
    Manages user profiles and persistent conversation memory.
    
    Uses Supabase PostgreSQL for persistence.
    Falls back to in-memory for local development.
    """
    
    def __init__(self, supabase_client=None):
        self._supabase = supabase_client
        self._local_cache: Dict[str, UserProfile] = {}
        self._conversation_cache: Dict[str, ConversationMemory] = {}
    
    async def get_or_create_profile(self, user_id: str) -> UserProfile:
        """Get existing profile or create default."""
        if self._supabase:
            try:
                result = self._supabase.table("user_profiles").select("*").eq("user_id", user_id).execute()
                if result.data:
                    data = result.data[0]
                    # Convert string values to Enums if necessary
                    if isinstance(data.get("preferred_language"), str):
                        data["preferred_language"] = LanguagePreference(data["preferred_language"])
                    if isinstance(data.get("spiritual_level"), str):
                        data["spiritual_level"] = SpiritualLevel(data["spiritual_level"])
                    return UserProfile(**data)
            except Exception as e:
                logger.warning(f"Supabase profile fetch failed for {user_id}: {e}")
        
        # Check local cache
        if user_id in self._local_cache:
            return self._local_cache[user_id]

        # Create default
        profile = UserProfile(
            user_id=user_id,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._local_cache[user_id] = profile
        return profile
    
    async def update_profile(self, profile: UserProfile) -> None:
        """Update user profile in database."""
        profile.updated_at = time.time()
        if self._supabase:
            try:
                data = asdict(profile)
                # Convert enums to strings for DB
                data["preferred_language"] = profile.preferred_language.value
                data["spiritual_level"] = profile.spiritual_level.value
                self._supabase.table("user_profiles").upsert(data).execute()
            except Exception as e:
                logger.warning(f"Supabase profile update failed for {profile.user_id}: {e}")
        self._local_cache[profile.user_id] = profile
    
    async def save_conversation_memory(self, memory: ConversationMemory) -> None:
        """Save conversation for multi-session continuity."""
        if self._supabase:
            try:
                self._supabase.table("conversation_memories").upsert({
                    "session_id": memory.session_id,
                    "user_id": memory.user_id,
                    "started_at": memory.started_at,
                    "messages": json.dumps(memory.messages[-20:]),  # Last 20 messages
                    "key_insights": memory.key_insights,
                    "emotional_arc": json.dumps(memory.emotional_arc),
                    "follow_up_suggestions": memory.follow_up_suggestions,
                }).execute()
            except Exception as e:
                logger.warning(f"Supabase memory save failed: {e}")
        self._conversation_cache[memory.session_id] = memory
    
    async def get_recent_memories(self, user_id: str, limit: int = 3) -> List[ConversationMemory]:
        """Get recent conversation summaries for context."""
        if self._supabase:
            try:
                result = self._supabase.table("conversation_memories")\
                    .select("*")\
                    .eq("user_id", user_id)\
                    .order("started_at", desc=True)\
                    .limit(limit)\
                    .execute()
                memories = []
                for row in result.data:
                    memories.append(ConversationMemory(
                        session_id=row["session_id"],
                        user_id=row["user_id"],
                        started_at=row["started_at"],
                        messages=json.loads(row["messages"]),
                        key_insights=row["key_insights"],
                        emotional_arc=json.loads(row["emotional_arc"]),
                        follow_up_suggestions=row["follow_up_suggestions"],
                    ))
                return memories
            except Exception as e:
                logger.warning(f"Supabase memory fetch failed for {user_id}: {e}")
        memories = [
            memory for memory in self._conversation_cache.values()
            if memory.user_id == user_id
        ]
        return sorted(memories, key=lambda mem: mem.started_at, reverse=True)[:limit]
    
    async def detect_language_preference(self, user_id: str, message: str) -> LanguagePreference:
        """Detect and update user's language preference."""
        # Check for code-mixed patterns
        hinglish_patterns = [r'\b(kya|kaise|kyun|acha|theek|nahi|haan|bas|yaar)\b']
        
        # Script-based detection
        if any('\u0900' <= c <= '\u097F' for c in message):
            detected = LanguagePreference.HINDI
        elif any('\u0B80' <= c <= '\u0BFF' for c in message):
            detected = LanguagePreference.TAMIL
        elif any('\u0C00' <= c <= '\u0C7F' for c in message):
            detected = LanguagePreference.TELUGU
        elif any('\u0C80' <= c <= '\u0CFF' for c in message):
            detected = LanguagePreference.KANNADA
        elif any('\u0D00' <= c <= '\u0D7F' for c in message):
            detected = LanguagePreference.MALAYALAM
        elif any('\u0980' <= c <= '\u09FF' for c in message):
            detected = LanguagePreference.BENGALI
        elif any('\u0A80' <= c <= '\u0AFF' for c in message):
            detected = LanguagePreference.GUJARATI
        elif any(re.search(p, message.lower()) for p in hinglish_patterns):
            detected = LanguagePreference.HINGLISH
        else:
            detected = LanguagePreference.ENGLISH
        
        # Update profile
        profile = await self.get_or_create_profile(user_id)
        if detected != profile.preferred_language:
            profile.preferred_language = detected
            if detected == LanguagePreference.HINGLISH:
                profile.codemix_preference = True
            await self.update_profile(profile)
            logger.info(f"Updated language preference for {user_id}: {detected.value}")
        
        return detected

# Singleton instance will be managed by ServiceContainer

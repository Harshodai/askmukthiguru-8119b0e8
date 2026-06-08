import logging
import asyncio
from typing import Optional, List, Dict, Any
from app.config import settings
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class MemoryExtraction(BaseModel):
    core_memories: List[str] = Field(
        description="A list of 0 or more permanent facts about the user (e.g., name, location, spiritual background, primary life concerns) that were newly revealed in this transcript. Do not duplicate existing knowledge. Return empty list if no new facts are found."
    )
    episodic_memories: List[str] = Field(
        description="A list of 0 or more specific episodic insights, reflections, or goals shared by the user in this transcript (e.g., 'User wants to start daily Soul Sync', 'User felt anxious about work'). Return empty list if none."
    )
    session_summary: str = Field(
        description="A concise 1-2 sentence summary of this conversation session's core topics and user state."
    )

class MemoryService:
    """
    Manages user episodic memories, core memories, and session summaries.
    Uses Supabase PostgreSQL for persistence and local embedding service for vector queries.
    """

    def __init__(self, supabase_client=None, embedding_service=None, llm_service=None):
        self._supabase = supabase_client
        self._embedding_service = embedding_service
        self._llm_service = llm_service

    async def get_core(self, user_id: str) -> List[Dict[str, Any]]:
        """Retrieve core memories for a user."""
        if not self._supabase:
            return []
        try:
            result = await asyncio.to_thread(
                self._supabase.table("guru_core_memory")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute
            )
            return result.data if result and hasattr(result, 'data') else []
        except Exception as e:
            logger.error(f"Failed to get core memories for {user_id}: {e}")
            return []

    async def search_semantic(self, user_id: str, query: str, limit: int = 5, min_similarity: float = 0.6) -> List[Dict[str, Any]]:
        """Search episodic memories using semantic vector search via the match_user_memories RPC."""
        if not self._supabase or not self._embedding_service:
            return []
        try:
            # Generate query embedding
            # Use encode_single_full which is already wrapped with instructions and caching
            emb_dict = await asyncio.to_thread(self._embedding_service.encode_single_full, query)
            query_embedding = emb_dict["dense"]

            # Call the match_user_memories RPC function
            result = await asyncio.to_thread(
                self._supabase.rpc(
                    "match_user_memories",
                    {
                        "p_user_id": user_id,
                        "p_query_embedding": query_embedding,
                        "p_k": limit,
                        "p_min_sim": min_similarity,
                    }
                ).execute
            )
            return result.data if result and hasattr(result, 'data') else []
        except Exception as e:
            logger.error(f"Semantic search failed for {user_id}: {e}")
            return []

    async def recent_summaries(self, user_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Retrieve recent session summaries for a user."""
        if not self._supabase:
            return []
        try:
            result = await asyncio.to_thread(
                self._supabase.table("guru_session_summaries")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute
            )
            return result.data if result and hasattr(result, 'data') else []
        except Exception as e:
            logger.error(f"Failed to fetch recent summaries for {user_id}: {e}")
            return []

    async def add_explicit(self, user_id: str, content: str, is_core: bool = False) -> Dict[str, Any]:
        """Manually add a memory (either core or episodic)."""
        if not self._supabase:
            return {}
        try:
            if is_core:
                # Core memory (max 2KB check)
                if len(content) > 2048:
                    content = content[:2045] + "..."
                result = await asyncio.to_thread(
                    self._supabase.table("guru_core_memory")
                    .insert({"user_id": user_id, "content": content})
                    .execute
                )
                return result.data[0] if result and hasattr(result, 'data') and result.data else {}
            else:
                # Episodic memory
                emb_dict = await asyncio.to_thread(self._embedding_service.encode_single_full, content)
                embedding = emb_dict["dense"]
                result = await asyncio.to_thread(
                    self._supabase.table("guru_memories")
                    .insert({
                        "user_id": user_id,
                        "content": content,
                        "embedding": embedding,
                        "source": "explicit"
                    })
                    .execute
                )
                return result.data[0] if result and hasattr(result, 'data') and result.data else {}
        except Exception as e:
            logger.error(f"Failed to add memory for {user_id}: {e}")
            return {}

    async def list_memories(self, user_id: str, page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """List episodic memories for a user, paginated."""
        if not self._supabase:
            return {"memories": [], "total": 0}
        try:
            # Get total count first
            count_res = await asyncio.to_thread(
                self._supabase.table("guru_memories")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .execute
            )
            total = count_res.count if count_res and hasattr(count_res, 'count') and count_res.count is not None else 0

            # Fetch paginated slice
            start = (page - 1) * page_size
            end = start + page_size - 1
            result = await asyncio.to_thread(
                self._supabase.table("guru_memories")
                .select("id, content, source, created_at, updated_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .range(start, end)
                .execute
            )
            data = result.data if result and hasattr(result, 'data') else []
            return {"memories": data, "total": total}
        except Exception as e:
            logger.error(f"Failed to list memories for {user_id}: {e}")
            return {"memories": [], "total": 0}

    async def forget(self, user_id: str, memory_id: str) -> bool:
        """Forget/delete a memory by its ID (checks both core and episodic)."""
        if not self._supabase:
            return False
        try:
            # Try core memory first
            res_core = await asyncio.to_thread(
                self._supabase.table("guru_core_memory")
                .delete()
                .eq("id", memory_id)
                .eq("user_id", user_id)
                .execute
            )
            if res_core and hasattr(res_core, 'data') and res_core.data:
                return True

            # Try episodic memory
            res_mem = await asyncio.to_thread(
                self._supabase.table("guru_memories")
                .delete()
                .eq("id", memory_id)
                .eq("user_id", user_id)
                .execute
            )
            if res_mem and hasattr(res_mem, 'data') and res_mem.data:
                return True

            return False
        except Exception as e:
            logger.error(f"Failed to forget memory {memory_id} for user {user_id}: {e}")
            return False

    async def extract_and_write(self, user_id: str, session_id: str, messages: List[Dict[str, Any]]) -> None:
        """
        Extract core memories, episodic memories, and session summaries from a conversation transcript,
        then persist them to the database.
        """
        if not self._supabase:
            return

        # Prepare conversation transcript string
        transcript = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            transcript += f"{role.upper()}: {content}\n"

        if not transcript.strip():
            return

        try:
            import instructor
            from openai import AsyncOpenAI

            # Build client based on active LLM provider
            if settings.is_sarvam_cloud:
                client = instructor.from_openai(
                    AsyncOpenAI(
                        base_url=settings.sarvam_base_url,
                        api_key="api-key-not-used-by-bearer",
                        default_headers={"api-subscription-key": settings.sarvam_api_key},
                    ),
                    mode=instructor.Mode.JSON,
                )
                model_name = settings.sarvam_cloud_classify_model or "sarvam-30b"
            else:
                client = instructor.from_openai(
                    AsyncOpenAI(
                        base_url=f"{settings.ollama_base_url}/v1",
                        api_key="ollama",
                    ),
                    mode=instructor.Mode.JSON,
                )
                model_name = settings.model_for_classification

            prompt = (
                f"Analyze the following conversation transcript between Mukthi Guru and a seeker (User).\n"
                f"Extract:\n"
                f"1. Core memories: Any new, long-term facts about the user (e.g. name, location, spiritual goals, major life concerns). Do not repeat generic facts.\n"
                f"2. Episodic memories: Any specific insights, real-world context, or reflections shared in this conversation.\n"
                f"3. Session summary: A 1-2 sentence summary of this conversation session's topics and user emotional state.\n\n"
                f"Transcript:\n{transcript}"
            )

            # Retrieve existing core memories to avoid duplicates
            existing_cores = await self.get_core(user_id)
            existing_core_texts = [c["content"] for c in existing_cores]
            if existing_core_texts:
                prompt += f"\n\nExisting core memories to avoid duplicating:\n- " + "\n- ".join(existing_core_texts)

            # Call LLM with timeout
            resp: MemoryExtraction = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a seeker memory extractor. Return a strictly formatted JSON object matching the requested schema. Do not include any reasoning inside think tags when returning JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_model=MemoryExtraction,
                max_retries=2,
                timeout=20.0,
            )

            extracted = resp
        except Exception as e:
            logger.warning(f"Memory extraction via Instructor failed: {e}. Falling back to default empty memory.")
            # Default empty memory structure
            extracted = MemoryExtraction(core_memories=[], episodic_memories=[], session_summary="Conversation session completed.")

        # Write core memories to DB
        for content in extracted.core_memories:
            if content.strip():
                await self.add_explicit(user_id, content.strip(), is_core=True)

        # Write episodic memories to DB
        for content in extracted.episodic_memories:
            if content.strip():
                await self.add_explicit(user_id, content.strip(), is_core=False)

        # Write session summary to DB
        if extracted.session_summary.strip():
            try:
                await asyncio.to_thread(
                    self._supabase.table("guru_session_summaries")
                    .insert({
                        "user_id": user_id,
                        "session_id": session_id,
                        "summary": extracted.session_summary.strip()
                    })
                    .execute
                )
            except Exception as e:
                logger.error(f"Failed to save session summary for {user_id}: {e}")

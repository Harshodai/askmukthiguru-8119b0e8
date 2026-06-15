import asyncio
import logging
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.config import settings

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
            from openai import AsyncOpenAI
            import json as _json

            # Build client based on active LLM provider
            if settings.is_sarvam_cloud:
                client = AsyncOpenAI(
                    base_url=settings.sarvam_base_url,
                    api_key="api-key-not-used-by-bearer",
                    default_headers={"api-subscription-key": settings.sarvam_api_key},
                )
                model_name = settings.sarvam_cloud_classify_model or "sarvam-30b"
            elif settings.llm_provider.lower() == "openrouter":
                client = AsyncOpenAI(
                    base_url=settings.openrouter_base_url,
                    api_key=settings.openrouter_api_key,
                )
                model_name = settings.model_for_classification
            else:
                client = AsyncOpenAI(
                    base_url=f"{settings.ollama_base_url}/v1",
                    api_key="ollama",
                )
                model_name = settings.model_for_classification

            # Embed existing core memories to avoid duplicates
            existing_cores = await self.get_core(user_id)
            existing_core_texts = [c["content"] for c in existing_cores]
            dedup_section = ""
            if existing_core_texts:
                dedup_section = "\n\nExisting core memories (DO NOT duplicate these):\n- " + "\n- ".join(existing_core_texts)

            # Use a direct JSON template prompt — more reliable than instructor for small models
            system_msg = (
                "You are a memory extractor for a spiritual guidance system. "
                "Extract information from the conversation and return a VALID JSON object. "
                "Return ONLY the JSON object, nothing else. No reasoning, no think tags, no explanations."
            )
            user_msg = (
                f"Analyze this conversation transcript between Mukthi Guru and a seeker.\n"
                f"Extract:\n"
                f"1. core_memories: List of 0+ permanent facts about the user (name, location, spiritual goals). Leave empty [] if none found.\n"
                f"2. episodic_memories: List of 0+ specific insights or reflections shared in this session. Leave empty [] if none.\n"
                f"3. session_summary: 1-2 sentence summary of the session topics and user state.\n"
                f"{dedup_section}\n\n"
                f"Transcript:\n{transcript}\n\n"
                f"Return ONLY this JSON (fill in the values):\n"
                f'{{"core_memories": [], "episodic_memories": [], "session_summary": "..."}}'  
            )

            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.0,
                    max_tokens=1024,
                ),
                timeout=50.0,
            )
            raw_content = response.choices[0].message.content or ""

            # Robustly extract JSON from potentially dirty output
            raw_content = raw_content.strip()
            # Strip markdown code fences
            if raw_content.startswith("```"):
                import re as _re
                raw_content = _re.sub(r"^```(?:json)?\n?(.*?)\n?```$", r"\1", raw_content, flags=_re.DOTALL).strip()
            # Find outermost braces
            first_brace = raw_content.find("{")
            last_brace = raw_content.rfind("}")
            if first_brace == -1 or last_brace == -1:
                raise ValueError(f"No JSON object found in LLM response: {raw_content[:200]}")
            json_str = raw_content[first_brace:last_brace + 1]
            data = _json.loads(json_str)

            # Safe extraction with per-field fallbacks
            core_mems = data.get("core_memories", [])
            episodic_mems = data.get("episodic_memories", [])
            session_sum = data.get("session_summary", "Conversation session completed.")

            # Validate types — models occasionally return strings instead of lists
            if isinstance(core_mems, str):
                core_mems = [core_mems] if core_mems.strip() else []
            if isinstance(episodic_mems, str):
                episodic_mems = [episodic_mems] if episodic_mems.strip() else []
            if not isinstance(session_sum, str):
                session_sum = "Conversation session completed."

            extracted = MemoryExtraction(
                core_memories=[m for m in core_mems if isinstance(m, str) and m.strip()],
                episodic_memories=[m for m in episodic_mems if isinstance(m, str) and m.strip()],
                session_summary=session_sum.strip() or "Conversation session completed.",
            )
            logger.info(
                f"Memory extraction OK: {len(extracted.core_memories)} core, "
                f"{len(extracted.episodic_memories)} episodic, summary={bool(extracted.session_summary)}"
            )
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

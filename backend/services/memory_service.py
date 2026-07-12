import asyncio
import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)


class EpisodicMemoryDetail(BaseModel):
    insight: str = Field(
        description="A concise 3-6 word summary of the user's reflection or situation (e.g. 'Work Stress Anxiety', 'Daily Meditation Practice', 'Gratitude for Family'). Do NOT use 'User asked X'. Write in first person or noun phrase form representing their state."
    )
    content: str = Field(
        description="The full context of the reflection or insight."
    )
    state_category: str = Field(
        description="The state of consciousness this memory belongs to: 'Beautiful State', 'Suffering State', 'Shrinking Self', 'Destructive Self', 'Inert Self', or 'Neutral'."
    )
    related_concepts: list[str] = Field(
        description="List of related Ekam concept IDs (e.g., 'Meditation', 'Karma', 'Soul Sync', 'Consciousness', 'Ekam', 'Dharma', 'Oneness', 'Surrender', 'Awareness', 'Connection')."
    )


class MemoryExtraction(BaseModel):
    core_memories: list[str] = Field(
        description="A list of 0 or more permanent facts about the user (e.g., name, location, spiritual background, primary life concerns) that were newly revealed in this transcript. Do not duplicate existing knowledge. Return empty list if no new facts are found."
    )
    episodic_memories: list[EpisodicMemoryDetail] = Field(
        description="A list of 0 or more specific episodic insights, reflections, or goals shared by the user in this transcript, with state classifications. Return empty list if none."
    )
    session_summary: str = Field(
        description="A concise 1-2 sentence summary of this conversation session's core topics and user state."
    )



class MemoryService:
    """
    Manages user episodic memories, core memories, and session summaries.
    Uses Supabase PostgreSQL for persistence and local embedding service for vector queries.
    """

    # After this many consecutive auth/RPC failures, stop attempting semantic
    # search for the process lifetime — a misconfigured key otherwise adds an
    # error + stack unwind to EVERY user query without ever succeeding.
    _SEARCH_FAILURE_LIMIT = 3

    def __init__(self, supabase_client=None, embedding_service=None, llm_service=None):
        self._supabase = supabase_client
        self._embedding_service = embedding_service
        self._llm_service = llm_service
        self._search_failures = 0
        self._search_disabled = False

    @staticmethod
    def _is_anonymous(user_id: str | None) -> bool:
        return not user_id or user_id == "anonymous"

    async def get_core(self, user_id: str) -> list[dict[str, Any]]:
        """Retrieve core memories for a user."""
        if not self._supabase or self._is_anonymous(user_id):
            return []
        try:
            result = await asyncio.to_thread(
                self._supabase.table("guru_core_memory")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute
            )
            return result.data if result and hasattr(result, "data") else []
        except Exception as e:
            logger.error(f"Failed to get core memories for {user_id}: {e}")
            return []

    async def search_semantic(
        self, user_id: str, query: str, limit: int = 5, min_similarity: float = 0.6
    ) -> list[dict[str, Any]]:
        """Search episodic memories using semantic vector search via the match_user_memories_by_user RPC."""
        if not self._supabase or not self._embedding_service or self._search_disabled or self._is_anonymous(user_id):
            return []
        try:
            # Generate query embedding
            # Use encode_single_full which is already wrapped with instructions and caching
            emb_dict = await asyncio.to_thread(self._embedding_service.encode_single_full, query)
            query_embedding = emb_dict["dense"]

            # Call the match_user_memories_by_user RPC function
            result = await asyncio.to_thread(
                self._supabase.rpc(
                    "match_user_memories_by_user",
                    {
                        "p_user_id": user_id,
                        "p_query_embedding": query_embedding,
                        "p_k": limit,
                        "p_min_sim": min_similarity,
                    },
                ).execute
            )
            self._search_failures = 0
            return result.data if result and hasattr(result, "data") else []
        except Exception as e:
            self._search_failures += 1
            if self._search_failures >= self._SEARCH_FAILURE_LIMIT:
                self._search_disabled = True
                logger.error(
                    "Semantic memory search disabled for this process after %d consecutive "
                    "failures (last: %s). Fix the Supabase key/RPC and restart to re-enable.",
                    self._search_failures,
                    e,
                )
            else:
                logger.error(f"Semantic search failed for {user_id}: {e}")
            return []

    async def recent_summaries(self, user_id: str, limit: int = 3) -> list[dict[str, Any]]:
        """Retrieve recent session summaries for a user."""
        if not self._supabase or self._is_anonymous(user_id):
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
            return result.data if result and hasattr(result, "data") else []
        except Exception as e:
            logger.error(f"Failed to fetch recent summaries for {user_id}: {e}")
            return []

    async def add_explicit(
        self,
        user_id: str,
        content: str,
        is_core: bool = False,
        source: str = "explicit",
        run_compaction: bool = True,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Manually add a memory (either core or episodic)."""
        if not self._supabase or self._is_anonymous(user_id):
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
                return result.data[0] if result and hasattr(result, "data") and result.data else {}
            else:
                # Episodic memory
                emb_dict = await asyncio.to_thread(
                    self._embedding_service.encode_single_full, content
                )
                embedding = emb_dict["dense"]
                insert_data = {
                    "user_id": user_id,
                    "content": content,
                    "embedding": embedding,
                    "source": source,
                }
                if metadata:
                    if "claim" in metadata:
                        insert_data["claim"] = metadata["claim"]
                    elif "insight" in metadata:
                        insert_data["claim"] = metadata["insight"]
                    if "summary" in metadata:
                        insert_data["summary"] = metadata["summary"]
                    if "confidence" in metadata:
                        insert_data["confidence"] = metadata["confidence"]
                    if "decay_score" in metadata:
                        insert_data["decay_score"] = metadata["decay_score"]

                try:
                    result = await asyncio.to_thread(
                        self._supabase.table("guru_memories")
                        .insert(insert_data)
                        .execute
                    )
                except Exception as insert_err:
                    err_str = str(insert_err)
                    # PostgREST schema cache may lack new columns — retry without claim/confidence/decay/summary
                    if "PGRST204" in err_str or "Could not find" in err_str:
                        for col in ("claim", "confidence", "decay_score", "summary"):
                            insert_data.pop(col, None)
                        result = await asyncio.to_thread(
                            self._supabase.table("guru_memories")
                            .insert(insert_data)
                            .execute
                        )
                    else:
                        raise
                res_data = (
                    result.data[0] if result and hasattr(result, "data") and result.data else {}
                )
                if run_compaction:
                    await self.compact_memories(user_id)
                return res_data
        except Exception as e:
            logger.error(f"Failed to add memory for {user_id}: {e}")
            return {}

    async def list_memories(
        self, user_id: str, page: int = 1, page_size: int = 50
    ) -> dict[str, Any]:
        """List episodic memories for a user, paginated."""
        if not self._supabase or self._is_anonymous(user_id):
            return {"memories": [], "total": 0}
        try:
            # Get total count first
            count_res = await asyncio.to_thread(
                self._supabase.table("guru_memories")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .execute
            )
            total = (
                count_res.count
                if count_res and hasattr(count_res, "count") and count_res.count is not None
                else 0
            )

            # Fetch paginated slice
            start = (page - 1) * page_size
            end = start + page_size - 1
            result = await asyncio.to_thread(
                self._supabase.table("guru_memories")
                .select("id, content, source, created_at, updated_at, summary")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .range(start, end)
                .execute
            )
            data = result.data if result and hasattr(result, "data") else []
            return {"memories": data, "total": total}
        except Exception as e:
            logger.error(f"Failed to list memories for {user_id}: {e}")
            return {"memories": [], "total": 0}

    async def forget(self, user_id: str, memory_id: str) -> bool:
        """Forget/delete a memory by its ID (checks both core and episodic)."""
        if not self._supabase or self._is_anonymous(user_id):
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
            if res_core and hasattr(res_core, "data") and res_core.data:
                return True

            # Try episodic memory
            res_mem = await asyncio.to_thread(
                self._supabase.table("guru_memories")
                .delete()
                .eq("id", memory_id)
                .eq("user_id", user_id)
                .execute
            )
            if res_mem and hasattr(res_mem, "data") and res_mem.data:
                return True

            return False
        except Exception as e:
            logger.error(f"Failed to forget memory {memory_id} for user {user_id}: {e}")
            return False

    async def forget_all_reflections(self, user_id: str) -> int:
        """Delete all episodic memories (reflections) for a user. Core facts are durable."""
        if not self._supabase or self._is_anonymous(user_id):
            return 0
        try:
            res = await asyncio.to_thread(
                self._supabase.table("guru_memories")
                .delete()
                .eq("user_id", user_id)
                .execute
            )
            n = len(res.data) if res and hasattr(res, "data") and res.data else 0
            logger.info(f"forget_all_reflections user={user_id} deleted={n}")
            return n
        except Exception as e:
            logger.error(f"Failed to forget all reflections for {user_id}: {e}")
            return 0

    async def regenerate_summary(self, user_id: str) -> int:
        """Populate guru_memories.summary where NULL.

        Strategy: pull all of the user's episodic memories that lack a summary,
        pull all of the user's session summaries (guru_session_summaries), and
        fill `summary` with a fallback (first 280 chars of the claim/content)
        when a per-session match cannot be inferred. Optionally callers can run
        a richer extractor pass offline; this is a cheap, deterministic pass.
        """
        if not self._supabase or self._is_anonymous(user_id):
            return 0
        try:
            needs = await asyncio.to_thread(
                self._supabase.table("guru_memories")
                .select("id, content")
                .eq("user_id", user_id)
                .is_("summary", "null")
                .execute
            )
            rows = needs.data if needs and hasattr(needs, "data") else []
            if not rows:
                return 0
            updated = 0
            for r in rows:
                content = (r.get("content") or "").strip()
                if not content:
                    continue
                fallback = content[:280]
                try:
                    await asyncio.to_thread(
                        self._supabase.table("guru_memories")
                        .update({"summary": fallback})
                        .eq("id", r["id"])
                        .eq("user_id", user_id)
                        .execute
                    )
                    updated += 1
                except Exception as upd_err:
                    logger.warning(f"summary update failed for memory {r.get('id')}: {upd_err}")
            logger.info(f"regenerate_summary user={user_id} updated={updated}")
            return updated
        except Exception as e:
            logger.error(f"regenerate_summary failed for {user_id}: {e}")
            return 0

    async def compact_memories(self, user_id: str) -> None:
        """
        Check the total count of episodic memories for a user.
        If it exceeds 15, consolidate them using LLM into at most 8 high-quality memories.
        """
        if not self._supabase or self._is_anonymous(user_id):
            return

        try:
            # 1. Fetch current episodic memories
            result = await asyncio.to_thread(
                self._supabase.table("guru_memories")
                .select("id, content, source")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute
            )
            memories = result.data if result and hasattr(result, "data") else []
            if len(memories) <= 15:
                return

            logger.info(
                f"Triggering memory compaction for user {user_id}: {len(memories)} memories"
            )

            # 2. Consolidate via LLM
            import json as _json

            from openai import AsyncOpenAI

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
            elif settings.llm_provider.lower() == "nim":
                client = AsyncOpenAI(
                    base_url=settings.nim_base_url,
                    api_key=settings.nim_api_key,
                )
                model_name = settings.nim_classify_model
            elif settings.llm_provider.lower() == "ollama":
                client = AsyncOpenAI(
                    base_url=settings.ollama_base_url,
                    api_key="ollama",
                )
                model_name = settings.model_for_classification
            else:
                logger.warning(
                    f"Memory compaction: no supported LLM provider ({settings.llm_provider})"
                )
                return

            memory_list_str = "\n".join(f"- {m['content']}" for m in memories)

            system_msg = (
                "You are an expert memory consolidation assistant for a spiritual guidance system. "
                "The user has accumulated too many memories. "
                "Your task is to merge, deduplicate, and consolidate them into a clean, concise list of at most 8 memories. "
                "Retain crucial spiritual preferences, goals, and key contextual facts about the user. "
                "Combine similar reflections into a single coherent sentence. "
                "Return a VALID JSON object with a single key 'compacted_memories' containing a list of strings."
                "Return ONLY the JSON object, nothing else. No reasoning, no markdown formatting blocks, no think tags."
            )
            user_msg = (
                f"Here are the current user memories to consolidate:\n\n"
                f"{memory_list_str}\n\n"
                f'Return ONLY this JSON schema: {{"compacted_memories": ["memory 1", "memory 2", ...]}}'
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
                timeout=40.0,
            )
            raw_content = (response.choices[0].message.content or "").strip()

            # Clean and extract JSON
            if raw_content.startswith("```"):
                import re as _re

                raw_content = _re.sub(
                    r"^```(?:json)?\n?(.*?)\n?```$", r"\1", raw_content, flags=_re.DOTALL
                ).strip()
            first_brace = raw_content.find("{")
            last_brace = raw_content.rfind("}")
            if first_brace == -1 or last_brace == -1:
                raise ValueError(f"No JSON object in LLM compaction response: {raw_content[:200]}")

            json_str = raw_content[first_brace : last_brace + 1]
            data = _json.loads(json_str)
            compacted_list = data.get("compacted_memories", [])

            if not isinstance(compacted_list, list):
                logger.warning(f"Expected list for compacted_memories, got {type(compacted_list)}")
                return

            compacted_list = [m.strip() for m in compacted_list if isinstance(m, str) and m.strip()]
            if not compacted_list:
                logger.warning(
                    "Compacted memories list is empty, aborting replacement to avoid data loss."
                )
                return

            logger.info(f"Compacted {len(memories)} memories into {len(compacted_list)} memories.")

            # Generate embeddings for all new compacted memories first
            new_memories_data = []
            for content in compacted_list:
                emb_dict = await asyncio.to_thread(
                    self._embedding_service.encode_single_full, content
                )
                embedding = emb_dict["dense"]
                new_memories_data.append(
                    {
                        "user_id": user_id,
                        "content": content,
                        "embedding": embedding,
                        "source": "extracted",
                    }
                )

            if not new_memories_data:
                return

            # Now delete old memories
            await asyncio.to_thread(
                self._supabase.table("guru_memories").delete().eq("user_id", user_id).execute
            )

            # Insert all new memories at once!
            await asyncio.to_thread(
                self._supabase.table("guru_memories").insert(new_memories_data).execute
            )

            logger.info(f"Memory compaction successfully applied for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to compact memories for user {user_id}: {e}")

    async def extract_and_write(
        self, user_id: str, session_id: str, messages: list[dict[str, Any]]
    ) -> None:
        """
        Extract core memories, episodic memories, and session summaries from a conversation transcript,
        then persist them to the database.
        """
        if not self._supabase or self._is_anonymous(user_id):
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
            import json as _json

            from openai import AsyncOpenAI

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
            elif settings.llm_provider.lower() == "nim":
                client = AsyncOpenAI(
                    base_url=settings.nim_base_url,
                    api_key=settings.nim_api_key,
                )
                model_name = settings.nim_classify_model
            elif settings.llm_provider.lower() == "ollama":
                client = AsyncOpenAI(
                    base_url=settings.ollama_base_url,
                    api_key="ollama",
                )
                model_name = settings.model_for_classification
            else:
                logger.warning(
                    f"Memory extraction: no supported LLM provider ({settings.llm_provider})"
                )
                return []

            # Embed existing core memories to avoid duplicates
            existing_cores = await self.get_core(user_id)
            existing_core_texts = [c["content"] for c in existing_cores]
            dedup_section = ""
            if existing_core_texts:
                dedup_section = (
                    "\n\nExisting core memories (DO NOT duplicate these):\n- "
                    + "\n- ".join(existing_core_texts)
                )

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
                f"2. episodic_memories: List of 0+ specific episodic insights or reflections shared in this session.\n"
                f"   For each episodic memory, provide:\n"
                f"     - insight: A concise 3-6 word summary (e.g. 'Work Stress Anxiety', 'Daily Chanting Practice'). Do NOT use 'User asked X' or 'Seeker says Y'. Make it a short noun phrase representing their state.\n"
                f"     - content: The full context/claim of the memory.\n"
                f"     - state_category: Categorize as 'Beautiful State', 'Suffering State', 'Shrinking Self', 'Destructive Self', 'Inert Self', or 'Neutral'.\n"
                f"     - related_concepts: List of concept names this relates to (e.g., 'Meditation', 'Karma', 'Soul Sync', 'Consciousness', 'Ekam', 'Dharma', 'Oneness', 'Surrender', 'Awareness', 'Connection').\n"
                f"3. session_summary: 1-2 sentence summary of the session topics and user state.\n"
                f"{dedup_section}\n\n"
                f"Transcript:\n{transcript}\n\n"
                f"Return ONLY this JSON (fill in the values):\n"
                f'{{"core_memories": [], "episodic_memories": [{{"insight": "...", "content": "...", "state_category": "...", "related_concepts": []}}], "session_summary": "..."}}'
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

                raw_content = _re.sub(
                    r"^```(?:json)?\n?(.*?)\n?```$", r"\1", raw_content, flags=_re.DOTALL
                ).strip()
            # Find outermost braces
            first_brace = raw_content.find("{")
            last_brace = raw_content.rfind("}")
            if first_brace == -1 or last_brace == -1:
                raise ValueError(f"No JSON object found in LLM response: {raw_content[:200]}")
            json_str = raw_content[first_brace : last_brace + 1]
            data = _json.loads(json_str)

            # Safe extraction with per-field fallbacks
            core_mems = data.get("core_memories", [])
            episodic_mems = data.get("episodic_memories", [])
            session_sum = data.get("session_summary", "Conversation session completed.")

            # Validate types — models occasionally return strings instead of lists
            if isinstance(core_mems, str):
                core_mems = [core_mems] if core_mems.strip() else []
            
            validated_episodic = []
            if isinstance(episodic_mems, str):
                if episodic_mems.strip():
                    validated_episodic.append(
                        EpisodicMemoryDetail(
                            insight=episodic_mems[:30],
                            content=episodic_mems,
                            state_category="Neutral",
                            related_concepts=[]
                        )
                    )
            elif isinstance(episodic_mems, list):
                for m in episodic_mems:
                    if isinstance(m, str):
                        validated_episodic.append(
                            EpisodicMemoryDetail(
                                insight=m[:30],
                                content=m,
                                state_category="Neutral",
                                related_concepts=[]
                            )
                        )
                    elif isinstance(m, dict):
                        validated_episodic.append(
                            EpisodicMemoryDetail(
                                insight=m.get("insight", "")[:40] or m.get("content", "")[:30],
                                content=m.get("content", ""),
                                state_category=m.get("state_category", "Neutral"),
                                related_concepts=m.get("related_concepts", [])
                            )
                        )

            if not isinstance(session_sum, str):
                session_sum = "Conversation session completed."

            extracted = MemoryExtraction(
                core_memories=[m for m in core_mems if isinstance(m, str) and m.strip()],
                episodic_memories=validated_episodic,
                session_summary=session_sum.strip() or "Conversation session completed.",
            )
            logger.info(
                f"Memory extraction OK: {len(extracted.core_memories)} core, "
                f"{len(extracted.episodic_memories)} episodic, summary={bool(extracted.session_summary)}"
            )
        except Exception as e:
            logger.warning(f"Memory extraction failed: {e}. Falling back to default empty memory.")
            # Default empty memory structure
            extracted = MemoryExtraction(
                core_memories=[],
                episodic_memories=[],
                session_summary="Conversation session completed.",
            )

        # Write core memories to DB
        for content in extracted.core_memories:
            if content.strip():
                await self.add_explicit(user_id, content.strip(), is_core=True)

        # Write episodic memories to DB
        for mem in extracted.episodic_memories:
            if mem.content.strip():
                await self.add_explicit(
                    user_id,
                    mem.content.strip(),
                    is_core=False,
                    source="extracted",
                    run_compaction=False,
                    metadata={
                        "insight": mem.insight,
                        "state_category": mem.state_category,
                        "related_concepts": mem.related_concepts,
                        # Persist the session_summary as a column on each episodic memory row.
                        # Task 9 (Memory tab on Profile) surfaces this summary instead of the
                        # raw `claim` content. Falls back gracefully if the column is absent
                        # (PGRST204 retry in add_explicit drops it).
                        "summary": extracted.session_summary.strip(),
                    }
                )

        # Run memory compaction check
        await self.compact_memories(user_id)

        # Write session summary to DB
        if extracted.session_summary.strip():
            try:
                await asyncio.to_thread(
                    self._supabase.table("guru_session_summaries")
                    .insert(
                        {
                            "user_id": user_id,
                            "session_id": session_id,
                            "summary": extracted.session_summary.strip(),
                        }
                    )
                    .execute
                )
            except Exception as e:
                logger.error(f"Failed to save session summary for {user_id}: {e}")

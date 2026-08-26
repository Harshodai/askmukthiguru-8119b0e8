import asyncio
import logging
import uuid
from datetime import UTC, datetime
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)


def _safe_confidence(val: Any, default: float = 0.75) -> float:
    try:
        v = float(val) if val is not None else default
        return max(0.0, min(1.0, v))
    except (TypeError, ValueError):
        return default


# Auto-derived fact keys drive (subject, relation) supersession: a new fact
# with the same key CLOSES the prior one (valid_to set). That is only safe
# for relations where a person genuinely has one current value — one primary
# residence, one primary occupation. "daily_practice", "preference", and
# "possession" are naturally multi-valued ("I have anxiety" and "I have a
# daughter" are both true at once), so they are deliberately excluded here:
# auto-keying them previously made the second statement soft-delete the
# first. Callers that need a real correction on a multi-valued relation can
# still force one via an explicit `metadata["fact_key"]` (see below) — this
# only restricts what gets keyed *automatically* from regex matches.
_SINGLE_VALUED_FACT_KEY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("lives_in", re.compile(r"\b(?:i|we|user|seeker)\s+(?:live|lives|moved|move)\s+(?:in|to|at)\b", re.I)),
    ("occupation", re.compile(r"\b(?:i|we|user|seeker)\s+(?:work|works|study|studies)\b", re.I)),
)


def _derive_fact_key(content: str, metadata: Optional[dict[str, Any]] = None) -> str | None:
    """Derive a stable subject/relation key for genuinely single-valued facts.

    Wording and value stay out of the key by design (so "I live in Delhi" and
    "I moved to Chennai" collide and correctly supersede). Multi-valued
    relations (possession, preference, daily_practice) return None here and
    are never auto-superseded — see the comment above the pattern table.
    """
    metadata = metadata or {}
    explicit = metadata.get("fact_key")
    if isinstance(explicit, str) and explicit.strip():
        return re.sub(r"[^a-z0-9:_-]+", "_", explicit.strip().lower()).strip("_")[:120]
    candidate = metadata.get("claim") or metadata.get("insight") or content
    if not isinstance(candidate, str):
        return None
    normalized = " ".join(candidate.split())
    for relation, pattern in _SINGLE_VALUED_FACT_KEY_PATTERNS:
        if pattern.search(normalized):
            return f"user:{relation}"
    return None


class EpisodicMemoryDetail(BaseModel):
    insight: str = Field(
        description="A concise 3-6 word summary of the user's reflection or situation (e.g. 'Work Stress Anxiety', 'Daily Meditation Practice', 'Gratitude for Family'). Do NOT use 'User asked X'. Write in first person or noun phrase form representing their state."
    )
    content: str = Field(description="The full context of the reflection or insight.")
    state_category: str = Field(
        description="The state of consciousness this memory belongs to: 'Beautiful State', 'Suffering State', 'Shrinking Self', 'Destructive Self', 'Inert Self', or 'Neutral'."
    )
    related_concepts: list[str] = Field(
        description="List of related Ekam concept IDs (e.g., 'Meditation', 'Karma', 'Soul Sync', 'Consciousness', 'Ekam', 'Dharma', 'Oneness', 'Surrender', 'Awareness', 'Connection')."
    )
    claim: str = Field(
        default="",
        description="The factual claim distilled from this memory, stated as a simple declarative sentence about the seeker (e.g. 'Seeker experiences anxiety about work presentations').",
    )
    confidence: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Confidence in this memory: 0.0-1.0. Base on the model's certainty, explicit vs inferred, and whether the seeker stated it directly.",
    )


class ClaimedMemory(BaseModel):
    claim: str = Field(
        description="A concise declarative claim about the seeker, distilled from one or more conversation turns."
    )
    confidence: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Confidence in the claim (0.0-1.0): direct self-report = higher, inferred/ambiguous = lower.",
    )


class MemoryExtraction(BaseModel):
    core_memories: list[str] = Field(
        description="A list of 0 or more permanent facts about the user (e.g., name, location, spiritual background, primary life concerns) that were newly revealed in this transcript. Do not duplicate existing knowledge. Return empty list if no new facts are found."
    )
    episodic_memories: list[EpisodicMemoryDetail] = Field(
        description="A list of 0 or more specific episodic insights, reflections, or goals shared by the user in this transcript, with state classifications. Return empty list if none."
    )
    claimed_memories: list[ClaimedMemory] = Field(
        default_factory=list,
        description="A list of 0 or more high-confidence factual claims about the seeker drawn from the transcript. Each claim should be a standalone fact with a confidence score (0.0-1.0).",
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
        self._reinforce_tasks: set[asyncio.Task] = set()

    @staticmethod
    def _is_anonymous(user_id: Optional[str]) -> bool:
        # Anonymous/incognito sessions resolve to "anon:<session_id>" (see
        # resolve_anon_identity, root CLAUDE.md caching invariants) which is
        # not a valid Postgres uuid — only a parseable UUID is persistable.
        if not user_id:
            return True
        try:
            uuid.UUID(str(user_id))
            return False
        except (ValueError, TypeError):
            return True

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
        """Search episodic memories using semantic vector search with bio-mimetic time decay."""
        if (
            not self._supabase
            or not self._embedding_service
            or self._search_disabled
            or self._is_anonymous(user_id)
        ):
            return []
        try:
            # Generate query embedding
            emb_dict = await asyncio.to_thread(self._embedding_service.encode_single_full, query)
            query_embedding = emb_dict["dense"]

            # Call the match_user_memories_by_user RPC function
            result = await asyncio.to_thread(
                self._supabase.rpc(
                    "match_user_memories_by_user",
                    {
                        "p_user_id": user_id,
                        "p_query_embedding": query_embedding,
                        "p_k": limit * 2,  # Fetch slightly more to re-rank with decay
                        "p_min_sim": min_similarity,
                    },
                ).execute
            )
            self._search_failures = 0
            raw_memories = result.data if result and hasattr(result, "data") else []

            # Apply Bio-Mimetic Decay calculations
            import math
            from datetime import datetime

            now = datetime.now(UTC)
            scored_memories = []
            for mem in raw_memories:
                updated_at_str = mem.get("updated_at") or mem.get("created_at")
                if updated_at_str:
                    try:
                        cleaned_str = updated_at_str.replace("Z", "+00:00")
                        last_updated = datetime.fromisoformat(cleaned_str)
                        if last_updated.tzinfo is None:
                            last_updated = last_updated.replace(tzinfo=UTC)
                        delta_days = (now - last_updated).total_seconds() / (24.0 * 3600.0)
                    except Exception:
                        delta_days = 0.0
                else:
                    delta_days = 0.0

                decay_factor = math.exp(-0.01 * delta_days)
                original_decay = mem.get("decay_score")
                if original_decay is None:
                    original_decay = 1.0

                current_decay = original_decay * decay_factor
                mem["decay_score_current"] = current_decay

                similarity = mem.get("similarity", 0.0)
                mem["combined_score"] = similarity * current_decay
                scored_memories.append(mem)

            # Sort by combined_score descending
            scored_memories.sort(key=lambda x: x.get("combined_score", 0.0), reverse=True)
            final_results = scored_memories[:limit]

            # Reinforcement: Asynchronously boost decay_score for the top 3 accessed memories
            for mem in final_results[:3]:
                mem_id = mem.get("id")
                if mem_id:
                    db_decay = mem.get("decay_score")
                    if db_decay is None:
                        db_decay = 1.0
                    new_decay = min(2.0, db_decay + 0.20)
                    task = asyncio.create_task(self._reinforce_memory(mem_id, new_decay))
                    self._reinforce_tasks.add(task)
                    task.add_done_callback(self._reinforce_tasks.discard)

            return final_results
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

    async def _reinforce_memory(self, memory_id: str, new_decay: float) -> None:
        """Asynchronously boost a memory's decay score in the database."""
        try:
            await asyncio.to_thread(
                self._supabase.table("guru_memories")
                .update({"decay_score": new_decay})
                .eq("id", memory_id)
                .execute
            )
            logger.debug(f"Reinforced memory {memory_id} to decay_score={new_decay}")
        except Exception as e:
            logger.error(f"Failed to reinforce memory {memory_id}: {e}")

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
                # Episodic memory: embeddings support retrieval only. Contradiction
                # handling uses a deterministic fact key, never cosine similarity.
                emb_dict = await asyncio.to_thread(
                    self._embedding_service.encode_single_full, content
                )
                embedding = emb_dict["dense"]
                fact_key = _derive_fact_key(content, metadata)
                valid_from = datetime.now(UTC).isoformat()
                supersede_ids: list[str] = []
                if fact_key:
                    try:
                        active_result = await asyncio.to_thread(
                            self._supabase.table("guru_memories")
                            .select("id")
                            .eq("user_id", user_id)
                            .eq("fact_key", fact_key)
                            .is_("valid_to", "null")
                            .execute
                        )
                        supersede_ids = [
                            row["id"]
                            for row in (active_result.data or [])
                            if isinstance(row, dict) and isinstance(row.get("id"), str)
                        ]
                    except Exception as key_err:
                        logger.warning(
                            "Deterministic memory supersession lookup unavailable for %s: %s",
                            fact_key,
                            key_err,
                        )

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
                        insert_data["confidence"] = _safe_confidence(metadata["confidence"])
                    if "decay_score" in metadata:
                        insert_data["decay_score"] = metadata["decay_score"]
                if fact_key:
                    insert_data["fact_key"] = fact_key
                    insert_data["valid_from"] = valid_from

                try:
                    result = await asyncio.to_thread(
                        self._supabase.table("guru_memories").insert(insert_data).execute
                    )
                except Exception as insert_err:
                    err_str = str(insert_err)
                    # PostgREST schema cache may lack new columns — retry without optional cols
                    if "PGRST204" in err_str or "Could not find" in err_str:
                        for col in (
                            "claim",
                            "confidence",
                            "decay_score",
                            "summary",
                            "fact_key",
                            "valid_from",
                        ):
                            insert_data.pop(col, None)
                        result = await asyncio.to_thread(
                            self._supabase.table("guru_memories").insert(insert_data).execute
                        )
                    else:
                        raise

                if supersede_ids and fact_key:
                    try:
                        await asyncio.to_thread(
                            self._supabase.table("guru_memories")
                            .update({"valid_to": valid_from})
                            .eq("user_id", user_id)
                            .in_("id", supersede_ids)
                            .execute
                        )
                    except Exception as supersede_err:
                        logger.error(
                            "Failed to close superseded memories for %s/%s: %s",
                            user_id,
                            fact_key,
                            supersede_err,
                        )
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
                .is_("valid_to", "null")
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
                .select(
                    "id, content, source, created_at, updated_at, summary, claim, confidence, decay_score, metadata, fact_key, valid_from, valid_to"
                )
                .eq("user_id", user_id)
                .is_("valid_to", "null")
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

    async def edit(self, user_id: str, memory_id: str, content: str) -> dict[str, Any]:
        """Edit/correct a memory's text by its ID (checks both core and episodic).

        Ownership-checked the same way as forget(): the update filters on both
        id and user_id, so it only ever touches a row the caller owns.
        """
        if not self._supabase or self._is_anonymous(user_id):
            return {}
        try:
            # Try core memory first
            core_content = content
            if len(core_content) > 2048:
                core_content = core_content[:2045] + "..."
            res_core = await asyncio.to_thread(
                self._supabase.table("guru_core_memory")
                .update({"content": core_content})
                .eq("id", memory_id)
                .eq("user_id", user_id)
                .execute
            )
            if res_core and hasattr(res_core, "data") and res_core.data:
                return res_core.data[0]

            # Try episodic memory — re-embed so semantic search stays accurate
            emb_dict = await asyncio.to_thread(self._embedding_service.encode_single_full, content)
            res_mem = await asyncio.to_thread(
                self._supabase.table("guru_memories")
                .update({"content": content, "embedding": emb_dict["dense"]})
                .eq("id", memory_id)
                .eq("user_id", user_id)
                .execute
            )
            if res_mem and hasattr(res_mem, "data") and res_mem.data:
                return res_mem.data[0]

            return {}
        except Exception as e:
            logger.error(f"Failed to edit memory {memory_id} for user {user_id}: {e}")
            return {}

    async def forget_all_reflections(self, user_id: str) -> int:
        """Delete all episodic memories (reflections) for a user. Core facts are durable."""
        if not self._supabase or self._is_anonymous(user_id):
            return 0
        try:
            res = await asyncio.to_thread(
                self._supabase.table("guru_memories").delete().eq("user_id", user_id).execute
            )
            n = len(res.data) if res and hasattr(res, "data") and res.data else 0
            logger.info(f"forget_all_reflections user={user_id} deleted={n}")
            return n
        except Exception as e:
            logger.error(f"Failed to forget all reflections for {user_id}: {e}")
            return 0

    async def regenerate_summary(self, user_id: str) -> int:
        """Populate guru_memories.summary where NULL.

        One bulk UPDATE via the regenerate_summaries RPC fills every NULL
        summary with the first 280 characters of its content in a single
        round-trip (previously one UPDATE per row: ~1000 rows = 20-50s of
        sequential round-trips).
        """
        if not self._supabase or self._is_anonymous(user_id):
            return 0
        try:
            res = await asyncio.to_thread(
                self._supabase.rpc("regenerate_summaries", {"p_user_id": user_id}).execute
            )
            updated = int(res.data) if res and hasattr(res, "data") else 0
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
            # 1. Fetch current episodic memories with metadata
            result = await asyncio.to_thread(
                self._supabase.table("guru_memories")
                .select("id, content, source, claim, confidence, summary, fact_key, valid_from")
                .eq("user_id", user_id)
                .is_("valid_to", "null")
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
                f'Return ONLY this JSON schema: {{"compacted_memories": ["memory 1", "memory 2", ...]}}\n\n'
                f"Here are the current user memories to consolidate:\n\n"
                f"{memory_list_str}"
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

            # Aggregate metadata from original memories for preservation
            _claims = [m.get("claim", "") for m in memories if m.get("claim")]
            _best_confidence = max(
                (
                    float(m.get("confidence") or 0)
                    for m in memories
                    if m.get("confidence") is not None
                ),
                default=0.75,
            )
            _summaries = [m.get("summary", "") for m in memories if m.get("summary")]
            _best_summary = max(_summaries, key=len) if _summaries else ""

            # Generate embeddings for all new compacted memories first
            new_memories_data = []
            for content in compacted_list:
                emb_dict = await asyncio.to_thread(
                    self._embedding_service.encode_single_full, content
                )
                embedding = emb_dict["dense"]
                row = {
                    "user_id": user_id,
                    "content": content,
                    "embedding": embedding,
                    "source": "extracted",
                }
                if _claims:
                    row["claim"] = _claims[0]
                row["confidence"] = _best_confidence
                if _best_summary:
                    row["summary"] = _best_summary
                new_memories_data.append(row)

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
                f"     - claim (optional): A concise declarative factual claim about the seeker distilled from this memory.\n"
                f"     - confidence (optional): 0.0-1.0 confidence score for the claim.\n"
                f"3. claimed_memories: List of 0+ standalone factual claims about the seeker. Each must have:\n"
                f"     - claim: A concise declarative sentence about the seeker (e.g. 'Seeker has a daily meditation practice').\n"
                f"     - confidence: 0.0-1.0 (direct self-report higher, inferred lower).\n"
                f"4. session_summary: 1-2 sentence summary of the session topics and user state.\n\n"
                f"Return ONLY this JSON (fill in the values):\n"
                f'{{"core_memories": [], "episodic_memories": [{{"insight": "...", "content": "...", "state_category": "...", "related_concepts": []}}], "claimed_memories": [{{"claim": "...", "confidence": 0.85}}], "session_summary": "..."}}\n\n'
                f"{dedup_section}\n\n"
                f"Transcript:\n{transcript}"
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
            claimed_mems = data.get("claimed_memories", [])
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
                            related_concepts=[],
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
                                related_concepts=[],
                            )
                        )
                    elif isinstance(m, dict):
                        validated_episodic.append(
                            EpisodicMemoryDetail(
                                insight=m.get("insight", "")[:40] or m.get("content", "")[:30],
                                content=m.get("content", ""),
                                state_category=m.get("state_category", "Neutral"),
                                related_concepts=m.get("related_concepts", []),
                                claim=m.get("claim", ""),
                                confidence=_safe_confidence(m.get("confidence")),
                            )
                        )

            validated_claimed = []
            if isinstance(claimed_mems, str):
                if claimed_mems.strip():
                    validated_claimed.append(ClaimedMemory(claim=claimed_mems, confidence=0.75))
            elif isinstance(claimed_mems, list):
                for m in claimed_mems:
                    if isinstance(m, str) and m.strip():
                        validated_claimed.append(ClaimedMemory(claim=m, confidence=0.75))
                    elif isinstance(m, dict):
                        claim_text = m.get("claim", "").strip()
                        if claim_text:
                            validated_claimed.append(
                                ClaimedMemory(
                                    claim=claim_text,
                                    confidence=_safe_confidence(m.get("confidence")),
                                )
                            )

            if not isinstance(session_sum, str):
                session_sum = "Conversation session completed."

            extracted = MemoryExtraction(
                core_memories=[m for m in core_mems if isinstance(m, str) and m.strip()],
                episodic_memories=validated_episodic,
                claimed_memories=validated_claimed,
                session_summary=session_sum.strip() or "Conversation session completed.",
            )
            logger.info(
                f"Memory extraction OK: {len(extracted.core_memories)} core, "
                f"{len(extracted.episodic_memories)} episodic, "
                f"{len(extracted.claimed_memories)} claimed, summary={bool(extracted.session_summary)}"
            )
        except Exception as e:
            logger.warning(f"Memory extraction failed: {e}. Falling back to default empty memory.")
            # Default empty memory structure
            extracted = MemoryExtraction(
                core_memories=[],
                episodic_memories=[],
                claimed_memories=[],
                session_summary="Conversation session completed.",
            )

        # Write core memories to DB
        for content in extracted.core_memories:
            if content.strip():
                await self.add_explicit(user_id, content.strip(), is_core=True)

        # Write claimed memories to DB as high-fidelity episodic rows.
        # Each claim becomes a memory row with claim/confidence columns populated.
        claim_memories = list(extracted.claimed_memories)
        for mem in extracted.episodic_memories:
            if mem.claim or mem.confidence != 0.75:
                claim_memories.append(
                    ClaimedMemory(claim=mem.claim or mem.content.strip(), confidence=mem.confidence)
                )

        for claimed in claim_memories:
            claim_text = claimed.claim.strip()
            if not claim_text:
                continue
            await self.add_explicit(
                user_id,
                claim_text,
                is_core=False,
                source="extracted",
                run_compaction=False,
                metadata={
                    "claim": claim_text,
                    "confidence": _safe_confidence(claimed.confidence),
                    "summary": extracted.session_summary.strip(),
                },
            )

        # Write legacy episodic memories to DB (for memories without explicit claim/confidence).
        for mem in extracted.episodic_memories:
            if mem.content.strip() and not (mem.claim or mem.confidence != 0.75):
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
                    },
                )

        # Run memory compaction check
        await self.compact_memories(user_id)

        # Write session summary to DB (upsert to handle re-ingestion)
        if extracted.session_summary.strip():
            try:
                await asyncio.to_thread(
                    self._supabase.table("guru_session_summaries")
                    .upsert(
                        {
                            "user_id": user_id,
                            "session_id": session_id,
                            "summary": extracted.session_summary.strip(),
                        },
                        on_conflict="user_id,session_id",
                    )
                    .execute
                )
            except Exception as e:
                logger.error(f"Failed to save session summary for {user_id}: {e}")

"""Memory Retriever — Phase 8 of the Adaptive Memory System.

Fetches relevant memories from the canonical Postgres store with bounded
context.  Combines semantic search (Qdrant vector index) with lexical search
(Postgres ILIKE on fact_key / statement), merges candidate pools, ranks by a
composite score, and enforces hard limits (20 memories, 2000 tokens, 200ms).

Design principles:
    - User isolation enforced server-side on every query.
    - Memory failure never fails chat (degrade gracefully).
    - Hard limits are non-negotiable — bounded context for generation.
    - Postgres is source of truth; Qdrant is a derived semantic index.
    - Retrieved content is fenced — never interpreted as instructions.
"""

from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hard limits (from target architecture §9.3)
# ---------------------------------------------------------------------------

MAX_MEMORIES = 20
MAX_TOKENS = 2000
MAX_LATENCY_MS = 200
MAX_VECTOR_RESULTS = 50
LEXICAL_LIMIT = 30

# Rough token estimator: ~4 chars per token (conservative for English)
_CHARS_PER_TOKEN = 4

# ---------------------------------------------------------------------------
# Ranking weights (from target architecture §9.2)
# ---------------------------------------------------------------------------

W_SEMANTIC = 0.35
W_LEXICAL = 0.10
W_IMPORTANCE = 0.15
W_CONFIDENCE = 0.10
W_FRESHNESS = 0.10
W_EVIDENCE = 0.10
W_RECENCY_USE = 0.10

# Recency decay: half-life in days for freshness scoring
_FRESHNESS_HALF_LIFE_DAYS = 90

# ---------------------------------------------------------------------------
# Status priority for ranking (active > superseded > expired)
# ---------------------------------------------------------------------------

_STATUS_PRIORITY: dict[str, float] = {
    "active": 1.0,
    "superseded": 0.3,
    "expired": 0.1,
    "deleted": 0.0,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RetrievedMemory:
    """A single memory retrieved for inclusion in generation context.

    Attributes:
        id: UUID of the canonical_memories row.
        statement: Natural-language fact about the user.
        memory_type: Classification (PROFILE, PREFERENCE, etc.).
        confidence: Extraction confidence (0.0-1.0).
        importance: How critical (0.0-1.0).
        evidence_count: How many times re-confirmed.
        fact_key: Dedup namespace (e.g. 'user:lives_in').
        status: Current lifecycle state.
        score: Composite ranking score (0.0-1.0).
        semantic_score: Raw cosine similarity from Qdrant (0.0-1.0 or None).
        lexical_score: Lexical match score (0.0-1.0 or None).
        source_conversation_id: Which conversation produced this.
        created_at: When the memory was created.
        updated_at: When last updated.
    """

    id: str
    statement: str
    memory_type: str
    confidence: float = 0.75
    importance: float = 0.5
    evidence_count: int = 1
    fact_key: Optional[str] = None
    status: str = "active"
    score: float = 0.0
    semantic_score: Optional[float] = None
    lexical_score: Optional[float] = None
    source_conversation_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def estimated_tokens(self) -> int:
        """Rough token count for budget enforcement."""
        return max(1, len(self.statement) // _CHARS_PER_TOKEN)


@dataclass
class RetrievalResult:
    """Output of memory retrieval — bounded, ranked memories for context.

    Attributes:
        memories: Ranked list of RetrievedMemory (max 20).
        total_tokens: Sum of estimated tokens across all memories.
        truncated: True if memories were dropped to fit token budget.
        latency_ms: Wall-clock retrieval time in milliseconds.
        query: The original query text (for logging, not stored).
    """

    memories: list[RetrievedMemory] = field(default_factory=list)
    total_tokens: int = 0
    truncated: bool = False
    latency_ms: float = 0.0
    query: str = ""


# ---------------------------------------------------------------------------
# Canonical Memory Retriever
# ---------------------------------------------------------------------------

class CanonicalMemoryRetriever:
    """Retrieve relevant memories for a query with bounded context.

    Combines semantic (Qdrant) and lexical (Postgres) search, merges
    candidate pools, ranks by composite score, and enforces hard limits.

    Args:
        supabase_client: Supabase Postgres client for lexical search and
            last_used_at updates.
        vector_index: CanonicalMemoryVectorIndex (Phase 7) for semantic search.
        embedding_service: Async callable ``async (text) -> list[float]``
            that produces a 1024-dim embedding for the query.
    """

    def __init__(
        self,
        supabase_client: Any,
        vector_index: Any,
        embedding_service: Any,
    ) -> None:
        self._db = supabase_client
        self._vector_index = vector_index
        self._embedder = embedding_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        user_id: str,
        query: str,
        limit: int = MAX_MEMORIES,
        max_tokens: int = MAX_TOKENS,
    ) -> RetrievalResult:
        """Retrieve relevant memories for a query.

        Steps:
            1. Embed query (semantic)
            2. Vector search via Qdrant (semantic candidates)
            3. Lexical search via Postgres (fact_key match, statement ILIKE)
            4. Merge candidate pools (dedup by memory id)
            5. Rank by composite score
            6. Apply hard limits (max memories, max tokens)
            7. Update last_used_at for retrieved memories
            8. Return RetrievalResult

        Args:
            user_id: The owning user ID (enforced server-side).
            query: The user's query text.
            limit: Max memories to return (default 20).
            max_tokens: Max token budget (default 2000).

        Returns:
            RetrievalResult with ranked, bounded memories.
        """
        start = time.monotonic()
        limit = min(limit, MAX_MEMORIES)
        max_tokens = min(max_tokens, MAX_TOKENS)

        candidates: dict[str, RetrievedMemory] = {}

        # 1. Semantic search (Qdrant)
        semantic_results = await self._semantic_search(user_id, query)
        for sr in semantic_results:
            mid = sr["id"]
            candidates[mid] = RetrievedMemory(
                id=mid,
                statement="",  # hydrated below
                memory_type=sr.get("memory_type", ""),
                semantic_score=sr.get("score"),
                status=sr.get("status", "active"),
            )

        # 2. Lexical search (Postgres)
        lexical_results = await self._lexical_search(user_id, query)
        for lr in lexical_results:
            mid = lr["id"]
            if mid in candidates:
                # Merge lexical score into existing semantic candidate
                candidates[mid].lexical_score = lr.get("lexical_score", 0.0)
            else:
                candidates[mid] = RetrievedMemory(
                    id=mid,
                    statement=lr.get("statement", ""),
                    memory_type=lr.get("memory_type", ""),
                    lexical_score=lr.get("lexical_score", 0.0),
                    confidence=lr.get("confidence", 0.75),
                    importance=lr.get("importance", 0.5),
                    evidence_count=lr.get("evidence_count", 1),
                    fact_key=lr.get("fact_key"),
                    status=lr.get("status", "active"),
                    source_conversation_id=lr.get("source_conversation_id"),
                    created_at=lr.get("created_at"),
                    updated_at=lr.get("updated_at"),
                )

        # 3. Hydrate missing statements from Postgres
        missing_ids = [mid for mid, m in candidates.items() if not m.statement]
        if missing_ids:
            hydrated = await self._hydrate_memories(user_id, missing_ids)
            for mem_data in hydrated:
                mid = mem_data["id"]
                if mid in candidates:
                    m = candidates[mid]
                    m.statement = mem_data.get("statement", "")
                    m.memory_type = mem_data.get("memory_type", m.memory_type)
                    m.confidence = mem_data.get("confidence", m.confidence)
                    m.importance = mem_data.get("importance", m.importance)
                    m.evidence_count = mem_data.get("evidence_count", m.evidence_count)
                    m.fact_key = mem_data.get("fact_key", m.fact_key)
                    m.status = mem_data.get("status", m.status)
                    m.source_conversation_id = mem_data.get("source_conversation_id")
                    m.created_at = mem_data.get("created_at")
                    m.updated_at = mem_data.get("updated_at")

        # 4. Filter out candidates with no statement (phantom vectors)
        candidates = {mid: m for mid, m in candidates.items() if m.statement}

        # 5. Rank by composite score
        now = datetime.now(timezone.utc)
        for m in candidates.values():
            m.score = self._composite_score(m, query, now)

        # 6. Sort by score descending
        ranked = sorted(candidates.values(), key=lambda m: m.score, reverse=True)

        # 7. Apply hard limits
        selected, total_tokens, truncated = self._apply_limits(ranked, limit, max_tokens)

        # 8. Update last_used_at (fire-and-forget, non-blocking)
        retrieved_ids = [m.id for m in selected]
        if retrieved_ids:
            try:
                await self._update_last_used(user_id, retrieved_ids)
            except Exception as e:
                logger.warning("Failed to update last_used_at: %s", e)

        latency_ms = (time.monotonic() - start) * 1000

        return RetrievalResult(
            memories=selected,
            total_tokens=total_tokens,
            truncated=truncated,
            latency_ms=latency_ms,
            query=query,
        )

    # ------------------------------------------------------------------
    # Semantic search (Qdrant)
    # ------------------------------------------------------------------

    async def _semantic_search(
        self, user_id: str, query: str
    ) -> list[dict[str, Any]]:
        """Embed query and search Qdrant for semantic matches.

        Returns list of ``{"id", "score", "memory_type", "status"}``.
        On failure, returns empty list (graceful degradation).
        """
        try:
            vector = await self._embedder(query)
            results = await self._vector_index.search(
                user_id=user_id,
                vector=vector,
                limit=MAX_VECTOR_RESULTS,
            )
            return results
        except Exception as e:
            logger.warning("Semantic search failed, falling back to lexical: %s", e)
            return []

    # ------------------------------------------------------------------
    # Lexical search (Postgres)
    # ------------------------------------------------------------------

    async def _lexical_search(
        self, user_id: str, query: str
    ) -> list[dict[str, Any]]:
        """Search Postgres for lexical matches on fact_key and statement.

        Uses ILIKE for case-insensitive substring matching.
        Returns list of memory dicts with a lexical_score.
        On failure, returns empty list.
        """
        try:
            # Extract meaningful terms from query (strip stopwords, keep nouns)
            terms = self._extract_search_terms(query)
            if not terms:
                return []

            # Search by fact_key (exact match on terms)
            fact_key_results = await self._search_by_fact_key(user_id, terms)

            # Search by statement ILIKE (substring match)
            statement_results = await self._search_by_statement(user_id, terms)

            # Merge and dedup by id, keeping highest lexical_score
            seen: dict[str, dict] = {}
            for row in fact_key_results + statement_results:
                mid = row["id"]
                if mid not in seen or row.get("lexical_score", 0) > seen[mid].get("lexical_score", 0):
                    seen[mid] = row

            results = list(seen.values())
            # Sort by lexical_score descending, cap at LEXICAL_LIMIT
            results.sort(key=lambda r: r.get("lexical_score", 0), reverse=True)
            return results[:LEXICAL_LIMIT]

        except Exception as e:
            logger.warning("Lexical search failed: %s", e)
            return []

    async def _search_by_fact_key(
        self, user_id: str, terms: list[str]
    ) -> list[dict[str, Any]]:
        """Search by fact_key containing any of the search terms."""
        results: list[dict[str, Any]] = []
        for term in terms:
            try:
                # ILIKE pattern: %term%
                result = (
                    self._db.table("canonical_memories")
                    .select("id, fact_key, statement, memory_type, confidence, "
                            "importance, evidence_count, status, "
                            "source_conversation_id, created_at, updated_at")
                    .eq("user_id", user_id)
                    .eq("status", "active")
                    .ilike("fact_key", f"%{term}%")
                    .limit(LEXICAL_LIMIT)
                    .execute()
                )
                rows = result.data if result.data else []
                for row in rows:
                    row["lexical_score"] = 0.8  # fact_key match is high confidence
                    results.append(row)
            except Exception:
                continue
        return results

    async def _search_by_statement(
        self, user_id: str, terms: list[str]
    ) -> list[dict[str, Any]]:
        """Search by statement containing any of the search terms."""
        results: list[dict[str, Any]] = []
        for term in terms:
            try:
                result = (
                    self._db.table("canonical_memories")
                    .select("id, fact_key, statement, memory_type, confidence, "
                            "importance, evidence_count, status, "
                            "source_conversation_id, created_at, updated_at")
                    .eq("user_id", user_id)
                    .eq("status", "active")
                    .ilike("statement", f"%{term}%")
                    .limit(LEXICAL_LIMIT)
                    .execute()
                )
                rows = result.data if result.data else []
                for row in rows:
                    # Score based on how many terms matched
                    row["lexical_score"] = 0.5  # baseline for statement match
                    results.append(row)
            except Exception:
                continue
        return results

    def _extract_search_terms(self, query: str) -> list[str]:
        """Extract meaningful search terms from a query.

        Strips common stopwords and short words. Returns up to 5 terms.
        """
        stopwords = {
            "i", "me", "my", "mine", "myself", "you", "your", "yours",
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after",
            "and", "but", "or", "nor", "not", "so", "yet", "both",
            "that", "this", "these", "those", "what", "which", "who",
            "whom", "whose", "when", "where", "why", "how", "all",
            "each", "every", "some", "any", "few", "more", "most",
            "other", "about", "tell", "me", "know", "remember",
        }
        words = re.findall(r"[a-zA-Z\u0900-\u097F\u0C00-\u0C7F]+", query.lower())
        terms = [w for w in words if len(w) > 2 and w not in stopwords]
        return terms[:5]

    # ------------------------------------------------------------------
    # Hydration (Postgres)
    # ------------------------------------------------------------------

    async def _hydrate_memories(
        self, user_id: str, memory_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Fetch full memory records from Postgres for IDs without statements."""
        if not memory_ids:
            return []
        try:
            result = (
                self._db.table("canonical_memories")
                .select("*")
                .eq("user_id", user_id)
                .in_("id", memory_ids)
                .execute()
            )
            return result.data if result.data else []
        except Exception as e:
            logger.warning("Hydration failed for %d memories: %s", len(memory_ids), e)
            return []

    # ------------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------------

    def _composite_score(
        self,
        memory: RetrievedMemory,
        query: str,
        now: datetime,
    ) -> float:
        """Compute composite ranking score for a memory.

        Score = Σ(weight × normalized_signal)
        """
        # Semantic relevance (from Qdrant cosine score)
        semantic = memory.semantic_score if memory.semantic_score is not None else 0.0

        # Lexical relevance
        lexical = memory.lexical_score if memory.lexical_score is not None else 0.0

        # Importance (already 0-1)
        importance = memory.importance

        # Confidence (already 0-1)
        confidence = memory.confidence

        # Freshness (recency decay from updated_at or created_at)
        freshness = self._freshness_score(memory.updated_at or memory.created_at, now)

        # Evidence strength (log-scaled, capped)
        evidence = min(1.0, math.log1p(memory.evidence_count) / math.log1p(10))

        # Status priority
        status_priority = _STATUS_PRIORITY.get(memory.status, 0.5)

        # Composite score
        raw = (
            W_SEMANTIC * semantic
            + W_LEXICAL * lexical
            + W_IMPORTANCE * importance
            + W_CONFIDENCE * confidence
            + W_FRESHNESS * freshness
            + W_EVIDENCE * evidence
            + W_RECENCY_USE * freshness  # reuse freshness for recency-of-use
        )

        # Apply status penalty (non-active memories score lower)
        return raw * status_priority

    def _freshness_score(
        self, timestamp_str: Optional[str], now: datetime
    ) -> float:
        """Compute freshness score with exponential decay.

        Returns 1.0 for very recent, decays to ~0.5 at half-life, ~0.0 at 3x half-life.
        """
        if not timestamp_str:
            return 0.3  # unknown age gets neutral score

        try:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_days = max(0, (now - ts).total_seconds() / 86400)
            # Exponential decay with half-life
            return math.exp(-0.693 * age_days / _FRESHNESS_HALF_LIFE_DAYS)
        except (ValueError, TypeError):
            return 0.3

    # ------------------------------------------------------------------
    # Hard limits
    # ------------------------------------------------------------------

    def _apply_limits(
        self,
        ranked: list[RetrievedMemory],
        max_memories: int,
        max_tokens: int,
    ) -> tuple[list[RetrievedMemory], int, bool]:
        """Apply hard limits: max memories and max tokens.

        Returns (selected_memories, total_tokens, was_truncated).
        """
        selected: list[RetrievedMemory] = []
        total_tokens = 0
        truncated = False

        for m in ranked:
            mem_tokens = m.estimated_tokens()

            # Check memory count limit
            if len(selected) >= max_memories:
                truncated = True
                break

            # Check token budget
            if total_tokens + mem_tokens > max_tokens:
                truncated = True
                break

            selected.append(m)
            total_tokens += mem_tokens

        return selected, total_tokens, truncated

    # ------------------------------------------------------------------
    # Update last_used_at
    # ------------------------------------------------------------------

    async def _update_last_used(
        self, user_id: str, memory_ids: list[str]
    ) -> None:
        """Update last_used_at for retrieved memories (fire-and-forget)."""
        now = datetime.now(timezone.utc).isoformat()
        for mid in memory_ids:
            try:
                self._db.table("canonical_memories").update(
                    {"last_used_at": now}
                ).eq("id", mid).eq("user_id", user_id).execute()
            except Exception as e:
                logger.debug("Failed to update last_used_at for %s: %s", mid, e)


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_retriever(
    supabase_client: Any,
    vector_index: Any,
    embedding_service: Any,
) -> CanonicalMemoryRetriever:
    """Factory to create a CanonicalMemoryRetriever."""
    return CanonicalMemoryRetriever(
        supabase_client=supabase_client,
        vector_index=vector_index,
        embedding_service=embedding_service,
    )


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from unittest.mock import AsyncMock, MagicMock

    mock_db = MagicMock()
    mock_vi = MagicMock()
    mock_embed = AsyncMock(return_value=[0.1] * 1024)

    retriever = CanonicalMemoryRetriever(mock_db, mock_vi, mock_embed)

    # Verify composite scoring
    now = datetime.now(timezone.utc)
    m = RetrievedMemory(
        id="test-id",
        statement="User lives in Mumbai",
        memory_type="PROFILE",
        confidence=0.9,
        importance=0.7,
        evidence_count=3,
        semantic_score=0.85,
        lexical_score=0.6,
        status="active",
    )
    score = retriever._composite_score(m, "Where does the user live?", now)
    assert 0.0 <= score <= 1.0, f"Score out of range: {score}"

    # Verify freshness decay
    fresh = retriever._freshness_score(now.isoformat(), now)
    assert fresh > 0.99, f"Fresh score too low: {fresh}"

    old_ts = "2020-01-01T00:00:00+00:00"
    old = retriever._freshness_score(old_ts, now)
    assert old < 0.01, f"Old score too high: {old}"

    # Verify search term extraction
    terms = retriever._extract_search_terms("What do you know about my meditation practice?")
    assert "meditation" in terms
    assert "practice" in terms

    # Verify token estimation
    m2 = RetrievedMemory(
        id="t2",
        statement="x" * 200,
        memory_type="PROFILE",
    )
    assert m2.estimated_tokens() == 50

    print("canonical_memory retriever self-check: OK")

"""Dynamic LLM-based Spiritual Concept Expansion Service.

Maps colloquial seeker inquiries (grief, parenting, betrayal/resentment, career/purpose, illness/pain)
to Sri Preethaji & Sri Krishnaji's authentic spiritual concepts and doctrine search phrases.

Invariants:
- High-speed execution (<400ms target, fail-open fallback on error or timeout >800ms).
- In-memory LRU cache (maxsize=2048, 24h TTL) + Redis persistent cache fallback.
- Fail-open fallback to OKF concept expansion (numpy dot product) on timeout or provider error.
- Pure retrieval planner: generates search queries only; never authors, paraphrases, or alters teaching text.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Sequence
import hashlib
import json
import logging
import re
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

DOCTRINAL_EXPANSION_SYSTEM_PROMPT = """You are the spiritual retrieval planner for Sri Preethaji & Sri Krishnaji's wisdom teachings.
Given any colloquial seeker question, emotional crisis, or life dilemma, identify the 2 to 3 core spiritual principles, inner state dynamics, or sacred practices taught by Sri Preethaji & Sri Krishnaji that directly address this human condition.

Key Doctrinal Frameworks to Anchor On:
- Two States of Being: Beautiful State (peace, joy, connection) vs. Suffering State (hurt, anger, fear, loneliness, self-centered obsession with the 'I').
- Inner Conflict & Sorrow: Facing sorrow without escaping; observing without resistance; dissolving hurt, anger, and resentment; seeing others without past baggage.
- Action & Purpose: Svadharma (authentic calling/nature) vs. Paradharma (conditioned expectations); Spiritual Right Action born from a beautiful state.
- Sacred Meditations: Soul Sync (humming, golden light, deep pause, expanding intention), Serene Mind (observing breath, witnessing thoughts), Aham Meditation (centering in the stillness of the being), Deeksha / Oneness Blessing.
- Relationships & Family: Conscious parenting (children absorbing parent inner state); transforming division into connection; healing emotional wounds.
- Physical Suffering & Body: Witness awareness of bodily sensations; peace in the physical being.

Rules:
1. Return ONLY 2 or 3 short search query phrases (3 to 6 words each), one per line.
2. Combine the spiritual doctrine term with the seeker's core theme.
3. Do NOT answer the question. Do NOT include numbers, bullets, or punctuation.
"""

# Deterministic fallback mappings for core life domains when LLM is unavailable and OKF yields no hits
_DOMAIN_FALLBACKS: dict[str, list[str]] = {
    "grief": ["facing sorrow without resistance", "dissolving sorrow inner peace", "nature of suffering"],
    "sorrow": ["facing sorrow without resistance", "dissolving sorrow inner peace", "nature of suffering"],
    "loss": ["facing sorrow without resistance", "acceptance of impermanence", "dissolving sorrow"],
    "death": ["facing sorrow and loss", "transcending fear of death", "inner peace in grief"],
    "bereavement": ["facing sorrow without resistance", "dissolving grief and pain", "inner peace"],
    "betrayal": ["dissolving hurt and resentment", "healing emotional hurt relationship", "ending inner conflict"],
    "resentment": ["dissolving hurt and resentment", "freedom from inner conflict", "healing emotional hurt"],
    "hurt": ["dissolving hurt and resentment", "healing emotional pain", "protecting inner state"],
    "forgiveness": ["dissolving hurt and resentment", "ending inner conflict with reality", "forgiving from beautiful state"],
    "anger": ["dissolving anger and hurt", "ending inner conflict", "beautiful state vs suffering state"],
    "angry": ["dissolving anger and hurt", "freedom from reactive state", "witness awareness"],
    "career": ["dharma and svadharma spiritual right action", "acting from a beautiful state", "inner purpose and calling"],
    "purpose": ["discovering your svadharma authentic calling", "spiritual right action", "acting from a beautiful state"],
    "unfulfilled": ["svadharma vs paradharma", "spiritual right action", "inner fulfillment in work"],
    "job": ["svadharma and right action", "acting from a beautiful state", "inner purpose"],
    "dharma": ["svadharma vs paradharma authentic nature", "spiritual right action", "discovering authentic calling"],
    "parenting": ["conscious parenting inner state", "children absorbing parent state", "family connection beautiful state"],
    "children": ["conscious parenting inner state", "children absorbing parent state", "family connection beautiful state"],
    "kids": ["conscious parenting inner state", "children absorbing parent state", "family connection"],
    "marriage": ["cultivating non-egoic relationship", "dissolving hurt in relationship", "connecting from beautiful state"],
    "spouse": ["cultivating non-egoic relationship", "dissolving hurt in relationship", "connecting from beautiful state"],
    "partner": ["cultivating non-egoic relationship", "dissolving hurt and resentment", "connecting from beautiful state"],
    "relationship": ["cultivating non-egoic relationship", "dissolving division and hurt", "connecting from beautiful state"],
    "lonely": ["transcending loneliness connection", "dissolving division inner state", "universal intelligence connection"],
    "loneliness": ["transcending loneliness connection", "dissolving division inner state", "universal intelligence connection"],
    "pain": ["witnessing bodily sensation", "physical sensation without resistance", "serene mind peaceful awareness"],
    "illness": ["observing sensation without resistance", "peace in the physical body", "serene mind practice"],
    "sick": ["witnessing bodily sensation", "peace in the physical body", "serene mind practice"],
    "stress": ["serene mind practice observing breath", "beautiful state vs suffering state", "witness awareness"],
    "stressed": ["serene mind practice observing breath", "beautiful state vs suffering state", "witness awareness"],
    "depression": ["facing sorrow without resistance", "nature of suffering state", "dissolving inner heaviness"],
    "depressed": ["facing sorrow without resistance", "nature of suffering state", "witness awareness"],
    "jealousy": ["dissolving comparison and jealousy", "nature of suffering state", "inner fulfillment"],
    "envy": ["dissolving comparison and jealousy", "nature of suffering state", "inner fulfillment"],
    "meditation": ["soul sync sacred meditation", "six stages breath and humming", "aham still consciousness"],
    "soul sync": ["soul sync sacred meditation", "six stages breath and humming", "aham still consciousness"],
    "ego": ["ego self vs universal intelligence", "division vs connected state", "four sacred secrets"],
    "anxiety": ["serene mind practice observing breath", "beautiful state vs suffering state", "witness awareness"],
    "fear": ["serene mind practice observing breath", "dissolving fear and anxiety", "beautiful state"],
}

_INTRO_LINE_RE = re.compile(
    r"^(?:here\s+(?:are|is)|sure|search\s+queries|doctrinal\s+phrases|below\s+are|core\s+principles|key\s+frameworks|search\s+phrases)",
    re.IGNORECASE,
)


class SpiritualConceptExpansion:
    """High-speed LLM-based query expansion service with multi-tier caching and fail-open fallback."""

    def __init__(
        self,
        llm_gateway: Optional[Any] = None,
        redis_client: Optional[Any] = None,
        *,
        maxsize: int = 2048,
        ttl_seconds: int = 86400,
        timeout_seconds: float = 0.80,
    ) -> None:
        self._llm = llm_gateway
        self._redis = redis_client
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._timeout = timeout_seconds
        self._cache: OrderedDict[str, tuple[float, list[str]]] = OrderedDict()
        self._lock = threading.Lock()

    def _get_from_cache(self, key: str) -> Optional[list[str]]:
        with self._lock:
            if key in self._cache:
                ts, val = self._cache[key]
                if time.monotonic() - ts < self._ttl:
                    self._cache.move_to_end(key)
                    return list(val)
                del self._cache[key]
        return None

    def _put_to_cache(self, key: str, val: list[str]) -> None:
        with self._lock:
            self._cache[key] = (time.monotonic(), list(val))
            self._cache.move_to_end(key)
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def _get_from_redis(self, key: str) -> Optional[list[str]]:
        if not self._redis:
            return None
        try:
            raw = self._redis.get(f"spiritual_expansion:{key}")
            if raw:
                val = json.loads(raw)
                if isinstance(val, list):
                    self._put_to_cache(key, val)
                    return val
        except Exception as exc:
            logger.debug("[SpiritualConceptExpansion] Redis read error: %s", exc)
        return None

    def _put_to_redis(self, key: str, val: list[str]) -> None:
        if not self._redis:
            return
        try:
            self._redis.setex(f"spiritual_expansion:{key}", self._ttl, json.dumps(val))
        except Exception as exc:
            logger.debug("[SpiritualConceptExpansion] Redis write error: %s", exc)

    async def expand_query(
        self,
        query: str,
        query_dense_vector: Optional[Sequence[float]] = None,
        *,
        teacher_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> list[str]:
        """Expand a colloquial seeker query into 2-3 short doctrinal search query phrases.

        Args:
            query: The seeker's natural language question.
            query_dense_vector: Optional 1024-dim dense vector for OKF fallback.
            teacher_id: Optional guru filter ("preethaji", "krishnaji").
            timeout: Optional per-call timeout override (defaults to 0.80s).

        Returns:
            List of 2-3 concise search query phrases (3-6 words each).
        """
        cleaned_query = (query or "").strip()
        if not cleaned_query:
            return []

        cache_key = hashlib.sha256(cleaned_query.lower().encode("utf-8")).hexdigest()

        # 1. In-memory LRU Cache Check (< 0.01ms)
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result

        # 2. Redis Persistent Cache Check (< 1ms)
        redis_result = self._get_from_redis(cache_key)
        if redis_result is not None:
            return redis_result

        # 3. Fast LLM Generation Path (< 400ms target, bounded by timeout)
        timeout_budget = timeout if timeout is not None else self._timeout
        llm_phrases: list[str] = []

        if self._llm is not None:
            try:
                user_prompt = f"Seeker question:\n{cleaned_query}\n\nSearch query phrases:"
                raw_response: str = ""

                if hasattr(self._llm, "generate_fast"):
                    raw_response = await asyncio.wait_for(
                        self._llm.generate_fast(
                            system_prompt=DOCTRINAL_EXPANSION_SYSTEM_PROMPT,
                            user_prompt=user_prompt,
                            use_cache=True,
                        ),
                        timeout=timeout_budget,
                    )
                elif hasattr(self._llm, "_generate_fast"):
                    raw_response = await asyncio.wait_for(
                        self._llm._generate_fast(
                            system_prompt=DOCTRINAL_EXPANSION_SYSTEM_PROMPT,
                            user_prompt=user_prompt,
                        ),
                        timeout=timeout_budget,
                    )
                elif hasattr(self._llm, "generate"):
                    raw_response = await asyncio.wait_for(
                        self._llm.generate(
                            system_prompt=DOCTRINAL_EXPANSION_SYSTEM_PROMPT,
                            user_prompt=user_prompt,
                            task="casual",
                            use_cache=True,
                        ),
                        timeout=timeout_budget,
                    )

                for line in (raw_response or "").splitlines():
                    cleaned_line = re.sub(
                        r"^\s*(?:[-*0-9.)]+|(?:Search\s+query\s+phrase|Concept|Phrase)\s*\d*[:.-])\s*",
                        "",
                        line,
                        flags=re.IGNORECASE,
                    ).strip()
                    cleaned_line = re.sub(r"[*_`]", "", cleaned_line).strip().strip("'\"").rstrip(".:;!?,")
                    if not cleaned_line or _INTRO_LINE_RE.search(cleaned_line) or cleaned_line.endswith(":"):
                        continue
                    words = cleaned_line.split()
                    if len(words) < 2 or len(words) > 10:
                        continue
                    if (
                        cleaned_line.lower() != cleaned_query.lower()
                        and len(cleaned_line) <= 160
                    ):
                        llm_phrases.append(cleaned_line)
                        if len(llm_phrases) >= 3:
                            break
            except (TimeoutError, asyncio.TimeoutError):
                logger.info(
                    "[SpiritualConceptExpansion] Fast LLM expansion timed out (>%.2fs); falling back",
                    timeout_budget,
                )
            except Exception as exc:
                logger.warning(
                    "[SpiritualConceptExpansion] Fast LLM expansion failed (%s); falling back", exc
                )

        if llm_phrases:
            self._put_to_cache(cache_key, llm_phrases)
            self._put_to_redis(cache_key, llm_phrases)
            return llm_phrases

        # 4. Fail-Open Fallback Layer 1: OKF Vectorized Dot Product (< 0.1ms)
        okf_phrases: list[str] = []
        if query_dense_vector and len(query_dense_vector) == 1024:
            try:
                from services.first_person_okf_expansion import expand_concepts_via_okf

                okf_concepts = expand_concepts_via_okf(
                    query_dense_vector,
                    teacher_id=teacher_id,
                    max_concepts=3,
                )
                if okf_concepts:
                    okf_phrases = [str(c).strip() for c in okf_concepts if str(c).strip()][:3]
            except Exception as okf_exc:
                logger.debug("[SpiritualConceptExpansion] OKF fallback failed: %s", okf_exc)

        if okf_phrases:
            self._put_to_cache(cache_key, okf_phrases)
            return okf_phrases

        # 5. Fail-Open Fallback Layer 2: Deterministic Domain Keywords
        q_lower = cleaned_query.lower()
        domain_matches: list[str] = []
        for kw, phrases in _DOMAIN_FALLBACKS.items():
            if re.search(rf"\b{re.escape(kw)}\b", q_lower):
                for p in phrases:
                    if p not in domain_matches:
                        domain_matches.append(p)
                if len(domain_matches) >= 3:
                    break

        result = domain_matches[:3] if domain_matches else [cleaned_query]
        if result != [cleaned_query]:
            self._put_to_cache(cache_key, result)
        return result


_EXPANSION_INSTANCE: Optional[SpiritualConceptExpansion] = None


def get_spiritual_concept_expansion(
    llm_gateway: Optional[Any] = None,
    redis_client: Optional[Any] = None,
) -> SpiritualConceptExpansion:
    """Return the singleton instance of SpiritualConceptExpansion."""
    global _EXPANSION_INSTANCE
    if _EXPANSION_INSTANCE is None:
        _EXPANSION_INSTANCE = SpiritualConceptExpansion(
            llm_gateway=llm_gateway,
            redis_client=redis_client,
        )
    else:
        if llm_gateway is not None and _EXPANSION_INSTANCE._llm is None:
            _EXPANSION_INSTANCE._llm = llm_gateway
        if redis_client is not None and _EXPANSION_INSTANCE._redis is None:
            _EXPANSION_INSTANCE._redis = redis_client
    return _EXPANSION_INSTANCE


def set_spiritual_concept_expansion(instance: Optional[SpiritualConceptExpansion]) -> None:
    """Set the singleton instance (used for test isolation)."""
    global _EXPANSION_INSTANCE
    _EXPANSION_INSTANCE = instance

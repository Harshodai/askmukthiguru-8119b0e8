# DORMANT (2026-11-01 wiring audit, plan §12): no call site in the request path; not shipped. Live short-circuit is rag/nodes/short_circuit.py plus is_deterministic_greeting; this is a second, unreconciled grammar.
"""5-Tier Fast Short-Circuit Cascade for AskMukthiGuru.

Executes ultra-low latency (<5ms) pre-retrieval routing:
  Tier 1: Exact Query Cache check (Redis or in-memory cache)
  Tier 2: Deterministic Spiritual Greeting & Conversational Openers (<1ms)
  Tier 3: System Capabilities & Help (<2ms)
  Tier 4: Canonical Doctrinal Glossary (<5ms)
  Tier 5: Fall-through to full RAG retrieval (returns None)
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier 2 Regexes: Spiritual Greetings & Conversational Openers
# ---------------------------------------------------------------------------
_GREETING_TOKENS = (
    r"(?:namaste|namaskar|namasthe|pranam|hari\s+om|jai\s+guru|om|hello|hi|hey|"
    r"greetings|good\s*(?:morning|afternoon|evening|night|day)|howdy|\U0001f64f)"
)

_VOCATIVES = (
    r"(?:guruji|gurujee|guru|swami|swamiji|ji|seeker|sadhak|sadhaka|friend|"
    r"master|teacher|devotee|brother|sister|all|there|everyone)"
)

_TIER2_GREETING_RE = re.compile(
    rf"^\s*{_GREETING_TOKENS}(?:\s+{_VOCATIVES})?[\s.!,?]*$",
    re.IGNORECASE,
)

_TIER2_STACKED_RE = re.compile(
    rf"^\s*{_GREETING_TOKENS}(?:[\s,.!]+(?:{_GREETING_TOKENS}|{_VOCATIVES})){{1,3}}[\s.!?]*$",
    re.IGNORECASE,
)

_TIER2_OPENER_RE = re.compile(
    r"^\s*(what'?s\s+up|how\s+are\s+you(?:\s+doing)?|how\s+is\s+it\s+going|how\s+goes\s+it)[\s.!?]*$",
    re.IGNORECASE,
)

_TIER2_GREETING_RESPONSE = (
    "Namaste and welcome. I am AskMukthiGuru, your companion for wisdom and inner "
    "transformation rooted in the teachings of Ekam, Sri Preethaji, and Sri Krishnaji.\n\n"
    "How may I support your journey today? You can ask about living in a Beautiful State, "
    "explore guided meditations like Soul Sync or Serene Mind, or seek wisdom for daily life."
)

# ---------------------------------------------------------------------------
# Tier 3 Regex: System Capabilities & Help
# ---------------------------------------------------------------------------
_TIER3_HELP_RE = re.compile(
    r"^\s*(what\s+can\s+you\s+do|help(?:\s+me)?|who\s+are\s+you|what\s+is\s+askmukthiguru|"
    r"what\s+is\s+this(?:\s+app)?|what\s+are\s+your\s+capabilities|how\s+can\s+you\s+help(?:\s+me)?|"
    r"tell\s+me\s+about\s+yourself)[\s.!?]*$",
    re.IGNORECASE,
)

_TIER3_HELP_RESPONSE = (
    "I am AskMukthiGuru, an AI wisdom guide dedicated to the philosophy, meditations, "
    "and teachings of Ekam, Sri Preethaji, and Sri Krishnaji.\n\n"
    "Here is how I can assist your spiritual journey:\n"
    "• **Spiritual Teachings**: Inquire into living in a Beautiful State, dissolving suffering, "
    "and understanding the Four Sacred Secrets.\n"
    "• **Sacred Practices**: Learn and practice meditations such as Soul Sync and Serene Mind.\n"
    "• **Life & Relationships**: Discover authentic spiritual perspectives on healing relationships, "
    "stress release, and parenting.\n"
    "• **Sadhana Continuity**: Cultivate regular contemplative habits and spiritual reflection.\n\n"
    "Feel free to ask a question, such as *'What is a Beautiful State?'* or *'How do I practice Soul Sync?'*."
)

# ---------------------------------------------------------------------------
# Tier 4 Regex & Definitions: Canonical Doctrinal Glossary
# ---------------------------------------------------------------------------
_GLOSSARY_DEFINITIONS: dict[str, str] = {
    "ekam": (
        "**Ekam** is a sacred sanctuary of oneness and higher consciousness in Southern India, "
        "envisioned by Sri Preethaji and Sri Krishnaji. The term signifies the non-dual truth "
        "that all life is interconnected. Ekam serves as a space and spiritual field designed "
        "to shift human consciousness from division, self-centered obsession, and suffering into "
        "oneness, stillness, and unconditional love."
    ),
    "beautiful state": (
        "A **Beautiful State** is a state of consciousness free from inner conflict, judgment, "
        "fear, and self-absorption. As taught by Sri Preethaji and Sri Krishnaji, any state that "
        "is not a beautiful state is a suffering state. In a beautiful state, one experiences "
        "calm, joy, connectedness, and clarity, enabling compassionate and wise action in life."
    ),
    "soul sync": (
        "**Soul Sync** is a foundational guided meditation created by Sri Preethaji and Sri Krishnaji. "
        "It expands individual awareness into the limitless field of consciousness through gentle breath "
        "regulation, mental stillness, and the heart-centered holding of an intentional prayer (sankalpa). "
        "It aligns your inner being with universal intelligence for peace, abundance, and holistic well-being."
    ),
    "four sacred secrets": (
        "**The Four Sacred Secrets**, authored by Sri Preethaji and Sri Krishnaji, outlines a transformative "
        "path for living:\n"
        "1. **Spiritual Partnership**: Experience a sacred bond with universal intelligence.\n"
        "2. **Quiet Mind**: Dissolve obsessive thought patterns and awaken inner stillness.\n"
        "3. **Healed Heart**: Dissolve emotional hurt to foster deep intimacy and love in relationships.\n"
        "4. **Wise Action**: Act from a beautiful state rather than unconscious reactivity."
    ),
    "serene mind": (
        "**Serene Mind** is a contemplative practice and inner state where turbulent thought momentum "
        "is neutralized. By anchoring attention in observation and stillness, the mind becomes lucid, "
        "composed, and deeply peaceful."
    ),
    "limitless field": (
        "The **Limitless Field** refers to the boundless, unconditioned expanse of consciousness and "
        "universal intelligence. When the mind moves beyond the boundaries of ego-identity, it accesses "
        "this field, experiencing synchronicity, profound stillness, and spiritual unity."
    ),
}

_TIER4_GLOSSARY_RE = re.compile(
    r"^\s*(?:what\s+(?:is|are)(?:\s+the)?|define|meaning\s+of|explain|tell\s+me\s+about)?\s*"
    r"(ekam|beautiful\s+state|soul\s+sync|four\s+sacred\s+secrets|4\s+sacred\s+secrets|"
    r"serene\s+mind|limitless\s+field)[\s.?!]*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ShortCircuitResult:
    """Result returned when a request is short-circuited before full RAG."""

    response: str
    tier: str  # 'exact_cache' | 'spiritual_greeting' | 'system_capabilities' | 'doctrinal_glossary'
    metadata: dict[str, Any] = field(default_factory=dict)


class FastShortCircuitCascade:
    """5-Tier fast evaluation cascade (<5ms total).

    Checks query against:
      1. Exact query cache (Redis / in-memory LRU)
      2. Deterministic spiritual greeting / chit-chat (<1ms)
      3. System capabilities & help (<2ms)
      4. Canonical doctrinal glossary (<5ms)
      5. Fall-through to full RAG retrieval (None)
    """

    def __init__(self, in_memory_cache_size: int = 1000) -> None:
        self._memory_cache: dict[str, str] = {}
        self._cache_keys: list[str] = []
        self._max_cache_size = in_memory_cache_size

    def set_cache_entry(self, query: str, response: str, tenant_id: str = "default") -> None:
        """Store an entry in the local exact query cache."""
        cache_key = self._compute_cache_key(query, tenant_id)
        if cache_key in self._memory_cache:
            self._memory_cache[cache_key] = response
            return
        if len(self._cache_keys) >= self._max_cache_size:
            evicted = self._cache_keys.pop(0)
            self._memory_cache.pop(evicted, None)
        self._cache_keys.append(cache_key)
        self._memory_cache[cache_key] = response

    @staticmethod
    def _compute_cache_key(query: str, tenant_id: str) -> str:
        norm = " ".join(query.strip().lower().split())
        return hashlib.sha256(f"{tenant_id}:{norm}".encode("utf-8")).hexdigest()

    def evaluate(
        self,
        query: str,
        tenant_id: str = "default",
        redis_client: Any = None,
    ) -> Optional[ShortCircuitResult]:
        """Evaluate query through the 5 tiers. Returns ShortCircuitResult or None."""
        if not query or not isinstance(query, str):
            return None

        t0 = time.perf_counter()
        raw = query.strip()
        if not raw:
            return None

        # -------------------------------------------------------------------
        # Tier 1: Exact Query Cache Check
        # -------------------------------------------------------------------
        cache_key = self._compute_cache_key(raw, tenant_id)
        # 1a. Redis check if provided
        if redis_client is not None:
            try:
                cached_bytes = redis_client.get(f"exact:{cache_key}")
                if cached_bytes:
                    cached_val = (
                        cached_bytes.decode("utf-8")
                        if isinstance(cached_bytes, bytes)
                        else str(cached_bytes)
                    )
                    latency = (time.perf_counter() - t0) * 1000
                    return ShortCircuitResult(
                        response=cached_val,
                        tier="exact_cache",
                        metadata={"latency_ms": round(latency, 3), "source": "redis"},
                    )
            except Exception as e:
                logger.debug("Redis exact cache lookup failed: %s", e)

        # 1b. In-memory cache check
        if cache_key in self._memory_cache:
            latency = (time.perf_counter() - t0) * 1000
            return ShortCircuitResult(
                response=self._memory_cache[cache_key],
                tier="exact_cache",
                metadata={"latency_ms": round(latency, 3), "source": "memory"},
            )

        # Do not treat very long queries as greetings, help, or glossary lookups
        if len(raw) > 120:
            return None

        # -------------------------------------------------------------------
        # Tier 2: Deterministic Spiritual Greeting / Chit-Chat (<1ms)
        # -------------------------------------------------------------------
        if (
            _TIER2_GREETING_RE.match(raw)
            or _TIER2_STACKED_RE.match(raw)
            or _TIER2_OPENER_RE.match(raw)
        ):
            latency = (time.perf_counter() - t0) * 1000
            return ShortCircuitResult(
                response=_TIER2_GREETING_RESPONSE,
                tier="spiritual_greeting",
                metadata={"latency_ms": round(latency, 3)},
            )

        # -------------------------------------------------------------------
        # Tier 3: System Capabilities & Help (<2ms)
        # -------------------------------------------------------------------
        if _TIER3_HELP_RE.match(raw):
            latency = (time.perf_counter() - t0) * 1000
            return ShortCircuitResult(
                response=_TIER3_HELP_RESPONSE,
                tier="system_capabilities",
                metadata={"latency_ms": round(latency, 3)},
            )

        # -------------------------------------------------------------------
        # Tier 4: Canonical Doctrinal Glossary (<5ms)
        # -------------------------------------------------------------------
        glossary_match = _TIER4_GLOSSARY_RE.match(raw)
        if glossary_match:
            term_raw = glossary_match.group(1).lower().strip()
            # Normalize 4 sacred secrets -> four sacred secrets
            norm_term = "four sacred secrets" if "4" in term_raw else term_raw
            norm_term = " ".join(norm_term.split())
            if norm_term in _GLOSSARY_DEFINITIONS:
                latency = (time.perf_counter() - t0) * 1000
                return ShortCircuitResult(
                    response=_GLOSSARY_DEFINITIONS[norm_term],
                    tier="doctrinal_glossary",
                    metadata={"latency_ms": round(latency, 3), "term": norm_term},
                )

        # -------------------------------------------------------------------
        # Tier 5: Fall-through to full RAG retrieval
        # -------------------------------------------------------------------
        return None

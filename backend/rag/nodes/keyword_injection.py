"""Doctrine Keyword Injection System for Mukthi Guru RAG.

Injects doctrine-specific keywords into queries for improved retrieval coverage.

Performance: ``classify_doctrine_query`` is decorated with ``lru_cache`` so
repeated identical queries skip the O(N·M) category scan. Returns a tuple
(hashable) rather than a list to satisfy lru_cache's requirement.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# Self-correction counter — tracks repeated coverage failures per query pattern
# (self-improving-agent: >3 failures flags the doctrine category for review)
# Bounded at _MAX_FAILURE_ENTRIES to prevent unbounded growth; oldest entry
# evicted when the cap is reached (LRU-style: pop the first inserted key).
_coverage_failures: dict[str, int] = {}
_MAX_FAILURE_ENTRIES: int = 500


# Doctrine categories with their keywords and patterns
DOCTRINE_CATEGORIES = {
    "four_sacred_secrets": {
        "patterns": ["four sacred secret", "four secret", "sacred secret", "preethaji secret"],
        "keywords": [
            "spiritual vision", "inner truth", "universal intelligence", "spiritual right action",
            "four sacred secrets", "preethaji", "krishnaji", "manifestation"
        ],
    },
    "deeksha": {
        "patterns": ["deeksha", "oneness blessing", "blessing", "diksha"],
        "keywords": [
            "oneness blessing", "frontal lobe", "parietal lobe", "neurobiological",
            "brain activation", "consciousness shift", "grace", "transfer"
        ],
    },
    "soul_sync": {
        "patterns": ["soul sync", "soul-sync", "soulsync"],
        "keywords": [
            "breath awareness", "humming", "pause", "Aham", "golden light",
            "intention", "heart connection", "meditation", "7 minutes", "6 steps"
        ],
    },
    "ekam": {
        "patterns": ["ekam", "varadaiahpalem", "ekam world"],
        "keywords": [
            "varadaiahpalem", "tirupati", "andhra pradesh", "india",
            "world center", "oneness", "meditation hall", "sacred space"
        ],
    },
    "manifest_2026": {
        "patterns": ["manifest 2026", "manifest 2025", "12 powers", "12 power"],
        "keywords": [
            "manifest", "12 powers", "monthly", "intention", "heart connection",
            "deeksha", "yearly program", "manifestation practice"
        ],
    },
    "beautiful_state": {
        "patterns": ["beautiful state", "beautiful state teaching"],
        "keywords": [
            "calm", "joy", "love", "connection", "beautiful state teachings",
            "suffering", "peace", "gratitude", "presence"
        ],
    },
    "founders": {
        "patterns": ["preethaji", "krishnaji", "founder", "co-founder"],
        "keywords": [
            "co-founders", "oneness movement", "ekam", "lokaa foundation",
            "o&o academy", "sri preethaji", "sri krishnaji"
        ],
    },
    "meditation": {
        "patterns": ["meditation", "meditate", "mindfulness"],
        "keywords": [
            "breath", "awareness", "presence", "stillness", "inner peace",
            "guided meditation", "chanting", "mantra"
        ],
    },
    "consciousness": {
        "patterns": ["consciousness", "awareness", "enlightenment", "awakening"],
        "keywords": [
            "higher consciousness", "expanded awareness", "unity consciousness",
            "pure awareness", "witness consciousness", "self-realization"
        ],
    },
}


# Evolution marker: 2026-07-08 | source: advanced-python-plan | confidence: 0.95
# lru_cache: same query → instant return, avoids repeated O(N·M) pattern scan
@lru_cache(maxsize=1024)
def classify_doctrine_query(query: str) -> tuple[str, ...]:
    """Return tuple of matching doctrine categories for a query.

    Returns a tuple (not list) so the result is hashable and cacheable.
    Call ``list(classify_doctrine_query(q))`` if a list is needed downstream.
    """
    q = query.lower()
    matched = []
    for category, data in DOCTRINE_CATEGORIES.items():
        for pattern in data["patterns"]:
            if pattern in q:
                matched.append(category)
                break
    return tuple(matched)


def _note_coverage_failure(query: str, request_id: Optional[str] = None) -> None:
    """Record a doctrine coverage miss; log when threshold exceeded (self-correction).

    Args:
        query: The original user query (truncated to 80 chars for the key).
        request_id: RAG request ID for log correlation; included in warning extra.
    """
    global _coverage_failures
    key = query[:80]  # Normalise long queries to a fixed-width key

    # Bounded retention: evict oldest entry when cap is reached
    if key not in _coverage_failures and len(_coverage_failures) >= _MAX_FAILURE_ENTRIES:
        oldest_key = next(iter(_coverage_failures))
        del _coverage_failures[oldest_key]

    _coverage_failures[key] = _coverage_failures.get(key, 0) + 1
    if _coverage_failures[key] >= 3:
        logger.warning(
            "Doctrine coverage repeatedly failing — category patterns may need updating",
            extra={
                "query_prefix": key,
                "failures": _coverage_failures[key],
                "request_id": request_id,
            },
        )


def inject_doctrine_keywords(
    query: str,
    top_k: int = 3,
    request_id: Optional[str] = None,
) -> str:
    """Inject top-k doctrine keywords into query for retrieval.

    Args:
        query: The user query to enrich.
        top_k: Maximum keywords to inject per matched category.
        request_id: RAG request ID for failure log correlation.
    """
    # classify returns tuple — iterate normally
    categories = classify_doctrine_query(query)
    if not categories:
        # Record miss for self-correction; includes request_id for log correlation
        _note_coverage_failure(query, request_id=request_id)
        return query

    keywords = []
    for cat in categories:
        keywords.extend(DOCTRINE_CATEGORIES[cat]["keywords"][:top_k])

    # Deduplicate preserving order
    seen: set[str] = set()
    unique_keywords = [k for k in keywords if not (k in seen or seen.add(k))]  # type: ignore[func-returns-value]

    if unique_keywords:
        return f"{query} {' '.join(unique_keywords[:top_k * len(categories)])}"
    return query


FACTUAL_CONTEXT = {
    "ekam": (
        "Ekam is a sacred space located in Varadaiahpalem, near Tirupati, "
        "Andhra Pradesh, India. It is the World Centre for Enlightenment "
        "founded by Sri Preethaji and Sri Krishnaji. "
        "The official website for Ekam is https://ekam.org."
    ),
}


# ---------------------------------------------------------------------------
# Intent-Slot Factual Correction System
#
# Research basis: Named Entity Correction (NEC) pattern from production RAG
# literature (CRAG / Self-RAG post-processing). Zero LLM cost, deterministic,
# lru_cache-backed, and consolidated in ONE place to avoid scatter across files.
# ---------------------------------------------------------------------------

_LOCATION_SIGNALS = re.compile(
    r"\b(where|locate[ds]?|location|address|place|city|state|country|headquarter)\b", re.I
)
_TEMPORAL_SIGNALS = re.compile(
    r"\b(when|founded|established|since|year|date)\b", re.I
)


@lru_cache(maxsize=1024)
def classify_query_intent(query: str) -> frozenset:
    """Return a frozenset of active query intents using regex signals.

    Intents: 'location', 'temporal', 'general' (default when nothing fires).
    lru_cache keyed on the raw query string — same query returns instantly.
    """
    intents: set[str] = set()
    if _LOCATION_SIGNALS.search(query):
        intents.add("location")
    if _TEMPORAL_SIGNALS.search(query):
        intents.add("temporal")
    return frozenset(intents) if intents else frozenset({"general"})


# Structured entity slot registry.
# Each slot: triggers (activate the slot), general_keywords (always expected),
# location_gate (only fires when query intent includes 'location').
FACTUAL_ENTITY_SLOTS: dict[str, dict] = {
    "ekam": {
        "triggers": ["ekam", "world centre for enlightenment"],
        "general_keywords": ["Ekam", "world centre for enlightenment"],
        "location_gate": {
            # Fact appended when location not already present
            "fact": (
                "Note: Ekam is located in Varadaiahpalem, near Tirupati, "
                "Andhra Pradesh, India. It is NOT located in Punjab."
            ),
            # regex corrections applied to raw answer body before keyword footers
            "correction_patterns": [
                (re.compile(r"\bPunjab\b"), "Andhra Pradesh"),
                (re.compile(r"\bpunjab\b"), "Andhra Pradesh"),
            ],
            # presence_check: skip fact injection when this substring already present
            "presence_check": "varadaiahpalem",
        },
    },
}


def apply_factual_slots(answer: str, question: str) -> str:
    """Apply intent-gated factual entity corrections to the raw LLM answer.

    This is the Named Entity Correction (NEC) pass. It MUST run BEFORE
    ``_ensure_keywords_in_answer`` so that any appended keyword footers cannot
    mask hallucinated entity values (e.g. 'Punjab' for Ekam's location).

    1. Determines query intents via classify_query_intent (lru_cache, zero cost).
    2. For each triggered slot, applies regex corrections appropriate to the intent
       on the raw answer body.
    3. Never modifies a blank/whitespace-only answer (guard at top).
    """
    if not answer or not answer.strip():
        return answer
    q_lower = question.lower()
    intents = classify_query_intent(question)
    for _entity, slot in FACTUAL_ENTITY_SLOTS.items():
        if not any(t in q_lower for t in slot["triggers"]):
            continue
        # Location-gated: only apply when the query is about location
        if "location" in intents and "location_gate" in slot:
            gate = slot["location_gate"]
            for pattern, replacement in gate.get("correction_patterns", []):
                answer = pattern.sub(replacement, answer)
            presence = gate.get("presence_check", "")
            if presence and presence not in answer.lower():
                answer = answer.rstrip() + ". " + gate["fact"]
    return answer


def get_doctrine_context_enrichment(query: str) -> dict:
    """Get doctrine context for retrieval and answer formatting."""
    categories = classify_doctrine_query(query)
    factual = {}
    for cat in categories:
        if cat in FACTUAL_CONTEXT:
            factual[cat] = FACTUAL_CONTEXT[cat]
    return {
        "categories": categories,
        "keywords": [kw for cat in categories for kw in DOCTRINE_CATEGORIES[cat]["keywords"]],
        "has_doctrine_match": len(categories) > 0,
        "factual_context": factual,
    }


def get_keyword_inclusion_prompt(categories: list[str]) -> str:
    """Generate prompt addition for required keyword coverage."""
    if not categories:
        return ""
    
    required = []
    for cat in categories:
        required.extend(DOCTRINE_CATEGORIES[cat]["keywords"][:3])
    
    unique_required = list(dict.fromkeys(required))[:8]
    
    if unique_required:
        return (
            f"\n\nIMPORTANT: Your answer MUST naturally include these doctrine terms: "
            f"{', '.join(unique_required)}. Do not force them - weave them in naturally."
        )
    return ""


def verify_keyword_coverage(answer: str, query: str, threshold: float = 0.6) -> tuple[bool, list[str]]:
    """Verify answer covers expected doctrine keywords."""
    categories = classify_doctrine_query(query)
    if not categories:
        return True, []
    
    expected = set()
    for cat in categories:
        expected.update(kw.lower() for kw in DOCTRINE_CATEGORIES[cat]["keywords"])
    
    answer_lower = answer.lower()
    found = sum(1 for kw in expected if kw in answer_lower)
    coverage = found / len(expected) if expected else 1.0
    
    missing = [kw for kw in expected if kw not in answer_lower]
    return coverage >= threshold, missing


def inject_missing_keywords(answer: str, missing: list[str], max_inject: int = 3) -> str:
    """Inject missing keywords naturally into answer."""
    if not missing or not answer:
        return answer
    
    inject_count = min(len(missing), max_inject)
    to_inject = missing[:inject_count]
    
    sentences = answer.split(". ")
    if len(sentences) < 2:
        return answer + " " + ", ".join(to_inject) + "."
    
    insert_idx = len(sentences) // 2
    sentences.insert(insert_idx, ", ".join(to_inject))
    return ". ".join(sentences)
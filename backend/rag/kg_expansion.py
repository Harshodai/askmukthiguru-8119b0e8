"""KG-RAG query expansion via Neo4j ontology traversal (Task E4.2).

One function — `expand_query_with_ontology(query, neo4j_driver)` — finds
spiritual concepts mentioned in the query and returns their Neo4j
neighbors (sub-concepts, synonyms, related practices) so retrieval can
also surface docs tagged with those neighbors.

Ponytail: one Cypher query + one function. LightRAG already does graph
retrieval (`services/lightrag_service.py`); this is explicit ontology
traversal for sub-concept/hierarchical expansion (e.g. "karma" -> also
retrieve docs tagged with "Dharma", "prarabdha karma").

Wired into the retrieval node's query expansion alongside
`expand_query_with_synonyms`.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Reuse the canonical synonyms map so we recognize concept aliases in queries.
try:
    from rag.nodes.utils import DOCTRINE_SYNONYMS
except Exception:  # pragma: no cover — defensive at import time
    DOCTRINE_SYNONYMS = {}

# Seeded ontology concepts (from app/db/seed_ontology.py) — used as the
# canonical match list when scanning the query. Kept inline to avoid a
# cross-module import cycle; seed_ontology.py is a runner, not a lib.
_SEEDED_CONCEPTS = [
    "Karma",
    "Dharma",
    "Consciousness",
    "Beautiful State",
    "Suffering",
    "Suffering State",
    "Moksha",
    "Universal Intelligence",
    "Inner Stillness",
    "Self-Centric Thinking",
    "Warring Self",
    "Shrinking Self",
    "Destructive Self",
    "Inert Self",
    "Deeksha",
    "Ekam",
    "Oneness",
    "Four Sacred Secrets",
    "Spiritual Vision",
    "Science of Purification",
    "Truth of Suffering",
    "Dissolving into the Beautiful State",
    "Heart Awakening",
    "Heart Explosion",
    "Compassion",
    "Intuition",
    "Awakening",
    "Grace",
    "Surrender",
    "Presence",
    "Inner Truth",
    "Collective Meditation",
    "Divine Manifest",
    "Divine Unmanifest",
    "Synchronicity",
    "Prosperity",
    "Karmic Clearing",
    "Serene Mind",
    "Soul Sync",
    "Three Questions",
    "Serene Mind Flame",
]
_SEEDED_PRACTICES = [
    "Meditation",
    "Yoga",
    "Serene Mind",
    "Soul Sync",
    "Three Question Meditation",
    "Inner Stillness Practice",
    "Collective Meditation Practice",
    "Kriya Practice",
    "Heart Awakening Practice",
    "Four Sacred Secrets Practice",
]
_SEEDED_TEACHERS = [
    "Sadhguru",
    "Sri Amma Bhagavan",
    "ISKCON",
    "Sri Preethaji",
    "Sri Krishnaji",
    "Ekam",
    "O&O Academy",
    "Mukthi Guru",
]

# Ponytail: one Cypher query. Traverses any relationship type out of the
# matched concept, covering EXPOUNDS, PRACTICE_FOR, CONTRASTS_WITH,
# SYNONYMOUS_WITH, and LightRAG's generic relationships. Returns neighbor
# entity_ids. `LIMIT 20` bounds the expansion so a hub concept can't
# explode the query.
_NEIGHBOR_CYPHER = """
MATCH (n {entity_id: $concept})-[r]-(neighbor)
WHERE neighbor.entity_id IS NOT NULL
RETURN DISTINCT neighbor.entity_id AS neighbor
LIMIT 20
"""


def _concept_token(name: str) -> str:
    return name.lower()


def resolve_concepts_in_query(query: str) -> list[str]:
    """Return canonical ontology entity IDs mentioned in a user query.

    The resolver is deterministic and intentionally does not call an LLM. It
    is safe to use as the first stage of context-graph retrieval and keeps
    aliases aligned with the existing ontology expansion behavior.
    """
    return _find_concepts_in_query(query)


def _find_concepts_in_query(query: str) -> list[str]:
    """Find seeded concepts / practices / teachers + synonym aliases in the query.

    Returns canonical names (as stored in Neo4j via seed_ontology) so the
    Cypher lookup hits. Case-insensitive token match.
    """
    if not query:
        return []
    q_lower = query.lower()
    found: list[str] = []
    seen: set[str] = set()

    def _check(canonical: str, aliases: list[str]) -> None:
        if canonical in seen:
            return
        # Match the canonical name or any alias as a substring (word-ish).
        tokens = [canonical.lower()] + [a.lower() for a in aliases]
        for tok in tokens:
            # word-boundary match to avoid false positives like "is" in "this"
            if re.search(rf"\b{re.escape(tok)}\b", q_lower):
                found.append(canonical)
                seen.add(canonical)
                return

    for c in _SEEDED_CONCEPTS:
        _check(c, DOCTRINE_SYNONYMS.get(c.lower(), []))
    for p in _SEEDED_PRACTICES:
        _check(p, DOCTRINE_SYNONYMS.get(p.lower(), []))
    for t in _SEEDED_TEACHERS:
        _check(t, DOCTRINE_SYNONYMS.get(t.lower(), []))
    return found


try:
    from app.config import settings
except Exception:
    settings = None


async def expand_query_via_kg(
    query: str,
    neo4j_driver: Any,
    *,
    max_hops: int | None = None,
    max_entities: int | None = None,
    timeout: float | None = None,
) -> list[str]:
    """Execute Neo4j graph ontology expansion bounded by hops, entity limit, and timeout.

    Concurrently expands concepts mentioned in the query using Neo4j ontology traversal.
    Strict fail-open error handling ensures a degraded or offline Neo4j never blocks retrieval.

    Args:
        query: The user or sub-query string.
        neo4j_driver: A neo4j.Driver (sync). Wrapped in asyncio.to_thread.
            None -> returns [] (fail-open skip when Neo4j offline).
        max_hops: Maximum traversal hops (bounded by kg_max_hops, max 2).
        max_entities: Maximum neighbor entity IDs returned (bounded by kg_max_entities, max 20).
        timeout: Timeout in seconds for graph query execution (defaults to kg_ontology_expansion_timeout, 2.0s).

    Returns:
        List of distinct neighbor entity IDs (e.g. ["Dharma", "Universal Intelligence"]).
        Never raises — logs and returns [] on any timeout or failure (fail-open).
    """
    if not query or neo4j_driver is None:
        return []

    concepts = _find_concepts_in_query(query)
    if not concepts:
        return []

    default_hops = getattr(settings, "kg_max_hops", 2) if settings else 2
    default_entities = getattr(settings, "kg_max_entities", 20) if settings else 20
    default_timeout = getattr(settings, "kg_ontology_expansion_timeout", 2.0) if settings else 2.0

    hops_val = max_hops if max_hops is not None else default_hops
    hops_clamped = min(max(1, int(hops_val)), 2)

    limit_val = max_entities if max_entities is not None else default_entities
    limit_clamped = min(max(1, int(limit_val)), 20)

    timeout_val = float(timeout if timeout is not None else default_timeout)

    cypher = (
        "MATCH (n {entity_id: $concept})-[r]-(neighbor) "
        "WHERE neighbor.entity_id IS NOT NULL AND neighbor.entity_id <> $concept "
        "RETURN DISTINCT neighbor.entity_id AS neighbor "
        "LIMIT $limit"
    ) if hops_clamped == 1 else (
        f"MATCH (n {{entity_id: $concept}})-[*1..{hops_clamped}]-(neighbor) "
        "WHERE neighbor.entity_id IS NOT NULL AND neighbor.entity_id <> $concept "
        "RETURN DISTINCT neighbor.entity_id AS neighbor "
        "LIMIT $limit"
    )

    def _run() -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        with neo4j_driver.session() as session:
            for concept in concepts:
                try:
                    result = session.run(cypher, concept=concept, limit=limit_clamped)
                    for rec in result:
                        neighbor = rec.get("neighbor")
                        if neighbor and neighbor not in seen and neighbor not in concepts:
                            seen.add(neighbor)
                            out.append(neighbor)
                            if len(out) >= limit_clamped:
                                return out
                except Exception as e:
                    logger.warning(
                        f"expand_query_via_kg: Cypher failed for '{concept}': {e}"
                    )
        return out

    try:
        return await asyncio.wait_for(asyncio.to_thread(_run), timeout=timeout_val)
    except asyncio.TimeoutError:
        logger.warning(
            f"expand_query_via_kg timed out after {timeout_val:.2f}s; continuing without neighbor terms"
        )
        return []
    except Exception as e:
        logger.warning(f"expand_query_via_kg failed (non-fatal): {e}")
        return []


async def expand_query_with_ontology(
    query: str,
    neo4j_driver: Any,
    *,
    max_neighbors: int = 10,
) -> list[str]:
    """Return ontology-neighbor terms to broaden the query (backward compatible)."""
    return await expand_query_via_kg(
        query,
        neo4j_driver,
        max_hops=1,
        max_entities=max_neighbors,
    )


_orig_expand_query_with_ontology = expand_query_with_ontology


def augment_query(query: str, neighbors: list[str]) -> str:
    """Append neighbor terms to a query string (used by retrieval expansion).

    Ponytail: one-liner helper. Keeps the original query intact and adds
    neighbor terms as extra retrieval keywords so Qdrant hits docs tagged
    with sub-concepts.
    """
    if not neighbors:
        return query
    return f"{query} {' '.join(neighbors)}"


if __name__ == "__main__":
    # Self-check — no live Neo4j needed. Exercise concept-finding only.
    q = "What does Sadhguru say about karma and the beautiful state?"
    concepts = _find_concepts_in_query(q)
    assert "Sadhguru" in concepts, f"Sadhguru not found: {concepts}"
    assert "Karma" in concepts, f"Karma not found: {concepts}"
    assert "Beautiful State" in concepts, f"Beautiful State not found: {concepts}"
    # No-match case
    assert _find_concepts_in_query("what is the weather") == []
    # None driver -> []
    import asyncio as _a

    out = _a.run(expand_query_with_ontology(q, None))
    assert out == []
    # augment helper
    assert augment_query("karma", ["Dharma"]) == "karma Dharma"
    assert augment_query("karma", []) == "karma"
    print(f"kg_expansion self-check OK — found concepts: {concepts}")

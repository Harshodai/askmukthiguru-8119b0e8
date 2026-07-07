"""Natural-language -> Cypher generator (Task E4.4 stub).

Ponytail: ONE function (`nl2cypher`) + ONE schema constant + ONE read-only
executor (`execute_cypher`). Full productionization (schema introspection,
query-plan validation, cost caps, multi-shot example library) is multi-week;
this is the stub.

Schema constant mirrors `app/db/seed_ontology.py` (Teachers / Concepts /
Practices + EXPOUNDS / PRACTICE_FOR / CONTRASTS_WITH / SYNONYMOUS_WITH).
LightRAG nodes (:base {entity_id}) are also queryable.

Read-only enforcement: `execute_cypher` rejects any query whose first
non-comment keyword isn't a read verb (MATCH / OPTIONAL MATCH / RETURN /
WITH / CALL { ... } that's read-only / SHOW). Defensive — not a substitute
for a real query guard.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph schema (mirror of app/db/seed_ontology.py)
# ---------------------------------------------------------------------------
GRAPH_SCHEMA = """\
# Neo4j Spiritual Knowledge Graph Schema

## Node labels
(:base {entity_id, entity_type, name, description, teacher_id, tenant_id})
(:Teacher {name, bio, entity_type, teacher_id})      # also labeled :base
(:Concept {name, description, entity_type})          # also labeled :base
(:Practice {name, description, entity_type})         # also labeled :base
(:User {id, tenant_id})
(:GlobalMemory {id, content, created_at, tenant_id})

## Relationship types
(:Teacher)-[:EXPOUNDS]->(:Concept)
(:Practice)-[:PRACTICE_FOR]->(:Concept)
(:Concept)-[:CONTRASTS_WITH]->(:Concept)
(:base)-[:SYNONYMOUS_WITH]->(:base)         # alias alignment (align_extracted_ontology)
(:base)-[:RELATED_TO]->(:base)              # generic / extracted triples
(:User)-[:HAS_MEMORY]->(:GlobalMemory)
(:GlobalMemory)-[:RELATED_TO]->(:GlobalMemory)

## Seeded entities (canonical names)
Teachers:  Sadhguru, Sri Amma Bhagavan, ISKCON, Sri Preethaji, Sri Krishnaji
Concepts:  Karma, Dharma, Consciousness, Beautiful State, Suffering
Practices: Meditation, Yoga, Serene Mind, Soul Sync

## Notes
- LightRAG-extracted nodes share the :base label and are linked via
  :RELATED_TO; use entity_id (not entity_name) for lookups.
- Per-user memory nodes (GlobalMemory) carry tenant_id; filter on it.
"""

# Few-shot examples — small, deliberately. Production would have a library.
_FEW_SHOT_EXAMPLES = """\
## Examples

Q: What does Sadhguru teach about karma?
Cypher:
MATCH (t:base {entity_id: 'Sadhguru'})-[:EXPOUNDS]->(c:base {entity_id: 'Karma'})
RETURN t.name AS teacher, c.name AS concept, c.description AS description

Q: Which practices lead to the Beautiful State?
Cypher:
MATCH (p:Practice)-[:PRACTICE_FOR]->(c:Concept {name: 'Beautiful State'})
RETURN p.name AS practice, p.description AS description

Q: What concepts contrast with Suffering?
Cypher:
MATCH (c1:Concept {name: 'Suffering'})-[:CONTRASTS_WITH]->(c2:Concept)
RETURN c2.name AS concept, c2.description AS description

Q: List all teachers and the concepts they expound.
Cypher:
MATCH (t:Teacher)-[:EXPOUNDS]->(c:Concept)
RETURN t.name AS teacher, collect(c.name) AS concepts
"""

_SYSTEM_PROMPT = (
    "You are a Cypher query generator for a Neo4j spiritual knowledge graph. "
    "Convert the user's question into a SINGLE read-only Cypher query. "
    "Return ONLY the Cypher — no prose, no markdown fences, no explanation.\n\n"
    f"{GRAPH_SCHEMA}\n{_FEW_SHOT_EXAMPLES}\n"
    "Rules:\n"
    "- Read-only: MATCH / OPTIONAL MATCH / WITH / RETURN / SHOW only. "
    "Never MERGE / CREATE / DELETE / SET / REMOVE.\n"
    "- Use entity_id (not name) for :base node lookups where possible.\n"
    "- If the question can't be answered from the schema, return: "
    "MATCH (n) RETURN 'unanswerable' AS result LIMIT 0\n"
)

# Read-only keyword guard. First non-comment, non-whitespace token must be
# one of these. Defensive — not a substitute for DB-level guardrails.
_READ_VERBS = {"MATCH", "OPTIONAL", "RETURN", "WITH", "SHOW", "CALL", "PROFILE", "EXPLAIN"}
_WRITE_VERBS = {"CREATE", "MERGE", "DELETE", "SET", "REMOVE", "DROP", "DETACH"}


def _strip_cypher(raw: str) -> str:
    """Strip markdown fences + leading/trailing whitespace."""
    raw = raw or ""
    raw = re.sub(r"^\s*```(?:cypher)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)
    # Some models prepend "Cypher:" — drop it.
    raw = re.sub(r"^\s*cypher:\s*", "", raw, flags=re.IGNORECASE)
    return raw.strip()


def _is_read_only(cypher: str) -> bool:
    """Defensive read-only check. False on any write verb or unknown first verb."""
    if not cypher:
        return False
    # Strip comments // ... and /* ... */
    no_comments = re.sub(r"/\*.*?\*/", " ", cypher, flags=re.DOTALL)
    no_comments = re.sub(r"//[^\n]*", " ", no_comments)
    tokens = no_comments.split()
    if not tokens:
        return False
    first = tokens[0].upper().rstrip(";")
    if first in _WRITE_VERBS:
        return False
    if first in _READ_VERBS:
        # Also scan the whole body for any write verb anywhere.
        upper = no_comments.upper()
        for w in _WRITE_VERBS:
            if re.search(rf"\b{w}\b", upper):
                return False
        return True
    return False


async def nl2cypher(question: str, llm: Any) -> str:
    """Generate a read-only Cypher query from a natural-language question.

    Args:
        question: User's question.
        llm: Object with `async def generate(system_prompt, user_prompt, context="", **kwargs) -> str`.

    Returns:
        A Cypher string. If validation fails or LLM errors, returns a safe
        no-op query: "MATCH (n) RETURN 'unanswerable' AS result LIMIT 0".
        Never raises.
    """
    if not question or not question.strip():
        return "MATCH (n) RETURN 'unanswerable' AS result LIMIT 0"
    if llm is None:
        logger.warning("nl2cypher: no llm provided; returning no-op")
        return "MATCH (n) RETURN 'unanswerable' AS result LIMIT 0"
    try:
        raw = await llm.generate(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=question,
            context="",
            max_tokens=512,
        )
    except Exception as e:
        logger.warning(f"nl2cypher: LLM call failed ({e}); returning no-op")
        return "MATCH (n) RETURN 'unanswerable' AS result LIMIT 0"
    cypher = _strip_cypher(raw)
    # Take up to the first semicolon (in case model emitted multi-statement).
    cypher = cypher.split(";", 1)[0].strip()
    if not _is_read_only(cypher):
        logger.warning(f"nl2cypher: rejected non-read-only query: {cypher[:120]}")
        return "MATCH (n) RETURN 'unanswerable' AS result LIMIT 0"
    return cypher


async def execute_cypher(query: str, neo4j_driver: Any, *, limit: int = 50) -> list[dict[str, Any]]:
    """Execute a Cypher query read-only against Neo4j. Returns list of record dicts.

    Args:
        query: Cypher string (will be re-validated as read-only).
        neo4j_driver: neo4j.Driver (sync). None -> returns [].
        limit: Hard row cap (defensive — appended as `LIMIT` if not present).

    Returns:
        List of dicts (one per record). Never raises — logs + returns [].
    """
    if neo4j_driver is None:
        logger.warning("execute_cypher: no driver provided; returning []")
        return []
    if not _is_read_only(query):
        logger.warning(f"execute_cypher: refused non-read-only query: {query[:120]}")
        return []
    try:
        def _run() -> list[dict[str, Any]]:
            with neo4j_driver.session() as session:
                result = session.run(query)
                rows: list[dict[str, Any]] = []
                for i, rec in enumerate(result):
                    if i >= limit:
                        break
                    rows.append(dict(rec))
                return rows
        return await __import__("asyncio").to_thread(_run)
    except Exception as e:
        logger.warning(f"execute_cypher failed: {e}")
        return []


if __name__ == "__main__":
    # Self-check — no live LLM or Neo4j. Exercise parser + guard.
    fake_raw = "```cypher\nMATCH (t:Teacher) RETURN t.name\n```"
    assert _strip_cypher(fake_raw) == "MATCH (t:Teacher) RETURN t.name"
    assert _is_read_only("MATCH (n) RETURN n")
    assert _is_read_only("OPTIONAL MATCH (n) RETURN n")
    assert not _is_read_only("CREATE (n:Foo)")
    assert not _is_read_only("MATCH (n) DELETE n")
    assert not _is_read_only("MERGE (n:Foo {x:1})")
    # Comment-stripping
    assert _is_read_only("// hi\nMATCH (n) RETURN n")
    # nl2cypher with no llm -> no-op
    import asyncio as _a
    out = _a.run(nl2cypher("What is karma?", None))
    assert "unanswerable" in out
    # execute_cypher with no driver -> []
    assert _a.run(execute_cypher("MATCH (n) RETURN n", None)) == []
    print("nl2cypher self-check OK")
    print(f"  no-op query: {out}")
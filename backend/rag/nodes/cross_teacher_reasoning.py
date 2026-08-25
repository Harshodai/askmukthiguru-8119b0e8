from __future__ import annotations

import asyncio
import hashlib
import logging

from cachetools import TTLCache
from neo4j import GraphDatabase

from app.config import settings
from app.tracing import trace_rag_node
from domain.spiritual_ontology import resolve_teacher_domain
from rag.nodes.retrieval import _screen_prompt_injection
from rag.states import GraphState

logger = logging.getLogger(__name__)

# ponytail: Neo4j cross-teacher query cache (5min TTL). Bounded TTLCache, not a
# plain dict — a dict here only checked TTL on read and never evicted expired
# entries, growing by one entry per unique teacher-set forever.
_cache_ttl_seconds = 300
_neo4j_query_cache: TTLCache = TTLCache(maxsize=500, ttl=_cache_ttl_seconds)


def _approved_edge_confidence_floor() -> float:
    """Return the configured floor for traversable ontology relationships."""
    return float(getattr(settings, "ontology_confidence_threshold", 0.7))

# Prefer the process-wide Container driver. Standalone tests/scripts retain a
# bounded fallback driver, but never create one per request.
_driver = None
_owns_driver = False


def _get_driver():
    global _driver, _owns_driver
    if _driver is None:
        try:
            from app import dependencies as app_dependencies

            container = getattr(app_dependencies, "_container", None)
            shared_driver = container.neo4j_driver if container is not None else None
            if shared_driver is not None:
                _driver = shared_driver
                _owns_driver = False
                return _driver
        except Exception as e:
            logger.debug("cross_teacher_reasoning: shared driver unavailable: %s", e)
        try:
            _driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
                max_connection_pool_size=settings.neo4j_max_connection_pool_size,
                connection_timeout=settings.neo4j_connection_timeout_s,
                connection_acquisition_timeout=settings.neo4j_connection_acquisition_timeout_s,
                max_transaction_retry_time=settings.neo4j_max_transaction_retry_time_s,
                max_connection_lifetime=settings.neo4j_max_connection_lifetime_s,
                keep_alive=settings.neo4j_keep_alive,
            )
            _owns_driver = True
        except Exception as e:
            logger.warning(f"cross_teacher_reasoning: Failed to create Neo4j driver: {e}")
            _driver = None
    return _driver


def close_neo4j_driver() -> None:
    global _driver, _owns_driver
    if _driver is not None and _owns_driver:
        _driver.close()
    _driver = None
    _owns_driver = False


def _licensed_pair(teacher1: str, teacher2: str) -> bool:
    """Both teachers must resolve to a rollout_enabled TeacherDomain for a
    concept-mapping doc to be injected as citable doctrine."""
    d1 = resolve_teacher_domain(teacher1)
    d2 = resolve_teacher_domain(teacher2)
    return bool(d1 and d1.rollout_enabled and d2 and d2.rollout_enabled)


def _build_doc(relationships: list[str], *, licensed: bool) -> dict | None:
    """Screen Neo4j-sourced comparison text before it enters relevant_docs.
    This node runs after retrieve_documents, so it bypasses that node's
    _screen_prompt_injection call unless applied here explicitly."""
    content = "\n".join(relationships)
    if not _screen_prompt_injection([{"text": content}]):
        logger.warning("cross_teacher_reasoning: dropped content failing prompt-injection screen")
        return None
    if licensed:
        return {
            "content": content,
            "score": 0.95,
            "title": "Cross-Teacher Ontology Mapping",
            "source": "neo4j://ontology/comparison",
            "content_type": "ontology_comparison",
        }
    return {
        "content": f"[External reference — not part of the licensed teaching corpus]\n{content}",
        "score": 0.4,
        "title": "External reference — not part of the licensed teaching corpus",
        "source": "neo4j://ontology/comparison",
        "content_type": "external_reference",
    }


@trace_rag_node("cross_teacher_reasoning")
async def cross_teacher_reasoning(state: GraphState, config: dict = None) -> dict:
    """
    RAG Node for Cross-Teacher comparisons.
    If the question mentions multiple spiritual teachers, it queries Neo4j
    to find paths/relationships between them and their concepts,
    appends structured graph context, and informs the generation stage.
    """
    question = state.get("question", "")
    if not question:
        return {}

    # Identify teachers mentioned in the question
    teachers = []
    question_lower = question.lower()
    import re

    has_sadhguru = bool(re.search(r"\bsadhguru\b", question_lower))
    has_preethaji = bool(re.search(r"\bpreethaji\b", question_lower))
    has_ekam = bool(re.search(r"\bekam\b", question_lower))
    has_krishnaji = bool(re.search(r"\bkrishnaji\b", question_lower))
    has_amma = bool(re.search(r"\bamma\b", question_lower))
    has_bhagavan = bool(re.search(r"\bbhagavan\b", question_lower))
    has_iskcon = bool(re.search(r"\biskcon\b", question_lower))
    has_krishna = bool(re.search(r"\bkrishna\b", question_lower))

    if has_sadhguru:
        teachers.append("Sadhguru")
    if has_preethaji or has_ekam:
        teachers.append("Sri Preethaji")
    if has_krishnaji or has_preethaji or has_ekam:
        teachers.append("Sri Krishnaji")
    if has_amma or has_bhagavan:
        teachers.append("Sri Amma Bhagavan")
    if has_iskcon or (has_krishna and not has_krishnaji):
        if "ISKCON" not in teachers:
            teachers.append("ISKCON")

    # Dedup and check if there are multiple teachers
    teachers = list(dict.fromkeys(teachers))
    if len(teachers) < 2:
        logger.debug(
            f"cross_teacher_reasoning: Comparison not needed (detected teachers: {teachers})"
        )
        return {}

    logger.info(f"cross_teacher_reasoning: Comparison detected between: {teachers}")

    # ponytail: Check cache before Neo4j query
    cache_key = hashlib.md5(",".join(sorted(teachers)).encode(), usedforsecurity=False).hexdigest()
    cached_results = _neo4j_query_cache.get(cache_key)
    if cached_results is not None:
        logger.info("Neo4j cross-teacher cache hit")
        licensed_rel, external_rel = cached_results
        docs_to_inject = []
        if licensed_rel:
            doc = _build_doc(licensed_rel, licensed=True)
            if doc:
                docs_to_inject.append(doc)
        if external_rel:
            doc = _build_doc(external_rel, licensed=False)
            if doc:
                docs_to_inject.append(doc)
        if docs_to_inject:
            current_docs = state.get("relevant_docs") or []
            return {
                "relevant_docs": docs_to_inject + current_docs,
                "is_cross_teacher": True,
                "compared_teachers": teachers,
            }
        return {}

    # Query Neo4j for relationships between these teachers and common concepts.
    # Only explicitly approved edges above the configured confidence floor are
    # traversable. Legacy edges without review metadata are intentionally excluded.
    # Split by whether BOTH teachers resolve to a rollout_enabled TeacherDomain
    # (see domain/spiritual_ontology.py) -- only licensed pairs are injected as
    # citable doctrine; anything else is relabeled as an external reference.
    licensed_relationships: list[str] = []
    external_relationships: list[str] = []
    if settings.neo4j_uri:
        try:

            def _query_paths(tx):
                # Find concepts that both teachers expound
                cypher = """
                MATCH (t1:Teacher)-[r1:EXPOUNDS]->(c:Concept)<-[r2:EXPOUNDS]-(t2:Teacher)
                WHERE t1.name IN $teachers
                  AND t2.name IN $teachers
                  AND t1.name <> t2.name
                  AND coalesce(r1.reviewed, false) = true
                  AND coalesce(r2.reviewed, false) = true
                  AND coalesce(r1.review_status, 'pending') = 'approved'
                  AND coalesce(r2.review_status, 'pending') = 'approved'
                  AND toFloat(coalesce(r1.confidence, 0.0)) >= $confidence_floor
                  AND toFloat(coalesce(r2.confidence, 0.0)) >= $confidence_floor
                RETURN t1.name AS teacher1, t2.name AS teacher2, c.name AS concept, c.description AS description
                """
                return [
                    dict(record)
                    for record in tx.run(
                        cypher,
                        teachers=teachers,
                        confidence_floor=_approved_edge_confidence_floor(),
                    )
                ]

            driver = _get_driver()
            if driver is None:
                raise RuntimeError("Neo4j driver unavailable")

            def _run_query():
                with driver.session() as session:
                    return session.execute_read(_query_paths)

            records = await asyncio.to_thread(_run_query)

            for r in records:
                text = (
                    f"Ontology Connection: Both {r['teacher1']} and {r['teacher2']} expound the concept of '{r['concept']}'. "
                    f"Concept definition: {r['description']}"
                )
                if _licensed_pair(r["teacher1"], r["teacher2"]):
                    licensed_relationships.append(text)
                else:
                    external_relationships.append(text)
        except Exception as e:
            logger.warning(
                f"cross_teacher_reasoning: Failed to query Neo4j for cross-teacher paths: {e}"
            )

    # If we found ontology connections, construct comparison context and add to documents
    if licensed_relationships or external_relationships:
        # Cache the results before returning
        _neo4j_query_cache[cache_key] = (licensed_relationships, external_relationships)

        docs_to_inject = []
        if licensed_relationships:
            doc = _build_doc(licensed_relationships, licensed=True)
            if doc:
                docs_to_inject.append(doc)
        if external_relationships:
            doc = _build_doc(external_relationships, licensed=False)
            if doc:
                docs_to_inject.append(doc)

        if docs_to_inject:
            current_docs = state.get("relevant_docs") or []
            logger.info(
                "cross_teacher_reasoning: Prepending ontology mapping to relevant_docs context."
            )
            return {
                "relevant_docs": docs_to_inject + current_docs,
                "is_cross_teacher": True,
                "compared_teachers": teachers,
            }
        return {}

    # Cache empty result too to avoid repeated queries with no results
    _neo4j_query_cache[cache_key] = ([], [])
    return {}

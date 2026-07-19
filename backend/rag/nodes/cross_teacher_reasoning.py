import asyncio
import hashlib
import logging
from cachetools import TTLCache
from neo4j import GraphDatabase
from rag.states import GraphState
from app.config import settings
from app.tracing import trace_rag_node

logger = logging.getLogger(__name__)

# ponytail: Neo4j cross-teacher query cache (5min TTL). Bounded TTLCache, not a
# plain dict — a dict here only checked TTL on read and never evicted expired
# entries, growing by one entry per unique teacher-set forever.
_cache_ttl_seconds = 300
_neo4j_query_cache: TTLCache = TTLCache(maxsize=500, ttl=_cache_ttl_seconds)

# Shared driver: constructing a driver does a handshake/routing-table fetch,
# so open one per process and reuse it instead of per-request.
_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        try:
            _driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password)
            )
        except Exception as e:
            logger.warning(f"cross_teacher_reasoning: Failed to create Neo4j driver: {e}")
            _driver = None
    return _driver

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
        logger.debug(f"cross_teacher_reasoning: Comparison not needed (detected teachers: {teachers})")
        return {}

    logger.info(f"cross_teacher_reasoning: Comparison detected between: {teachers}")

    # ponytail: Check cache before Neo4j query
    cache_key = hashlib.md5(",".join(sorted(teachers)).encode()).hexdigest()
    cached_results = _neo4j_query_cache.get(cache_key)
    if cached_results is not None:
        logger.info("Neo4j cross-teacher cache hit")
        if cached_results:
            comparison_doc = {
                "content": "\n".join(cached_results),
                "score": 0.95,
                "title": "Cross-Teacher Ontology Mapping",
                "source": "neo4j://ontology/comparison",
                "content_type": "ontology_comparison"
            }
            current_docs = state.get("relevant_docs") or []
            return {
                "relevant_docs": [comparison_doc] + current_docs,
                "is_cross_teacher": True,
                "compared_teachers": teachers
            }
        return {}

    # Query Neo4j for relationships between these teachers and common concepts
    relationships_found = []
    if settings.neo4j_uri:
        try:
            def _query_paths(tx):
                # Find concepts that both teachers expound
                cypher = """
                MATCH (t1:Teacher)-[:EXPOUNDS]->(c:Concept)<-[:EXPOUNDS]-(t2:Teacher)
                WHERE t1.name IN $teachers AND t2.name IN $teachers AND t1.name <> t2.name
                RETURN t1.name AS teacher1, t2.name AS teacher2, c.name AS concept, c.description AS description
                """
                return [dict(record) for record in tx.run(cypher, teachers=teachers)]

            driver = _get_driver()
            if driver is None:
                raise RuntimeError("Neo4j driver unavailable")

            def _run_query():
                with driver.session() as session:
                    return session.execute_read(_query_paths)

            records = await asyncio.to_thread(_run_query)

            for r in records:
                relationships_found.append(
                    f"Ontology Connection: Both {r['teacher1']} and {r['teacher2']} expound the concept of '{r['concept']}'. "
                    f"Concept definition: {r['description']}"
                )
        except Exception as e:
            logger.warning(f"cross_teacher_reasoning: Failed to query Neo4j for cross-teacher paths: {e}")

    # If we found ontology connections, construct a comparison context and add to documents
    if relationships_found:
        # Cache the results before returning
        _neo4j_query_cache[cache_key] = relationships_found

        comparison_doc = {
            "content": "\n".join(relationships_found),
            "score": 0.95,
            "title": "Cross-Teacher Ontology Mapping",
            "source": "neo4j://ontology/comparison",
            "content_type": "ontology_comparison"
        }
        # Prepend to relevant_docs
        current_docs = state.get("relevant_docs") or []
        logger.info("cross_teacher_reasoning: Prepending ontology mapping to relevant_docs context.")
        return {
            "relevant_docs": [comparison_doc] + current_docs,
            "is_cross_teacher": True,
            "compared_teachers": teachers
        }

    # Cache empty result too to avoid repeated queries with no results
    _neo4j_query_cache[cache_key] = []
    return {}

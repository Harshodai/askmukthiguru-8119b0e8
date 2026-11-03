"""DEPRECATED / RETIRED (Phase 6 / Decision D8).

The experimental NL->Cypher generator stub has been retired per Master Plan D8.
Structured-data questions abstain honestly through standard pipeline gates
rather than generating unvalidated, schema-uninspected Cypher queries.

This module is preserved as a tombstone/deprecated interface for backward
compatibility. Any invocation logs a retirement notice and returns a safe
honest abstention/no-op result.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

logger = logging.getLogger(__name__)

warnings.warn(
    "backend.rag.nodes.nl2cypher is deprecated and retired per Phase 6 / Decision D8. "
    "Structured-data queries abstain honestly.",
    DeprecationWarning,
    stacklevel=2,
)

GRAPH_SCHEMA = ""
_SYSTEM_PROMPT = ""
_READ_VERBS = frozenset(
    {"MATCH", "OPTIONAL", "RETURN", "WITH", "SHOW", "CALL", "PROFILE", "EXPLAIN"}
)
_WRITE_VERBS = frozenset({"CREATE", "MERGE", "DELETE", "SET", "REMOVE", "DROP", "DETACH"})


def _strip_cypher(raw: str) -> str:
    return ""


def _is_read_only(cypher: str) -> bool:
    return False


async def nl2cypher(question: str, llm: Any = None) -> str:
    """Retired NL->Cypher stub. Returns a safe no-op unanswerable query."""
    logger.info("nl2cypher is retired (D8); returning honest unanswerable query.")
    return "MATCH (n) RETURN 'unanswerable' AS result LIMIT 0"


async def execute_cypher(
    query: str,
    neo4j_driver: Any = None,
    *,
    limit: int = 50,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Retired Cypher executor. Returns [] safely."""
    logger.info("execute_cypher is retired (D8); returning empty result.")
    return []


if __name__ == "__main__":
    import asyncio as _a

    out = _a.run(nl2cypher("What is karma?", None))
    assert "unanswerable" in out
    assert _a.run(execute_cypher("MATCH (n) RETURN n", None)) == []
    print("nl2cypher retired stub check OK")

import asyncio
import hashlib
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)


def _query_token(query: str) -> str:
    """Non-reversible 8-char token derived from query for log correlation.

    Avoids exposing raw user content in logs while still allowing
    correlation between retrieval failure entries for the same query.
    """
    return hashlib.sha256(query.encode()).hexdigest()[:8]


class ConcurrentRetriever:
    """
    Wraps vector and graph retrievers to fetch results concurrently.

    Uses asyncio.TaskGroup (Python 3.11+) for structured concurrency:
    - Any exception in vector or graph fetcher immediately cancels the sibling
    - ExceptionGroup raised by TaskGroup is caught and re-raised as the root cause
    - No silent exception swallowing (unlike asyncio.gather with return_exceptions=True)
    """

    def __init__(
        self,
        vector_fetcher: Callable[[str], Coroutine[Any, Any, list[str]]],
        graph_fetcher: Callable[[str], Coroutine[Any, Any, list[str]]],
    ):
        self.vector_fetcher = vector_fetcher
        self.graph_fetcher = graph_fetcher

    async def retrieve(self, query: str) -> dict[str, list[str]]:
        """Structured concurrent retrieval — TaskGroup cancels all on first failure."""
        try:
            async with asyncio.TaskGroup() as tg:
                vt = tg.create_task(self.vector_fetcher(query), name="vector_retrieval")
                gt = tg.create_task(self.graph_fetcher(query), name="graph_retrieval")
        except Exception as eg:
            # Unwrap the first exception from the ExceptionGroup for clean logging.
            # Use a non-reversible hash token — never log raw user query content.
            first_exc = eg.exceptions[0]
            logger.error(
                "Concurrent retrieval failed",
                extra={"error": str(first_exc), "query_token": _query_token(query)},
            )
            raise first_exc from None
        return {
            "vector": vt.result(),
            "graph": gt.result(),
        }
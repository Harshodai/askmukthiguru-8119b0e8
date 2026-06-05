import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ConcurrentRetriever:
    """
    Wraps vector and graph retrievers to fetch results concurrently via asyncio.gather.
    """

    def __init__(
        self,
        vector_fetcher: Callable[[str], Coroutine[Any, Any, list[str]]],
        graph_fetcher: Callable[[str], Coroutine[Any, Any, list[str]]],
    ):
        self.vector_fetcher = vector_fetcher
        self.graph_fetcher = graph_fetcher

    async def retrieve(self, query: str) -> dict[str, list[str]]:
        """Executes vector and graph retrieval concurrently to eliminate blocking latency."""
        vector_task = self.vector_fetcher(query)
        graph_task = self.graph_fetcher(query)

        vector_res, graph_res = await asyncio.gather(vector_task, graph_task)
        return {
            "vector": vector_res,
            "graph": graph_res,
        }
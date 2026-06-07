"""
Mukthi Guru — Tool Use Abstraction (Tool Design Pattern)

Provides a unified interface for nodes that call external services
(Qdrant, embedding, etc.).

Design Patterns:
  - Tool Use: Each external capability is wrapped as a Tool
  - Strategy Pattern: Pluggable tool implementations
  - Future: LLM can select tools dynamically via tool descriptions

Usage:
    tool = QdrantSearchTool(qdrant_service)
    result = await tool.execute(query="...", top_k=5)
"""

from __future__ import annotations

import abc
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class Tool(abc.ABC):
    """
    Base class for all pluggable tools in the RAG pipeline.

    Subclasses describe their inputs (``parameters``) and implement
    ``execute()`` to carry out the work.
    """

    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}

    @abc.abstractmethod
    async def execute(self, **params) -> Any:
        """Run the tool and return its output."""
        ...


class QdrantSearchTool(Tool):
    """Tool for searching the Qdrant vector store."""

    name = "qdrant_search"
    description = "Search Qdrant vector store for relevant documents."
    parameters = {
        "query": "str — search query text",
        "top_k": "int — number of results (default: 5)",
        "filter": "dict | None — optional metadata filter",
    }

    def __init__(self, qdrant_service, embedding_service):
        self._qdrant = qdrant_service
        self._embedding = embedding_service

    async def execute(self, *, query: str, top_k: int = 5, filter: Optional[Dict] = None) -> list[dict]:
        """Embed the query and search Qdrant for matching documents."""
        logger.debug(f"[QdrantSearchTool] query={query!r}, top_k={top_k}")
        query_embedding = self._embedding.embed_query(query)
        return self._qdrant.search(query_embedding, top_k=top_k, filter=filter)


class EmbeddingTool(Tool):
    """Tool for embedding text (query or document)."""

    name = "embedding"
    description = "Embed text into a dense vector using the configured embedding model."
    parameters = {
        "text": "str — text to embed",
        "is_query": "bool — True for query, False for document (default: True)",
    }

    def __init__(self, embedding_service):
        self._embedding = embedding_service

    async def execute(self, *, text: str, is_query: bool = True) -> list[float]:
        """Return the embedding vector for the given text."""
        logger.debug(f"[EmbeddingTool] text={text[:60]!r}..., is_query={is_query}")
        return self._embedding.embed_query(text) if is_query else self._embedding.embed_document(text)


class LLMGenerateTool(Tool):
    """Tool for LLM text generation via the configured provider."""

    name = "llm_generate"
    description = "Generate text using the LLM provider (Ollama / Sarvam Cloud)."
    parameters = {
        "system_prompt": "str — system / persona prompt",
        "user_prompt": "str — user message / task",
        "context": "str — retrieved context to inject",
    }

    def __init__(self, llm_service):
        self._llm = llm_service

    async def execute(self, *, system_prompt: str, user_prompt: str, context: str = "", **kwargs) -> str:
        """Generate text using the LLM service."""
        logger.debug(f"[LLMGenerateTool] user_prompt={user_prompt[:60]!r}...")
        return await self._llm.generate(system_prompt, user_prompt, context, **kwargs)


class ToolRegistry:
    """
    Registry for all available tools.

    Usage:
        registry = ToolRegistry()
        registry.register(QdrantSearchTool(qdrant_svc, embedding_svc))
        tool = registry.get("qdrant_search")
        result = await tool.execute(query="...")
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry.")
        return self._tools[name]

    def list(self) -> list[str]:
        return list(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

"""Service Contracts (Protocols) — enables Dependency Inversion.

All service interfaces are defined as typing.Protocol so that any concrete
implementation can be swapped without changing consumers.

Usage:
    from app.contracts import LLMService, VectorStore, EmbeddingService, GuardrailsService, TranscriptionProvider
"""

from __future__ import annotations

from app.contracts.embedding import EmbeddingService
from app.contracts.guardrails import GuardrailsService
from app.contracts.llm import LLMService
from app.contracts.translation import TranslationService
from app.contracts.transcription import TranscriptionProvider
from app.contracts.vector_store import VectorStore

__all__ = [
    "LLMService",
    "EmbeddingService",
    "VectorStore",
    "GuardrailsService",
    "TranslationService",
    "TranscriptionProvider",
]


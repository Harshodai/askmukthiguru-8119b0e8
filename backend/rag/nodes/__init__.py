"""Mukthi Guru — LangGraph Node Functions Layer Modules.

This package exposes all LangGraph node functions by re-exporting them from their
individual layer modules (intent, retrieval, reranking, generation, verification, short_circuit).
"""

from __future__ import annotations

import sys
from typing import Any

from app.config import settings as app_settings
from . import _services
from . import utils

from ._services import init_services
from .utils import (
    select_llm_model,
)
from .intent import (
    intent_router,
    handle_casual,
    handle_distress,
    handle_meditation,
    route_by_intent,
    route_after_grading,
)
from .retrieval import (
    decompose_query,
    generate_hyde,
    navigate_knowledge_tree,
    retrieve_documents,
    retrieve_single,
    merge_sub_results,
)
from .reranking import (
    rerank_documents,
    grade_documents,
    check_context_sufficiency,
    enrich_context,
)
from .generation import (
    context_engineer,
    generate_answer,
    format_final_answer,
)
from .verification import (
    reflect_on_answer,
    verify_answer,
    check_contradiction,
    explain_retrieval,
)
from .short_circuit import (
    rewrite_query,
    handle_fallback,
)

# Placeholder module-level attributes for IDE/static analysis and direct access
_ollama: Any = None
_embedder: Any = None
_qdrant: Any = None
_lightrag: Any = None
_serene_mind: Any = None
_semantic_cache: Any = None
_lettuce_detect: Any = None
_reranker: Any = None
_context_compressor: Any = None
settings: Any = app_settings

from types import ModuleType

class NodesModule(ModuleType):
    def __getattr__(self, name: str) -> Any:
        if name == "settings":
            return app_settings
        if name in {
            "_ollama",
            "_embedder",
            "_qdrant",
            "_lightrag",
            "_serene_mind",
            "_semantic_cache",
            "_lettuce_detect",
            "_reranker",
            "_context_compressor",
        }:
            return getattr(_services, name)
        if name in {
            "strip_cot",
            "_generation_kwargs",
            "_rrf_docs",
            "_estimate_tokens",
            "_generation_route",
        }:
            return getattr(utils, name)
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {
            "_ollama",
            "_embedder",
            "_qdrant",
            "_lightrag",
            "_serene_mind",
            "_semantic_cache",
            "_lettuce_detect",
            "_reranker",
            "_context_compressor",
        }:
            setattr(_services, name, value)
        else:
            super().__setattr__(name, value)

sys.modules[__name__].__class__ = NodesModule

__all__ = [
    "select_llm_model",
    "init_services",
    "intent_router",
    "handle_casual",
    "handle_distress",
    "handle_meditation",
    "route_by_intent",
    "route_after_grading",
    "decompose_query",
    "generate_hyde",
    "navigate_knowledge_tree",
    "retrieve_documents",
    "retrieve_single",
    "merge_sub_results",
    "rerank_documents",
    "grade_documents",
    "check_context_sufficiency",
    "enrich_context",
    "context_engineer",
    "generate_answer",
    "format_final_answer",
    "reflect_on_answer",
    "verify_answer",
    "check_contradiction",
    "explain_retrieval",
    "rewrite_query",
    "handle_fallback",
    "settings",
]


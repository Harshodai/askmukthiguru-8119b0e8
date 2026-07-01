"""Mukthi Guru — LangGraph Node Functions Layer Modules.

This package exposes all LangGraph node functions by re-exporting them from their
individual layer modules (intent, retrieval, reranking, generation, verification, short_circuit).
"""

from __future__ import annotations

import sys
from typing import Any

from app.config import settings as app_settings

from . import _services, utils
from ._services import init_services
from .generation import (
    context_engineer,
    format_final_answer,
    generate_answer,
)
from .intent import (
    handle_casual,
    handle_distress,
    handle_distress_check,
    handle_meditation,
    intent_router,
    route_after_grading,
    route_by_intent,
)
from .reranking import (
    check_context_sufficiency,
    enrich_context,
    grade_documents,
    rerank_documents,
)
from .retrieval import (
    decompose_query,
    generate_hyde,
    merge_sub_results,
    navigate_and_hyde,
    navigate_knowledge_tree,
    retrieve_documents,
    retrieve_single,
)
from .short_circuit import (
    handle_fallback,
    rewrite_query,
)
from .utils import (
    select_llm_model,
)
from .citation_extractor import extract_citations
from .verification import (
    check_contradiction,
    explain_retrieval,
    reflect_on_answer,
    verify_answer,
)
from .web_search import web_search_node

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
_sarvam_cloud: Any = None
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
            "_sarvam_cloud",
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
            "_sarvam_cloud",
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
    "handle_distress_check",
    "handle_meditation",
    "route_by_intent",
    "route_after_grading",
    "decompose_query",
    "generate_hyde",
    "navigate_knowledge_tree",
    "navigate_and_hyde",
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
    "extract_citations",
    "rewrite_query",
    "handle_fallback",
    "settings",
    "web_search_node",
]


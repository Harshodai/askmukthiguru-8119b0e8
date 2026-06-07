"""Mukthi Guru — Per-Node LLM Configuration

Centralized per-node LLM parameters. Loaded once at module import.
Nodes read their own config at runtime per pipeline path variant.
"""

from typing import Any, Dict

# Per-node LLM settings for each pipeline variant.
# effort: "low" | "medium" | "high" — passed to LLM as reasoning_effort
# timeout: per-node LLM call timeout (seconds)
# model: optional model name override (None = use default model)
# max_tokens: optional max-tokens override (None = use default)

FAST_PATH_CONFIG: Dict[str, Dict[str, Any]] = {
    "intent_router":       {"effort": "low",  "timeout": 15, "model": None, "max_tokens": None},
    "resolve_followup":  {"effort": "low",  "timeout": 15, "model": None, "max_tokens": None},
    "retrieve_documents":  {"effort": None,  "timeout": 10, "model": None, "max_tokens": None},
    "generate_answer":     {"effort": "low",  "timeout": 30, "model": None, "max_tokens": 512},
    "format_final_answer": {"effort": "low",  "timeout": 10, "model": None, "max_tokens": None},
    "handle_casual":       {"effort": "low",  "timeout": 10, "model": None, "max_tokens": None},
    "handle_distress":     {"effort": "low",  "timeout": 15, "model": None, "max_tokens": None},
    "handle_meditation":   {"effort": None,  "timeout": 2,  "model": None, "max_tokens": None},
    "handle_fallback":     {"effort": "low",  "timeout": 10, "model": None, "max_tokens": None},
}

STANDARD_PATH_CONFIG: Dict[str, Dict[str, Any]] = {
    "intent_router":       {"effort": "low",    "timeout": 15, "model": None, "max_tokens": None},
    "resolve_followup":    {"effort": "low",    "timeout": 15, "model": None, "max_tokens": None},
    "decompose_query":     {"effort": "medium", "timeout": 30, "model": None, "max_tokens": None},
    "navigate_knowledge_tree": {"effort": "medium", "timeout": 30, "model": None, "max_tokens": None},
    "generate_hyde":       {"effort": "medium", "timeout": 30, "model": None, "max_tokens": None},
    "retrieve_documents":  {"effort": None,     "timeout": 10, "model": None, "max_tokens": None},
    "rerank_documents":    {"effort": None,     "timeout": 5,  "model": None, "max_tokens": None},
    "grade_documents":     {"effort": "low",   "timeout": 20, "model": None, "max_tokens": None},
    "check_context_sufficiency": {"effort": "low", "timeout": 15, "model": None, "max_tokens": None},
    "enrich_context":      {"effort": None,     "timeout": 5,  "model": None, "max_tokens": None},
    "context_engineer":    {"effort": None,     "timeout": 5,  "model": None, "max_tokens": None},
    "generate_answer":     {"effort": "high",   "timeout": 60, "model": None, "max_tokens": 1024},
    "reflect_on_answer":   {"effort": "medium", "timeout": 30, "model": None, "max_tokens": None},
    "verify_answer":       {"effort": "medium", "timeout": 30, "model": None, "max_tokens": None},
    "check_contradiction": {"effort": "low",   "timeout": 15, "model": None, "max_tokens": None},
    "explain_retrieval":   {"effort": "low",   "timeout": 15, "model": None, "max_tokens": None},
    "format_final_answer": {"effort": "low",   "timeout": 10, "model": None, "max_tokens": None},
    "rewrite_query":       {"effort": "medium", "timeout": 30, "model": None, "max_tokens": None},
    "handle_casual":       {"effort": "low",   "timeout": 10, "model": None, "max_tokens": None},
    "handle_distress":     {"effort": "low",   "timeout": 15, "model": None, "max_tokens": None},
    "handle_meditation":   {"effort": None,     "timeout": 2,  "model": None, "max_tokens": None},
    "handle_fallback":     {"effort": "low",   "timeout": 10, "model": None, "max_tokens": None},
}

# Deep path = standard + overrides for deeper reasoning
DEEP_PATH_CONFIG: Dict[str, Dict[str, Any]] = {
    **STANDARD_PATH_CONFIG,  # Inherit everything from standard
    # Override specific nodes for deeper reasoning
    "generate_answer":     {"effort": "high",   "timeout": 90, "model": "sarvam-105b", "max_tokens": 2048},
    "reflect_on_answer":   {"effort": "high",   "timeout": 60, "model": None, "max_tokens": None},
    "verify_answer":       {"effort": "high",   "timeout": 60, "model": None, "max_tokens": None},
}

def get_node_config(node_name: str, path: str = "standard") -> Dict[str, Any]:
    """Get per-node LLM configuration for a specific pipeline path.

    Args:
        node_name: Name of the node (must match the name used in graph wiring).
        path: Which pipeline path config to use ("fast", "standard", or "deep").

    Returns:
        Dict with keys: effort, timeout, model, max_tokens.
        Returns an empty dict if the node or path is not found.
    """
    configs = {
        "fast": FAST_PATH_CONFIG,
        "standard": STANDARD_PATH_CONFIG,
        "deep": DEEP_PATH_CONFIG,
    }
    path_config = configs.get(path, STANDARD_PATH_CONFIG)
    return path_config.get(node_name, {}) or {}

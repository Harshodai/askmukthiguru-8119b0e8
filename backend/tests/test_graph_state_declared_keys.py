"""LangGraph drops node-returned keys that GraphState does not declare.

Static guard: any key a rag/nodes `return {...}` emits AND that some later
reader fetches via state/graph_result/result `.get("k")` or `["k"]` must be
declared in GraphState, or sit in the commented allowlist below.
"""

import ast
import re
from pathlib import Path

from rag.states import GraphState

ROOT = Path(__file__).resolve().parents[1]
READER_DIRS = [ROOT / "rag", ROOT / "app" / "pipeline"]
READ_RE = re.compile(r"\b(?:state|graph_result|result)(?:\.get\(|\[)\s*[\"'](\w+)[\"']")

# Intentionally NOT declared. Declaring any of these changes behaviour in a way
# that needs an owner decision (see backend task notes 2026-11-20).
INTENTIONALLY_DROPPED = {
    # Declaring makes reflection verification SKIP the semantic pass
    # (verification.py reflection_semantic) -> relaxes a verification gate.
    "high_confidence_retrieval",
    # Declaring makes resolve_followup skip question contextualisation, but
    # intent_router does not itself contextualise -> follow-ups lose context.
    "follow_up_detected",
    # Read only by the agentic traversal node (flag off by default) across loop
    # steps; declaring would change that flag-gated path's behaviour.
    "graph_traversal_context",
}
# Keys that appear in nested result dicts (verification/LettuceDetect payloads,
# tool outputs), not as graph-state channels.
NESTED_NOT_STATE = {
    "passed", "details", "claims", "score", "is_valid", "method", "verdict", "ratio",
    "action", "done", "reasoning", "entity_id", "content", "title", "metadata",
    "text", "source", "semantic", "contradictions", "has_contradiction",
    "unsupported_sentences", "timed_out", "citations_verified", "redacted_sentences",
    "draft_details", "relevancy_score", "context_chunks", "content_type", "categories",
    "adjacent_concepts", "navigation_hints", "node_data", "relation_summary",
    "traversal_options", "keywords", "tags", "terms", "teachers", "factual_context", "has_doctrine_match",
}


def _returned_keys() -> set[str]:
    keys: set[str] = set()
    for p in (ROOT / "rag" / "nodes").rglob("*.py"):
        for n in ast.walk(ast.parse(p.read_text())):
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict):
                keys |= {
                    k.value
                    for k in n.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
    return keys


def _read_keys() -> set[str]:
    keys: set[str] = set()
    for d in READER_DIRS:
        for p in d.rglob("*.py"):
            keys |= set(READ_RE.findall(p.read_text()))
    return keys


def test_returned_and_read_keys_are_declared():
    declared = set(GraphState.__annotations__)
    missing = (
        (_returned_keys() & _read_keys())
        - declared
        - INTENTIONALLY_DROPPED
        - NESTED_NOT_STATE
    )
    assert not missing, f"Declare in GraphState (or allowlist with a reason): {sorted(missing)}"


def test_telemetry_keys_survive_graph():
    for k in ("no_context", "orphan_citations_stripped"):
        assert k in GraphState.__annotations__

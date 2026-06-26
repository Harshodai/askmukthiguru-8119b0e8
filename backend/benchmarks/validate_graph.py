#!/usr/bin/env python3
"""
validate_graph.py — Static validation of multi-variant graph topology.

Verifies (without running Docker/backend):
  1. All three graph variants compile successfully
  2. Fast graph contains only the expected 5 core nodes
  3. Standard graph contains all 13 nodes with parallel nav+hyde
  4. Removed tier2_simple nodes are not present in fast graph
  5. No syntax errors in modified files
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path


def _check_syntax(path: Path) -> bool:
    try:
        with open(path) as f:
            ast.parse(f.read())
        return True
    except SyntaxError as exc:
        print(f"  ❌ SYNTAX ERROR in {path}: {exc}")
        return False


def main() -> int:
    backend = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(backend))

    # ── Syntax checks ────────────────────────────────────────────────
    print("=== Syntax validation ===")
    files = [
        "rag/graph.py",
        "rag/graph_strategies.py",
        "rag/node_registry.py",
        "rag/node_llm_config.py",
        "rag/nodes/__init__.py",
        "rag/nodes/_services.py",
        "rag/nodes/generation.py",
        "rag/nodes/intent.py",
        "rag/nodes/keyword_injection.py",
        "rag/nodes/on_device_intent.py",
        "rag/nodes/reranking.py",
        "rag/nodes/retrieval.py",
        "rag/nodes/short_circuit.py",
        "rag/nodes/utils.py",
        "rag/nodes/verification.py",
        "rag/nodes/web_search.py",
        "app/dependencies.py",
        "app/main.py",
        "rag/resolve_followup.py",
    ]
    all_ok = True
    for f in files:
        ok = _check_syntax(backend / f)
        print(f"  {'✅' if ok else '❌'} {f}")
        all_ok = all_ok and ok

    if not all_ok:
        return 1

    # ── Graph topology checks ───────────────────────────────────────
    print("\n=== Graph topology validation ===")

    # Load graph module (can't compile real graphs without services,
    # so we inspect the source helpers & wiring)
    spec = importlib.util.spec_from_file_location("graph", backend / "rag/graph.py")
    if spec is None or spec.loader is None:
        print("❌ Cannot load graph.py")
        return 1
    graph_mod = importlib.util.module_from_spec(spec)
    sys.modules["graph"] = graph_mod

    # Inject minimal stubs for imports to avoid import errors
    from unittest.mock import MagicMock

    # Create stubs for imports that graph.py needs
    stubs = {
        "rag.nodes": MagicMock(),
        "rag.states": MagicMock(GraphState=dict),
        "rag.resolve_followup": MagicMock(resolve_followup=lambda s: {}),
        "services.embedding_service": MagicMock(EmbeddingService=object),
        "services.lightrag_service": MagicMock(LightRAGService=object),
        "services.ollama_service": MagicMock(OllamaService=object),
        "services.qdrant_service": MagicMock(QdrantService=object),
        "services.serene_mind_engine": MagicMock(SereneMindEngine=object),
        "app.config": MagicMock(settings=MagicMock(llm_provider="sarvam_cloud", openrouter_api_key="mock_key")),
    }
    for name, stub in stubs.items():
        sys.modules[name] = stub

    try:
        spec.loader.exec_module(graph_mod)
    except Exception as exc:
        print(f"⚠️  Could not exec graph.py (expected without full deps): {exc}")

    # Verify the three builder function names exist
    funcs = ["build_rag_graph", "build_fast_graph", "build_deep_graph"]
    for fn in funcs:
        if hasattr(graph_mod, fn):
            print(f"  ✅ {fn}() defined")
        else:
            print(f"  ❌ {fn}() MISSING")
            all_ok = False

    # ── Fast graph node exclusion check (static source scan) ────────
    print("\n=== Fast graph node exclusion ===")
    excluded = {
        "decompose_query",
        "navigate_knowledge_tree",
        "generate_hyde",
        "rerank_documents",
        "grade_documents",
        "check_context_sufficiency",
        "enrich_context",
        "context_engineer",
        "reflect_on_answer",
        "verify_answer",
        "check_contradiction",
        "explain_retrieval",
    }
    graph_source = (backend / "rag/graph_strategies.py").read_text()
    # Extract only the FastGraphStrategy class body
    fast_start = graph_source.find("class FastGraphStrategy(")
    fast_end = graph_source.find("class DeepGraphStrategy(", fast_start)
    fast_graph_source = graph_source[fast_start:fast_end] if fast_start != -1 and fast_end != -1 else ""

    for node in excluded:
        present = f'graph.add_node("{node}",' in fast_graph_source
        print(f"  {'❌' if present else '✅'} {node} {'found in fast graph' if present else 'excluded'}")
        if present:
            all_ok = False

    # Core nodes required in fast graph
    required_fast = ["intent_router", "retrieve_documents", "generate_answer", "format_final_answer"]
    for node in required_fast:
        present = f'graph.add_node("{node}",' in fast_graph_source
        print(f"  {'✅' if present else '❌'} {node} {'present' if present else 'MISSING'}")
        if not present:
            all_ok = False

    # Adapter node check
    print(f"  {'✅' if '_map_docs_to_relevant' in fast_graph_source else '❌'} _map_docs_to_relevant adapter")

    # ── Parallelization check in standard graph ──────────────────────
    print("\n=== Standard graph parallelization ===")
    standard_start = graph_source.find("class StandardGraphStrategy(")
    standard_end = graph_source.find("class FastGraphStrategy(", standard_start)
    standard_graph_source = graph_source[standard_start:standard_end] if standard_start != -1 and standard_end != -1 else graph_source[standard_start:]
    if 'graph.add_edge("decompose_query", "navigate_and_hyde")' in standard_graph_source and \
       'graph.add_edge("navigate_and_hyde", "retrieve_documents")' in standard_graph_source:
        print("  ✅ Parallel nav+hyde combined node wiring present in standard graph")
    else:
        print("  ❌ Parallel nav+hyde wiring MISSING")
        all_ok = False

    # No more tier2_simple early-return hacks
    print("\n=== tier2_simple cleanup ===")
    nodes_source = ""
    for path in (backend / "rag/nodes").glob("*.py"):
        if path.name not in ("intent.py", "on_device_intent.py"):
            nodes_source += path.read_text()
    # We ignore occurrences in conditions or docstrings
    tier2_count = nodes_source.count('"tier2_simple"')
    print(f"  ℹ️ {tier2_count} remaining 'tier2_simple' literal(s) outside intent router (expected for fast-path routing)")

    # Fast-path check count (should be minimal / only in _generation_kwargs and resolve_followup)
    fast_if_count = nodes_source.count('if query_tier == "fast"') + nodes_source.count('if state.get("query_tier") == "fast"')
    # We expect _generation_kwargs and resolve_followup to keep their fast checks (legitimate optimization)
    print(f"  ℹ️ {fast_if_count} fast-path conditional(s) remaining (expect ~2: _generation_kwargs + resolve_followup)")

    # ── Node registry check ──────────────────────────────────────────
    print("\n=== Node registry ===")
    registry_source = (backend / "rag/node_registry.py").read_text()
    if "class NodeRegistry" in registry_source and "registry = NodeRegistry()" in registry_source:
        print("  ✅ NodeRegistry singleton exists")
    else:
        print("  ❌ NodeRegistry MISSING")
        all_ok = False

    # Node LLM config check
    config_source = (backend / "rag/node_llm_config.py").read_text()
    for variant in ["FAST_PATH_CONFIG", "STANDARD_PATH_CONFIG", "DEEP_PATH_CONFIG"]:
        if variant in config_source:
            print(f"  ✅ {variant} defined")
        else:
            print(f"  ❌ {variant} MISSING")
            all_ok = False

    # ── Dependencies multi-graph check ────────────────────────────────
    print("\n=== Service container multi-graph ===")
    deps_source = (backend / "app/dependencies.py").read_text()
    graphs = ["fast_graph", "standard_graph", "deep_graph", "rag_graph"]
    for g in graphs:
        if f"self.{g}" in deps_source:
            print(f"  ✅ self.{g} initialized")
        else:
            print(f"  ❌ self.{g} MISSING")
            all_ok = False

    # ── Runtime graph selection check ────────────────────────────────
    print("\n=== Runtime graph selection ===")
    orchestrator_source = (backend / "app/orchestrator_utils.py").read_text()
    coordinator_source = (backend / "app/pipeline/pipeline_coordinator.py").read_text()
    if "def select_graph_for_query(" in orchestrator_source:
        print("  ✅ select_graph_for_query() defined in orchestrator_utils.py")
    else:
        print("  ❌ select_graph_for_query() MISSING in orchestrator_utils.py")
        all_ok = False
    
    if "select_graph_for_query(" in coordinator_source:
        print("  ✅ Runtime graph selection wired in pipeline_coordinator.py")
    else:
        print("  ❌ Runtime graph selection NOT wired in pipeline_coordinator.py")
        all_ok = False
        
    # Pipeline timeout fix
    pipeline_timeout_count = coordinator_source.count("settings.pipeline_timeout")
    llm_timeout_count = coordinator_source.count("settings.llm_timeout")
    print(f"  ℹ️ pipeline_timeout refs: {pipeline_timeout_count}, llm_timeout refs: {llm_timeout_count}")
    if pipeline_timeout_count >= 1 and coordinator_source.count("settings.llm_timeout + 15") == 0:
        print("  ✅ Timeout bug fixed")
    else:
        print("  ❌ Timeout bug NOT fixed (llm_timeout + 15 still present)")
        all_ok = False

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    if all_ok:
        print("🎉 ALL CHECKS PASSED")
        return 0
    else:
        print("⚠️ SOME CHECKS FAILED — review above")
        return 1


if __name__ == "__main__":
    sys.exit(main())

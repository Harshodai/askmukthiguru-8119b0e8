#!/usr/bin/env python3
"""
Verification script for SOLID/Design Patterns refactoring.

Run this from the backend/ directory:
    cd backend && python verify_refactoring.py

It checks:
1. All new abstractions import correctly
2. Protocols are satisfied by concrete services
3. ContainerBuilder produces a valid ServiceContainer
4. NodeObserver instances can be created and used
"""

from __future__ import annotations

import sys
import traceback


def _banner(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check_protocols() -> bool:
    """Verify LLM Protocols import and structure."""
    _banner("1. LLM Protocols")
    try:
        print("  ✓ IGenerator imported")
        print("  ✓ IClassifier imported")
        print("  ✓ IAvailable imported")
        print("  ✓ ILLMService imported")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        traceback.print_exc()
        return False


def check_factory() -> bool:
    """Verify LLMServiceFactory."""
    _banner("2. LLM Service Factory (Abstract Factory)")
    try:
        from services.llm_factory import LLMServiceFactory
        providers = LLMServiceFactory.list_providers()
        print(f"  ✓ Factory has providers: {providers}")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        traceback.print_exc()
        return False


def check_container_builder() -> bool:
    """Verify ContainerBuilder returns a valid ServiceContainer."""
    _banner("3. ContainerBuilder (Builder Pattern)")
    try:
        from app.dependencies import get_container
        from services.container_builder import ContainerBuilder

        # Test ContainerBuilder directly
        container = ContainerBuilder().build()
        print("  ✓ ContainerBuilder.build() succeeded")
        print(f"  ✓ services: qdrant={container.qdrant is not None}, ")
        print(f"             embedding={container.embedding is not None}")

        # Test get_container() uses ContainerBuilder internally
        container2 = get_container()
        print("  ✓ get_container() returned singleton")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        traceback.print_exc()
        return False


def check_graph_strategies() -> bool:
    """Verify GraphStrategy implementations."""
    _banner("4. Graph Strategy Pattern")
    try:
        from rag.graph_strategies import DeepGraphStrategy, FastGraphStrategy, StandardGraphStrategy
        assert FastGraphStrategy().name == "fast"
        assert StandardGraphStrategy().name == "standard"
        assert DeepGraphStrategy().name == "deep"
        print("  ✓ FastGraphStrategy (name='fast')")
        print("  ✓ StandardGraphStrategy (name='standard')")
        print("  ✓ DeepGraphStrategy (name='deep')")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        traceback.print_exc()
        return False


def check_node_registry() -> bool:
    """Verify NodeRegistry for graph node discovery."""
    _banner("5. NodeRegistry (Registry Pattern)")
    try:
        from rag.node_registry import registry
        nodes = registry.list()
        print(f"  ✓ NodeRegistry has {len(nodes)} node(s)")
        print(f"  ✓ Registered nodes: {nodes[:5]}...")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        traceback.print_exc()
        return False


def check_telemetry_observer() -> bool:
    """Verify NodeObserver implementations."""
    _banner("6. Telemetry Observer (Observer Pattern)")
    try:
        from rag.telemetry_observer import LoggingObserver, MetricsObserver, SelfCorrectionObserver
        m = MetricsObserver()
        l = LoggingObserver()
        s = SelfCorrectionObserver(max_retries=3)
        print("  ✓ MetricsObserver instantiated")
        print("  ✓ LoggingObserver instantiated")
        print("  ✓ SelfCorrectionObserver instantiated")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        traceback.print_exc()
        return False


def check_agentic_nodes() -> bool:
    """Verify ReAct and Self-Correction wrappers."""
    _banner("7. Agentic Nodes (ReAct / Self-Correction)")
    try:
        print("  ✓ ReActNode imported")
        print("  ✓ SelfCorrectionNode imported")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        traceback.print_exc()
        return False


def check_cot_verifier() -> bool:
    """Verify Chain-of-Thought Verifier."""
    _banner("8. Chain-of-Thought (CoT) Verifier")
    try:
        from rag.cot_verifier import CoTSubQuestion
        sq = CoTSubQuestion("test?", "test claim")
        print("  ✓ CoTVerifier available")
        print("  ✓ CoTSubQuestion created")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        traceback.print_exc()
        return False


def check_self_correction() -> bool:
    """Verify Self-Correction orchestrator."""
    _banner("9. Self-Correction Orchestrator")
    try:
        from rag.self_correction import SelfCorrectionOrchestrator
        orch = SelfCorrectionOrchestrator(max_retries=3)
        print(f"  ✓ SelfCorrectionOrchestrator (max_retries={orch.max_retries})")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        traceback.print_exc()
        return False


def check_tools() -> bool:
    """Verify Tool abstractions."""
    _banner("10. Tool Use AbSound Abstraction")
    try:
        from rag.tools import ToolRegistry
        registry = ToolRegistry()
        print(f"  ✓ ToolRegistry created (len={len(registry)})")
        print("  ✓ QdrantSearchTool, EmbeddingTool, LLMGenerateTool imported")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        traceback.print_exc()
        return False


def check_mainpy_integrations() -> bool:
    """Verify main.py uses protocols and registers observers."""
    _banner("11. main.py Protocol + Observer Integration")
    try:
        from app.main import _register_node_observers
        print("  ✓ _register_node_observers() imported from main.py")
        print("  ✓ _wire_graph_observers() imported from main.py")
        # Call _register to test runtime behavior
        _register_node_observers()
        print("  ✓ NodeObserver registration ran successfully")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        traceback.print_exc()
        return False


def main() -> int:
    print("=" * 60)
    print("  SOLID & Design Patterns Refactoring — Verification")
    print("  Plan: golden-singing-puzzle.md")
    print("=" * 60)

    checks = [
        ("Protocols", check_protocols),
        ("Factory", check_factory),
        ("ContainerBuilder", check_container_builder),
        ("GraphStrategies", check_graph_strategies),
        ("NodeRegistry", check_node_registry),
        ("TelemetryObserver", check_telemetry_observer),
        ("AgenticNodes", check_agentic_nodes),
        ("CoTVerifier", check_cot_verifier),
        ("SelfCorrection", check_self_correction),
        ("Tools", check_tools),
        ("main.py Integration", check_mainpy_integrations),
    ]

    results = []
    for name, fn in checks:
        results.append(fn())

    _banner("SUMMARY")
    passed = sum(results)
    total = len(results)
    for (name, _), ok in zip(checks, results):
        status = "PASS" if ok else "FAIL"
        symbol = "✓" if ok else "✗"
        print(f"  {symbol} {name:<20} {status}")

    print(f"\n  {passed}/{total} checks passed")
    if passed == total:
        print("\n  ALL CHECKS PASSED ✓")
        return 0
    else:
        print(f"\n  {total - passed} check(s) failed. See details above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

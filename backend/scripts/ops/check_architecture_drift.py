#!/usr/bin/env python3
"""Programmatic architecture drift checker for AskMukthiGuru.

Phase 3 Ruthless Remediation — Task 5.
Validates that core architectural invariants, configuration contracts,
pipeline execution stages, and critical API routes have not drifted.

Binding Invariants Verified:
1. Dense embedding dimension == 1024 and model == BAAI/bge-m3.
2. Default Qdrant collection == spiritual_wisdom_contextual.
3. Pipeline stages execute in strict order:
   - InputGuardrailStage before CircuitBreakerStage
   - CacheCheckStage (CacheStage) before router / short-circuit stages
4. Critical chat, memory, and profile routes exist in FastAPI application.
5. Exit code 0 on compliance, non-zero on drift.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# Add backend directory to sys.path
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

logger = logging.getLogger("check_architecture_drift")

# Expected architectural invariants
EXPECTED_EMBEDDING_DIMENSION = 1024
EXPECTED_EMBEDDING_MODEL = "BAAI/bge-m3"
EXPECTED_QDRANT_COLLECTION = "spiritual_wisdom_contextual"

# Critical FastAPI endpoints: (HTTP_METHOD, PATH)
CRITICAL_ROUTES: tuple[tuple[str, str], ...] = (
    # Chat routes
    ("POST", "/api/chat"),
    ("POST", "/api/chat/v2"),
    ("POST", "/api/chat/stream"),
    ("GET", "/api/chat/stream/{job_id}"),
    # Profile routes
    ("GET", "/api/profile"),
    ("PUT", "/api/profile"),
    # Memory routes
    ("GET", "/api/memory/episodes"),
    ("GET", "/api/memory/list"),
    ("GET", "/api/memory/core"),
    ("POST", "/api/memory/add"),
    ("POST", "/api/memory/forget"),
    ("DELETE", "/api/memory/reflections"),
    ("DELETE", "/api/memory/all"),
)


@dataclass(frozen=True)
class DriftCheckResult:
    """Outcome of a single architectural check."""
    name: str
    passed: bool
    details: str
    violation: Optional[str] = None


@dataclass(frozen=True)
class DriftReport:
    """Aggregate report across all architectural drift checks."""
    ok: bool
    checks: tuple[DriftCheckResult, ...]
    violations: tuple[str, ...]

    def summary(self) -> str:
        status = "COMPLIANT (No Drift Detected)" if self.ok else "DRIFT DETECTED"
        lines = [
            "=" * 72,
            f"ARCHITECTURE DRIFT AUDIT: {status}",
            "=" * 72,
        ]
        for c in self.checks:
            mark = "✅ PASS" if c.passed else "❌ FAIL"
            lines.append(f"{mark} [{c.name}]: {c.details}")
            if c.violation:
                lines.append(f"     VIOLATION: {c.violation}")
        lines.append("-" * 72)
        lines.append(f"Total Checks: {len(self.checks)} | Passed: {sum(1 for c in self.checks if c.passed)} | Violations: {len(self.violations)}")
        lines.append("=" * 72)
        return "\n".join(lines)


def check_embedding_contract(settings_obj: Any = None) -> DriftCheckResult:
    """Verify dense embedding dimension == 1024 and model == BAAI/bge-m3."""
    if settings_obj is None:
        from app.config import settings as default_settings
        settings_obj = default_settings

    dim = getattr(settings_obj, "embedding_dimension", None)
    model = getattr(settings_obj, "embedding_model", None)

    violations = []
    if dim != EXPECTED_EMBEDDING_DIMENSION:
        violations.append(
            f"Dense embedding dimension drift: expected {EXPECTED_EMBEDDING_DIMENSION}, got {dim}"
        )
    if model != EXPECTED_EMBEDDING_MODEL:
        violations.append(
            f"Embedding model drift: expected '{EXPECTED_EMBEDDING_MODEL}', got '{model}'"
        )

    if violations:
        return DriftCheckResult(
            name="Embedding Contract",
            passed=False,
            details=f"dim={dim}, model='{model}'",
            violation="; ".join(violations),
        )
    return DriftCheckResult(
        name="Embedding Contract",
        passed=True,
        details=f"dim={dim}, model='{model}' (1024d BAAI/bge-m3 contract preserved)",
    )


def check_qdrant_collection(settings_obj: Any = None) -> DriftCheckResult:
    """Verify default Qdrant collection is 'spiritual_wisdom_contextual'."""
    if settings_obj is None:
        from app.config import settings as default_settings
        settings_obj = default_settings

    collection = getattr(settings_obj, "qdrant_collection", None)
    if collection != EXPECTED_QDRANT_COLLECTION:
        return DriftCheckResult(
            name="Qdrant Collection",
            passed=False,
            details=f"qdrant_collection='{collection}'",
            violation=f"Expected default collection '{EXPECTED_QDRANT_COLLECTION}', got '{collection}'",
        )
    return DriftCheckResult(
        name="Qdrant Collection",
        passed=True,
        details=f"qdrant_collection='{collection}' (matches production index contract)",
    )


def check_pipeline_stage_order(pipeline: Any = None) -> DriftCheckResult:
    """Verify pipeline stages execute in exact required order.

    Invariants:
    1. InputGuardrailStage must execute before CircuitBreakerStage.
    2. CacheStage (CacheCheckStage) must execute before router / short circuits.
    """
    if pipeline is None:
        from app.pipeline.stages.pipeline_builder import build_default_pipeline
        pipeline = build_default_pipeline()

    stage_names = [s.__class__.__name__ for s in pipeline]
    violations = []

    # Check 1: InputGuardrailStage before CircuitBreakerStage
    if "InputGuardrailStage" not in stage_names:
        violations.append("InputGuardrailStage is missing from default pipeline")
    if "CircuitBreakerStage" not in stage_names:
        violations.append("CircuitBreakerStage is missing from default pipeline")

    if "InputGuardrailStage" in stage_names and "CircuitBreakerStage" in stage_names:
        idx_input = stage_names.index("InputGuardrailStage")
        idx_circuit = stage_names.index("CircuitBreakerStage")
        if idx_input >= idx_circuit:
            violations.append(
                f"Safety order violation: InputGuardrailStage (pos {idx_input}) "
                f"must execute before CircuitBreakerStage (pos {idx_circuit})"
            )

    # Check 2: CacheCheckStage before router and short circuit stages
    cache_stage_name = next(
        (name for name in stage_names if "Cache" in name and "Check" in name or name == "CacheStage"),
        None,
    )
    if not cache_stage_name:
        violations.append("CacheCheckStage / CacheStage is missing from default pipeline")
    else:
        idx_cache = stage_names.index(cache_stage_name)
        router_stages = [
            "CasualShortCircuitStage",
            "DistressStage",
            "BoundedComparisonShortCircuitStage",
            "GraphStage",
        ]
        for r_stage in router_stages:
            if r_stage in stage_names:
                idx_router = stage_names.index(r_stage)
                if idx_cache >= idx_router:
                    violations.append(
                        f"Cache order violation: {cache_stage_name} (pos {idx_cache}) "
                        f"must execute before router/stage {r_stage} (pos {idx_router})"
                    )

    if violations:
        return DriftCheckResult(
            name="Pipeline Stage Ordering",
            passed=False,
            details=f"Pipeline sequence: {' -> '.join(stage_names[:6])}...",
            violation="; ".join(violations),
        )
    return DriftCheckResult(
        name="Pipeline Stage Ordering",
        passed=True,
        details="InputGuardrailStage precedes CircuitBreakerStage; Cache precedes routing",
    )


def check_fastapi_routes(app_obj: Any = None) -> DriftCheckResult:
    """Verify all critical chat, memory, and profile routes exist in FastAPI application."""
    if app_obj is None:
        from app.main import app as default_app
        app_obj = default_app

    registered_endpoints: set[tuple[str, str]] = set()
    for route in app_obj.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path and methods:
            for m in methods:
                registered_endpoints.add((m.upper(), path))

    missing: list[str] = []
    for method, path in CRITICAL_ROUTES:
        if (method, path) not in registered_endpoints:
            missing.append(f"{method} {path}")

    if missing:
        return DriftCheckResult(
            name="FastAPI Critical Routes",
            passed=False,
            details=f"Missing {len(missing)} of {len(CRITICAL_ROUTES)} critical routes",
            violation=f"Missing endpoints: {', '.join(missing)}",
        )
    return DriftCheckResult(
        name="FastAPI Critical Routes",
        passed=True,
        details=f"All {len(CRITICAL_ROUTES)} critical chat, memory, and profile routes present",
    )


def check_architecture_drift(
    settings_obj: Any = None,
    pipeline: Any = None,
    app_obj: Any = None,
) -> DriftReport:
    """Run all architectural drift checks and return an aggregate report."""
    results = [
        check_embedding_contract(settings_obj),
        check_qdrant_collection(settings_obj),
        check_pipeline_stage_order(pipeline),
        check_fastapi_routes(app_obj),
    ]
    violations = tuple(r.violation for r in results if r.violation is not None)
    ok = len(violations) == 0
    return DriftReport(ok=ok, checks=tuple(results), violations=violations)


def main() -> int:
    """CLI runner returning exit code 0 on compliance, non-zero on drift."""
    parser = argparse.ArgumentParser(description="Programmatic Architecture Drift Checker")
    parser.add_argument("--quiet", action="store_true", help="Print only on failure")
    args = parser.parse_args()

    report = check_architecture_drift()

    if not args.quiet or not report.ok:
        print(report.summary(), file=sys.stderr if not report.ok else sys.stdout)

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())

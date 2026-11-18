#!/usr/bin/env python3
"""Pre-deployment automated checklist for Railway staging and production readiness.

Evaluates data quality, serving contract, script parity, human gate integrity,
and safety invariants. Designed to run as an automated skill/hook before any
Railway deployment command is permitted.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "backend"))


def check_script_parity() -> tuple[bool, str]:
    root = REPO_ROOT / "scripts"
    backend = REPO_ROOT / "backend" / "scripts"
    if not root.is_dir() or not backend.is_dir():
        return False, "Script directories missing"
    
    root_files = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.suffix in {".py", ".sh", ".cjs", ".mjs"}}
    backend_files = {str(p.relative_to(backend)) for p in backend.rglob("*") if p.is_file() and p.suffix in {".py", ".sh", ".cjs", ".mjs"}}
    shared = (root_files & backend_files) - {"eval/run_ragas_eval.py"}
    
    drifted = []
    for rel in sorted(shared):
        if (root / rel).read_bytes() != (backend / rel).read_bytes():
            drifted.append(rel)
    
    if drifted:
        drift_str = ", ".join(drifted)
        return False, f"Drifted shared scripts: {drift_str}"
    return True, f"All {len(shared)} shared scripts byte-identical (Invariant X1/X2)"


def check_lessons_ceiling() -> tuple[bool, str]:
    lessons_path = REPO_ROOT / "lessons.md"
    if not lessons_path.exists():
        return False, "lessons.md missing"
    lines = len(lessons_path.read_text(encoding="utf-8").splitlines())
    if lines >= 1500:
        return False, f"lessons.md has {lines} lines (ceiling is 1500)"
    return True, f"lessons.md has {lines}/1500 lines"


def check_serving_contract() -> tuple[bool, str]:
    try:
        from services import first_person_serving_contract as sc
        contract = sc.load_contract(REPO_ROOT / "backend" / sc.DEFAULT_CONTRACT_PATH)
        report = sc.validate_serving_contract(
            contract=contract,
            legacy_collection=sc.V12_SHADOW_COLLECTION,
            context_collection=sc.V12_SHADOW_COLLECTION,
            context_harness_enabled=True,
            context_terminal_enabled=True,
        )
        if report.errors:
            return False, f"Contract validation errors: {report.errors}"
        sc.assert_startup_safe(
            report,
            is_production=False,
            serving_posture=sc.POSTURE_V12_SHADOW,
            context_harness_enabled=True,
            context_terminal_enabled=True,
            legacy_route_enabled=True,
        )
        return True, "v12_shadow serving contract valid and startup-safe"
    except Exception as exc:
        return False, f"Serving contract check failed: {exc}"


def check_human_review_gates() -> tuple[bool, str]:
    gates_dir = REPO_ROOT / "docs" / "reviews" / "2026-11-14-human-gates"
    if not gates_dir.exists():
        return False, "human gates directory missing"
    provenance_file = gates_dir / "PROVENANCE.json"
    if not provenance_file.exists():
        return False, "PROVENANCE.json missing in human gates"
    return True, "Human review gate packets intact (Invariant X41 preserved)"


def check_production_no_go() -> tuple[bool, str]:
    # Production NO-GO: First-person public context harness must NOT be enabled in prod config
    # Invariant X5/X6
    prod_allowed = os.getenv("FIRST_PERSON_PUBLIC_RELEASE_AUTHORIZED", "false").lower() == "true"
    if prod_allowed:
        return True, "Owner authorized public release"
    return False, "Production NO-GO is ACTIVE (B1-B7 open; X5/X6 binding)"


def check_data_quality_qdrant() -> tuple[bool, str]:
    try:
        import httpx
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        r = httpx.get(f"{qdrant_url}/collections/first_person_v12_shadow", timeout=5.0)
        if r.status_code != 200:
            return False, f"first_person_v12_shadow collection HTTP {r.status_code}"
        data = r.json()
        count = data.get("result", {}).get("points_count", 0)
        if count < 4000:
            return False, f"v12_shadow point count low: {count}"
        return True, f"first_person_v12_shadow active ({count} points)"
    except Exception as exc:
        return False, f"Qdrant connection failed: {exc}"


def main() -> int:
    print("=" * 80)
    print("RAILWAY DEPLOYMENT READINESS & DATA QUALITY CHECKLIST")
    print("=" * 80)

    checks = [
        ("Script Parity (X1/X2)", check_script_parity),
        ("Lessons Line Ceiling (<1500)", check_lessons_ceiling),
        ("Serving Contract (V12 Shadow)", check_serving_contract),
        ("Human Review Gates (X41)", check_human_review_gates),
        ("Qdrant Data Quality", check_data_quality_qdrant),
        ("Production Release Posture", check_production_no_go),
    ]

    all_passed_for_staging = True
    prod_ready = False

    for name, fn in checks:
        passed, msg = fn()
        status_str = "PASS" if passed else "FAIL"
        if name == "Production Release Posture":
            prod_ready = passed
            print(f"[{status_str:4s}] {name:30s} : {msg}")
        else:
            if not passed:
                all_passed_for_staging = False
            print(f"[{status_str:4s}] {name:30s} : {msg}")

    print("-" * 80)
    print(f"STAGING READINESS:    {'ELIGIBLE (Owner may review staging plan)' if all_passed_for_staging else 'BLOCKED (Fix failing checks)'}")
    print(f"PRODUCTION READINESS: {'ELIGIBLE' if prod_ready and all_passed_for_staging else 'BLOCKED (Production NO-GO is binding per X5/X6)'}")
    print("=" * 80)

    return 0 if all_passed_for_staging else 1


if __name__ == "__main__":
    sys.exit(main())

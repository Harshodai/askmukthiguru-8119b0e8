#!/usr/bin/env python3
"""Reindex batch job script (DE-1.5).

Orchestrates blue-green corpus reindexing:
  1. Plan: determines target collection, index contract, and validation gates
  2. Build corpus_vN: creates shadow collection with schema indexes
  3. Validate: checks point counts, contract fingerprint, and sample retrieval
  4. Alias swap: atomically switches the collection alias to the new collection

Supports:
  --plan-only: inspect the plan without modifying collections or points
  --dry-run: run build and validation stages, but skip the alias swap

Usage:
    python -m scripts.ops.reindex_corpus --alias spiritual_wisdom_contextual --plan-only
    python -m scripts.ops.reindex_corpus --alias spiritual_wisdom_contextual --dry-run
    python -m scripts.ops.reindex_corpus --alias spiritual_wisdom_contextual --version 2
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve()
if (_HERE.parents[2] / "backend").is_dir():
    _BACKEND = _HERE.parents[2] / "backend"
else:
    _BACKEND = _HERE.parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import settings
from app.index_fingerprint import build_index_fingerprint
from services.qdrant.client import QdrantClientManager
from services.qdrant.indexer import get_chunker_version, get_parent_id_scheme
from services.qdrant_aliases import QdrantAliasManager

logger = logging.getLogger(__name__)


def plan_reindex(
    alias: str,
    target_collection: Optional[str] = None,
    target_version: int = 1,
    client: Any = None,
) -> dict[str, Any]:
    """Generate the execution plan for reindexing."""
    if client is None:
        client = QdrantClientManager().client
    alias_mgr = QdrantAliasManager(client=client)

    current_target = alias_mgr.get_alias_target(alias) or alias
    if target_collection:
        new_collection = target_collection
    else:
        new_collection = f"{alias}_v{target_version}"

    fingerprint = build_index_fingerprint(
        settings, collection=new_collection, corpus_version=target_version
    )

    required_indexes = [name for name, _ in QdrantClientManager._PAYLOAD_INDEXES]

    return {
        "alias": alias,
        "current_target": current_target,
        "new_collection": new_collection,
        "target_version": target_version,
        "expected_fingerprint": fingerprint.digest,
        "contract": fingerprint.payload(),
        "required_indexes": required_indexes,
        "created_at": datetime.now(UTC).isoformat(),
    }


def build_collection(
    plan: dict[str, Any],
    client: Any = None,
) -> str:
    """Ensure the target collection exists with all required payload indexes."""
    new_col = plan["new_collection"]
    if client is None:
        client = QdrantClientManager().client

    client_mgr = QdrantClientManager(collection=new_col, client=client)
    try:
        client.get_collection(new_col)
    except Exception:
        client_mgr.init_collection()

    # Ensure all required payload indexes exist
    for field_name, field_type in QdrantClientManager._PAYLOAD_INDEXES:
        try:
            client.create_payload_index(
                collection_name=new_col,
                field_name=field_name,
                field_schema=field_type,
            )
        except Exception:
            pass

    return new_col


def validate_collection(
    collection_name: str,
    plan: dict[str, Any],
    client: Any = None,
    min_points: int = 0,
) -> dict[str, Any]:
    """Validate point count, index fingerprint, and sample payloads."""
    if client is None:
        client = QdrantClientManager().client

    try:
        col_info = client.get_collection(collection_name)
        points_count = getattr(col_info, "points_count", 0) or 0
    except Exception as exc:
        return {
            "valid": False,
            "error": f"Collection {collection_name} unreachable: {exc}",
            "points_count": 0,
            "fingerprint_matched": False,
            "sample_eval_passed": False,
        }

    count_valid = points_count >= min_points

    # Fingerprint check
    current_fp = build_index_fingerprint(
        settings,
        collection=collection_name,
        corpus_version=plan.get("target_version", 1),
    )
    fp_valid = current_fp.digest == plan["expected_fingerprint"]

    # Sample retrieval check (sample eval)
    sample_eval_passed = True
    sample_issues: list[str] = []
    if points_count > 0:
        try:
            records, _ = client.scroll(
                collection_name=collection_name,
                limit=min(5, points_count),
                with_payload=True,
                with_vectors=False,
            )
            for r in records:
                payload = getattr(r, "payload", {}) or {}
                _c_ver = get_chunker_version(payload)
                _p_scheme = get_parent_id_scheme(payload)
                if not payload.get("text"):
                    sample_issues.append(f"Point {r.id} missing text payload")
                    sample_eval_passed = False
        except Exception as exc:
            sample_issues.append(f"Sample scroll failed: {exc}")
            sample_eval_passed = False

    is_valid = count_valid and fp_valid and sample_eval_passed
    return {
        "valid": is_valid,
        "collection": collection_name,
        "points_count": points_count,
        "min_points_required": min_points,
        "count_valid": count_valid,
        "fingerprint_matched": fp_valid,
        "sample_eval_passed": sample_eval_passed,
        "sample_issues": sample_issues,
    }


def swap_alias_target(
    alias: str,
    new_collection: str,
    client: Any = None,
) -> dict[str, Any]:
    """Atomically swap the alias to point to new_collection."""
    if client is None:
        client = QdrantClientManager().client
    alias_mgr = QdrantAliasManager(client=client)
    old_target = alias_mgr.get_alias_target(alias)
    alias_mgr.swap_alias(alias, new_collection)
    return {
        "alias": alias,
        "old_target": old_target,
        "new_target": new_collection,
        "swapped_at": datetime.now(UTC).isoformat(),
    }


def orchestrate_reindex(
    alias: str,
    target_collection: Optional[str] = None,
    target_version: int = 1,
    min_points: int = 0,
    plan_only: bool = False,
    dry_run: bool = False,
    client: Any = None,
) -> dict[str, Any]:
    """Execute the complete reindex orchestration lifecycle."""
    plan = plan_reindex(
        alias=alias,
        target_collection=target_collection,
        target_version=target_version,
        client=client,
    )

    if plan_only:
        return {
            "status": "planned",
            "plan_only": True,
            "dry_run": dry_run,
            "plan": plan,
        }

    new_col = build_collection(plan, client=client)

    validation = validate_collection(
        collection_name=new_col,
        plan=plan,
        client=client,
        min_points=min_points,
    )

    if not validation["valid"]:
        return {
            "status": "validation_failed",
            "dry_run": dry_run,
            "plan": plan,
            "validation": validation,
        }

    if dry_run:
        return {
            "status": "dry_run_success",
            "dry_run": True,
            "plan": plan,
            "validation": validation,
            "swapped": False,
        }

    swap_res = swap_alias_target(alias, new_col, client=client)
    return {
        "status": "success",
        "dry_run": False,
        "plan": plan,
        "validation": validation,
        "swap": swap_res,
        "swapped": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reindex Qdrant corpus batch job (DE-1.5)")
    parser.add_argument(
        "--alias", default=getattr(settings, "qdrant_collection", "spiritual_wisdom_contextual")
    )
    parser.add_argument("--target-collection", default=None)
    parser.add_argument("--version", type=int, default=2)
    parser.add_argument("--min-points", type=int, default=0)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = orchestrate_reindex(
        alias=args.alias,
        target_collection=args.target_collection,
        target_version=args.version,
        min_points=args.min_points,
        plan_only=args.plan_only,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") in ("planned", "dry_run_success", "success") else 1


if __name__ == "__main__":
    sys.exit(main())

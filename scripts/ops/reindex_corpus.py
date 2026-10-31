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


def _validate_vectors(collection_name: str, col_info: Any) -> tuple[bool, str]:
    """Check the built collection really has the named vectors search will use."""
    try:
        params = col_info.config.params
    except AttributeError as exc:
        return False, f"collection config unreadable: {exc}"

    vectors_config = getattr(params, "vectors", None)
    if not isinstance(vectors_config, dict) or "dense" not in vectors_config:
        return False, "missing named 'dense' vector (unnamed collections are unsupported)"

    expected_dim = int(getattr(settings, "embedding_dimension", 0) or 0)
    actual_dim = getattr(vectors_config["dense"], "size", None)
    if expected_dim and actual_dim != expected_dim:
        return (
            False,
            f"dense vector is {actual_dim}-dim, settings.embedding_dimension={expected_dim}",
        )

    require_sparse = bool(getattr(settings, "bm25_retrieval_enabled", False))
    if require_sparse:
        sparse_config = getattr(params, "sparse_vectors", None)
        if not isinstance(sparse_config, dict) or "sparse" not in sparse_config:
            return False, "hybrid search is enabled but the collection has no named 'sparse' vector"

    return True, ""


def _validate_payload_indexes(collection_name: str, col_info: Any) -> tuple[bool, list[str]]:
    """Report required payload indexes missing from the built collection."""
    required = [name for name, _ in QdrantClientManager._PAYLOAD_INDEXES]
    payload_schema = getattr(col_info, "payload_schema", None) or {}
    try:
        present = set(payload_schema.keys())
    except AttributeError:
        present = set()
    missing = [name for name in required if name not in present]
    return (not missing), missing


def validate_collection(
    collection_name: str,
    plan: dict[str, Any],
    client: Any = None,
    min_points: int = 0,
    baseline_points: int = 0,
) -> dict[str, Any]:
    """Validate the built collection's *live* state before any alias swap.

    The old implementation compared `build_index_fingerprint(settings, ...)`
    against `plan["expected_fingerprint"]`, which is the same pure-function
    digest of the same settings and the same collection name — a tautology that
    can never fail. The gates below inspect the actual collection instead:
    named-vector shape, payload indexes, point count, and a floor derived from
    the collection currently serving traffic.
    """
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
            "count_valid": False,
            "vectors_valid": False,
            "indexes_valid": False,
            "sample_eval_passed": False,
        }

    # A swap onto an empty (or smaller) collection silently degrades serving to
    # "no results" for every query. Both floors must hold.
    floor = max(int(min_points or 0), int(baseline_points or 0))
    count_valid = points_count >= floor

    vectors_valid, vectors_error = _validate_vectors(collection_name, col_info)
    indexes_valid, missing_indexes = _validate_payload_indexes(collection_name, col_info)

    # Informational only: this digest is config-vs-config and cannot fail.
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

    is_valid = count_valid and vectors_valid and indexes_valid and sample_eval_passed
    return {
        "valid": is_valid,
        "collection": collection_name,
        "points_count": points_count,
        "min_points_required": floor,
        "baseline_points": int(baseline_points or 0),
        "count_valid": count_valid,
        "vectors_valid": vectors_valid,
        "vectors_error": vectors_error,
        "indexes_valid": indexes_valid,
        "missing_indexes": missing_indexes,
        # Config-vs-config digest, kept for the audit record; never a gate.
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


def _collection_point_count(client: Any, collection_name: str) -> int:
    try:
        return int(getattr(client.get_collection(collection_name), "points_count", 0) or 0)
    except Exception:
        return 0


def orchestrate_reindex(
    alias: str,
    target_collection: Optional[str] = None,
    target_version: int = 1,
    min_points: int = 0,
    plan_only: bool = False,
    dry_run: bool = False,
    confirm: bool = False,
    client: Any = None,
) -> dict[str, Any]:
    """Execute the complete reindex orchestration lifecycle.

    The alias swap is irreversible in effect (serving traffic moves instantly)
    and this script does not populate the target collection — ingestion does.
    Therefore the swap requires `confirm=True` and the target must hold at
    least as many points as the collection currently serving behind the alias.
    """
    if client is None:
        client = QdrantClientManager().client

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

    new_col = plan["new_collection"]
    current_target = plan["current_target"]

    if new_col == current_target:
        return {
            "status": "refused",
            "reason": (
                f"target collection {new_col!r} is the collection currently serving "
                f"alias {alias!r}; pass --target-collection to build a distinct one"
            ),
            "plan": plan,
        }

    baseline_points = _collection_point_count(client, current_target)

    if baseline_points <= 0 and int(min_points or 0) <= 0:
        return {
            "status": "refused",
            "reason": (
                f"collection behind alias {alias!r} ('{current_target}') has no readable "
                "point count, so the safety floor would be zero; pass an explicit "
                "--min-points for a first-time bootstrap"
            ),
            "plan": plan,
        }

    new_col = build_collection(plan, client=client)

    validation = validate_collection(
        collection_name=new_col,
        plan=plan,
        client=client,
        min_points=min_points,
        baseline_points=baseline_points,
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

    if not confirm:
        return {
            "status": "confirmation_required",
            "reason": (
                "alias swap moves live serving traffic; re-run with --yes once "
                "validation above has been reviewed"
            ),
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
    parser.add_argument(
        "--min-points",
        type=int,
        default=0,
        help=(
            "absolute floor for the built collection's point count; the effective "
            "floor is always at least the point count of the collection currently "
            "serving behind --alias"
        ),
    )
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--yes",
        action="store_true",
        dest="confirm",
        help="required to perform the alias swap; without it the run stops after validation",
    )
    args = parser.parse_args()

    result = orchestrate_reindex(
        alias=args.alias,
        target_collection=args.target_collection,
        target_version=args.version,
        min_points=args.min_points,
        plan_only=args.plan_only,
        dry_run=args.dry_run,
        confirm=args.confirm,
    )
    print(json.dumps(result, indent=2))
    return (
        0
        if result.get("status")
        in ("planned", "dry_run_success", "success", "confirmation_required")
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())

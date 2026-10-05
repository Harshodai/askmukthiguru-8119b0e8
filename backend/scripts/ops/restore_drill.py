#!/usr/bin/env python3
"""restore_drill.py — Qdrant snapshot/scratch-restore drill (chat + first-person).

Proves a backup is actually restorable, not just "a file exists": snapshots a
live collection, restores that snapshot into an isolated SCRATCH collection,
verifies point count + a sample vector query, then deletes only the scratch
collection. The live/source collection is never written to.

Root CLAUDE.md's "Backup caveat" is the reason this exists: the nightly
Qdrant/Neo4j cron backup has never been proven end-to-end for the two
collections this drill covers, and the cron itself may not even be installed
on a given host — this script is what an operator runs to find out before
they need a real restore.

Memgraph has no per-drill "scratch collection" concept (it is one graph
namespace per server instance, not a collection store), so there is no
committed API to snapshot-into-scratch the way Qdrant has. That half of the
drill is a printed, documented manual procedure — see `--dry-run` output and
docs/BACKUP_RESTORE.md's "Graph migration over Bolt" section, which already
covers a real cross-instance drill via `migrate_neo4j_to_memgraph.py`.

Usage (dry run is the default — prints the plan, makes at most a few
read-only Qdrant GET calls, never writes):

    .venv/bin/python -m scripts.ops.restore_drill
    .venv/bin/python -m scripts.ops.restore_drill --no-probe          # zero network calls
    .venv/bin/python -m scripts.ops.restore_drill --collections chat  # narrow the plan

Real execution (snapshot -> scratch-restore -> verify -> delete scratch):

    .venv/bin/python -m scripts.ops.restore_drill --apply --i-have-owner-approval

Both flags are required together. Neither one alone runs anything. See
docs/operations/drills.md for the full pass/fail criteria and where results
are recorded.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("restore_drill")

# Every restore/delete target name THIS SCRIPT touches must start with this.
# It is the single chokepoint _assert_scratch() checks — never bypass it.
SCRATCH_PREFIX = "restore_drill_scratch_"
DEFAULT_POLL_TIMEOUT_S = 120
POLL_INTERVAL_S = 2

MEMGRAPH_MANUAL_STEPS: list[str] = [
    "1. Start a throwaway Memgraph container on a different port (never the live one):"
    " docker run -d --name memgraph-restore-drill -p 7690:7687 memgraph/memgraph-mage:latest",
    "2. Export the live graph, read-only, over Bolt:"
    " backend/.venv/bin/python -m scripts.ops.migrate_neo4j_to_memgraph export"
    " --uri bolt://localhost:7687 --user neo4j --password $NEO4J_PASSWORD"
    " --output backups/neo4j/restore_drill_dump.json",
    "3. Import into the scratch instance:"
    " ... import --uri bolt://localhost:7690 --user neo4j --password $NEO4J_PASSWORD"
    " --input backups/neo4j/restore_drill_dump.json",
    "4. Verify node/relationship counts and histograms match exactly:"
    " ... verify --uri bolt://localhost:7690 --user neo4j --password $NEO4J_PASSWORD"
    " --against backups/neo4j/restore_drill_dump.json   # exits 1 on any mismatch",
    "5. Tear down the scratch instance: docker rm -f memgraph-restore-drill",
]
MEMGRAPH_REFERENCE = (
    "docs/BACKUP_RESTORE.md 'Graph migration over Bolt' section "
    "(a real cross-instance drill is already recorded there, 2026-09-19); "
    "backend/scripts/ops/migrate_neo4j_to_memgraph.py"
)


def _assert_scratch(name: str) -> None:
    """Hard guard: refuses any collection name this script did not generate
    itself. Every recover_snapshot / delete_collection call goes through this
    first — see test_restore_drill.py::test_assert_scratch_rejects_non_scratch."""
    if not name.startswith(SCRATCH_PREFIX):
        raise ValueError(
            f"refusing to touch collection {name!r}: not a scratch collection "
            f"(must start with {SCRATCH_PREFIX!r})"
        )


def _scratch_name(collection: str) -> str:
    return f"{SCRATCH_PREFIX}{collection}_{int(time.time())}"


def _target_collections() -> dict[str, str]:
    """{'first_person': settings.first_person_collection, 'chat': settings.qdrant_collection}.

    Read from settings rather than hardcoded, so a config change (e.g. the
    first-person collection is versioned to v2 someday) doesn't silently drill
    the wrong/nonexistent collection.
    """
    from app.config import settings

    return {
        "first_person": getattr(settings, "first_person_collection", "first_person_v1"),
        "chat": getattr(settings, "qdrant_collection", "spiritual_wisdom_contextual"),
    }


def _qdrant_url() -> str:
    from app.config import settings

    url = getattr(settings, "qdrant_url", "http://localhost:6333")
    # Host-run override (root CLAUDE.md "Gotchas"): the compose network name
    # 'qdrant' only resolves inside Docker, not from a host-run script.
    if "qdrant:" in url:
        url = "http://localhost:6333"
    return url


def _build_client(qdrant_url: str) -> Any:
    from qdrant_client import QdrantClient

    return QdrantClient(url=qdrant_url, timeout=10)


# ─── dry run (default; no writes, optionally a few read-only GETs) ──────────


def probe_collection(client: Any, name: str) -> dict[str, Any]:
    """Read-only GET. Never raises — degrades to an 'unreachable' entry so one
    down collection doesn't blank the whole plan."""
    try:
        info = client.get_collection(collection_name=name)
        return {"exists": True, "points_count": info.points_count, "status": str(info.status)}
    except Exception as exc:
        return {"exists": False, "error": f"{type(exc).__name__}: {exc}"}


def dry_run(qdrant_url: str, probe: bool = True) -> dict[str, Any]:
    targets = _target_collections()
    plan: dict[str, Any] = {
        "qdrant_url": qdrant_url,
        "targets": targets,
        "scratch_prefix": SCRATCH_PREFIX,
        "qdrant_steps": [
            "1. create_snapshot(<collection>) for each target above",
            "2. recover_snapshot(collection_name=<scratch>, location=<this server's own snapshot URL>) "
            f"— scratch name is always generated here as {SCRATCH_PREFIX}<collection>_<unix_ts>, never "
            "user-supplied or taken from a CLI argument",
            "3. poll get_collection(<scratch>) until status == green (timeout configurable, default "
            f"{DEFAULT_POLL_TIMEOUT_S}s)",
            "4. verify points_count(<scratch>) == points_count(<source>)",
            "5. scroll 1 point from <scratch> with its vector, re-query that vector, assert the top hit "
            "is that same point id",
            "6. delete_collection(<scratch>) — guarded by the scratch-prefix check, never the source",
            "7. the snapshot itself is left in place (it IS the backup artifact) — only the scratch "
            "collection is deleted",
        ],
        "memgraph": {
            "note": "Memgraph is one graph namespace per server instance, not a collection store, so "
            "there is no 'scratch collection' to restore into on the same instance. Documented manual "
            "procedure below — NOT executed by this script.",
            "manual_steps": MEMGRAPH_MANUAL_STEPS,
            "reference": MEMGRAPH_REFERENCE,
        },
        "apply_requirements": [
            "Real execution needs --apply AND --i-have-owner-approval together; neither flag alone runs "
            "anything.",
            "Flow: dry-run (this) -> owner reads the report -> --apply creates a real snapshot -> owner "
            "approves proceeding -> restore/verify/delete-scratch happens in the same run.",
        ],
        "probes": {},
    }
    if probe:
        try:
            client = _build_client(qdrant_url)
        except Exception as exc:
            plan["probes"]["error"] = (
                f"could not construct Qdrant client: {type(exc).__name__}: {exc}"
            )
        else:
            for label, name in targets.items():
                plan["probes"][label] = {"collection": name, **probe_collection(client, name)}
    return plan


# ─── apply (real snapshot -> scratch-restore -> verify -> delete scratch) ───


def _verify_sample_query(client: Any, scratch: str, failures: list[str]) -> None:
    """Scroll one point from the scratch collection and re-query its own
    vector, asserting the top hit is that same point. Handles both a plain
    single-vector collection and a named multi-vector one (first_person_v1)."""
    try:
        points, _ = client.scroll(
            collection_name=scratch, limit=1, with_payload=False, with_vectors=True
        )
    except Exception as exc:
        failures.append(f"sample scroll failed: {type(exc).__name__}: {exc}")
        return
    if not points:
        failures.append("scratch collection has zero points to sample")
        return

    sample = points[0]
    vector = sample.vector
    vector_name: Optional[str] = None
    vector_for_query = vector
    if isinstance(vector, dict):
        vector_name = next(iter(vector))
        vector_for_query = vector[vector_name]

    try:
        response = client.query_points(
            collection_name=scratch,
            query=vector_for_query,
            using=vector_name,
            limit=1,
        )
    except Exception as exc:
        failures.append(f"sample vector query failed: {type(exc).__name__}: {exc}")
        return
    hits = response.points
    if not hits or hits[0].id != sample.id:
        failures.append("sample vector query did not return the sampled point as its own top hit")


def restore_one_collection(
    client: Any,
    qdrant_url: str,
    collection: str,
    poll_timeout: int = DEFAULT_POLL_TIMEOUT_S,
) -> dict[str, Any]:
    """Snapshot `collection`, restore into a fresh scratch collection, verify,
    then delete the scratch collection. Never mutates `collection` itself."""
    result: dict[str, Any] = {"collection": collection, "passed": False, "failures": []}
    failures: list[str] = result["failures"]

    try:
        source_info = client.get_collection(collection_name=collection)
    except Exception as exc:
        failures.append(f"source collection unreadable: {type(exc).__name__}: {exc}")
        return result
    source_points = source_info.points_count

    try:
        snapshot = client.create_snapshot(collection_name=collection, wait=True)
    except Exception as exc:
        failures.append(f"create_snapshot failed: {type(exc).__name__}: {exc}")
        return result
    if snapshot is None:
        failures.append("create_snapshot returned no snapshot description")
        return result
    result["snapshot_name"] = snapshot.name

    scratch = _scratch_name(collection)
    _assert_scratch(scratch)  # guard #1: restore target

    location = f"{qdrant_url}/collections/{collection}/snapshots/{snapshot.name}"
    try:
        client.recover_snapshot(collection_name=scratch, location=location, wait=True)
    except Exception as exc:
        failures.append(f"recover_snapshot failed: {type(exc).__name__}: {exc}")
        return result
    result["scratch_collection"] = scratch

    deadline = time.monotonic() + poll_timeout
    status = None
    while time.monotonic() < deadline:
        info = client.get_collection(collection_name=scratch)
        status = str(info.status)
        if status.lower() == "green":
            break
        time.sleep(POLL_INTERVAL_S)
    if status is None or status.lower() != "green":
        failures.append(f"scratch collection never reached green status (last seen: {status})")

    scratch_info = client.get_collection(collection_name=scratch)
    result["source_points_count"] = source_points
    result["scratch_points_count"] = scratch_info.points_count
    if scratch_info.points_count != source_points:
        failures.append(
            f"point count mismatch: source={source_points} scratch={scratch_info.points_count}"
        )

    _verify_sample_query(client, scratch, failures)
    if not any("sample" in f for f in failures):
        result["sample_query_verified"] = True

    _assert_scratch(scratch)  # guard #2: delete target, re-checked right before the call
    try:
        client.delete_collection(collection_name=scratch)
        result["scratch_deleted"] = True
    except Exception as exc:
        failures.append(
            f"failed to delete scratch collection {scratch}: {type(exc).__name__}: {exc}"
        )

    result["passed"] = not failures
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Qdrant snapshot/scratch-restore drill (Memgraph is a documented manual step)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute for real. Requires --i-have-owner-approval too — neither flag alone runs anything.",
    )
    parser.add_argument(
        "--i-have-owner-approval",
        action="store_true",
        help="Confirms the owner reviewed the dry-run report before --apply is allowed to proceed.",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=None,
        help="Override settings.qdrant_url (e.g. http://localhost:6333 when running on the host).",
    )
    parser.add_argument(
        "--collections",
        type=str,
        default="first_person,chat",
        help="Comma-separated subset of {first_person,chat} to drill.",
    )
    parser.add_argument(
        "--no-probe",
        action="store_true",
        help="Dry-run only: skip the read-only get_collection() probes (pure plan listing, zero network).",
    )
    parser.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT_S)
    args = parser.parse_args()

    qdrant_url = args.qdrant_url or _qdrant_url()
    selected = [c.strip() for c in args.collections.split(",") if c.strip()]

    if not args.apply:
        plan = dry_run(qdrant_url, probe=not args.no_probe)
        print(json.dumps(plan, indent=2, default=str))
        print(
            "\nDRY RUN only — nothing was written. Pass --apply AND --i-have-owner-approval to execute for real."
        )
        return 0

    if not args.i_have_owner_approval:
        print("Refusing to --apply without --i-have-owner-approval.")
        print(
            "Flow: dry-run -> report -> owner reviews -> owner approves -> "
            "--apply --i-have-owner-approval."
        )
        return 1

    targets = _target_collections()
    client = _build_client(qdrant_url)
    overall_passed = True
    for label in selected:
        if label not in targets:
            print(f"Unknown collection label {label!r}; expected one of {list(targets)}")
            return 1
        collection = targets[label]
        print(f"\n=== Restore drill: {label} ({collection}) ===")
        report = restore_one_collection(
            client, qdrant_url, collection, poll_timeout=args.poll_timeout
        )
        print(json.dumps(report, indent=2, default=str))
        overall_passed = overall_passed and report["passed"]

    print(
        "\nMemgraph: no scratch-database API exists; see the manual steps in --dry-run output "
        f"({MEMGRAPH_REFERENCE}) — not executed by this script."
    )
    print(f"\nRestore Drill Result: {'PASS' if overall_passed else 'FAIL'}")
    return 0 if overall_passed else 1


if __name__ == "__main__":
    sys.exit(main() or 0)

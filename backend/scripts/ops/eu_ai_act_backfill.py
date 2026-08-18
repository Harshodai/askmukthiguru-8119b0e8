#!/usr/bin/env python3
"""EU AI Act Retrospective 3+ Year Data Backfill Script.

Tagging & Provenance Backfill CLI for:
1. Qdrant spiritual_wisdom collection (Classifies points as 'human_generated' vs 'ai_generated', tags provenance_schema_version='1.0', compliance_tagged_at).
2. Postgres chat_messages & user_brain_nodes (Classifies user vs assistant turns).
3. Neo4j Knowledge Graph (:HumanAuthored vs :AiSynthesized labels).

Usage:
  python eu_ai_act_backfill.py --dry-run --scope all
  python eu_ai_act_backfill.py --scope qdrant --collection spiritual_wisdom --batch-size 500
"""

from __future__ import annotations

import argparse
import datetime as _dt
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.config import settings
from app.schemas.compliance import OriginType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eu_ai_act_backfill")


# ---------------------------------------------------------------------------
# Classification Logic
# ---------------------------------------------------------------------------


def classify_qdrant_point_payload(payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Determine whether a Qdrant point is primary human source or AI-generated.

    Returns:
        tuple (origin_type_str, update_dict)
    """
    is_summary = bool(payload.get("is_summary"))
    is_expansion = bool(payload.get("is_expansion"))
    has_cluster = payload.get("cluster_id") is not None
    doc_type = str(payload.get("doc_type", "")).lower()
    source_type = str(payload.get("source_type", "")).lower()
    existing_origin = payload.get("origin_type")

    # Explicit AI generated / synthesized indicators
    if (
        is_summary
        or is_expansion
        or has_cluster
        or doc_type in ("summary", "expansion", "synthetic", "raptor_summary")
        or source_type in ("summary", "expansion", "synthetic", "raptor_summary", "cluster_summary")
        or existing_origin in ("ai_generated", "ai_synthesized")
    ):
        origin = OriginType.AI_GENERATED.value
    else:
        # Primary human source discourse (transcripts, books, talks, youtube discourses)
        origin = OriginType.HUMAN_GENERATED.value

    timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat()
    update_payload = {
        "origin_type": origin,
        "provenance_schema_version": "1.0",
        "compliance_tagged_at": timestamp,
    }
    return origin, update_payload


# ---------------------------------------------------------------------------
# Qdrant Backfill
# ---------------------------------------------------------------------------


def backfill_qdrant(
    collection: str = "spiritual_wisdom",
    batch_size: int = 500,
    dry_run: bool = True,
    limit: Optional[int] = None,
    qdrant_url: Optional[str] = None,
    qdrant_api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Scroll Qdrant collection and backfill EU AI Act provenance tags."""
    logger.info(
        "Starting Qdrant backfill [collection=%s, batch_size=%d, dry_run=%s, limit=%s]",
        collection,
        batch_size,
        dry_run,
        limit,
    )

    try:
        from qdrant_client import QdrantClient
    except ImportError:
        logger.error("qdrant-client not installed. Skipping Qdrant backfill.")
        return {"status": "skipped", "reason": "qdrant-client missing"}

    url = qdrant_url or getattr(settings, "qdrant_url", "http://localhost:6333")
    api_key = qdrant_api_key or getattr(settings, "qdrant_api_key", None)

    try:
        client = QdrantClient(url=url, api_key=api_key, timeout=30.0)
    except Exception as exc:
        logger.error("Failed to connect to Qdrant at %s: %s", url, exc)
        return {"status": "error", "error": str(exc)}

    offset = None
    scanned = 0
    human_count = 0
    ai_count = 0
    updated_points = 0

    start_time = time.time()

    while True:
        scroll_limit = batch_size
        if limit is not None:
            remaining = limit - scanned
            if remaining <= 0:
                break
            scroll_limit = min(batch_size, remaining)

        try:
            records, next_offset = client.scroll(
                collection_name=collection,
                limit=scroll_limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            logger.error("Error scrolling Qdrant points: %s", exc)
            break

        if not records:
            break

        batch_human = []
        batch_ai = []

        for rec in records:
            payload = rec.payload or {}
            point_id = rec.id
            origin, _ = classify_qdrant_point_payload(payload)

            if origin == OriginType.HUMAN_GENERATED.value:
                human_count += 1
                batch_human.append(point_id)
            else:
                ai_count += 1
                batch_ai.append(point_id)

            scanned += 1

        timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat()

        if not dry_run:
            try:
                if batch_human:
                    client.set_payload(
                        collection_name=collection,
                        payload={
                            "origin_type": OriginType.HUMAN_GENERATED.value,
                            "provenance_schema_version": "1.0",
                            "compliance_tagged_at": timestamp,
                        },
                        points=batch_human,
                    )
                    updated_points += len(batch_human)

                if batch_ai:
                    client.set_payload(
                        collection_name=collection,
                        payload={
                            "origin_type": OriginType.AI_GENERATED.value,
                            "provenance_schema_version": "1.0",
                            "compliance_tagged_at": timestamp,
                        },
                        points=batch_ai,
                    )
                    updated_points += len(batch_ai)
            except Exception as exc:
                logger.error("Failed to update payload batch: %s", exc)

        offset = next_offset
        if offset is None:
            break

    elapsed = time.time() - start_time
    logger.info(
        "Qdrant backfill completed: scanned=%d, human=%d, ai=%d, updated=%d in %.2fs (dry_run=%s)",
        scanned,
        human_count,
        ai_count,
        updated_points if not dry_run else 0,
        elapsed,
        dry_run,
    )

    return {
        "status": "success",
        "scanned": scanned,
        "human_generated": human_count,
        "ai_generated": ai_count,
        "updated": updated_points if not dry_run else 0,
        "dry_run": dry_run,
        "elapsed_seconds": round(elapsed, 2),
    }


# ---------------------------------------------------------------------------
# Database Backfill (Postgres / Supabase)
# ---------------------------------------------------------------------------


def backfill_database(dry_run: bool = True) -> Dict[str, Any]:
    """Backfill origin classifications on Postgres chat_messages & user_brain_nodes."""
    logger.info("Starting Postgres / Supabase database backfill [dry_run=%s]", dry_run)

    supabase_url = os.getenv("SUPABASE_URL") or getattr(settings, "supabase_url", None)
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or getattr(settings, "supabase_service_role_key", None) or os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        logger.warning("Supabase credentials not configured in environment. Simulating database backfill.")
        return {
            "status": "simulated",
            "dry_run": dry_run,
            "chat_messages_updated": 0,
            "user_brain_nodes_updated": 0,
        }

    try:
        from supabase import create_client
        supabase = create_client(supabase_url, supabase_key)
    except Exception as exc:
        logger.error("Failed to initialize Supabase client: %s", exc)
        return {"status": "error", "error": str(exc)}

    timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat()
    chat_updated = 0
    brain_updated = 0

    if not dry_run:
        try:
            # Tag user messages as human_generated
            res_user = (
                supabase.table("chat_messages")
                .update({
                    "origin_type": OriginType.HUMAN_GENERATED.value,
                    "provenance_schema_version": "1.0",
                    "compliance_tagged_at": timestamp,
                })
                .eq("role", "user")
                .execute()
            )
            chat_updated += len(res_user.data) if res_user and res_user.data else 0

            # Tag assistant messages as ai_generated
            res_asst = (
                supabase.table("chat_messages")
                .update({
                    "origin_type": OriginType.AI_GENERATED.value,
                    "provenance_schema_version": "1.0",
                    "compliance_tagged_at": timestamp,
                })
                .eq("role", "assistant")
                .execute()
            )
            chat_updated += len(res_asst.data) if res_asst and res_asst.data else 0

            # Tag user_brain_nodes as human_generated
            res_brain = (
                supabase.table("user_brain_nodes")
                .update({
                    "origin_type": OriginType.HUMAN_GENERATED.value,
                    "provenance_schema_version": "1.0",
                    "compliance_tagged_at": timestamp,
                })
                .is_("origin_type", "null")
                .execute()
            )
            brain_updated += len(res_brain.data) if res_brain and res_brain.data else 0

        except Exception as exc:
            logger.error("Error executing database update queries: %s", exc)
            return {"status": "error", "error": str(exc)}
    else:
        logger.info("[Dry Run] Would update chat_messages and user_brain_nodes with provenance tags.")

    logger.info(
        "Database backfill completed: chat_messages=%d, user_brain_nodes=%d (dry_run=%s)",
        chat_updated,
        brain_updated,
        dry_run,
    )

    return {
        "status": "success",
        "chat_messages_updated": chat_updated,
        "user_brain_nodes_updated": brain_updated,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Neo4j Graph Backfill
# ---------------------------------------------------------------------------


def backfill_neo4j(dry_run: bool = True) -> Dict[str, Any]:
    """Tag Neo4j graph nodes with :HumanAuthored vs :AiSynthesized labels."""
    logger.info("Starting Neo4j Knowledge Graph backfill [dry_run=%s]", dry_run)

    neo4j_uri = os.getenv("NEO4J_URI") or getattr(settings, "neo4j_uri", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER") or getattr(settings, "neo4j_user", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD") or getattr(settings, "neo4j_password", "password")

    try:
        from neo4j import GraphDatabase
    except ImportError:
        logger.warning("neo4j driver not installed. Skipping Neo4j backfill.")
        return {"status": "skipped", "reason": "neo4j library missing"}

    timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat()
    ai_labeled = 0
    human_labeled = 0

    try:
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        with driver.session() as session:
            if not dry_run:
                # Label AI Synthesized / LightRAG Extracted nodes
                ai_query = """
                MATCH (n)
                WHERE n.origin_type = 'ai_generated'
                   OR n.synthetic = true
                   OR n:__Entity__
                   OR n:__Chunk__
                SET n:AiSynthesized,
                    n.provenance_schema_version = '1.0',
                    n.compliance_tagged_at = $ts
                RETURN count(n) AS cnt
                """
                res_ai = session.run(ai_query, ts=timestamp).single()
                ai_labeled = res_ai["cnt"] if res_ai else 0

                # Label Human Authored Canonical Doctrine nodes
                human_query = """
                MATCH (n)
                WHERE NOT n:AiSynthesized
                SET n:HumanAuthored,
                    n.provenance_schema_version = '1.0',
                    n.compliance_tagged_at = $ts
                RETURN count(n) AS cnt
                """
                res_human = session.run(human_query, ts=timestamp).single()
                human_labeled = res_human["cnt"] if res_human else 0
            else:
                count_res = session.run("MATCH (n) RETURN count(n) AS total").single()
                total = count_res["total"] if count_res else 0
                logger.info("[Dry Run] Found %d total Neo4j nodes to classify.", total)

        driver.close()
    except Exception as exc:
        logger.warning("Neo4j backfill encounter / offline: %s", exc)
        return {"status": "warning", "message": str(exc), "dry_run": dry_run}

    logger.info(
        "Neo4j backfill completed: AiSynthesized=%d, HumanAuthored=%d (dry_run=%s)",
        ai_labeled,
        human_labeled,
        dry_run,
    )

    return {
        "status": "success",
        "ai_synthesized_nodes": ai_labeled,
        "human_authored_nodes": human_labeled,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="EU AI Act Article 50 Retrospective Provenance Backfill CLI"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate backfill without mutating Qdrant, Postgres, or Neo4j",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default="spiritual_wisdom",
        help="Target Qdrant collection name (default: spiritual_wisdom)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Batch size for vector scrolling and payload updates (default: 500)",
    )
    parser.add_argument(
        "--scope",
        type=str,
        choices=["qdrant", "db", "neo4j", "all"],
        default="all",
        help="Scope of backfill execution (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of items to process",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=None,
        help="Optional override for Qdrant URL",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger.info(
        "Starting EU AI Act Backfill CLI [scope=%s, dry_run=%s, batch_size=%d]",
        args.scope,
        args.dry_run,
        args.batch_size,
    )

    results: Dict[str, Any] = {}

    if args.scope in ("qdrant", "all"):
        results["qdrant"] = backfill_qdrant(
            collection=args.collection,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            limit=args.limit,
            qdrant_url=args.qdrant_url,
        )

    if args.scope in ("db", "all"):
        results["database"] = backfill_database(dry_run=args.dry_run)

    if args.scope in ("neo4j", "all"):
        results["neo4j"] = backfill_neo4j(dry_run=args.dry_run)

    logger.info("EU AI Act Backfill finished. Results summary: %s", results)
    return 0


if __name__ == "__main__":
    sys.exit(main())

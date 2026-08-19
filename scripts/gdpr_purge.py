"""Idempotent cross-store user erasure executor.

The command is dry-run by default. Real deletion requires ``--confirm`` and a
specific ``--user-id``. Optional Qdrant and Neo4j deletion is enabled only when
the corresponding GDPR-specific environment variables are present, preventing a
misconfigured run from deleting an entire shared collection or graph.

Examples:
    python scripts/gdpr_purge.py --user-id <uuid>
    python scripts/gdpr_purge.py --user-id <uuid> --confirm
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

logger = logging.getLogger("gdpr_purge")

# Tables with a direct user_id ownership column. Missing optional tables are
# reported and do not prevent the other stores from being processed.
_DIRECT_USER_TABLES = (
    "user_brain_edges",
    "user_brain_nodes",
    "user_brain_keys",
    "user_memories",
    "memory_reflections",
    "chat_sessions",
    "chat_queries",
    "chat_responses",
    "push_subscriptions",
)


def _make_client() -> Any:
    from supabase import create_client  # type: ignore

    url = os.environ.get("SUPABASE_URL") or os.environ.get("VITE_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY) are required")
    return create_client(url, key)


async def _delete_direct_user_table(db: Any, table: str, user_id: str, dry_run: bool) -> dict[str, Any]:
    try:
        query = db.table(table).select("id").eq("user_id", user_id)
        result = await asyncio.to_thread(query.execute)
        rows = getattr(result, "data", None) or []
        if dry_run:
            return {"status": "would_delete", "count": len(rows)}
        deleted = await asyncio.to_thread(db.table(table).delete().eq("user_id", user_id).execute)
        return {"status": "deleted", "count": len(getattr(deleted, "data", None) or rows)}
    except Exception as exc:  # tables vary by deployment migration level
        logger.warning("table %s skipped: %s", table, exc)
        return {"status": "skipped", "count": 0, "error": str(exc)}


async def _delete_conversations(db: Any, user_id: str, dry_run: bool) -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(
            lambda: db.table("conversations").select("id").eq("user_id", user_id).execute()
        )
        ids = [str(row["id"]) for row in (getattr(result, "data", None) or []) if row.get("id")]
        if dry_run:
            return {"status": "would_delete", "conversations": len(ids), "messages": "unknown"}
        message_count = 0
        for conversation_id in ids:
            deleted = await asyncio.to_thread(
                lambda cid=conversation_id: db.table("chat_messages").delete().eq("conversation_id", cid).execute()
            )
            message_count += len(getattr(deleted, "data", None) or [])
        await asyncio.to_thread(lambda: db.table("conversations").delete().eq("user_id", user_id).execute())
        return {"status": "deleted", "conversations": len(ids), "messages": message_count}
    except Exception as exc:
        logger.warning("conversation purge failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


async def _delete_qdrant(user_id: str, dry_run: bool) -> dict[str, Any]:
    url = os.environ.get("GDPR_QDRANT_URL", "").strip().rstrip("/")
    collection = os.environ.get("GDPR_QDRANT_COLLECTION", "").strip()
    api_key = os.environ.get("QDRANT_API_KEY", "").strip()
    if not url or not collection:
        return {"status": "not_configured"}
    if dry_run:
        return {"status": "would_delete", "collection": collection}
    import requests

    headers = {"api-key": api_key} if api_key else {}
    response = await asyncio.to_thread(
        requests.post,
        f"{url}/collections/{collection}/points/delete",
        headers=headers,
        json={"filter": {"must": [{"key": "user_id", "match": {"value": user_id}}]}, "wait": True},
        timeout=30,
    )
    response.raise_for_status()
    return {"status": "deleted", "collection": collection}


async def _delete_neo4j(user_id: str, dry_run: bool) -> dict[str, Any]:
    uri = os.environ.get("GDPR_NEO4J_URI", "").strip()
    user = os.environ.get("GDPR_NEO4J_USER", "").strip()
    password = os.environ.get("GDPR_NEO4J_PASSWORD", "").strip()
    tenant_id = os.environ.get("GDPR_TENANT_ID", "").strip()
    if not uri or not user or not password or not tenant_id:
        return {"status": "not_configured"}
    if dry_run:
        return {"status": "would_delete"}
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        def _delete() -> int:
            with driver.session() as session:
                row = session.run(
                    """
                    MATCH (u:User {tenant_id: $tenant_id, id: $user_id})
                    OPTIONAL MATCH (u)-[:HAS_MEMORY]->(m:GlobalMemory)
                    WITH u, collect(m) AS memories
                    FOREACH (memory IN memories | DETACH DELETE memory)
                    DETACH DELETE u
                    RETURN size(memories) AS deleted
                    """,
                    tenant_id=tenant_id,
                    user_id=user_id,
                ).single()
                return int(row["deleted"]) if row else 0
        return {"status": "deleted", "nodes": await asyncio.to_thread(_delete)}
    finally:
        driver.close()


async def purge_user(user_id: str, *, dry_run: bool) -> dict[str, Any]:
    db = _make_client()
    stores: dict[str, Any] = {"conversations": await _delete_conversations(db, user_id, dry_run)}
    for table in _DIRECT_USER_TABLES:
        stores[table] = await _delete_direct_user_table(db, table, user_id, dry_run)
    stores["qdrant"] = await _delete_qdrant(user_id, dry_run)
    stores["neo4j"] = await _delete_neo4j(user_id, dry_run)
    failed = [name for name, result in stores.items() if result.get("status") == "failed"]
    return {
        "user_id": user_id,
        "mode": "dry_run" if dry_run else "confirm",
        "status": "partial_failure" if failed else ("would_delete" if dry_run else "completed"),
        "failed_stores": failed,
        "stores": stores,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run-first cross-store GDPR user erasure")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--confirm", action="store_true", help="Actually delete data; omitted means dry-run")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s gdpr_purge %(levelname)s %(message)s")
    result = asyncio.run(purge_user(args.user_id, dry_run=not args.confirm))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] not in {"partial_failure"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

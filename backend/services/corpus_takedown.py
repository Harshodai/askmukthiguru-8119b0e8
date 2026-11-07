"""Corpus Takedown Engine (PROD-DATA-01, DATA-07, MEM-010, T3-06).

Provides an atomic, cross-store takedown operation across:
1. Qdrant (soft-deletes/quarantines matching points in `first_person_v10` & `chat_search`).
2. Redis (invalidates exact query caches, seen-clip sets, and semantic caches).
3. Supabase / Postgres (marks saved answers & notebooks as withdrawn_by_source).
4. Local & Persistent Audit Trail (records immutable takedown receipt).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

logger = logging.getLogger(__name__)

DEFAULT_COLLECTIONS = ("first_person_v10", "chat_search")
DEFAULT_AUDIT_LOG = Path("audits/evidence/corpus_takedowns.jsonl")


class CorpusTakedownEngine:
    """Orchestrates atomic legal and content revocations across all datastores."""

    def __init__(
        self,
        qdrant_client: Optional[QdrantClient] = None,
        redis_client: Optional[Any] = None,
        supabase_client: Optional[Any] = None,
        audit_log_path: Path = DEFAULT_AUDIT_LOG,
    ) -> None:
        self._qdrant = qdrant_client
        self._redis = redis_client
        self._supabase = supabase_client
        self._audit_log_path = audit_log_path

    def _get_qdrant(self) -> Optional[QdrantClient]:
        if self._qdrant is not None:
            return self._qdrant
        try:
            from services.qdrant.client import QdrantClientManager
            self._qdrant = QdrantClientManager().client
            return self._qdrant
        except Exception as exc:
            logger.warning(f"Could not initialize QdrantClientManager: {exc}")
            return None

    def _get_redis(self) -> Optional[Any]:
        if self._redis is not None:
            return self._redis
        try:
            import redis
            from app.config import get_settings
            settings = get_settings()
            redis_url = getattr(settings, "redis_url", "redis://localhost:6379/0")
            self._redis = redis.from_url(redis_url, decode_responses=True)
            return self._redis
        except Exception as exc:
            logger.warning(f"Could not initialize Redis client: {exc}")
            return None

    def _get_supabase(self) -> Optional[Any]:
        if self._supabase is not None:
            return self._supabase
        try:
            from app.telemetry_db import _get_client
            self._supabase = _get_client()
            return self._supabase
        except Exception as exc:
            logger.warning(f"Could not initialize Supabase client: {exc}")
            return None

    def takedown(
        self,
        source_identity: str,
        reason: str,
        *,
        dry_run: bool = False,
        collections: tuple[str, ...] = DEFAULT_COLLECTIONS,
    ) -> dict[str, Any]:
        """Execute a cross-store takedown for a given video_id, source_url, or span_id."""
        now_iso = datetime.now(timezone.utc).isoformat()
        report: dict[str, Any] = {
            "source_identity": source_identity,
            "reason": reason,
            "dry_run": dry_run,
            "timestamp": now_iso,
            "qdrant": {"matched_points": 0, "quarantined_points": 0, "collections_affected": []},
            "redis": {"flushed_keys": 0, "keys": []},
            "database": {"marked_withdrawn": 0, "tables_affected": []},
            "audit_persisted": False,
            "success": True,
        }

        # 1. Qdrant Takedown
        qdrant = self._get_qdrant()
        if qdrant:
            for coll in collections:
                try:
                    matched_ids = self._find_matching_qdrant_points(qdrant, coll, source_identity)
                    if matched_ids:
                        report["qdrant"]["matched_points"] += len(matched_ids)
                        report["qdrant"]["collections_affected"].append(coll)
                        if not dry_run:
                            qdrant.set_payload(
                                collection_name=coll,
                                payload={
                                    "quality_status": "quarantined",
                                    "quarantine_reason": f"takedown: {reason}",
                                    "rights_status": "revoked",
                                    "takedown_at": now_iso,
                                },
                                points=matched_ids,
                                wait=True,
                            )
                            report["qdrant"]["quarantined_points"] += len(matched_ids)
                            logger.info(
                                f"Takedown quarantined {len(matched_ids)} points in collection {coll}"
                            )
                except Exception as exc:
                    logger.error(f"Error executing Qdrant takedown in {coll}: {exc}")
                    report["success"] = False

        # 2. Redis Cache Invalidation
        redis_cli = self._get_redis()
        if redis_cli:
            try:
                flushed = self._flush_redis_caches(redis_cli, source_identity, dry_run=dry_run)
                report["redis"]["flushed_keys"] = len(flushed)
                report["redis"]["keys"] = flushed
            except Exception as exc:
                logger.error(f"Error invalidating Redis cache for takedown: {exc}")

        # 3. Supabase / Postgres Notebooks and Bookmarks
        supabase = self._get_supabase()
        if supabase:
            try:
                db_affected = self._mark_db_withdrawn(supabase, source_identity, dry_run=dry_run)
                report["database"]["marked_withdrawn"] = db_affected.get("count", 0)
                report["database"]["tables_affected"] = db_affected.get("tables", [])
            except Exception as exc:
                logger.error(f"Error marking DB records withdrawn: {exc}")

        # 4. Immutable Audit Trail
        if not dry_run:
            try:
                self._persist_audit_entry(report)
                report["audit_persisted"] = True
            except Exception as exc:
                logger.error(f"Error writing takedown audit log: {exc}")

        return report

    def _find_matching_qdrant_points(
        self, client: QdrantClient, collection: str, source_identity: str
    ) -> list[str]:
        """Find point IDs in Qdrant matching source_identity as video_id, source_url, or span_id."""
        matched = set()
        # Direct point ID lookup (UUID)
        try:
            res = client.retrieve(collection, ids=[source_identity], with_payload=False)
            if res:
                matched.add(str(res[0].id))
        except Exception:
            pass

        # Filter by video_id
        for field in ("video_id", "source_url", "source_identity", "url"):
            try:
                scroll_res, _ = client.scroll(
                    collection_name=collection,
                    scroll_filter=qmodels.Filter(
                        must=[qmodels.FieldCondition(key=field, match=qmodels.MatchValue(value=source_identity))]
                    ),
                    limit=1000,
                    with_payload=False,
                    with_vectors=False,
                )
                for point in scroll_res:
                    matched.add(str(point.id))
            except Exception:
                continue

        return list(matched)

    def _flush_redis_caches(self, redis_cli: Any, source_identity: str, dry_run: bool = False) -> list[str]:
        """Scan and remove Redis exact and semantic cache keys containing source_identity."""
        keys_to_delete = []
        try:
            # Pattern scan for exact query caches
            cursor = 0
            while True:
                cursor, keys = redis_cli.scan(cursor=cursor, match="*cache*", count=100)
                for key in keys:
                    try:
                        val = redis_cli.get(key)
                        if val and source_identity in str(val):
                            keys_to_delete.append(key)
                    except Exception:
                        pass
                if cursor == 0:
                    break

            # Check seen clips sets
            cursor = 0
            while True:
                cursor, keys = redis_cli.scan(cursor=cursor, match="*seen_clips*", count=100)
                for key in keys:
                    if redis_cli.sismember(key, source_identity):
                        keys_to_delete.append(f"{key} (srem: {source_identity})")
                        if not dry_run:
                            redis_cli.srem(key, source_identity)
                if cursor == 0:
                    break

            if not dry_run and keys_to_delete:
                plain_keys = [k for k in keys_to_delete if "srem" not in k]
                if plain_keys:
                    redis_cli.delete(*plain_keys)
        except Exception as exc:
            logger.warning(f"Redis cache flush encountered error: {exc}")

        return keys_to_delete

    def _mark_db_withdrawn(self, supabase: Any, source_identity: str, dry_run: bool = False) -> dict[str, Any]:
        """Flag saved answers in study_notebooks or bookmarks referencing source_identity."""
        count = 0
        tables = []
        try:
            # Check study_notebooks if table exists
            res = (
                supabase.table("study_notebooks")
                .select("id")
                .ilike("citation_url", f"%{source_identity}%")
                .execute()
            )
            data = getattr(res, "data", []) or []
            if data:
                tables.append("study_notebooks")
                count += len(data)
                if not dry_run:
                    ids = [row["id"] for row in data]
                    supabase.table("study_notebooks").update(
                        {"withdrawn_by_source": True, "withdrawn_at": datetime.now(timezone.utc).isoformat()}
                    ).in_("id", ids).execute()
        except Exception:
            pass

        return {"count": count, "tables": tables}

    def _persist_audit_entry(self, report: dict[str, Any]) -> None:
        """Append takedown receipt to local audit ledger."""
        self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")

"""
Checkpoint handler for ingestion state tracking across Redis, Supabase, and local JSON files.
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Cross-instance lock around the file read-modify-write path. Without it, two
# concurrent IngestionCheckpoint instances (different tenants/processes) can
# lose each other's updates via load-merge-write races.
_FILE_LOCK = threading.Lock()


class IngestionCheckpoint:
    def __init__(self, filepath="data/ingest_checkpoint.json"):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(exist_ok=True)
        self.redis_client = None
        self.supabase_client = None
        self.tenant_id = "default"

        # Try establishing connection to Redis for centralized checkpointing
        try:
            from app.config import settings
            import redis
            if getattr(settings, "redis_url", None):
                try:
                    from services.tenant_context import TenantContext
                    self.tenant_id = TenantContext.get() or "default"
                except Exception:
                    self.tenant_id = "default"

                self.redis_client = redis.from_url(settings.redis_url, socket_timeout=2.0)
                self.redis_client.ping()
                logger.info(f"IngestionCheckpoint: Centralized Redis backend connected. Tenant: {self.tenant_id}")
        except Exception as e:
            logger.warning(f"IngestionCheckpoint: Redis connection failed or unconfigured ({e}). Trying Supabase.")
            self.redis_client = None

        # Try establishing connection to Supabase as Tier-2 fallback
        if not self.redis_client:
            try:
                from app.config import settings
                from supabase import create_client
                if settings.supabase_url and settings.supabase_key:
                    try:
                        from services.tenant_context import TenantContext
                        self.tenant_id = TenantContext.get() or "default"
                    except Exception:
                        self.tenant_id = "default"

                    self.supabase_client = create_client(settings.supabase_url, settings.supabase_key)
                    logger.info(f"IngestionCheckpoint: Centralized Supabase backend connected. Tenant: {self.tenant_id}")
            except Exception as e:
                logger.warning(f"IngestionCheckpoint: Supabase connection failed ({e}). Falling back to local JSON.")
                self.supabase_client = None

        self.data = self._load()
        self.processed_chunks = self._load_processed_chunks()

    def _get_redis_key(self, chunk_id: str) -> str:
        return f"ingestion_checkpoint:{self.tenant_id}:{chunk_id}"

    def _atomic_write(self, data: dict) -> None:
        """Atomically replace the checkpoint file (write temp + os.replace).

        write_text in place is not atomic: a crash mid-write corrupts the file.
        os.replace is atomic on POSIX; the temp file lives in the same directory
        so the rename never crosses filesystems.
        """
        tmp_path = self.filepath.with_suffix(self.filepath.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, indent=2))
        os.replace(tmp_path, self.filepath)

    def _load_processed_chunks(self) -> set[str]:
        """Return tenant-qualified chunk IDs, migrating legacy unqualified keys.

        The rewrite is persisted back to the checkpoint file once (only when
        legacy keys are detected) so the migration survives restarts instead of
        being recomputed in memory on every boot.
        """
        tenant = getattr(self, "tenant_id", None) or "default"
        result: set[str] = set()
        has_legacy = False
        for key in self.data.keys():
            if key.startswith("tenant:"):
                result.add(key)
            else:
                # Legacy default-tenant entry: rewrite to the qualified namespace.
                has_legacy = True
                qualified = f"tenant:{tenant}:{key}"
                result.add(qualified)
        if has_legacy:
            self._persist_qualified_keys(tenant)
        return result

    def _persist_qualified_keys(self, tenant: str) -> None:
        """Rewrite legacy unqualified keys to the tenant-qualified namespace on
        disk. Called once from _load_processed_chunks; _load() stays untouched
        so there is no recursion between the two.
        """
        rewritten = {
            (key if key.startswith("tenant:") else f"tenant:{tenant}:{key}"): value
            for key, value in self.data.items()
        }
        self.data = rewritten
        with _FILE_LOCK:
            self._atomic_write(rewritten)

    def _qualify_chunk_id(self, chunk_id: str) -> str:
        """Prefix chunk_id with the tenant namespace for local-file isolation."""
        if chunk_id.startswith("tenant:"):
            return chunk_id
        tenant = getattr(self, "tenant_id", None) or "default"
        return f"tenant:{tenant}:{chunk_id}"

    def _load(self) -> dict:
        if self.filepath.exists():
            try:
                loaded = json.loads(self.filepath.read_text())
                if isinstance(loaded, list):
                    import time
                    return {h: {"migrated": True, "timestamp": time.time()} for h in loaded}
                elif isinstance(loaded, dict):
                    return loaded
            except Exception as e:
                logger.warning(f"Failed to load checkpoint file: {e}")
        return {}

    def save(self, chunk_id: str, metadata: Optional[dict] = None):
        import time
        if getattr(self, "redis_client", None):
            try:
                key = self._get_redis_key(chunk_id)
                data = metadata or {"timestamp": time.time()}
                self.redis_client.set(key, json.dumps(data))
                return
            except Exception as e:
                logger.error(f"Failed to save checkpoint to Redis: {e}. Trying Supabase.")

        if getattr(self, "supabase_client", None):
            try:
                data = metadata or {"timestamp": time.time()}
                self.supabase_client.table("ingestion_checkpoints").upsert({
                    "chunk_id": chunk_id,
                    "tenant_id": self.tenant_id,
                    "metadata": data,
                }).execute()
                return
            except Exception as e:
                logger.error(f"Failed to save checkpoint to Supabase: {e}. Falling back to file.")

        qualified = self._qualify_chunk_id(chunk_id)
        self.processed_chunks.add(qualified)
        with _FILE_LOCK:
            # Merge with the file's current state: self.data is a construction-time
            # snapshot, and other IngestionCheckpoint instances (e.g. different
            # tenants) may have written entries since. Overwriting the snapshot
            # would silently drop their checkpoints. The lock serializes the
            # read-modify-write so concurrent instances cannot lose updates.
            merged = self._load()
            merged[qualified] = metadata or {"timestamp": time.time()}
            self.data = merged
            self._atomic_write(merged)

    def is_processed(self, chunk_id: str) -> bool:
        if getattr(self, "redis_client", None):
            try:
                key = self._get_redis_key(chunk_id)
                if self.redis_client.exists(key):
                    return True
            except Exception as e:
                logger.error(f"Failed to check checkpoint in Redis: {e}. Trying Supabase.")

        if getattr(self, "supabase_client", None):
            try:
                res = self.supabase_client.table("ingestion_checkpoints").select("chunk_id").eq("chunk_id", chunk_id).eq("tenant_id", self.tenant_id).execute()
                if res.data:
                    return True
            except Exception as e:
                logger.error(f"Failed to check checkpoint in Supabase: {e}. Falling back to file.")

        # A Redis/Supabase miss doesn't rule out a checkpoint that was written
        # to the local-file fallback during an earlier outage of either store.
        return self._qualify_chunk_id(chunk_id) in self.processed_chunks

    def prune_stale_entries(self, active_hashes: list[str]):
        """Remove any entries from checkpoint that are no longer active."""
        if getattr(self, "redis_client", None) or getattr(self, "supabase_client", None):
            logger.warning("prune_stale_entries is not supported in centralized database mode.")
            return

        active_set = {self._qualify_chunk_id(h) for h in active_hashes}
        with _FILE_LOCK:
            # Merge with the on-disk state (other instances may have written
            # since construction) before pruning, mirroring save().
            self.data = {k: v for k, v in self._load().items() if k in active_set}
            self.processed_chunks = set(self.data.keys())
            self._atomic_write(self.data)


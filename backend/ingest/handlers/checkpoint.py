"""
Checkpoint handler for ingestion state tracking across Redis, Supabase, and local JSON files.
"""

import contextlib
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None

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
        self.tenant_id = self._default_tenant_id()
        try:
            from services.tenant_context import TenantContext
            self.tenant_id = TenantContext.get() or self._default_tenant_id()
        except Exception:
            self.tenant_id = self._default_tenant_id()

        # Try establishing connection to Redis for centralized checkpointing
        try:
            from app.config import settings
            import redis
            if getattr(settings, "redis_url", None):
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
        A unique temp file per call avoids two concurrent writers colliding on
        the same temp name. os.replace is atomic on POSIX; the temp file lives
        in the same directory so the rename never crosses filesystems.
        """
        fd, tmp_path = tempfile.mkstemp(
            dir=self.filepath.parent, prefix=".ckpt-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self.filepath)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @contextlib.contextmanager
    def _file_lock(self):
        """Serialize checkpoint-file read-modify-write across processes.

        fcntl.flock serializes processes sharing the checkpoint file; the
        module-level _FILE_LOCK additionally serializes threads within this
        process. Both are always acquired in the same order.
        """
        lock_path = self.filepath.with_suffix(self.filepath.suffix + ".ckpt.lock")
        lock_fh = lock_path.open("a+")
        try:
            if fcntl is not None:
                fcntl.flock(lock_fh, fcntl.LOCK_EX)
            with _FILE_LOCK:
                yield
        finally:
            try:
                if fcntl is not None:
                    fcntl.flock(lock_fh, fcntl.LOCK_UN)
            finally:
                lock_fh.close()

    def _default_tenant_id(self) -> str:
        """Tenant id of the legacy default namespace (settings or 'default')."""
        try:
            from app.config import settings
            return getattr(settings, "default_tenant_id", None) or "default"
        except Exception:
            return "default"

    def _load_processed_chunks(self) -> set[str]:
        """Return tenant-qualified chunk IDs, migrating legacy unqualified keys.

        The rewrite is persisted back to the checkpoint file once (only when
        legacy keys are detected) so the migration survives restarts instead of
        being recomputed in memory on every boot. Legacy keys predate tenant
        support and always belong to the default tenant, so they migrate into
        the default-tenant namespace regardless of the loading instance's
        tenant.
        """
        result: set[str] = set()
        has_legacy = False
        for key in self.data.keys():
            if key.startswith("tenant:"):
                result.add(key)
            else:
                # Legacy default-tenant entry: rewrite to the qualified namespace.
                has_legacy = True
                qualified = f"tenant:{self._default_tenant_id()}:{key}"
                result.add(qualified)
        if has_legacy:
            self._persist_qualified_keys()
        return result

    def _persist_qualified_keys(self) -> None:
        """Rewrite legacy unqualified keys to the default-tenant namespace on
        disk. Called once from _load_processed_chunks; _load() stays untouched
        so there is no recursion between the two.
        """
        with self._file_lock():
            # Reload under the lock: self.data is a construction-time snapshot,
            # and another instance may have written to disk since.
            current = self._load()
            rewritten = {k: v for k, v in current.items() if k.startswith("tenant:")}
            default_tenant = self._default_tenant_id()
            for key, value in current.items():
                if not key.startswith("tenant:"):
                    qualified = f"tenant:{default_tenant}:{key}"
                    if qualified not in rewritten:
                        rewritten[qualified] = value
            self.data = rewritten
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
        with self._file_lock():
            # Merge with the file's current state: self.data is a construction-time
            # snapshot, and other IngestionCheckpoint instances (e.g. different
            # tenants) may have written entries since. Overwriting the snapshot
            # would silently drop their checkpoints. The lock serializes the
            # read-modify-write so concurrent instances cannot lose updates.
            merged = self._load()
            merged[qualified] = metadata or {"timestamp": time.time()}
            self.data = merged
            self.processed_chunks = set(merged.keys())
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
        # Reload the on-disk state so writes from other instances are visible.
        self.data = self._load()
        self.processed_chunks = self._load_processed_chunks()
        return self._qualify_chunk_id(chunk_id) in self.processed_chunks

    def prune_stale_entries(self, active_hashes: list[str]):
        """Remove any entries from checkpoint that are no longer active."""
        if getattr(self, "redis_client", None) or getattr(self, "supabase_client", None):
            logger.warning("prune_stale_entries is not supported in centralized database mode.")
            return

        active_set = {self._qualify_chunk_id(h) for h in active_hashes}
        tenant_ns = f"tenant:{self.tenant_id}:"
        with self._file_lock():
            # Reload the on-disk state (other instances may have written since
            # construction) before pruning, mirroring save(). Only the current
            # tenant's namespace is pruned; other tenants' entries stay.
            current = self._load()
            self.data = {
                k: v
                for k, v in current.items()
                if not k.startswith(tenant_ns) or k in active_set
            }
            self.processed_chunks = set(self.data.keys())
            self._atomic_write(self.data)


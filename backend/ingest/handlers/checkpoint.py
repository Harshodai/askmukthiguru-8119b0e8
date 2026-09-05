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
            import redis

            from app.config import settings

            if getattr(settings, "redis_url", None):
                self.redis_client = redis.from_url(settings.redis_url, socket_timeout=2.0)
                self.redis_client.ping()
                logger.info(
                    f"IngestionCheckpoint: Centralized Redis backend connected. Tenant: {self.tenant_id}"
                )
        except Exception as e:
            logger.warning(
                f"IngestionCheckpoint: Redis connection failed or unconfigured ({e}). Trying Supabase."
            )
            self.redis_client = None

        # Try establishing connection to Supabase as Tier-2 fallback
        if not self.redis_client:
            try:
                from supabase import create_client

                from app.config import settings

                if settings.supabase_url and settings.supabase_key:
                    client = create_client(
                        settings.supabase_url, settings.supabase_key
                    )
                    # Verify auth and access to ingestion_checkpoints table
                    client.table("ingestion_checkpoints").select("chunk_id").limit(0).execute()
                    self.supabase_client = client
                    logger.info(
                        f"IngestionCheckpoint: Centralized Supabase backend connected. Tenant: {self.tenant_id}"
                    )
            except Exception as e:
                err_str = str(e)
                if "401" in err_str or "unauthorized" in err_str.lower() or "credentials" in err_str.lower():
                    logger.warning(
                        f"IngestionCheckpoint: Supabase auth failed ({e}). Falling back to local JSON."
                    )
                else:
                    logger.warning(
                        f"IngestionCheckpoint: Supabase connection failed ({e}). Falling back to local JSON."
                    )
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
        fd, tmp_path = tempfile.mkstemp(dir=self.filepath.parent, prefix=".ckpt-", suffix=".tmp")
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
                self.supabase_client.table("ingestion_checkpoints").upsert(
                    {
                        "chunk_id": chunk_id,
                        "tenant_id": self.tenant_id,
                        "metadata": data,
                    }
                ).execute()
                return
            except Exception as e:
                err_str = str(e)
                if "401" in err_str or "unauthorized" in err_str.lower() or "credentials" in err_str.lower():
                    logger.warning(
                        f"IngestionCheckpoint: Supabase auth failed ({e}). Disabling Supabase and falling back to file."
                    )
                    self.supabase_client = None
                else:
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
        # A miss at one tier does NOT rule out a checkpoint written to a lower
        # tier during an earlier outage of a higher one — save() writes to
        # exactly one tier (first available), never all three, so a clean
        # "not found" here must fall through to the next tier rather than
        # returning False outright. Only an explicit failed/error status is
        # authoritative enough to short-circuit (production-audit finding
        # checkpoint-multitier-fallback-broken).
        if getattr(self, "redis_client", None):
            try:
                key = self._get_redis_key(chunk_id)
                if self.redis_client.exists(key):
                    val = self.redis_client.get(key)
                    if val:
                        try:
                            data = json.loads(val)
                            if isinstance(data, dict) and data.get("status") in ("failed", "error"):
                                return False
                        except Exception:
                            pass
                    return True
            except Exception as e:
                logger.error(f"Failed to check checkpoint in Redis: {e}. Trying Supabase.")

        if getattr(self, "supabase_client", None):
            try:
                res = (
                    self.supabase_client.table("ingestion_checkpoints")
                    .select("chunk_id, metadata")
                    .eq("chunk_id", chunk_id)
                    .eq("tenant_id", self.tenant_id)
                    .execute()
                )
                if res.data:
                    row = res.data[0]
                    meta = row.get("metadata")
                    if isinstance(meta, dict) and meta.get("status") in ("failed", "error"):
                        return False
                    return True
            except Exception as e:
                err_str = str(e)
                if "401" in err_str or "unauthorized" in err_str.lower() or "credentials" in err_str.lower():
                    logger.warning(
                        f"IngestionCheckpoint: Supabase auth failed ({e}). Disabling Supabase and falling back to file."
                    )
                    self.supabase_client = None
                else:
                    logger.error(f"Failed to check checkpoint in Supabase: {e}. Falling back to file.")

        # A Redis/Supabase outage falls back to local-file state.
        # Reload the on-disk state so writes from other instances are visible.
        self.data = self._load()
        self.processed_chunks = self._load_processed_chunks()
        qid = self._qualify_chunk_id(chunk_id)
        if qid in self.processed_chunks:
            entry = self.data.get(qid)
            if isinstance(entry, dict) and entry.get("status") in ("failed", "error"):
                return False
            return True
        return False

    def acquire_lock(self, chunk_id: str, ttl_seconds: int = 900) -> bool:
        """Best-effort reservation so two concurrent ingests of the same
        source don't both run the full pipeline (production-audit finding
        IC-1: is_processed()/save() are a read and a much-later unconditional
        write with no reservation held across the processing window).

        Returns True if the caller now holds the lock (or no Redis is
        configured, in which case there is no cross-process concurrency to
        guard against in the first place — file-mode checkpointing is
        single-process). Returns False if another worker already holds it —
        the caller should skip this source rather than reprocess it.

        The lease has a TTL so a crashed worker's lock self-expires instead of
        wedging the source forever; it is NOT a substitute for save() — a
        caller must still call release_lock() when done (success or failure).
        """
        if not getattr(self, "redis_client", None):
            return True
        try:
            key = f"{self._get_redis_key(chunk_id)}:lock"
            return bool(self.redis_client.set(key, "1", nx=True, ex=ttl_seconds))
        except Exception as e:
            logger.warning(f"IngestionCheckpoint.acquire_lock failed (proceeding without lock): {e}")
            return True

    def release_lock(self, chunk_id: str) -> None:
        if not getattr(self, "redis_client", None):
            return
        try:
            key = f"{self._get_redis_key(chunk_id)}:lock"
            self.redis_client.delete(key)
        except Exception as e:
            logger.warning(f"IngestionCheckpoint.release_lock failed (will self-expire via TTL): {e}")

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
                k: v for k, v in current.items() if not k.startswith(tenant_ns) or k in active_set
            }
            self.processed_chunks = set(self.data.keys())
            self._atomic_write(self.data)

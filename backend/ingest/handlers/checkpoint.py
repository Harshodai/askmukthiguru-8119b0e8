"""
Checkpoint handler for ingestion state tracking across Redis, Supabase, and local JSON files.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


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
        self.processed_chunks = set(self.data.keys())

    def _get_redis_key(self, chunk_id: str) -> str:
        return f"ingestion_checkpoint:{self.tenant_id}:{chunk_id}"

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

        self.processed_chunks.add(chunk_id)
        self.data[chunk_id] = metadata or {"timestamp": time.time()}
        try:
            self.filepath.write_text(json.dumps(self.data, indent=2))
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    def is_processed(self, chunk_id: str) -> bool:
        if getattr(self, "redis_client", None):
            try:
                key = self._get_redis_key(chunk_id)
                return bool(self.redis_client.exists(key))
            except Exception as e:
                logger.error(f"Failed to check checkpoint in Redis: {e}. Trying Supabase.")

        if getattr(self, "supabase_client", None):
            try:
                res = self.supabase_client.table("ingestion_checkpoints").select("chunk_id").eq("chunk_id", chunk_id).eq("tenant_id", self.tenant_id).execute()
                return bool(res.data)
            except Exception as e:
                logger.error(f"Failed to check checkpoint in Supabase: {e}. Falling back to file.")

        return chunk_id in self.processed_chunks

    def prune_stale_entries(self, active_hashes: list[str]):
        """Remove any entries from checkpoint that are no longer active."""
        if getattr(self, "redis_client", None) or getattr(self, "supabase_client", None):
            logger.warning("prune_stale_entries is not supported in centralized database mode.")
            return

        active_set = set(active_hashes)
        self.data = {k: v for k, v in self.data.items() if k in active_set}
        self.processed_chunks = set(self.data.keys())
        try:
            self.filepath.write_text(json.dumps(self.data, indent=2))
        except Exception as e:
            logger.error(f"Failed to prune checkpoint file: {e}")


#!/usr/bin/env python3
"""
AskMukthiGuru Cache Flusher

Flushes:
  1. Qdrant semantic cache collection (semantic_query_cache)
  2. Redis (all keys) using auth password from settings

Designed to run INSIDE the Docker backend container where Python deps are installed:
  docker compose exec -T backend python3 /app/../scripts/ops/flush_cache.py

Or from the host Makefile via docker compose exec.
"""
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SEPARATOR = "═" * 55


def _flush_qdrant(qdrant_url: str, collection_name: str = "semantic_query_cache") -> bool:
    """Delete and recreate the Qdrant semantic cache collection."""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
    except ImportError:
        logger.warning("qdrant_client not installed — skipping Qdrant flush.")
        return False

    try:
        client = QdrantClient(url=qdrant_url, timeout=10)
        collections = [c.name for c in client.get_collections().collections]

        if collection_name in collections:
            client.delete_collection(collection_name)
            logger.info(f"✅ Qdrant collection '{collection_name}' deleted.")
        else:
            logger.info(f"ℹ️  Qdrant collection '{collection_name}' does not exist (already clean).")

        # Recreate an empty collection so the app can write to it immediately
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
        )
        logger.info(f"✅ Qdrant collection '{collection_name}' recreated (empty).")
        return True
    except Exception as e:
        logger.error(f"❌ Qdrant flush failed: {e}")
        return False


def _flush_redis(redis_url: str, password: str = None) -> bool:
    """Flush all Redis keys."""
    try:
        import redis as redis_lib
    except ImportError:
        logger.warning("redis package not installed — trying redis-cli fallback.")
        _redis_cli_fallback(password)
        return False

    try:
        if password:
            r = redis_lib.from_url(redis_url, password=password, socket_connect_timeout=5)
        else:
            r = redis_lib.from_url(redis_url, socket_connect_timeout=5)
        r.flushall()
        logger.info("✅ Redis flushed (all keys removed).")
        return True
    except Exception as e:
        logger.error(f"❌ Redis flush via client failed: {e}. Trying redis-cli fallback.")
        _redis_cli_fallback(password)
        return False


def _redis_cli_fallback(password: str = None) -> None:
    """Best-effort redis-cli flushall for environments without the Python package."""
    try:
        if password:
            cmd = f"redis-cli -a '{password}' flushall"
        else:
            cmd = "redis-cli flushall"
        ret = os.system(cmd)
        if ret == 0:
            logger.info("✅ Redis flushed via redis-cli.")
        else:
            logger.warning("⚠️  redis-cli returned non-zero; Redis may not be accessible.")
    except Exception as e:
        logger.warning(f"⚠️  redis-cli fallback failed: {e}")


def _load_settings():
    """Attempt to load backend settings for correct URLs/passwords."""
    try:
        # Add backend dir to path so app.config is importable inside container
        backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "backend")
        sys.path.insert(0, os.path.abspath(backend_dir))
        from app.config import settings
        return settings
    except Exception as e:
        logger.warning(f"Could not load app.config settings ({e}). Falling back to env vars.")
        return None


def main():
    print("\n" + SEPARATOR)
    print("  🧹  AskMukthiGuru Cache Flusher")
    print(SEPARATOR + "\n")

    settings = _load_settings()

    # --- Resolve connection parameters ---
    if settings:
        qdrant_url = getattr(settings, "qdrant_url", None) or os.getenv("QDRANT_URL", "http://qdrant:6333")
        redis_url = getattr(settings, "redis_url", None) or os.getenv("REDIS_URL", "redis://redis:6379/0")
        redis_password = getattr(settings, "redis_password", None) or os.getenv("REDIS_PASSWORD", "")
    else:
        qdrant_url = os.getenv("QDRANT_URL", "http://qdrant:6333")
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        redis_password = os.getenv("REDIS_PASSWORD", "")

    logger.info(f"Qdrant URL: {qdrant_url}")
    logger.info(f"Redis URL: {redis_url}")

    # --- Flush Qdrant semantic cache ---
    print("\n[1/2] Flushing Qdrant semantic cache collection...")
    _flush_qdrant(qdrant_url)

    # --- Flush Redis ---
    print("\n[2/2] Flushing Redis cache...")
    _flush_redis(redis_url, redis_password or None)

    print("\n" + SEPARATOR)
    print("  ✨  Cache flush complete.")
    print(SEPARATOR + "\n")


if __name__ == "__main__":
    main()

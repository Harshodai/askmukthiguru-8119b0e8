"""Celery tasks for web content ingestion."""
from __future__ import annotations
import logging
from celery import shared_task
from app.config import settings
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _sanitize_url(url: str) -> str:
    """Remove query string and fragment from URL for safe logging."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


@shared_task(
    bind=True,
    max_retries=getattr(settings, "ingest_url_max_retries", 2),
    default_retry_delay=getattr(settings, "ingest_url_retry_delay", 30),
    soft_time_limit=getattr(settings, "ingest_url_soft_time_limit", 120),
    time_limit=getattr(settings, "ingest_url_time_limit", 180),
)
def ingest_url_task(self, url: str, mode: str = "auto") -> dict:
    """Fetch a URL, extract clean text, chunk it, index into doctrine, return chunk metadata."""
    import asyncio
    from ingestion.web_ingest_pipeline import ingest_url
    safe_url = _sanitize_url(url)
    try:
        chunks = asyncio.run(ingest_url(url, mode=mode))
        logger.info("ingest_url_task: %s → %d chunks", safe_url, len(chunks))
        if chunks:
            _index_chunks(chunks)
            logger.info("ingest_url_task: %d chunks indexed into doctrine for %s", len(chunks), safe_url)
        return {"url": url, "chunks": len(chunks), "status": "ok"}
    except Exception as exc:
        logger.warning("ingest_url_task failed for %s: %s", safe_url, type(exc).__name__)
        raise self.retry(exc=exc)


def _index_chunks(chunks: list[dict]) -> None:
    """Embed and upsert chunks into Qdrant via the pipeline's ingest_raw_text."""
    import asyncio
    from ingest.pipeline import IngestionPipeline
    from services.embedding_service import EmbeddingService
    from services.qdrant_service import QdrantService
    embedder = EmbeddingService()
    qdrant = QdrantService()
    pipeline = IngestionPipeline(
        qdrant_service=qdrant,
        embedding_service=embedder,
        ollama_service=None,
        lightrag_service=None,
        ocr_service=None,
        semantic_cache_service=None,
    )
    for chunk in chunks:
        text = chunk.get("text", "")
        if not text.strip():
            continue
        asyncio.run(pipeline.ingest_raw_text(
            text=text,
            source_url=chunk.get("source", ""),
            title=chunk.get("title", ""),
            content_type="web_ingestion",
        ))

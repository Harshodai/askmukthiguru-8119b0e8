"""Specialized Celery tasks for the ingestion pipeline.

4 task types routed to separate queues:
  1. transcribe_video — YouTube URL → text transcript
  2. embed_chunks — text chunks → vector embeddings
  3. index_vectors — vectors → Qdrant storage
  4. orchestrate_ingestion — full pipeline coordinator
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Any, Optional

from celery import Task

from celery_config import celery_app

logger = logging.getLogger(__name__)


class AsyncTask(Task):
    """Base task with async support via asyncio.run()."""

    _loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop

    def run_async(self, coro):
        return self.loop.run_until_complete(coro)


@celery_app.task(base=AsyncTask, bind=True, max_retries=3, default_retry_delay=30)
def transcribe_video(self, video_url: str, language: str = "en") -> dict[str, Any]:
    """Transcribe a YouTube video to text."""
    logger.info(f"Transcribing: {video_url} (lang={language})")

    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        video_id = _extract_video_id(video_url)
        if not video_id:
            raise ValueError(f"Could not extract video ID from {video_url}")

        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=[language, "en"])
        full_text = " ".join(entry["text"] for entry in transcript_list)

        chunks = _chunk_text(full_text, chunk_size=1500, overlap=200)

        return {
            "status": "success",
            "video_url": video_url,
            "video_id": video_id,
            "full_text_length": len(full_text),
            "chunk_count": len(chunks),
            "chunks": chunks,
            "content_hash": hashlib.sha256(full_text.encode()).hexdigest()[:16],
        }
    except Exception as exc:
        logger.error(f"Transcription failed for {video_url}: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(base=AsyncTask, bind=True, max_retries=3, default_retry_delay=15)
def embed_chunks(self, chunks: list[str], content_hash: str) -> dict[str, Any]:
    """Generate embeddings for text chunks."""
    logger.info(f"Embedding {len(chunks)} chunks (hash={content_hash})")

    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("intfloat/multilingual-e5-large-instruct")
        embeddings = model.encode(chunks, normalize_embeddings=True, show_progress_bar=False)

        return {
            "status": "success",
            "content_hash": content_hash,
            "chunk_count": len(chunks),
            "embedding_dim": embeddings.shape[1],
            "embeddings": embeddings.tolist(),
        }
    except Exception as exc:
        logger.error(f"Embedding failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(base=AsyncTask, bind=True, max_retries=3, default_retry_delay=15)
def index_vectors(
    self,
    chunks: list[str],
    embeddings: list[list[float]],
    content_hash: str,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Index vectors into Qdrant."""
    logger.info(f"Indexing {len(chunks)} vectors (hash={content_hash})")

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qdrant_models

        qdrant_url = os.environ.get("QDRANT_URL", "http://qdrant:6333")
        client = QdrantClient(url=qdrant_url)

        collection = os.environ.get("QDRANT_COLLECTION", "spiritual_wisdom")

        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = hashlib.md5(f"{content_hash}:{i}".encode()).hexdigest()
            points.append(
                qdrant_models.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "content": chunk,
                        "chunk_index": i,
                        "content_hash": content_hash,
                        "source": (metadata or {}).get("source", ""),
                        "title": (metadata or {}).get("title", ""),
                    },
                )
            )

        client.upsert(collection_name=collection, points=points)

        return {
            "status": "success",
            "content_hash": content_hash,
            "indexed_count": len(points),
            "collection": collection,
        }
    except Exception as exc:
        logger.error(f"Indexing failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(base=AsyncTask, bind=True, max_retries=2, default_retry_delay=60)
def orchestrate_ingestion(
    self,
    video_url: str,
    language: str = "en",
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Orchestrate the full ingestion pipeline as a chain of tasks."""
    logger.info(f"Orchestrating ingestion for: {video_url}")

    try:
        result = transcribe_video(video_url, language)
        if result.get("status") != "success":
            raise RuntimeError(f"Transcription failed: {result}")

        chunks = result["chunks"]
        content_hash = result["content_hash"]

        embed_result = embed_chunks(chunks, content_hash)
        if embed_result.get("status") != "success":
            raise RuntimeError(f"Embedding failed: {embed_result}")

        index_result = index_vectors(chunks, embed_result["embeddings"], content_hash, metadata)
        if index_result.get("status") != "success":
            raise RuntimeError(f"Indexing failed: {index_result}")

        return {
            "status": "success",
            "video_url": video_url,
            "content_hash": content_hash,
            "transcription": {"chunks": len(chunks)},
            "embedding": {"count": embed_result["chunk_count"]},
            "indexing": {"count": index_result["indexed_count"]},
        }
    except Exception as exc:
        logger.error(f"Orchestration failed for {video_url}: {exc}")
        raise self.retry(exc=exc)


def _extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from various URL formats."""
    import re
    patterns = [
        r"(?:v=)([\w-]{11})",
        r"(?:youtu\.be/)([\w-]{11})",
        r"(?:embed/)([\w-]{11})",
        r"(?:shorts/)([\w-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _chunk_text(text: str, chunk_size: int = 1500, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks at sentence boundaries."""
    sentences = text.replace("! ", "!||").replace("? ", "?||").replace(". ", ".||").split("||")
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) <= chunk_size:
            current += (" " if current else "") + sentence
        else:
            if current:
                chunks.append(current)
            overlap_text = current[-overlap:] if len(current) > overlap else current
            current = overlap_text + " " + sentence
    if current:
        chunks.append(current)
    return chunks
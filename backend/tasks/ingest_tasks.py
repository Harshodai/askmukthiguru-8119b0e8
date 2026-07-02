"""Specialized Celery tasks for the ingestion pipeline.

4 task types routed to separate queues:
  1. transcribe_video — YouTube URL → text transcript (3-tier: captions → Whisper → auto)
  2. embed_chunks — text chunks → vector embeddings (project's all-MiniLM-L6-v2)
  3. index_vectors — vectors → Qdrant storage (batch upload, 1000-pt batches)
  4. orchestrate_ingestion — full pipeline coordinator with job tracking
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Any, Optional

from celery import Task

from celery_config import celery_app, update_job_progress, retry_backoff

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


@celery_app.task(base=AsyncTask, bind=True, max_retries=3)
def transcribe_video(self, video_url: str, language: str = "en", job_id: str = None) -> dict[str, Any]:
    """Transcribe a YouTube video to text (3-tier: captions → Whisper → auto)."""
    if job_id:
        update_job_progress(job_id, "running", progress_pct=10, worker_id=self.request.hostname)

    try:
        video_id = _extract_video_id(video_url)
        if not video_id:
            raise ValueError(f"Could not extract video ID from {video_url}")

        # Tier 1: Try manual/caption transcripts first (fastest)
        full_text, tier_used = _transcribe_tier1(video_id, language)

        # Tier 2: Whisper if captions unavailable
        if not full_text:
            full_text, tier_used = _transcribe_tier2(video_url, language)

        # Tier 3: Auto-captions as last resort
        if not full_text:
            full_text, tier_used = _transcribe_tier3(video_id, language)

        if not full_text:
            raise RuntimeError(f"All transcription tiers failed for {video_url}")

        chunks = _chunk_text(full_text, chunk_size=500, overlap=50)

        if job_id:
            update_job_progress(job_id, "running", progress_pct=40, chunks_indexed=0)

        return {
            "status": "success",
            "video_url": video_url,
            "video_id": video_id,
            "transcription_tier": tier_used,
            "full_text_length": len(full_text),
            "chunk_count": len(chunks),
            "chunks": chunks,
            "content_hash": hashlib.sha256(full_text.encode()).hexdigest()[:16],
        }
    except Exception as exc:
        logger.error(f"Transcription failed for {video_url}: {exc}")
        if job_id:
            update_job_progress(job_id, "failed", error_message=str(exc))
        delay = min(2 ** self.request.retries * 5, 30)
        raise self.retry(exc=exc, countdown=delay)


@celery_app.task(base=AsyncTask, bind=True, max_retries=3)
def embed_chunks(self, chunks: list[str], content_hash: str, job_id: str = None) -> dict[str, Any]:
    """Generate embeddings for text chunks using project's all-MiniLM-L6-v2."""
    logger.info(f"Embedding {len(chunks)} chunks (hash={content_hash})")

    if job_id:
        update_job_progress(job_id, "running", progress_pct=60)

    try:
        from services.embedding_service import EmbeddingService

        embedder = EmbeddingService()
        result = embedder.encode_batch(chunks)
        embeddings = result["dense"]

        if hasattr(embeddings, "tolist"):
            embeddings = embeddings.tolist()

        return {
            "status": "success",
            "content_hash": content_hash,
            "chunk_count": len(chunks),
            "embedding_dim": len(embeddings[0]) if embeddings else 0,
            "embeddings": embeddings,
        }
    except Exception as exc:
        logger.error(f"Embedding failed: {exc}")
        if job_id:
            update_job_progress(job_id, "failed", error_message=str(exc))
        delay = min(2 ** self.request.retries * 5, 30)
        raise self.retry(exc=exc, countdown=delay)


@celery_app.task(base=AsyncTask, bind=True, max_retries=3)
def index_vectors(
    self,
    chunks: list[str],
    embeddings: list[list[float]],
    content_hash: str,
    metadata: Optional[dict[str, Any]] = None,
    job_id: str = None,
) -> dict[str, Any]:
    """Index vectors into Qdrant (batch upload, 1000-pt batches)."""
    logger.info(f"Indexing {len(chunks)} vectors (hash={content_hash})")

    if job_id:
        update_job_progress(job_id, "running", progress_pct=80)

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

        # Batch upload — 1000 points per batch for efficiency
        batch_size = 1000
        for batch_start in range(0, len(points), batch_size):
            batch = points[batch_start : batch_start + batch_size]
            client.upsert(collection_name=collection, points=batch)
            if job_id:
                update_job_progress(
                    job_id,
                    "running",
                    progress_pct=80 + int(20 * batch_start / max(len(points), 1)),
                    chunks_indexed=batch_start + len(batch),
                )

        if job_id:
            update_job_progress(job_id, "running", progress_pct=95, chunks_indexed=len(points))

        return {
            "status": "success",
            "content_hash": content_hash,
            "indexed_count": len(points),
            "collection": collection,
        }
    except Exception as exc:
        logger.error(f"Indexing failed: {exc}")
        if job_id:
            update_job_progress(job_id, "failed", error_message=str(exc))
        delay = min(2 ** self.request.retries * 5, 30)
        raise self.retry(exc=exc, countdown=delay)


@celery_app.task(base=AsyncTask, bind=True, max_retries=2)
def orchestrate_ingestion(
    self,
    video_url: str,
    language: str = "en",
    metadata: Optional[dict[str, Any]] = None,
    job_id: str = None,
) -> dict[str, Any]:
    """Orchestrate the full ingestion pipeline as a chain of tasks."""
    logger.info(f"Orchestrating ingestion for: {video_url}")

    if job_id:
        update_job_progress(job_id, "running", progress_pct=5, worker_id=self.request.hostname)

    try:
        result = transcribe_video(video_url, language, job_id=job_id)
        if result.get("status") != "success":
            raise RuntimeError(f"Transcription failed: {result}")

        chunks = result["chunks"]
        content_hash = result["content_hash"]

        # Run quality gate on the full text (reconstructed from chunks)
        raw_text = " ".join(chunks)
        
        # Instantiate services needed for quality gate
        from services.ollama_service import OllamaService
        from app.config import settings
        from supabase import create_client
        
        llm = OllamaService()
        supabase_client = None
        if settings.supabase_url and settings.supabase_key:
            try:
                supabase_client = create_client(settings.supabase_url, settings.supabase_key)
            except Exception as e:
                logger.warning(f"Could not init Supabase in Celery task: {e}")
                
        from ingest.quality_gate import DataQualityGate
        gate = DataQualityGate(
            llm_service=llm,
            supabase_client=supabase_client,
            quality_threshold=getattr(settings, "data_quality_threshold", 65),
            enabled=getattr(settings, "data_quality_gate_enabled", True)
        )
        
        # Run quality gate
        if job_id:
            update_job_progress(job_id, "running", progress_pct=50)
            
        quality_result = self.run_async(gate.run(raw_text, source_url=video_url))
        
        if not quality_result.passed:
            msg = f"Rejected by quality gate: score {quality_result.score}/100. Reasons: {'; '.join(quality_result.reasons)}. Staging ID: {quality_result.staging_id or 'N/A'}"
            logger.warning(msg)
            if job_id:
                update_job_progress(job_id, "failed", error_message=msg)
            return {
                "status": "rejected",
                "message": msg,
                "video_url": video_url,
                "content_hash": content_hash,
                "quality_score": quality_result.score,
                "staging_id": quality_result.staging_id,
            }

        # Quality passed, continue to embedding
        if job_id:
            update_job_progress(job_id, "running", progress_pct=60)

        embed_result = embed_chunks(chunks, content_hash, job_id=job_id)
        if embed_result.get("status") != "success":
            raise RuntimeError(f"Embedding failed: {embed_result}")

        index_result = index_vectors(
            chunks, embed_result["embeddings"], content_hash, metadata, job_id=job_id
        )
        if index_result.get("status") != "success":
            raise RuntimeError(f"Indexing failed: {index_result}")

        if job_id:
            update_job_progress(job_id, "completed", progress_pct=100, chunks_indexed=index_result["indexed_count"])

        return {
            "status": "success",
            "video_url": video_url,
            "content_hash": content_hash,
            "transcription": {"chunks": len(chunks), "tier": result.get("transcription_tier", "unknown")},
            "embedding": {"count": embed_result["chunk_count"]},
            "indexing": {"count": index_result["indexed_count"]},
            "quality_score": quality_result.score,
        }
    except Exception as exc:
        logger.error(f"Orchestration failed for {video_url}: {exc}")
        if job_id:
            update_job_progress(job_id, "failed", error_message=str(exc))
        delay = min(2 ** self.request.retries * 5, 30)
        raise self.retry(exc=exc, countdown=delay)


# ---- Transcription tiers ----

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


def _transcribe_tier1(video_id: str, language: str) -> tuple[str, str]:
    """Tier 1: Manual/caption transcripts (fastest)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=[language, "en"])
        full_text = " ".join(entry["text"] for entry in transcript_list)
        return full_text, "captions"
    except Exception:
        return "", ""


def _transcribe_tier2(video_url: str, language: str) -> tuple[str, str]:
    """Tier 2: Whisper (faster-whisper large-v3)."""
    try:
        from faster_whisper import WhisperModel

        # ponytail: download model lazily, reuse across calls
        model_size = os.environ.get("WHISPER_MODEL", "large-v3")
        compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")
        model = WhisperModel(model_size, device="cuda" if _cuda_available() else "cpu", compute_type=compute_type)

        # Download audio via yt-dlp
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, "audio.mp3")
            subprocess.run(
                ["yt-dlp", "-x", "--audio-format", "mp3", "-o", audio_path, video_url],
                check=True,
                capture_output=True,
                timeout=300,
            )
            segments, info = model.transcribe(audio_path, language=language if language != "en" else None)
            full_text = " ".join(s.text for s in segments)

        return full_text, "whisper"
    except Exception as e:
        logger.warning(f"Whisper transcription failed: {e}")
        return "", ""


def _transcribe_tier3(video_id: str, language: str) -> tuple[str, str]:
    """Tier 3: Auto-generated captions (lowest quality)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        # Try auto-generated captions
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=[language, "en"], preserve_formatting=False)
        # Filter for auto-generated (often lower quality)
        full_text = " ".join(entry["text"] for entry in transcript_list)
        return full_text, "auto_captions"
    except Exception:
        return "", ""


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
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


def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


@celery_app.task(bind=True, max_retries=2)
def ingest_playlist(self, playlist_url: str, language: str = "en", tags: Optional[list[str]] = None, job_id: str = None) -> dict[str, Any]:
    """Process a playlist: extract video URLs, create ingest_jobs for each, and chain them as a Celery chord."""
    from ingest.youtube_loader import get_playlist_video_urls
    from celery import chord
    from app.config import settings
    from supabase import create_client

    logger.info(f"Extracting playlist videos for URL: {playlist_url}")
    if job_id:
        update_job_progress(job_id, "running", progress_pct=10, worker_id=self.request.hostname)

    videos = get_playlist_video_urls(playlist_url)
    if not videos:
        err_msg = "No videos found in playlist or failed to extract."
        logger.error(err_msg)
        if job_id:
            update_job_progress(job_id, "failed", error_message=err_msg)
        return {"status": "failed", "error": err_msg}

    child_tasks = []
    supabase_client = None
    if settings.supabase_url and settings.supabase_key:
        try:
            supabase_client = create_client(settings.supabase_url, settings.supabase_key)
        except Exception as e:
            logger.warning(f"Could not init Supabase in ingest_playlist: {e}")

    for idx, video in enumerate(videos):
        child_job_id = None
        if supabase_client:
            try:
                resp = supabase_client.table("ingest_jobs").insert({
                    "source": video["url"],
                    "status": "queued",
                    "progress_pct": 0,
                    "tags": tags or ["general"],
                }).execute()
                if resp.data:
                    child_job_id = resp.data[0]["id"]
            except Exception as e:
                logger.warning(f"Failed to create child job record: {e}")

        metadata = {
            "title": video.get("title", "Unknown"),
            "speaker": video.get("speaker", "Unknown"),
            "topic": video.get("topic", "Spiritual"),
        }
        child_tasks.append(
            orchestrate_ingestion.signature(
                args=[video["url"]],
                kwargs={
                    "language": language,
                    "metadata": metadata,
                    "job_id": child_job_id,
                }
            )
        )

    callback = playlist_complete.s(playlist_url=playlist_url, parent_job_id=job_id, total_count=len(videos))
    chord(child_tasks)(callback)

    return {
        "status": "queued",
        "video_count": len(videos),
        "message": f"Queued chord with {len(videos)} videos.",
    }


@celery_app.task(bind=True)
def playlist_complete(self, results, playlist_url: str, parent_job_id: str = None, total_count: int = 0) -> dict[str, Any]:
    """Called when all orchestrate_ingestion tasks in the playlist chord finish."""
    success_count = 0
    fail_count = 0
    rejected_count = 0
    indexed_chunks = 0

    for r in results:
        if not r:
            fail_count += 1
            continue
        status = r.get("status")
        if status == "success":
            success_count += 1
            indexed_chunks += r.get("indexing", {}).get("count", 0)
        elif status == "rejected":
            rejected_count += 1
        else:
            fail_count += 1

    msg = f"Playlist ingestion completed: {success_count}/{total_count} succeeded, {rejected_count} rejected by quality gate, {fail_count} failed."
    logger.info(msg)

    if parent_job_id:
        status_str = "completed" if fail_count == 0 else "failed"
        update_job_progress(
            parent_job_id,
            status_str,
            progress_pct=100,
            chunks_indexed=indexed_chunks,
            error_message=None if fail_count == 0 else msg
        )

    return {
        "status": "success",
        "playlist_url": playlist_url,
        "total": total_count,
        "success": success_count,
        "rejected": rejected_count,
        "failed": fail_count,
        "chunks_indexed": indexed_chunks,
    }

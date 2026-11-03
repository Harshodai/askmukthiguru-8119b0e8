"""Video ingestion pipeline for MukthiGuru.

Extracts audio from video, transcribes with Whisper, chunks, embeds, and upserts to Qdrant.
Ponytail: optional features (diarization, VLM) stubbed with graceful skip if deps missing.
"""

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional

from ingest.cleaner import clean_transcript
from services.embedding_service import EmbeddingService
from services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)

try:
    import ffmpeg
except ImportError:
    ffmpeg = None  # type: ignore


@dataclass
class VideoIngestResult:
    chunks_ingested: int
    duration_seconds: float
    transcript_preview: str
    status: str
    # The exact point ids written for this file. A caller that wants to stamp
    # extra payload onto the chunks must use these ids: they are uuid5 ids, and
    # a caller that reconstructs them from "video_id_index" writes to ids that
    # do not exist (silent no-op — the direct-video upload path did exactly that).
    point_ids: list[str] = field(default_factory=list)


class VideoPipeline:
    """Ingest a video file: extract audio -> transcribe -> chunk -> embed -> upsert."""

    def __init__(
        self,
        qdrant_service: QdrantService,
        embedding_service: EmbeddingService,
        whisper_service: Optional[Any] = None,
    ):
        self._qdrant = qdrant_service
        self._embedder = embedding_service
        self._whisper = whisper_service

    async def ingest_video(self, file_path: str) -> VideoIngestResult:
        """Ingest a single video file."""
        logger.info("Starting video ingestion: %s", file_path)
        if not os.path.exists(file_path):
            return VideoIngestResult(0, 0.0, "", "file_not_found")

        # 1. Extract audio to temporary WAV
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, "audio.wav")
            duration = await self._extract_audio(file_path, audio_path)

            # 2. Transcribe with Whisper
            transcript = await self._transcribe(audio_path)
            if not transcript or len(transcript.strip()) < 50:
                return VideoIngestResult(0, duration, transcript[:200], "transcript_too_short")

        # 3. Clean transcript
        cleaned = clean_transcript(transcript)

        # 4. Chunk text
        chunks = self._chunk_text(cleaned)
        if not chunks:
            return VideoIngestResult(0, duration, cleaned[:200], "no_chunks")

        # 5. Embed and upsert
        written, point_ids = await self._upsert_chunks(chunks, file_path)
        if written == 0:
            return VideoIngestResult(0, duration, cleaned[:200], "chunks_rejected")

        return VideoIngestResult(
            chunks_ingested=written,
            duration_seconds=duration,
            transcript_preview=cleaned[:500],
            status="ok",
            point_ids=point_ids,
        )

    async def _extract_audio(self, video_path: str, output_path: str) -> float:
        """Extract audio from video using ffmpeg. Returns estimated duration."""
        import subprocess

        try:
            if ffmpeg is not None:
                # ponytail: use ffmpeg-python when available for cleaner syntax
                (
                    ffmpeg.input(video_path)
                    .output(output_path, ac=1, ar=16000)
                    .overwrite_output()
                    .run(quiet=True)
                )
            else:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-i",
                        video_path,
                        "-vn",
                        "-acodec",
                        "pcm_s16le",
                        "-ac",
                        "1",
                        "-ar",
                        "16000",
                        "-y",
                        output_path,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
        except Exception:
            logger.error("ffmpeg audio extraction failed for %s", video_path)
            raise

        # Estimate duration via ffprobe
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    video_path,
                ],
                capture_output=True,
                text=True,
            )
            return float(result.stdout.strip()) if result.returncode == 0 else 0.0
        except Exception:
            return 0.0

    async def _transcribe(self, audio_path: str) -> str:
        """Transcribe audio using local Whisper.

        Falls back to the module-level ``transcribe_with_whisper`` helper when
        no Whisper service was injected (production bulk-ingest caller constructs
        VideoPipeline without ``whisper_service``), mirroring social_media_loader.
        """
        import concurrent.futures

        if self._whisper is None:
            # ponytail: thin fallback — delegate to the shared mlx-whisper helper
            def _run_fallback(path: str) -> str:
                from services.whisper_local_service import transcribe_with_whisper

                text = transcribe_with_whisper("", path)
                if not text:
                    raise RuntimeError("Whisper transcription returned empty result")
                return text

            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return await loop.run_in_executor(pool, _run_fallback, audio_path)

        # ponytail: direct run_sync call into thread pool for blocking whisper
        def _run_whisper(path: str) -> str:
            try:
                result = self._whisper.transcribe(path)
                if isinstance(result, dict):
                    return result.get("text", "")
                return str(result)
            except Exception:
                # Fallback: try faster-whisper style
                try:
                    raw = self._whisper.model.transcribe(path)
                    if isinstance(raw, dict) and "text" in raw:
                        return raw["text"]
                    if isinstance(raw, str):
                        return raw
                except Exception as _e:
                    logger.debug("[video ingest] suppressed non-critical error: %s", _e)
                raise

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, _run_whisper, audio_path)

    def _chunk_text(self, text: str, chunk_size: int = 0, overlap: int = 0) -> list[str]:
        """Chunk text using AdaptiveChunker (preferred) or RecursiveCharacterTextSplitter fallback.

        Uses config-driven chunk sizes from settings.rag_chunk_size / settings.rag_chunk_overlap.
        AdaptiveChunker auto-selects Recursive vs Semantic strategy based on intrinsic quality scoring.
        """
        from app.config import settings

        # Use config values if not explicitly overridden by caller
        effective_size = chunk_size or settings.rag_chunk_size
        effective_overlap = overlap or settings.rag_chunk_overlap

        # Prefer AdaptiveChunker (same strategy used by IngestionPipeline._split_text)
        if getattr(settings, "use_adaptive_chunking", True):
            try:
                from ingest.adaptive_chunking import AdaptiveChunker

                chunker = AdaptiveChunker(
                    embedder=self._embedder,
                    chunk_size=effective_size,
                    chunk_overlap=effective_overlap,
                )
                return chunker.chunk_document(text)
            except Exception as e:
                logger.warning(
                    "AdaptiveChunker unavailable in VideoPipeline (%s) — falling back to recursive",
                    e,
                )

        # Fallback: RecursiveCharacterTextSplitter with config-driven sizes
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=effective_size,
                chunk_overlap=effective_overlap,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            return splitter.split_text(text)
        except Exception:
            # ponytail: last-resort naive word-window
            words = text.split()
            step = max(effective_size - effective_overlap, 1)
            return [" ".join(words[i : i + effective_size]) for i in range(0, len(words), step)]

    async def _upsert_chunks(self, chunks: list, source: str) -> tuple[int, list[str]]:
        """Embed and upsert chunks to Qdrant with modality:video.

        Returns ``(written, point_ids)`` — the number of points actually written
        after the quality gate, and the uuid5 ids those points carry. Zero
        written means every chunk was rejected, so callers can distinguish a
        clean skip from a successful write. ``point_ids`` exists so a caller can
        stamp payload onto exactly the points this write created instead of
        rebuilding ids it cannot know (the direct-video path did the latter and
        silently wrote to nothing).
        """
        import hashlib
        import uuid

        from app.config import settings
        from services.qdrant.client import QdrantClientManager
        from services.qdrant.indexer import QdrantIndexer, resolve_source_rights_status
        from services.text_quality_filter import select_clean

        _keep, _rejected = select_clean(chunks)
        if _rejected:
            logger.warning(
                "video_pipeline: rejected %d/%d chunks from %s failing the "
                "quality gate. First: %r in %r",
                len(_rejected),
                len(chunks),
                source,
                _rejected[0][1],
                _rejected[0][2],
            )
            chunks = [chunks[i] for i in _keep]
        if not chunks:
            logger.warning("video_pipeline: all chunks from %s rejected — nothing written", source)
            return 0, []

        embeddings = self._embedder.embed(chunks)
        texts = chunks
        vectors = embeddings
        # Rights are resolved once per file, from the curated register, and fail
        # closed to "unverified". A caller must never overwrite this with a
        # hardcoded "licensed" (X40: register -> stamp -> filter -> enforce).
        rights_status = resolve_source_rights_status(source)
        metadatas = []
        point_ids: list[str] = []
        for i, chunk in enumerate(texts):
            content_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:16]
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}_{i}_0"))
            point_ids.append(point_id)
            metadatas.append(
                {
                    "text": chunk,
                    "source_url": source,
                    "title": "",
                    "speaker": "Unknown",
                    "topic": "Spiritual",
                    "chunk_index": i,
                    "content_type": "video_transcript",
                    "raptor_level": 0,
                    "chunker_version": "v10",
                    "parent_id_scheme": "url_hash",
                    "modality": "video",
                    "rights_status": rights_status,
                    "content_hash": content_hash,
                    "point_id": point_id,
                }
            )

        collection_name = getattr(settings, "qdrant_collection", "mukthi_guru")
        client = getattr(self._qdrant, "_client", None) or QdrantClientManager().client
        indexer = QdrantIndexer(client=client, collection=collection_name)
        written = indexer.upsert_chunks(
            texts=texts,
            vectors=vectors,
            metadatas=metadatas,
            replace_source_url=source,
        )
        logger.info("Upserted %d video chunks via QdrantIndexer", written)
        return written, point_ids[:written] if written else []

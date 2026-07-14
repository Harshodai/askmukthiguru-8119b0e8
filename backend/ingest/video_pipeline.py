"""Video ingestion pipeline for MukthiGuru.

Extracts audio from video, transcribes with Whisper, chunks, embeds, and upserts to Qdrant.
Ponytail: optional features (diarization, VLM) stubbed with graceful skip if deps missing.
"""

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
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
        await self._upsert_chunks(chunks, file_path)

        return VideoIngestResult(
            chunks_ingested=len(chunks),
            duration_seconds=duration,
            transcript_preview=cleaned[:500],
            status="ok",
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
                    ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "-y", output_path],
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
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                capture_output=True,
                text=True,
            )
            return float(result.stdout.strip()) if result.returncode == 0 else 0.0
        except Exception:
            return 0.0

    async def _transcribe(self, audio_path: str) -> str:
        """Transcribe audio using local Whisper."""
        if self._whisper is None:
            raise RuntimeError("Whisper service not available")
        # ponytail: direct run_sync call into thread pool for blocking whisper
        import concurrent.futures

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
                except Exception:
                    pass
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
                logger.warning("AdaptiveChunker unavailable in VideoPipeline (%s) — falling back to recursive", e)

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

    async def _upsert_chunks(self, chunks: list, source: str) -> None:
        """Embed and upsert chunks to Qdrant with modality:video."""
        import uuid

        embeddings = self._embedder.embed(chunks)
        points = []
        for i, (chunk, vec) in enumerate(zip(chunks, embeddings)):
            points.append(
                {
                    "id": str(uuid.uuid4()),
                    "vector": vec,
                    "payload": {
                        "text": chunk,
                        "source": source,
                        "modality": "video",
                        "chunk_index": i,
                    },
                }
            )
        await self._qdrant.upsert("mukthi_guru", points)
        logger.info("Upserted %d video chunks", len(points))

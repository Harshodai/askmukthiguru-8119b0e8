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
        qdrant_service: Optional[QdrantService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        whisper_service: Optional[Any] = None,
    ):
        if embedding_service is None:
            embedding_service = EmbeddingService()
        if qdrant_service is None:
            qdrant_service = QdrantService()
        self._qdrant = qdrant_service
        self._embedder = embedding_service
        self._whisper = whisper_service

    async def ingest_video(
        self,
        file_path: str,
        *,
        speaker: str = "",
        title: str = "",
        video_id: Optional[str] = None,
        audio_path: Optional[str] = None,
        collection_name: Optional[str] = None,
        graph_namespace: Optional[str] = None,
    ) -> VideoIngestResult:
        """Ingest a single video file.

        ``speaker`` / ``title`` / ``video_id`` come from the caller so the payload
        names the source instead of ``"Unknown"``. ``audio_path`` is an already
        extracted 16 kHz mono WAV owned by the caller (the upload route archives one
        before it calls in); when it is absent this method extracts its own into a
        temporary directory that lives until the write finishes.
        """
        logger.info("Starting video ingestion: %s", file_path)
        if not os.path.exists(file_path):
            return VideoIngestResult(0, 0.0, "", "file_not_found")

        import contextlib

        with contextlib.ExitStack() as stack:
            if audio_path and os.path.exists(audio_path):
                resolved_audio = audio_path
                duration = await self._probe_duration(file_path)
            else:
                tmpdir = stack.enter_context(tempfile.TemporaryDirectory())
                resolved_audio = os.path.join(tmpdir, "audio.wav")
                duration = await self._extract_audio(file_path, resolved_audio)

            # 2. Transcribe with Whisper (text + real segment timings when available)
            transcript, segments = await self._transcribe_with_segments(resolved_audio, video_id)
            if not transcript or len(transcript.strip()) < 50:
                return VideoIngestResult(0, duration, (transcript or "")[:200], "transcript_too_short")

            # 3. Clean transcript
            cleaned = clean_transcript(transcript)

            # 4. Chunk text
            chunks, chunker_version = self._chunk_text_with_version(cleaned)
            if not chunks:
                return VideoIngestResult(0, duration, cleaned[:200], "no_chunks")

            # 5. Per-chunk timing from the ASR segments. Unknown timing stays None:
            # a timestamp on the wrong chunk is a misattribution-class defect, and the
            # speaker gate needs real bounds to score anything.
            chunk_starts, chunk_ends = self._align_chunk_timings(chunks, segments)

            # 6. Embed and upsert (inside the stack: the WAV must outlive the gate)
            written, point_ids = await self._upsert_chunks(
                chunks,
                file_path,
                speaker=speaker,
                title=title,
                video_id=video_id,
                chunk_starts=chunk_starts,
                chunk_ends=chunk_ends,
                chunker_version=chunker_version,
                audio_path=resolved_audio,
                collection_name=collection_name,
                graph_namespace=graph_namespace,
            )

        if written == 0:
            return VideoIngestResult(0, duration, cleaned[:200], "chunks_rejected")

        return VideoIngestResult(
            chunks_ingested=written,
            duration_seconds=duration,
            transcript_preview=cleaned[:500],
            status="ok",
            point_ids=point_ids,
        )

    async def _probe_duration(self, video_path: str) -> float:
        """Duration in seconds via ffprobe; 0.0 when unknown."""
        import subprocess

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

    async def _transcribe(self, audio_path: str, video_id: str = "") -> str:
        """Transcribe audio using local Whisper.

        Falls back to the module-level ``transcribe_with_whisper`` helper when
        no Whisper service was injected (production bulk-ingest caller constructs
        VideoPipeline without ``whisper_service``), mirroring social_media_loader.

        ``video_id`` is the cache key the helper uses to stash the full ASR result
        (segments + word times) so :meth:`_transcribe_with_segments` can read real
        timings afterwards. Passing an empty key stored the result under ``""`` and
        every later lookup missed.
        """
        import concurrent.futures

        if self._whisper is None:
            # ponytail: thin fallback — delegate to the shared mlx-whisper helper
            def _run_fallback(path: str) -> str:
                from services.whisper_local_service import transcribe_with_whisper

                text = transcribe_with_whisper(video_id, path)
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
        chunks, _version = self._chunk_text_with_version(text, chunk_size, overlap)
        return chunks

    def _chunk_text_with_version(
        self, text: str, chunk_size: int = 0, overlap: int = 0
    ) -> tuple[list[str], str]:
        """Chunk text and name the chunker that actually ran.

        The returned version is a real chunker identifier per the payload grammar
        (``adaptive_v1`` / ``recursive_v1:…``), never the old hardcoded ``"v10"``:
        a ``chunker_version`` that does not name an algorithm is a false provenance
        claim (AGENTS.md X40).
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
                    embedding_service=self._embedder,
                    chunk_size=effective_size,
                    chunk_overlap=effective_overlap,
                )
                return chunker.chunk_document(text), "adaptive_v1"
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
            return splitter.split_text(text), "recursive_v1:langchain"
        except Exception:
            # ponytail: last-resort naive word-window
            words = text.split()
            step = max(effective_size - effective_overlap, 1)
            return (
                [" ".join(words[i : i + effective_size]) for i in range(0, len(words), step)],
                "recursive_v1:word_window_fallback",
            )

    async def _transcribe_with_segments(
        self, audio_path: str, video_id: Optional[str] = None
    ) -> tuple[str, list[dict[str, Any]]]:
        """Transcribe and return ``(text, segments)``.

        Segments come from the shared whisper cache (populated by
        ``transcribe_with_whisper``) or from an injected service that returns a
        dict. No segments means no timings, which means the speaker gate stamps
        ``pending_voice_check`` — never a guessed window.
        """
        key = video_id or os.path.splitext(os.path.basename(audio_path))[0]
        segments: list[dict[str, Any]] = []

        # If _transcribe was patched on this instance (e.g. in tests), honor it
        if getattr(self._transcribe, "__func__", None) is not VideoPipeline._transcribe:
            import inspect

            sig = inspect.signature(self._transcribe)
            if len(sig.parameters) == 1:
                text = await self._transcribe(audio_path)
            else:
                text = await self._transcribe(audio_path, video_id=key)
            return text, []

        if self._whisper is None:
            text = await self._transcribe(audio_path, video_id=key)
            try:
                from services.whisper_local_service import get_cached_whisperx_result

                cached = get_cached_whisperx_result(key)
                if isinstance(cached, dict):
                    segments = list(cached.get("segments") or [])
            except Exception as exc:
                logger.debug("video_pipeline: segment cache lookup failed: %s", exc)
            return text, segments

        def _run() -> tuple[str, list[dict[str, Any]]]:
            raw = self._whisper.transcribe(audio_path)
            if isinstance(raw, dict):
                return str(raw.get("text", "")), list(raw.get("segments") or [])
            return str(raw), []

        loop = asyncio.get_running_loop()
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, _run)

    @staticmethod
    def _align_chunk_timings(
        chunks: list[str], segments: list[dict[str, Any]]
    ) -> tuple[list[Optional[float]], list[Optional[float]]]:
        """Map each chunk to ``(start_s, end_s)`` from real ASR segments.

        Same word-overlap rule as ``ingest/pipeline.py::_resolve_chunk_timing_from_cache``:
        the segment sharing the most words with the chunk defines its span. No
        overlap → ``None`` for both, never an interpolation.
        """
        starts: list[Optional[float]] = [None] * len(chunks)
        ends: list[Optional[float]] = [None] * len(chunks)
        if not chunks or not segments:
            return starts, ends

        import re

        def words(value: str) -> list[str]:
            return re.findall(r"[a-z0-9']+", (value or "").lower())

        seg_words = [words(str(seg.get("text") or "")) for seg in segments]

        for index, chunk in enumerate(chunks):
            chunk_words = words(chunk)
            if not chunk_words:
                continue
            best = -1
            best_hits = 0
            for seg_index, seg in enumerate(seg_words):
                hits = len(set(chunk_words) & set(seg))
                if hits > best_hits:
                    best, best_hits = seg_index, hits
            if best < 0 or best_hits == 0:
                continue
            start = segments[best].get("start")
            end = segments[best].get("end")
            if start is None or end is None:
                continue
            starts[index] = float(start)
            ends[index] = float(end)
        return starts, ends

    async def _upsert_chunks(
        self,
        chunks: list,
        source: str,
        *,
        speaker: str = "",
        title: str = "",
        video_id: Optional[str] = None,
        chunk_starts: Optional[list[Optional[float]]] = None,
        chunk_ends: Optional[list[Optional[float]]] = None,
        chunker_version: str = "unknown_legacy",
        audio_path: Optional[str] = None,
        collection_name: Optional[str] = None,
        graph_namespace: Optional[str] = None,
    ) -> tuple[int, list[str]]:
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
            if chunk_starts is not None:
                chunk_starts = [chunk_starts[i] for i in _keep if i < len(chunk_starts)]
            if chunk_ends is not None:
                chunk_ends = [chunk_ends[i] for i in _keep if i < len(chunk_ends)]
        if not chunks:
            logger.warning("video_pipeline: all chunks from %s rejected — nothing written", source)
            return 0, []

        # Per-chunk speaker labels: a single-file upload names one speaker for the
        # whole file, so the caller's label applies to every chunk. It is only a
        # label — the voice gate below decides whether the claim is evidenced.
        chunk_speakers = [speaker or None] * len(chunks)

        # Windowed ECAPA gate. Fail-closed: no audio or no verdict → the chunk is
        # stamped pending_voice_check, never speaker_verified.
        chunk_voice: list[dict[str, Any]] = []
        try:
            from services import speaker_gate

            chunk_voice = speaker_gate.annotate_chunks(
                chunks=chunks,
                starts=[
                    None if s is None else float(s) * 1000.0 for s in chunk_starts
                ]
                if chunk_starts is not None
                else None,
                ends=[None if e is None else float(e) * 1000.0 for e in chunk_ends]
                if chunk_ends is not None
                else None,
                speakers=chunk_speakers,
                audio_path=audio_path,
                video_id=video_id,
                source_url=source,
            )
        except Exception as exc:
            logger.warning("video_pipeline: speaker gate failed for %s: %s", source, exc)
            chunk_voice = []

        # EmbeddingService exposes ``encode_batch`` (dense + sparse), while a
        # few lightweight callers still provide the older dense-only ``encode``
        # or test-only ``embed`` shape. Prefer the canonical hybrid API and
        # preserve the compatibility fallbacks without changing production
        # vector dimensions or inventing sparse values.
        sparse_vectors = None
        if hasattr(self._embedder, "encode_batch"):
            encoded = self._embedder.encode_batch(chunks)
            vectors = encoded["dense"]
            sparse_vectors = encoded.get("sparse")
        elif hasattr(self._embedder, "encode"):
            vectors = self._embedder.encode(chunks)
        elif hasattr(self._embedder, "embed"):
            vectors = self._embedder.embed(chunks)
        else:
            raise TypeError("embedding service must expose encode_batch(), encode(), or embed()")
        texts = chunks
        # Rights are resolved once per file, from the curated register, and fail
        # closed to "unverified". A caller must never overwrite this with a
        # hardcoded "licensed" (X40: register -> stamp -> filter -> enforce).
        rights_status = resolve_source_rights_status(source)
        metadatas = []
        point_ids: list[str] = []
        voice_verified = 0
        for i, chunk in enumerate(texts):
            content_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:16]
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}_{i}_0"))
            point_ids.append(point_id)
            metadata: dict[str, Any] = {
                "text": chunk,
                "source_url": source,
                "title": title or "",
                "speaker": speaker or "Unknown",
                "topic": "Spiritual",
                "chunk_index": i,
                "content_type": "video_transcript",
                "raptor_level": 0,
                # Real chunker id (X40). The old literal "v10" named no algorithm.
                "chunker_version": chunker_version,
                "parent_id_scheme": "url_hash",
                "modality": "video",
                "rights_status": rights_status,
                "domain_rights_status": rights_status,
                "content_hash": content_hash,
                "point_id": point_id,
                "video_id": video_id,
                "ingest_namespace": graph_namespace or "default",
                # D2 timing: real ASR bounds when known, None otherwise. Never
                # interpolated — the speaker gate reads these same bounds.
                "chunk_start": chunk_starts[i] if chunk_starts and i < len(chunk_starts) else None,
                "chunk_end": chunk_ends[i] if chunk_ends and i < len(chunk_ends) else None,
                "start_ms": int(chunk_starts[i] * 1000) if (chunk_starts and i < len(chunk_starts) and chunk_starts[i] is not None) else None,
                "end_ms": int(chunk_ends[i] * 1000) if (chunk_ends and i < len(chunk_ends) and chunk_ends[i] is not None) else None,
                "verbatim_text": chunk,
                "is_verbatim": True,
                "provenance_kind": "speech_turn_clip",
            }
            if chunk_voice and i < len(chunk_voice) and chunk_voice[i]:
                metadata.update(chunk_voice[i])
                if metadata.get("speaker_verified") is True:
                    voice_verified += 1
            metadatas.append(metadata)

        if chunk_voice:
            logger.info(
                "video_pipeline: voice evidence on %d/%d chunks for %s (%d verified)",
                sum(1 for v in chunk_voice if v),
                len(chunks),
                source,
                voice_verified,
            )

        target_collection = (
            collection_name
            or getattr(settings, "first_person_collection", None)
            or getattr(settings, "qdrant_collection", "mukthi_guru")
        )
        client = getattr(self._qdrant, "_client", None) or QdrantClientManager().client
        indexer = QdrantIndexer(client=client, collection=target_collection)
        written = indexer.upsert_chunks(
            texts=texts,
            vectors=vectors,
            metadatas=metadatas,
            sparse_vectors=sparse_vectors,
            replace_source_url=source,
        )
        logger.info("Upserted %d video chunks to %s via QdrantIndexer", written, target_collection)

        # Best-effort Memgraph dual-write for relational ontology
        try:
            from app.dependencies import get_container

            container = get_container()
            memgraph_driver = getattr(container, "memgraph_driver", None)
            if memgraph_driver:
                with memgraph_driver.session() as session:
                    graph_video_id = (
                        f"{graph_namespace}:{video_id or source}"
                        if graph_namespace else str(video_id or source)
                    )
                    session.run(
                        "MERGE (v:Video {video_id: $video_id}) "
                        "SET v.title = $title, v.speaker = $speaker, v.source_url = $source_url, "
                        "v.ingest_namespace = $ingest_namespace",
                        video_id=graph_video_id,
                        title=str(title or ""),
                        speaker=str(speaker or "Unknown"),
                        source_url=str(source),
                        ingest_namespace=graph_namespace or "default",
                    )
                    for meta in metadatas:
                        session.run(
                            "CREATE (tu:TeachingUnit {point_id: $point_id, text: $text, chunk_index: $chunk_index, rights: $rights, ingest_namespace: $ingest_namespace}) "
                            "WITH tu MATCH (v:Video {video_id: $video_id}) "
                            "MERGE (v)-[:HAS_TEACHING_UNIT]->(tu)",
                            point_id=meta.get("point_id"),
                            text=meta.get("text", "")[:250],
                            chunk_index=meta.get("chunk_index", 0),
                            rights=meta.get("rights_status"),
                            video_id=graph_video_id,
                            ingest_namespace=graph_namespace or "default",
                        )
                logger.info("Indexed %d TeachingUnits in Memgraph for video %s", len(metadatas), video_id)
        except Exception as mg_exc:
            logger.debug("Memgraph video indexing non-fatal exception: %s", mg_exc)

        return written, point_ids[:written] if written else []

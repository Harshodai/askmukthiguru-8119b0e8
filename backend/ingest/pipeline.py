"""
Mukthi Guru — Ingestion Pipeline Orchestrator

Design Patterns:
  - Orchestrator Pattern: Coordinates all ingestion sub-components
  - Pipeline Pattern: URL → Load → Clean → Chunk → Embed → Index → RAPTOR
  - Strategy Pattern: Automatically routes to correct loader (video vs image)
  - Observer Pattern: Progress callbacks for frontend status updates

This is the single entry point for ALL content ingestion.
"""

import hashlib
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional


class IngestionCheckpoint:
    def __init__(self, filepath="data/ingest_checkpoint.json"):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(exist_ok=True)
        self.data = self._load()
        self.processed_chunks = set(self.data.keys())

    def _load(self) -> dict:
        if self.filepath.exists():
            try:
                loaded = json.loads(self.filepath.read_text())
                if isinstance(loaded, list):
                    # Backward compatibility conversion: list to dict
                    import time
                    return {h: {"migrated": True, "timestamp": time.time()} for h in loaded}
                elif isinstance(loaded, dict):
                    return loaded
            except Exception as e:
                logger.warning(f"Failed to load checkpoint file: {e}")
        return {}

    def save(self, chunk_id: str, metadata: Optional[dict] = None):
        import time
        self.processed_chunks.add(chunk_id)
        self.data[chunk_id] = metadata or {"timestamp": time.time()}
        try:
            self.filepath.write_text(json.dumps(self.data, indent=2))
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    def is_processed(self, chunk_id: str) -> bool:
        return chunk_id in self.processed_chunks

    def prune_stale_entries(self, active_hashes: list[str]):
        """Remove any entries from checkpoint that are no longer active."""
        active_set = set(active_hashes)
        self.data = {k: v for k, v in self.data.items() if k in active_set}
        self.processed_chunks = set(self.data.keys())
        self.filepath.write_text(json.dumps(self.data, indent=2))


from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from ingest.boundary_chunker import chunk_with_contextual_headers, split_text_at_boundaries
from ingest.cleaner import clean_transcript
from ingest.deduplication import deduplicate_by_payload
from ingest.hyper_extract_adapter import enrich_text, is_eligible
from ingest.image_loader import is_image_url, process_image_url
from ingest.raptor import RaptorIndexer
from ingest.youtube_loader import (
    extract_video_id,
    fetch_transcript_hybrid,
    fetch_transcripts_concurrent,
    get_playlist_video_urls,
    is_channel_url,
    is_playlist_url,
)
from services.adaptive_chunking_adapter import AdaptiveChunkingAdapter
from services.contextual_chunking_service import ContextualChunkingService
from services.embedding_service import EmbeddingService
from services.injection_scanner import scan_chunks_for_injection
from services.ocr_service import OCRService
from services.metadata_extractor import extract_video_metadata
from services.ollama_service import OllamaService
from services.pii_scanner import redact_pii
from services.proposition_service import PropositionService
from services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)

from ingest.adaptive_chunking import AdaptiveChunker
from ingest.auditor import DataAuditor
from ingest.corrector import TranscriptCorrector


def is_valid_text_deterministic(text: str) -> tuple[bool, str]:
    """
    Run low-cost deterministic checks on text before calling LLMs.
    Returns (is_valid, reason).
    """
    if not text or not text.strip():
        return False, "Empty text"
    
    # Check length
    if len(text.strip()) < 50:
        return False, "Text too short (<50 characters)"
        
    # Check if mostly HTML tags
    import re
    html_tags = re.findall(r"<[^>]+>", text)
    if html_tags and len(html_tags) * 15 > len(text):
        return False, "Input contains mostly HTML tag structure"
        
    return True, ""


def extract_doctrine_tags(text: str) -> list[str]:
    """
    Scans text for terms in DOCTRINE_SYNONYMS and returns matching canonical concepts.
    """
    from rag.nodes.utils import DOCTRINE_SYNONYMS
    matched = set()
    text_lower = text.lower()
    for canonical, alternates in DOCTRINE_SYNONYMS.items():
        for alt in alternates:
            import re
            pattern = r'\b' + re.escape(alt.lower()) + r'\b'
            if re.search(pattern, text_lower):
                matched.add(canonical)
                break
    return list(matched)


async def _okf_extract_for_video(video_id: str) -> None:
    """Queue OKF extraction for a single video. Non-fatal — never breaks ingestion.

    Prefers the Celery `okf_extract_tasks.extract_okf_entries` task (has its own
    retry/backoff, runs on the celery-worker service off the request path) and
    falls back to running extract_okf() in-process if Celery/Redis is unreachable
    — e.g. local dev without the worker container running.
    """
    try:
        from tasks.okf_extract_tasks import extract_okf_entries
        extract_okf_entries.delay(target_video_id=video_id, limit=5, auto_approve=False)
        logger.debug(f"OKF extraction dispatched to Celery for video: {video_id}")
        return
    except Exception as e:
        logger.warning(f"OKF Celery dispatch failed for video {video_id}, falling back to in-process: {e}")

    try:
        from scripts.extract_okf_from_stores import extract_okf
        await extract_okf(target_video_id=video_id, limit=5, auto_approve=False)
    except Exception as e:
        # ponytail: OKF extraction is optional augmentation — must never break ingestion.
        logger.warning(f"In-process OKF extraction failed for video {video_id}: {e}")


class IngestionPipeline:
    """
    Orchestrates the full content ingestion workflow.

    URL → Detect Type → Load Content → Audit → Clean → Chunk → Embed → Index → RAPTOR

    Supports:
    - Single YouTube video URLs
    - YouTube playlist URLs
    - Image URLs (JPG, PNG, etc.)
    """

    def __init__(
        self,
        qdrant_service: QdrantService,
        embedding_service: EmbeddingService,
        ollama_service: OllamaService,
        lightrag_service: Optional[Any] = None,
        ocr_service: Optional[OCRService] = None,
        semantic_cache_service: Optional[Any] = None,
    ) -> None:
        """
        Dependency Injection: All services are injected, not created internally.
        This makes the pipeline testable and decoupled.
        """
        self._qdrant = qdrant_service
        self._embedder = embedding_service
        self._llm = ollama_service
        self._ocr = ocr_service or OCRService()
        
        from ingest.quality_gate import DataQualityGate
        from app.config import settings
        supabase_client = None
        if settings.supabase_url and settings.supabase_key:
            try:
                from supabase import create_client
                supabase_client = create_client(settings.supabase_url, settings.supabase_key)
            except Exception as e:
                logger.warning(f"Could not init Supabase in IngestionPipeline: {e}")
                
        self._auditor = DataQualityGate(
            llm_service=ollama_service,
            supabase_client=supabase_client,
            quality_threshold=getattr(settings, "data_quality_threshold", 65),
            enabled=getattr(settings, "data_quality_gate_enabled", True)
        )
        self._corrector = TranscriptCorrector(ollama_service)
        self._lightrag = lightrag_service
        self._semantic_cache = semantic_cache_service

        self._adaptive_chunker = AdaptiveChunkingAdapter(self._embedder)
        self._proposition_service = PropositionService(self._llm)
        self._contextual_chunker = ContextualChunkingService(self._llm)
        self._neo4j_driver = None

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        self._raptor = RaptorIndexer(
            embedding_service=self._embedder,
            ollama_service=self._llm,
            qdrant_service=self._qdrant,
        )

    def _get_neo4j_driver(self):
        if self._neo4j_driver is None:
            from neo4j import GraphDatabase
            self._neo4j_driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
        return self._neo4j_driver

    async def ingest_file(
        self,
        file_path: str,
        max_accuracy: bool = False,
        on_progress: Optional[Callable] = None,
    ) -> dict:
        """
        Ingest a local PDF or TXT file.
        """
        self._notify(on_progress, f"Loading file: {os.path.basename(file_path)}", 0.1)

        text = ""
        ext = os.path.splitext(file_path)[1].lower()
        supported_exts = {".pdf", ".txt", ".csv", ".docx", ".pptx", ".xlsx", ".mp3", ".wav", ".m4a"}

        if ext not in supported_exts:
            return {"status": "error", "message": f"Unsupported file type: {ext}"}

        if settings.use_markitdown_parser:
            try:
                from markitdown import MarkItDown
                from openai import OpenAI
                
                # Configure local OpenAI-compatible client for Ollama
                ollama_v1_url = f"{settings.ollama_base_url.rstrip('/')}/v1"
                llm_client = OpenAI(base_url=ollama_v1_url, api_key="ollama")
                
                md = MarkItDown(
                    llm_client=llm_client,
                    llm_model=settings.model_for_generation
                )
                # Run convert synchronously
                result = md.convert(file_path)
                text = result.text_content
            except Exception as e:
                logger.error(f"MarkItDown conversion failed for {file_path}: {e}. Falling back to default parsers.")

        if not text:
            if ext == ".pdf":
                from pypdf import PdfReader

                reader = PdfReader(file_path)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            elif ext in [".txt", ".csv"]:
                with open(file_path, encoding="utf-8") as f:
                    text = f.read()
            else:
                return {
                    "status": "error",
                    "message": f"MarkItDown parser failed and no native fallback exists for {ext}"
                }

        if not text.strip():
            return {"status": "error", "message": "No text extracted from file"}

        # Ingest as raw text
        return await self.ingest_raw_text(
            text=text,
            source_url=os.path.basename(file_path),
            title=os.path.basename(file_path),
            content_type="document",
            max_accuracy=max_accuracy,
            on_progress=on_progress,
        )

    async def ingest_url(
        self,
        url: str,
        max_accuracy: bool = False,
        on_progress: Optional[Callable[[str, float], None]] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """
        Main entry point: ingest content from any supported URL.

        Strategy Pattern: Auto-detect URL type and route to the correct loader.

        Args:
            url: YouTube video/playlist URL or image URL
            max_accuracy: If True, use enhanced transcription/hierarchical chunks
            on_progress: Optional callback(status_message, percent_complete)
            tags: Knowledge tags to attach to every chunk (defaults to ["general"])

        Returns:
            Dict with 'chunks_indexed', 'summaries_created', 'source_url', etc.
        """
        self._notify(on_progress, "Detecting content type...", 0.05)
        tags = list({t.strip().lower() for t in (tags or ["general"]) if t and t.strip()})

        # === Route to correct loader ===
        from app.security_utils import is_valid_youtube_url

        is_yt = "youtube.com" in url or "youtu.be" in url
        if is_yt and not is_valid_youtube_url(url):
            return {
                "status": "error",
                "message": f"Invalid YouTube URL format: {url}",
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        if is_playlist_url(url) or is_channel_url(url):
            return await self._ingest_playlist(url, max_accuracy, on_progress, tags=tags)
        elif is_image_url(url):
            return await self._ingest_image(url, on_progress, tags=tags)
        if extract_video_id(url):
            if max_accuracy:
                return await self._ingest_video_enhanced(url, on_progress, tags=tags)
            return await self._ingest_video(url, max_accuracy, on_progress, tags=tags)
        else:
            return {
                "status": "error",
                "message": f"Unsupported URL format: {url}",
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

    async def ingest_raw_text(
        self,
        text: str,
        source_url: str,
        title: str,
        speaker: str = "Unknown",
        topic: str = "Spiritual",
        content_type: str = "migration",
        max_accuracy: bool = False,
        on_progress: Optional[Callable] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """
        Ingest raw text directly, bypassing any fetching/loaders.
        Useful for migrations or re-processing existing data.
        """
        import hashlib
        tags = list({t.strip().lower() for t in (tags or ["general"]) if t and t.strip()})
        doc_tags = extract_doctrine_tags(text)
        if doc_tags:
            tags = list(set(tags + doc_tags))
        content_hash = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
        checkpoint = IngestionCheckpoint()
        if checkpoint.is_processed(content_hash):
            self._notify(on_progress, "Content already processed. Skipping.", 1.0)
            return {
                "status": "success",
                "source_url": source_url,
                "chunks_indexed": 0,
                "summaries_created": 0,
                "message": "Content already processed. Skipped.",
            }

        self._notify(on_progress, "Starting raw text processing...", 0.1)

        # Step 1: Clean & redact PII
        clean_text = clean_transcript(text)
        clean_text, pii_found = redact_pii(clean_text)
        if pii_found:
            logger.warning(f"PII redacted from source_url={source_url} — {pii_found} instances")

        # Step 1b: Optional Hyper-Extract enrichment (Phase 5.3)
        self._notify(on_progress, "Extracting structure, entities, and atomic facts...", 0.25)
        hyper_extract_result = self._enrich_text(clean_text)

        # Step 2: Chunk (Hierarchical or Standard)
        self._notify(on_progress, "Chunking and indexing...", 0.3)
        extra_metadatas = None
        if max_accuracy:
            # Phase 2 Improvement: Parent-Child Hierarchical Chunking
            self._notify(on_progress, "Generating hierarchical parent-child chunks...", 0.4)
            final_chunks, extra_metadatas = self._hierarchical_split(
                clean_text, title=title, speaker=speaker, topic=topic
            )
            chunks = final_chunks  # For RAPTOR later
        else:
            chunks = self._split_text(clean_text, title=title, speaker=speaker, topic=topic)

            # Step 3: Document Augmentation (only for standard mode to avoid blowing up child chunk tokens)
            # Pass clean_text as full_document so ContextualChunkingService can prepend situating context
            self._notify(on_progress, "Augmenting chunks...", 0.5)
            final_chunks = await self._augment_chunks(chunks, full_document=clean_text)

        if not final_chunks:
            return {"status": "error", "message": "No meaningful chunks", "source_url": source_url}

        # Iceberg-style safety net: snapshot any existing points for this source
        # before overwriting. Fix: this is the live path behind ingest_document()
        # (PDF/txt uploads) — previously had zero rollback protection against a
        # downstream RAPTOR/LightRAG failure. migrate_data.py also calls this
        # method but already takes its own outer backup/rollback around it; this
        # inner safety net is harmless there (separate backup-collection prefix,
        # pruned independently) and adds real protection for the document path.
        backup_collection = self._backup_before_reindex(source_url)

        # Step 5: Embed and index
        chunks_count = self._embed_and_index(
            final_chunks,
            source_url=source_url,
            title=title,
            speaker=speaker,
            topic=topic,
            content_type=content_type,
            source_type=content_type,
            extra_metadatas=extra_metadatas,
            tags=tags,
        )

        try:
            # Step 6: RAPTOR tree
            self._notify(on_progress, "Building RAPTOR tree...", 0.85)
            chunk_dicts = [
                {
                    "text": c,
                    "source_url": source_url,
                    "title": title,
                    "speaker": speaker,
                    "topic": topic,
                }
                for c in chunks
            ]
            if max_accuracy and getattr(settings, "raptor_parent_summaries_enabled", False):
                self._notify(on_progress, "Summarizing parent chunks for RAPTOR...", 0.87)
                chunk_dicts = await self._raptor.summarize_parent_chunks(chunk_dicts)
            summaries_count = await self._raptor.build_tree(chunk_dicts)

            # Step 7: Graph RAG Extraction (Phase 4 Improvement)
            if self._lightrag:
                self._notify(on_progress, "Extracting knowledge graph...", 0.95)
                await self._lightrag.ainsert(clean_text)
        except Exception as e:
            logger.error(f"Downstream ingestion step failed for {source_url}, rolling back: {e}")
            self._rollback_reindex(source_url, backup_collection)
            return {
                "status": "error",
                "message": f"Ingestion rolled back — downstream step failed: {e}",
                "source_url": source_url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        # Implicit Teachings Concept Connector & Conflict/Synergy Detector
        await self._implicit_teachings_connector(chunks)

        # Consolidate duplicate entities in Neo4j to keep graph clean and high quality
        await self._consolidate_graph_entities()

        checkpoint.save(content_hash)
        self._notify(on_progress, "Complete!", 1.0)
        return {
            "status": "success",
            "source_url": source_url,
            "chunks_indexed": chunks_count,
            "summaries_created": summaries_count,
            "hyper_extract": hyper_extract_result,
        }

    async def _ingest_video(
        self,
        url: str,
        max_accuracy: bool = False,
        on_progress: Optional[Callable] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Ingest a single YouTube video."""
        tags = list({t.strip().lower() for t in (tags or ["general"]) if t and t.strip()})
        video_id = extract_video_id(url)
        if not video_id:
            return {"status": "error", "message": "Invalid YouTube URL"}

        # Step 1: Fetch transcript
        self._notify(on_progress, "Fetching transcript...", 0.1)
        result = fetch_transcript_hybrid(video_id, title="", max_accuracy=max_accuracy)

        if not result.get("text"):
            return {
                "status": "error",
                "message": f"Could not extract transcript: {result.get('error', 'unknown')}",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        raw_text = result["text"]

        content_hash = hashlib.sha256(raw_text.strip().encode("utf-8")).hexdigest()
        checkpoint = IngestionCheckpoint()
        if checkpoint.is_processed(content_hash):
            self._notify(on_progress, "Video content already processed. Skipping.", 1.0)
            return {
                "status": "success",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
                "message": "Content already processed. Skipped.",
            }

        is_ok, reason = is_valid_text_deterministic(raw_text)
        if not is_ok:
            logger.warning(f"Deterministic pre-filter rejected {url}: {reason}")
            self._notify(on_progress, f"Rejected by pre-filter: {reason}", 1.0)
            return {
                "status": "error",
                "message": f"Pre-filter rejection: {reason}",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        sanitized_text = raw_text.replace("<|begin_of_text|>", "").replace("<|eot_id|>", "")
        raw_text = await self._corrector.correct_transcript(sanitized_text, url)

        self._notify(on_progress, "Auditing content quality...", 0.2)
        quality_res = await self._auditor.run(raw_text, url)

        if not quality_res.passed:
            return {
                "status": "rejected",
                "message": f"Content rejected by Data Quality Gate: score {quality_res.score}/100. Reasons: {'; '.join(quality_res.reasons)}",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        # Step 2: Clean & redact PII
        self._notify(on_progress, "Cleaning text...", 0.3)
        clean_text = clean_transcript(raw_text)
        clean_text, pii_found = redact_pii(clean_text)
        if pii_found:
            logger.warning(f"PII redacted from video url={url} — {pii_found} instances")

        # Step 2b: Optional Hyper-Extract enrichment (Phase 5.3)
        self._notify(on_progress, "Extracting structure, entities, and atomic facts...", 0.35)
        hyper_extract_result = self._enrich_text(clean_text)

        # Step 2c: Enrich video metadata from transcript for non-Apify paths
        method = result.get("method", "")
        if not method.startswith("pre_extracted_"):
            self._notify(on_progress, "Extracting video metadata...", 0.4)
            enriched = extract_video_metadata(raw_text, video_id)
            if enriched.get("title"):
                result["title"] = enriched["title"]
            if enriched.get("speaker") and enriched["speaker"] != "Unknown":
                result["speaker"] = enriched["speaker"]
            if enriched.get("language"):
                result["language"] = enriched["language"]

        # Step 3: Chunk (Hierarchical or Standard)
        self._notify(on_progress, "Chunking and indexing...", 0.5)
        video_title = result.get("title", "") or ""
        video_speaker = result.get("speaker", "Unknown")
        video_topic = result.get("topic", "Spiritual")
        video_language = result.get("language") or None

        extra_metadatas = None
        if max_accuracy:
            self._notify(on_progress, "Generating hierarchical parent-child chunks...", 0.6)
            final_chunks, extra_metadatas = self._hierarchical_split(
                clean_text, title=video_title, speaker=video_speaker, topic=video_topic
            )
            chunks = final_chunks
        else:
            chunks = self._split_text(
                clean_text, title=video_title, speaker=video_speaker, topic=video_topic
            )

            # Step 4: Document Augmentation (Standard only)
            # Pass clean_text as full_document to activate contextual enrichment
            self._notify(on_progress, "Augmenting chunks with potential questions...", 0.6)
            final_chunks = await self._augment_chunks(chunks, full_document=clean_text)

        if not final_chunks:
            return {
                "status": "error",
                "message": "No meaningful chunks after cleaning",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        # Iceberg-style safety net: snapshot any existing points for this source
        # before overwriting, so a downstream RAPTOR/LightRAG failure can roll back.
        backup_collection = self._backup_before_reindex(url)

        # Step 5: Embed and index
        chunks_count = self._embed_and_index(
            final_chunks,
            source_url=url,
            title=video_title,
            speaker=video_speaker,
            topic=video_topic,
            content_type="video",
            source_type="video",
            language=video_language,
            extra_metadatas=extra_metadatas,
            tags=tags,
        )

        try:
            # Step 5: RAPTOR tree (reuses the same chunks, passes source metadata)
            self._notify(on_progress, "Building RAPTOR tree...", 0.8)
            chunk_dicts = [
                {
                    "text": c,
                    "source_url": url,
                    "title": video_title,
                    "speaker": video_speaker,
                    "topic": video_topic,
                }
                for c in chunks
            ]
            if max_accuracy and getattr(settings, "raptor_parent_summaries_enabled", False):
                self._notify(on_progress, "Summarizing parent chunks for RAPTOR...", 0.82)
                chunk_dicts = await self._raptor.summarize_parent_chunks(chunk_dicts)
            summaries_count = await self._raptor.build_tree(chunk_dicts)

            # Step 6: Graph RAG Extraction (Phase 4 Improvement)
            if self._lightrag:
                self._notify(on_progress, "Extracting knowledge graph (LightRAG)...", 0.9)
                await self._lightrag.ainsert(clean_text)
        except Exception as e:
            logger.error(f"Downstream ingestion step failed for {url}, rolling back: {e}")
            self._rollback_reindex(url, backup_collection)
            return {
                "status": "error",
                "message": f"Ingestion rolled back — downstream step failed: {e}",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        checkpoint.save(content_hash)

        # OKF auto-extraction: fire-and-forget for newly ingested content.
        # ponytail: gated by rag_okf_auto_extract_enabled (default on — hardened
        # w/ Celery retry + logging in _okf_extract_for_video). Non-fatal — OKF
        # extraction must never break ingestion.
        if getattr(settings, "rag_okf_auto_extract_enabled", False):
            try:
                video_id = extract_video_id(url)
                if video_id:
                    asyncio.create_task(_okf_extract_for_video(video_id))
                    logger.debug("OKF extraction queued for video: %s", video_id)
            except Exception as e:
                logger.warning(f"Failed to queue OKF extraction for {url}: {e}")

        self._notify(on_progress, "Complete!", 1.0)
        return {
            "status": "success",
            "source_url": url,
            "method": result.get("method", "unknown"),
            "chunks_indexed": chunks_count,
            "summaries_created": summaries_count,
            "text_length": len(clean_text),
            "hyper_extract": hyper_extract_result,
        }

    async def _ingest_video_enhanced(
        self,
        url: str,
        on_progress: Optional[Callable] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """
        Production Ingestion (Phase 3): Enhanced video processing.
        Includes speaker diarization, topic extraction, and partitioned indexing.
        """
        import uuid

        tags = list({t.strip().lower() for t in (tags or ["general"]) if t and t.strip()})
        video_id = extract_video_id(url)
        self._notify(on_progress, "Phase 3: Starting enhanced ingestion...", 0.1)

        # 1. Fetch transcript with Diarization (via Sarvam STT)
        self._notify(on_progress, "Extracting audio and diarizing speakers...", 0.2)
        result = fetch_transcript_hybrid(video_id, max_accuracy=True)
        if not result.get("text"):
            return {"status": "error", "message": "Extraction failed", "source_url": url}

        raw_text = result["text"]

        content_hash = hashlib.sha256(raw_text.strip().encode("utf-8")).hexdigest()
        checkpoint = IngestionCheckpoint()
        if checkpoint.is_processed(content_hash):
            self._notify(on_progress, "Video content already processed. Skipping.", 1.0)
            return {
                "status": "success",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
                "message": "Content already processed. Skipped.",
            }

        # Step 1.15: Deterministic pre-filter to save LLM/API costs
        is_ok, reason = is_valid_text_deterministic(raw_text)
        if not is_ok:
            logger.warning(f"Deterministic pre-filter rejected {url}: {reason}")
            self._notify(on_progress, f"Rejected by pre-filter: {reason}", 1.0)
            return {
                "status": "error",
                "message": f"Pre-filter rejection: {reason}",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        # Step 1.2: Correct Transcript (Council Recommendation)
        self._notify(on_progress, "Correcting transcript (LLM)...", 0.3)
        sanitized_text = raw_text.replace("<|begin_of_text|>", "").replace("<|eot_id|>", "")
        raw_text = await self._corrector.correct_transcript(sanitized_text, url)

        # Step 1.3: Data Quality Gate (Iceberg-style stage-before-merge).
        # Fix: enhanced path skipped this entirely — only the deterministic
        # pre-filter ran. Same 3-tier gate as _ingest_video() for parity.
        self._notify(on_progress, "Auditing content quality...", 0.32)
        quality_res = await self._auditor.run(raw_text, url)
        if not quality_res.passed:
            return {
                "status": "rejected",
                "message": f"Content rejected by Data Quality Gate: score {quality_res.score}/100. "
                           f"Reasons: {'; '.join(quality_res.reasons)}",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        # Enrich video metadata from transcript for non-Apify paths
        method = result.get("method", "")
        if not method.startswith("pre_extracted_"):
            self._notify(on_progress, "Extracting video metadata...", 0.35)
            enriched = extract_video_metadata(raw_text, video_id)
            if enriched.get("title"):
                result["title"] = enriched["title"]
            if enriched.get("speaker") and enriched["speaker"] != "Unknown":
                result["speaker"] = enriched["speaker"]
            if enriched.get("language"):
                result["language"] = enriched["language"]

        video_title = result.get("title", "")
        video_speaker = result.get("speaker", "Unknown")
        video_language = result.get("language") or None

        # 2. Extract key spiritual topics (LLM)
        self._notify(on_progress, "Analyzing spiritual topics...", 0.4)
        topics = await self._extract_topics(raw_text)

        # 3. Clean & redact PII
        clean_text = clean_transcript(raw_text)
        clean_text, pii_found = redact_pii(clean_text)
        if pii_found:
            logger.warning(f"PII redacted from enhanced video url={url} — {pii_found} instances")

        # 4. Partition into topic-based sub-sections
        self._notify(on_progress, "Partitioning by topic relevance...", 0.6)
        sections = self._topic_partition(clean_text, topics)

        # We will split parent texts into chunks of 1500 chars to avoid oversized parents
        parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=200,
            length_function=len,
        )

        all_chunks = []
        all_extra_metadatas = []

        speaker = result.get("speaker", "Unknown")

        apply_props = self._proposition_service.should_apply_propositions(clean_text)

        # Process each topic partition
        topic_index = 0
        for topic, text in sections.items():
            self._notify(on_progress, f"Processing topic: {topic}...", 0.7 + (topic_index * 0.05))

            # Split the topic segment into parent chunks
            parent_chunks = parent_splitter.split_text(text)

            for parent_chunk in parent_chunks:
                parent_id = str(uuid.uuid4())

                # Decompose the parent chunk into propositions (child chunks) or use adaptive chunking
                if apply_props:
                    propositions = await self._proposition_split(parent_chunk)
                else:
                    propositions = self._adaptive_chunker.chunk_document(parent_chunk)

                # Pass the full clean_text so ContextualChunkingService situates each proposition
                augmented = await self._augment_chunks(propositions, full_document=clean_text)

                # Prepend contextual header to each child chunk to guarantee UI clarity
                header_parts = [f"Source: {video_title}"]
                if speaker and speaker != "Unknown":
                    header_parts.append(f"Speaker: {speaker}")
                if topic and topic != "Spiritual":
                    header_parts.append(f"Topic: {topic}")
                header = f"[{' | '.join(header_parts)}]\n"

                for child_prop in augmented:
                    all_chunks.append(header + child_prop)
                    all_extra_metadatas.append(
                        {
                            "parent_id": parent_id,
                            "parent_text": parent_chunk,
                            "is_child": True,
                            "topic": topic,
                        }
                    )
            topic_index += 1

        # Iceberg-style safety net: snapshot any existing points for this source
        # before overwriting, so a downstream RAPTOR/LightRAG failure can roll back.
        backup_collection = self._backup_before_reindex(url)

        # Embed and index all leaf chunks at once to prevent catastrophic deletion/overwrite
        self._notify(on_progress, "Indexing all extracted topic chunks...", 0.85)
        total_chunks = 0
        if all_chunks:
            total_chunks = self._embed_and_index(
                all_chunks,
                source_url=url,
                title=video_title,
                speaker=video_speaker,
                topic="Multi-Topic",
                content_type="video_enhanced",
                source_type="video",
                language=video_language,
                extra_metadatas=all_extra_metadatas,
                tags=tags,
            )

        try:
            # 5. Build RAPTOR and Graph
            self._notify(on_progress, "Finalizing knowledge structure...", 0.9)
            if all_chunks:
                # Build RAPTOR summaries using the actual compiled leaf chunks
                chunks_data = [{"text": c, "source_url": url, "title": video_title} for c in all_chunks]
                if getattr(settings, "raptor_parent_summaries_enabled", False):
                    chunks_data = await self._raptor.summarize_parent_chunks(chunks_data)
                await self._raptor.build_tree(chunks_data)

            if self._lightrag:
                await self._lightrag.ainsert(clean_text)
        except Exception as e:
            logger.error(f"Downstream ingestion step failed for {url}, rolling back: {e}")
            self._rollback_reindex(url, backup_collection)
            return {
                "status": "error",
                "message": f"Ingestion rolled back — downstream step failed: {e}",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        checkpoint.save(content_hash)

        # OKF auto-extraction hook (same gate as _ingest_video).
        # ponytail: simplified from the previous to_thread(asyncio.run(...)) wrapper —
        # we're already inside a running event loop here, so create_task() directly
        # is correct and matches _ingest_video()'s pattern (no need for a new thread
        # + a nested event loop).
        if getattr(settings, "rag_okf_auto_extract_enabled", False):
            try:
                video_id = extract_video_id(url)
                if video_id:
                    asyncio.create_task(_okf_extract_for_video(video_id))
                    logger.debug("OKF extraction queued for enhanced video: %s", video_id)
            except Exception as e:
                logger.warning(f"Failed to queue OKF extraction for {url}: {e}")

        self._notify(on_progress, "Enhanced ingestion complete!", 1.0)
        return {
            "status": "success",
            "source_url": url,
            "title": video_title,
            "topics_detected": list(sections.keys()),
            "chunks_indexed": total_chunks,
            "method": "enhanced_diarization",
        }

    async def _extract_topics(self, text: str) -> list[str]:
        """Extract top 3-5 spiritual topics from text using LLM."""
        prompt = "Analyze this spiritual teaching and list the top 3-5 distinct topics discussed (e.g., 'Nature of Suffering', 'Power of Observation', 'Relationship with EGO'). Return as a comma-separated list."
        try:
            response = await self._llm.generate(
                prompt,
                text[:5000],
                max_tokens=1024,
                reasoning_effort="low",
                operation="extraction",
                is_structured=True,
            )
            if not response or not response.strip():
                return ["Spiritual"]
            return [t.strip() for t in response.split(",") if t.strip()]
        except Exception as e:
            logger.error(f"Error in _extract_topics: {e}. Falling back to ['Spiritual']")
            return ["Spiritual"]

    def _topic_partition(self, text: str, topics: list[str]) -> dict[str, str]:
        """Partition text into topic sections using sentence-boundary awareness."""
        if not topics:
            return {"General": text}

        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) <= len(topics):
            eq = len(text) // len(topics)
            sections = {}
            for i, topic in enumerate(topics):
                start = i * eq
                end = (i + 1) * eq if i < len(topics) - 1 else len(text)
                sections[topic] = text[start:end]
            return sections

        sentences_per_topic = max(1, len(sentences) // len(topics))
        sections = {}
        for i, topic in enumerate(topics):
            s = i * sentences_per_topic
            e = (i + 1) * sentences_per_topic if i < len(topics) - 1 else len(sentences)
            sections[topic] = " ".join(sentences[s:e])
        return sections

    async def _ingest_playlist(
        self,
        url: str,
        max_accuracy: bool = False,
        on_progress: Optional[Callable] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Ingest all videos in a YouTube playlist/channel using concurrent extraction."""
        tags = list({t.strip().lower() for t in (tags or ["general"]) if t and t.strip()})
        self._notify(on_progress, "Fetching playlist/channel videos...", 0.05)
        videos = get_playlist_video_urls(url)

        if not videos:
            return {"status": "error", "message": "No videos found in playlist/channel"}

        # Phase 1: Filter out already processed videos
        checkpoint = IngestionCheckpoint()
        unprocessed_videos = []
        for i, video in enumerate(videos):
            if checkpoint.is_processed(video["url"]):
                self._notify(
                    on_progress,
                    f"Skipping {i + 1}/{len(videos)}: {video.get('title', 'Unknown')[:50]}... (already processed)",
                    0.05 + (i / len(videos)) * 0.05,
                )
            else:
                unprocessed_videos.append(video)

        if not unprocessed_videos:
            self._notify(on_progress, "All videos already processed!", 1.0)
            return {"status": "success", "message": "All videos already processed"}

        self._notify(
            on_progress,
            f"Extracting transcripts for {len(unprocessed_videos)} videos concurrently...",
            0.1,
        )

        transcript_results = await fetch_transcripts_concurrent(
            unprocessed_videos,
            on_progress=lambda idx, total, res: self._notify(
                on_progress,
                f"Transcript {idx + 1}/{total}: {unprocessed_videos[idx].get('title', '')[:40]}... [{res.get('method', '?')}]",
                0.1 + (idx / total) * 0.4,
            ),
        )

        # Phase 2: Process transcripts (clean, chunk, embed, index)
        total_chunks = 0
        total_summaries = 0
        processed = 0
        errors = []

        for i, (video, transcript) in enumerate(zip(unprocessed_videos, transcript_results)):
            progress = 0.5 + (i / len(videos)) * 0.4
            self._notify(
                on_progress,
                f"Indexing {i + 1}/{len(videos)}: {video.get('title', 'Unknown')[:50]}...",
                progress,
            )

            if not transcript.get("text"):
                errors.append(
                    {"url": video["url"], "error": transcript.get("error", "No transcript")}
                )
                continue

            try:
                raw_text = transcript["text"]

                # Correct + audit
                sanitized_text = raw_text.replace("<|begin_of_text|>", "").replace("<|eot_id|>", "")
                raw_text = await self._corrector.correct_transcript(sanitized_text, video["url"])
                # Fix: self._auditor is a DataQualityGate (no audit_transcript method) —
                # this raised AttributeError on every playlist video, silently swallowed
                # by the broad except below. Use the same .run() gate as _ingest_video().
                quality_res = await self._auditor.run(raw_text, video["url"])
                if not quality_res.passed:
                    errors.append({
                        "url": video["url"],
                        "error": f"Rejected by Data Quality Gate: score {quality_res.score}/100. "
                                 f"{'; '.join(quality_res.reasons)}",
                    })
                    continue

                # Clean & redact PII, then chunk, embed, index
                clean_text = clean_transcript(raw_text)
                clean_text, pii_found = redact_pii(clean_text)
                if pii_found:
                    logger.warning(f"PII redacted from playlist video url={video['url']} — {pii_found} instances")
                video_title = transcript.get("title", "")
                video_speaker = transcript.get("speaker", "Unknown")
                video_topic = transcript.get("topic", "Spiritual")
                video_language = transcript.get("language") or None

                chunks = self._split_text(
                    clean_text,
                    title=video_title,
                    speaker=video_speaker,
                    topic=video_topic,
                    semantic=max_accuracy and not settings.use_boundary_chunker,
                    use_boundary=max_accuracy,
                )
                if not chunks:
                    continue

                # Phase 2: Proposition Chunking (only if not using boundary-aware chunking)
                if max_accuracy and not settings.use_boundary_chunker:
                    proposition_chunks = []
                    for chunk in chunks:
                        props = await self._proposition_split(chunk)
                        proposition_chunks.extend(props)
                    final_chunks = proposition_chunks
                else:
                    final_chunks = chunks

                # Iceberg-style safety net: snapshot any existing points for this
                # source before overwriting, so a downstream RAPTOR/LightRAG failure
                # can roll back this one video without aborting the whole playlist.
                backup_collection = self._backup_before_reindex(video["url"])

                chunks_count = self._embed_and_index(
                    final_chunks,
                    source_url=video["url"],
                    title=video_title,
                    speaker=video_speaker,
                    topic=video_topic,
                    language=video_language,
                    content_type="video",
                    source_type="video",
                    tags=tags,
                )

                try:
                    # RAPTOR
                    chunk_dicts = [
                        {
                            "text": c,
                            "source_url": video["url"],
                            "title": video_title,
                            "speaker": video_speaker,
                            "topic": video_topic,
                        }
                        for c in chunks
                    ]
                    if max_accuracy and getattr(settings, "raptor_parent_summaries_enabled", False):
                        chunk_dicts = await self._raptor.summarize_parent_chunks(chunk_dicts)
                    summaries_count = await self._raptor.build_tree(chunk_dicts)

                    # Step 6: Graph RAG
                    await self._lightrag.ainsert(clean_text)
                except Exception as e:
                    logger.error(f"Downstream ingestion step failed for {video['url']}, rolling back: {e}")
                    self._rollback_reindex(video["url"], backup_collection)
                    errors.append({
                        "url": video["url"],
                        "error": f"Rolled back — downstream step failed: {e}",
                    })
                    continue

                total_chunks += chunks_count
                total_summaries += summaries_count

                content_hash_pl = hashlib.sha256(clean_text.strip().encode("utf-8")).hexdigest()
                checkpoint.save(content_hash_pl)
                processed += 1

                # OKF auto-extraction: fire-and-forget per video. Fix: playlist path
                # had no OKF hook at all, unlike _ingest_video()/_ingest_video_enhanced().
                if getattr(settings, "rag_okf_auto_extract_enabled", False):
                    try:
                        pl_video_id = extract_video_id(video["url"])
                        if pl_video_id:
                            asyncio.create_task(_okf_extract_for_video(pl_video_id))
                            logger.debug(f"OKF extraction queued for playlist video: {pl_video_id}")
                    except Exception as e:
                        logger.warning(f"Failed to queue OKF extraction for {video['url']}: {e}")

            except Exception as e:
                errors.append({"url": video["url"], "error": str(e)})
                logger.error(f"Failed to process {video['url']}: {e}")

        self._notify(on_progress, "Complete!", 1.0)
        return {
            "status": "success",
            "source_url": url,
            "videos_total": len(videos),
            "videos_processed": processed,
            "videos_failed": len(errors),
            "chunks_indexed": total_chunks,
            "summaries_created": total_summaries,
            "errors": errors if errors else None,
        }

    async def _ingest_image(
        self,
        url: str,
        on_progress: Optional[Callable] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Ingest text from an image via OCR."""
        tags = list({t.strip().lower() for t in (tags or ["general"]) if t and t.strip()})
        self._notify(on_progress, "Extracting text from image...", 0.3)
        result = await process_image_url(url, self._ocr)

        if not result.get("text"):
            return {
                "status": "error",
                "message": "No text extracted from image",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        self._notify(on_progress, "Cleaning and indexing...", 0.6)
        clean_text = clean_transcript(result["text"])
        clean_text, pii_found = redact_pii(clean_text)
        if pii_found:
            logger.warning(f"PII redacted from file url={url} — {pii_found} instances")

        # Data Quality Gate (Iceberg-style stage-before-merge). Fix: image path had
        # no quality gating whatsoever — OCR noise/garbage text was indexed unfiltered.
        self._notify(on_progress, "Auditing content quality...", 0.65)
        quality_res = await self._auditor.run(clean_text, url)
        if not quality_res.passed:
            return {
                "status": "rejected",
                "message": f"Content rejected by Data Quality Gate: score {quality_res.score}/100. "
                           f"Reasons: {'; '.join(quality_res.reasons)}",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        chunks_count = self._chunk_embed_index(
            clean_text,
            source_url=url,
            title=result.get("title", ""),
            content_type="image",
            source_type="image",
            tags=tags,
        )

        self._notify(on_progress, "Complete!", 1.0)
        return {
            "status": "success",
            "source_url": url,
            "method": "easyocr",
            "confidence": result.get("confidence", 0.0),
            "chunks_indexed": chunks_count,
            "summaries_created": 0,  # Too few for RAPTOR
            "text_length": len(clean_text),
        }

    def _enrich_text(self, text: str) -> Optional[dict]:
        """
        Optional Hyper-Extract enrichment: structure, atomic facts, entities, relationships.

        Safe no-op when disabled or text is outside configured length bounds.
        Failures are logged and swallowed so enrichment never blocks ingestion.
        """
        if not getattr(settings, "use_hyper_extract_enrichment", False):
            return None
        if not is_eligible(text, settings.hyper_extract_min_chars):
            return None
        try:
            return enrich_text(
                text,
                max_text_length=settings.hyper_extract_max_chars,
                min_text_length=settings.hyper_extract_min_chars,
            )
        except Exception as e:
            logger.warning(f"Hyper-Extract enrichment failed (non-fatal): {e}")
            return None

    async def _consolidate_graph_entities(self) -> None:
        """
        Consolidate duplicate entities in Neo4j (e.g. Krishnaji vs Sri Krishnaji)
        and runs the self-healing sequence to prune orphans and synchronize Qdrant.
        Runs as a post-ingestion cleanup to maintain high graph data quality.
        """
        from collections import defaultdict

        def clean_name(name):
            cleaned = name.strip()
            cleaned = re.sub(r'^(sri|shri|sree|guruji|guru|swami|swamiji|acharya)\s+', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+(ji|deva|dev|maharaj|swami|swamiji)$', '', cleaned, flags=re.IGNORECASE)
            return cleaned.strip().lower()

        try:
            logger.info("Running post-ingestion self-healing and entity consolidation...")
            def run_consolidation():
                try:
                    driver = self._get_neo4j_driver()
                    neo4j_entities = set()
                    with driver.session() as session:
                        # 1. Entity consolidation
                        res = session.run("MATCH (n:base) WHERE n.entity_id IS NOT NULL RETURN elementId(n) as id, n.entity_id as name, n.description as desc")
                        nodes = [{"id": r["id"], "name": r["name"], "desc": r["desc"] or ""} for r in res]
                        
                        groups = defaultdict(list)
                        for node in nodes:
                            cleaned = clean_name(node["name"])
                            if len(cleaned) < 3:
                                continue
                            groups[cleaned].append(node)
                            
                        merged_total = 0
                        for cleaned_root, group in groups.items():
                            if len(group) <= 1:
                                continue
                                
                            node_metrics = []
                            for node in group:
                                deg_res = session.run("MATCH (n:base) WHERE elementId(n) = $node_id RETURN COUNT { (n)-[]-() } as degree", node_id=node["id"]).single()
                                deg = deg_res["degree"] if deg_res else 0
                                node_metrics.append((deg, len(node["desc"]), len(node["name"]), node))
                                
                            node_metrics.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
                            master = node_metrics[0][3]
                            duplicates = [x[3] for x in node_metrics[1:]]
                            
                            for dup in duplicates:
                                with session.begin_transaction() as tx:
                                    tx.run("""
                                    MATCH (dup:base)-[r]->(target)
                                    WHERE elementId(dup) = $dup_id AND elementId(target) <> $master_id
                                    MERGE (master:base)-[new_r:DIRECTED]->(target)
                                    ON CREATE SET new_r = properties(r)
                                    WITH r
                                    DELETE r
                                    """, dup_id=dup["id"], master_id=master["id"])
                                    
                                    tx.run("""
                                    MATCH (source)-[r]->(dup:base)
                                    WHERE elementId(dup) = $dup_id AND elementId(source) <> $master_id
                                    MERGE (source)-[new_r:DIRECTED]->(master:base)
                                    ON CREATE SET new_r = properties(r)
                                    WITH r
                                    DELETE r
                                    """, dup_id=dup["id"], master_id=master["id"])
                                    
                                    if dup["desc"] and dup["desc"] != master["desc"]:
                                        combined = master["desc"] + " | " + dup["desc"]
                                        if len(combined) > 2000:
                                            combined = combined[:1997] + "..."
                                        tx.run("MATCH (m:base) WHERE elementId(m) = $master_id SET m.description = $desc", master_id=master["id"], desc=combined)
                                        master["desc"] = combined
                                        
                                    tx.run("MATCH (dup:base) WHERE elementId(dup) = $dup_id DETACH DELETE dup", dup_id=dup["id"])
                                    merged_total += 1
                        
                        if merged_total > 0:
                            logger.info(f"Ingestion entity consolidation complete: merged {merged_total} duplicate nodes.")

                        # 2. Prune orphaned nodes (0 relationships)
                        orphans_res = session.run("MATCH (n:base) WHERE NOT (n)-[]-() RETURN count(n) as c").single()
                        orphans = orphans_res["c"] if orphans_res else 0
                        if orphans > 0:
                            session.run("MATCH (n:base) WHERE NOT (n)-[]-() DETACH DELETE n")
                            logger.info(f"Ingestion data cleanup: pruned {orphans} orphaned Neo4j nodes.")

                        # 3. Clean corrupted types
                        corrupted_res = session.run("""
                            MATCH (n:base) 
                            WHERE n.entity_type IS NOT NULL AND (
                                n.entity_type CONTAINS '"' OR 
                                n.entity_type CONTAINS '\\\\' OR 
                                size(n.entity_type) > 50
                            )
                            RETURN count(n) as c
                        """).single()
                        corrupted = corrupted_res["c"] if corrupted_res else 0
                        if corrupted > 0:
                            session.run("""
                                MATCH (n:base) 
                                WHERE n.entity_type IS NOT NULL AND (
                                    n.entity_type CONTAINS '"' OR 
                                    n.entity_type CONTAINS '\\\\' OR 
                                    size(n.entity_type) > 50
                                )
                                DETACH DELETE n
                            """)
                            logger.info(f"Ingestion data cleanup: deleted {corrupted} corrupted entity type nodes.")

                        # Fetch remaining entities for cross check
                        active_res = session.run("MATCH (n:base) WHERE n.entity_id IS NOT NULL RETURN n.entity_id as name")
                        neo4j_entities = {r["name"].strip().lower() for r in active_res if r["name"]}

                    # 4. Synchronize Qdrant Vector Mismatches
                    from qdrant_client import QdrantClient
                    qdrant_url = getattr(settings, "qdrant_url", "http://localhost:6333")
                    qdrant = QdrantClient(url=qdrant_url, timeout=15)
                    all_cols = {c.name for c in qdrant.get_collections().collections}
                    entity_cols = [c for c in all_cols if c.startswith("lightrag_vdb_entities_")]
                    
                    total_deleted_points = 0
                    for col in entity_cols:
                        cnt = qdrant.count(col, exact=True).count
                        if cnt > 0:
                            res_pts, _ = qdrant.scroll(collection_name=col, limit=min(cnt, 10000), with_payload=True)
                            points_to_delete = []
                            for p in res_pts:
                                pay = p.payload or {}
                                ent_name = pay.get("entity_name") or pay.get("entity_id") or pay.get("id")
                                if ent_name:
                                    if str(ent_name).strip().lower() not in neo4j_entities:
                                        points_to_delete.append(p.id)
                            if points_to_delete:
                                qdrant.delete(collection_name=col, points_selector=points_to_delete)
                                total_deleted_points += len(points_to_delete)
                    if total_deleted_points > 0:
                        logger.info(f"Ingestion Qdrant synchronization: pruned {total_deleted_points} orphaned vector points.")
                except Exception as ex:
                    logger.error(f"Error inside post-ingestion self-healing: {ex}")

            # Run in executor to keep it async friendly
            await asyncio.get_event_loop().run_in_executor(None, run_consolidation)
        except Exception as e:
            logger.error(f"Failed to trigger post-ingestion self-healing: {e}")

    # === Iceberg-style stage/commit/rollback for live ingestion ==============
    # Fix: only the offline migrate_data.py script had backup/rollback around
    # re-ingestion. A source passing the Data Quality Gate could still be left
    # in an inconsistent state if a downstream step (RAPTOR, LightRAG, Neo4j
    # consolidation) failed AFTER Qdrant was already overwritten. These two
    # helpers extend the same backup_source()/restore_from_backup() primitives
    # used by migrate_data.py into _ingest_video/_ingest_video_enhanced/
    # _ingest_playlist, so a mid-pipeline failure rolls the source back instead
    # of leaving it half-indexed.

    _BACKUP_COLLECTION_PREFIX = "spiritual_wisdom_ingest_backup"

    def _backup_before_reindex(self, source_url: str) -> Optional[str]:
        """Snapshot a source's existing points before it gets overwritten.

        Returns the backup collection name if a backup was taken (source already
        existed), or None for first-time ingestion (nothing to roll back to —
        on downstream failure the new source is simply deleted, not restored).
        """
        if not self._qdrant.check_source_exists(source_url):
            return None
        from datetime import datetime, timezone
        backup_collection = f"{self._BACKUP_COLLECTION_PREFIX}_{datetime.now(timezone.utc):%Y%m%d}"
        if self._qdrant.backup_source(source_url, backup_collection):
            self._qdrant.prune_backups(self._BACKUP_COLLECTION_PREFIX, max_backups=5)
            return backup_collection
        logger.warning(f"Pre-reindex backup failed for {source_url} — proceeding without rollback safety net")
        return None

    def _rollback_reindex(self, source_url: str, backup_collection: Optional[str]) -> None:
        """Iceberg-style rollback after a downstream ingestion step fails.

        Restores the pre-ingestion snapshot if one was taken, otherwise removes
        the partially-indexed new source so it isn't left half-processed.
        """
        if backup_collection:
            if self._qdrant.restore_from_backup(source_url, backup_collection):
                logger.warning(f"Rolled back {source_url} to its pre-ingestion state after a downstream failure")
            else:
                logger.error(f"Rollback FAILED for {source_url} — no backup data found in {backup_collection}")
        else:
            self._qdrant.delete_by_source(source_url)
            logger.warning(f"Removed partially-indexed new source {source_url} after a downstream failure")

    def _embed_and_index(
        self,
        chunks: list[str],
        source_url: str,
        title: str,
        content_type: str,
        speaker: str = "Unknown",
        topic: str = "Spiritual",
        extra_metadatas: Optional[list[dict]] = None,
        language: str = "en",
        tags: Optional[list[str]] = None,
        source_type: Optional[str] = None,
    ) -> int:
        """
        Embed pre-split chunks (dense + sparse) and upsert to Qdrant.

        Uses encode_batch() to generate both dense and sparse vectors
        in a single pass for hybrid search support.
        """
        if not chunks:
            return 0

        tags = list({t.strip().lower() for t in (tags or ["general"]) if t and t.strip()})

        # Optional ingestion-time deduplication
        if getattr(settings, "ingestion_deduplication_enabled", False):
            placeholder_metas = [extra_metadatas[i] if extra_metadatas and i < len(extra_metadatas) else {} for i in range(len(chunks))]
            chunks, extra_metadatas = deduplicate_by_payload(
                chunks,
                placeholder_metas,
                threshold=settings.ingestion_dedup_threshold,
            )

        # Injection scan and skip risky chunks
        clean_chunks, risky_chunks = scan_chunks_for_injection(chunks)
        if risky_chunks:
            logger.warning(
                f"Injection patterns detected in {len(risky_chunks)}/{len(chunks)} chunks "
                f"from source_url={source_url} — skipped"
            )
        if not clean_chunks:
            return 0

        # Check for existing content and delete for clean re-ingestion
        if self._qdrant.check_source_exists(source_url):
            logger.info(f"Source already indexed, overwriting: {source_url}")
            self._qdrant.delete_by_source(source_url)

        # Generate both dense and sparse embeddings in one pass
        embeddings = self._embedder.encode_batch(clean_chunks)

        # Build metadata for each chunk
        metadatas = []
        for i in range(len(clean_chunks)):
            base_meta = {
                "source_url": source_url,
                "title": title,
                "speaker": speaker,
                "topic": topic,
                "content_type": content_type,
                "source_type": source_type or content_type,
                "language": language,
                "tags": tags or [],
                "chunk_index": i,
                "raptor_level": 0,  # Leaf node
            }
            if extra_metadatas and i < len(extra_metadatas):
                base_meta.update(extra_metadatas[i])
            # ponytail: Gap 2 — important_kwd ingest tagging. Reuses extract_doctrine_tags.
            if getattr(settings, "important_kwd_boost_enabled", True):
                base_meta["important_kwd"] = extract_doctrine_tags(clean_chunks[i])
            metadatas.append(base_meta)

        # Persist source-level metadata to telemetry (best-effort)
        self._record_kb_source(source_url, title, content_type, tags)

        # Upsert to Qdrant with both dense and sparse vectors
        upserted = self._qdrant.upsert_chunks(
            clean_chunks,
            embeddings["dense"],
            metadatas,
            sparse_vectors=embeddings["sparse"],
        )

        # Invalidate semantic cache entries similar to newly ingested content
        if self._semantic_cache and self._semantic_cache.is_available:
            try:
                for emb in embeddings["dense"]:
                    self._semantic_cache.invalidate_by_embedding(emb)
                logger.debug("Semantic cache invalidated for new ingestion")
            except Exception as e:
                logger.warning(f"Semantic cache invalidation failed (non-fatal): {e}")

        return upserted

    def _record_kb_source(
        self,
        source_url: str,
        title: str,
        content_type: str,
        tags: list[str],
    ) -> None:
        """Best-effort persistence of source metadata to kb_sources telemetry table."""
        try:
            from datetime import datetime, timezone

            from app.telemetry_db import _get_client

            client = _get_client()
            if not client:
                return

            payload = {
                "source_url": source_url,
                "title": title,
                "content_type": content_type,
                "tags": tags,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            # Upsert by source_url if the table supports it; otherwise insert.
            try:
                client.table("kb_sources").upsert(payload).execute()
            except Exception:
                client.table("kb_sources").insert(payload).execute()
            logger.debug(f"Recorded kb_sources entry for {source_url}")
        except Exception as e:
            # Non-fatal: ingestion must succeed even if telemetry table is absent.
            logger.warning(f"Failed to record kb_sources entry for {source_url}: {e}")

    def _hierarchical_split(
        self, text: str, title: str = "", speaker: str = "", topic: str = ""
    ) -> tuple[list[str], list[dict]]:
        """
        Phase 2 Improvement: Parent-Child Hierarchical Chunking.
        Splits text into large Parent Chunks, and then into smaller Child Chunks.
        Returns: (child_texts, child_metadatas) where metadatas contain parent mapping.
        """
        import uuid
        import re

        # 1. Split into parent chunks using semantic splitting
        parent_chunks = self._semantic_split(text)

        all_child_texts = []
        all_child_metadatas = []

        for parent_text in parent_chunks:
            parent_id = str(uuid.uuid4())

            # 2. Split parent_text into child chunks strictly at sentence boundaries (~400 chars target)
            sentences = re.split(r"(?<=[.!?]) +", parent_text)
            children = []
            current_child_sentences = []
            current_len = 0

            for sentence in sentences:
                sentence_len = len(sentence)
                if current_len + sentence_len > 400 and current_child_sentences:
                    children.append(" ".join(current_child_sentences))
                    current_child_sentences = [sentence]
                    current_len = sentence_len
                else:
                    current_child_sentences.append(sentence)
                    current_len += sentence_len + (1 if current_child_sentences else 0)
            if current_child_sentences:
                children.append(" ".join(current_child_sentences))

            for child in children:
                # Add context headers to the child
                header_parts = [f"Source: {title}"]
                if speaker and speaker != "Unknown":
                    header_parts.append(f"Speaker: {speaker}")
                if topic and topic != "Spiritual":
                    header_parts.append(f"Topic: {topic}")
                header = f"[{' | '.join(header_parts)}]\n"

                all_child_texts.append(header + child)
                all_child_metadatas.append(
                    {"parent_id": parent_id, "parent_text": parent_text, "is_child": True}
                )

        return all_child_texts, all_child_metadatas

    def _chunk_embed_index(
        self,
        text: str,
        source_url: str,
        title: str,
        content_type: str,
        speaker: str = "Unknown",
        topic: str = "Spiritual",
        tags: Optional[list[str]] = None,
        source_type: Optional[str] = None,
    ) -> int:
        """
        Split text → embed → upsert to Qdrant.

        Convenience method for content types that don't need the split result.
        """
        chunks = self._split_text(text, title=title, speaker=speaker, topic=topic)
        return self._embed_and_index(
            chunks,
            source_url,
            title,
            content_type,
            speaker=speaker,
            topic=topic,
            tags=tags,
            source_type=source_type or content_type,
        )

    def _split_text(
        self,
        text: str,
        title: str = "",
        speaker: str = "",
        topic: str = "",
        semantic: bool = False,
        use_boundary: bool = False,
    ) -> list[str]:
        """
        Split text into chunks using Boundary-aware, Semantic, Adaptive, or Recursive splitting,
        then prepend Contextual Chunk Headers.
        """
        if not text or len(text.strip()) < 50:
            return []

        use_boundary = use_boundary or settings.use_boundary_chunker
        if use_boundary:
            chunks = chunk_with_contextual_headers(
                text,
                title=title,
                speaker=speaker,
                topic=topic,
                target_size=settings.rag_chunk_size,
                overlap_sentences=1,
            )
            return chunks

        if settings.use_ingest_adaptive_chunker and len(text) >= settings.adaptive_chunking_min_chars:
            chunks = AdaptiveChunker(self._embedder).chunk_document(text)
        elif settings.use_adaptive_chunking:
            chunks = self._adaptive_chunker.chunk_document(text)
        elif semantic:
            chunks = self._semantic_split(text)
        else:
            chunks = self._splitter.split_text(text)

        if title:
            # Prepend Contextual Header to every chunk to maintain narrative origin
            # Recommendation: Source: {video_title} | Speaker: {speaker} | Topic: {topic}
            header_parts = [f"Source: {title}"]
            if speaker and speaker != "Unknown":
                header_parts.append(f"Speaker: {speaker}")
            if topic and topic != "Spiritual":
                header_parts.append(f"Topic: {topic}")

            header = f"[{' | '.join(header_parts)}]\n"
            return [header + chunk for chunk in chunks]

        return chunks

    async def _augment_chunks(
        self,
        chunks: list[str],
        full_document: str = "",
    ) -> list[str]:
        """
        Document Augmentation pipeline:
        1. Contextual Retrieval (Anthropic-style) — prepend a 1-2 sentence situating
           context generated by the LLM.  Reduces retrieval failures by ~49%.
        2. Hypothetical Questions — append 2-3 questions the chunk answers to improve
           recall (Ch 11 RAG Made Simple).

        Both steps are skipped when running with local models (non-cloud) to keep
        ingestion time manageable.  Contextual enrichment runs first because it
        produces the text that the embedding model will encode.
        """
        if not settings.is_sarvam_cloud:
            return chunks  # Skip for local models to save time

        # Step 1: Contextual enrichment (situate each chunk in the document)
        if full_document:
            try:
                chunks = await self._contextual_chunker.enrich_chunks(full_document, chunks)
            except Exception as e:
                logger.warning(f"Contextual enrichment failed (non-fatal): {e}")

        # Step 2: Hypothetical question augmentation
        augmented = []
        for i, chunk in enumerate(chunks):
            try:
                if i % 2 == 0 and len(chunk) > 200:
                    questions = await self._llm.generate(
                        "Generate 2-3 brief hypothetical questions that this spiritual teaching answers.",
                        chunk,
                        max_tokens=100,
                    )
                    augmented.append(f"{chunk}\n\n[Potential Questions: {questions}]")
                else:
                    augmented.append(chunk)
            except Exception as e:
                logger.warning(f"Augmentation failed for chunk {i}: {e}")
                augmented.append(chunk)

        return augmented

    async def _proposition_split(self, text: str) -> list[str]:
        """
        Phase 2 Improvement: Proposition Chunking.
        Decomposes a chunk into independent, self-contained propositions using an LLM.
        """
        return await self._proposition_service.extract_propositions(text)

    def _semantic_split(self, text: str) -> list[str]:
        """
        Phase 3 Improvement: Semantic Chunking.
        Splits text into sentences and groups them based on embedding similarity.
        """
        import re

        import numpy as np

        # 1. Split into sentences
        sentences = re.split(r"(?<=[.!?]) +", text)
        if len(sentences) < 5:
            return [text]

        # 2. Embed sentences
        sentence_embeddings = self._embedder.encode(sentences)

        # 3. Calculate similarities between adjacent sentences
        similarities = []
        for i in range(len(sentence_embeddings) - 1):
            s1 = sentence_embeddings[i]
            s2 = sentence_embeddings[i + 1]
            # Cosine similarity
            sim = np.dot(s1, s2) / (np.linalg.norm(s1) * np.linalg.norm(s2))
            similarities.append(sim)

        # 4. Find split points (local minima in similarity)
        # We split where similarity is below a percentile (e.g., 20th percentile)
        # or below a fixed threshold.
        threshold = np.percentile(similarities, 20)

        chunks = []
        current_chunk = [sentences[0]]

        for i, sim in enumerate(similarities):
            if sim < threshold and len(" ".join(current_chunk)) > 300:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sentences[i + 1]]
            else:
                current_chunk.append(sentences[i + 1])

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        logger.info(
            f"Semantic Chunking: Created {len(chunks)} chunks from {len(sentences)} sentences"
        )
        return chunks

    @staticmethod
    def _notify(callback: Optional[Callable], message: str, progress: float) -> None:
        """Helper to send progress updates if callback is provided."""
        if callback:
            try:
                callback(message, progress)
            except Exception:
                pass  # Progress callbacks should never crash the pipeline
        logger.info(f"[{progress:.0%}] {message}")

    async def _implicit_teachings_connector(self, chunks: list[str]) -> None:
        """
        Calculates similarity of new chunk embeddings against all Neo4j concepts,
        auto-creates RELATED_TO, and detects EXPANDS_ON / CONTRADICTS via fast LLM check.
        """
        if not settings.neo4j_uri:
            return

        try:
            import asyncio
            from app.constants import CONCEPT_SIMILARITY_THRESHOLD
            from datetime import datetime
            import numpy as np

            # 1. Fetch all concept/entity nodes from Neo4j
            def _get_entities():
                driver = self._get_neo4j_driver()
                entities = []
                with driver.session() as session:
                    # Fix: LightRAG's Neo4JStorage writes the entity_id property,
                    # not entity_name — this query always returned 0 rows, silently
                    # disabling the Implicit Teachings Concept Connector entirely.
                    result = session.run("MATCH (n) WHERE n.entity_id IS NOT NULL RETURN n.entity_id AS name, n.description AS desc LIMIT 150")
                    for r in result:
                        entities.append({
                            "name": r["name"],
                            "desc": r["desc"] or ""
                        })
                return entities

            entities = await asyncio.to_thread(_get_entities)
            if not entities:
                return

            # 2. Compute embeddings for these concepts/entities
            texts_to_embed = [f"{e['name']}: {e['desc'][:100]}" for e in entities]
            
            entity_embeddings = []
            for text in texts_to_embed:
                emb = self._embedder.encode_single(text)
                entity_embeddings.append(emb)

            # 3. Process each chunk
            for chunk_text in chunks[:15]:
                chunk_emb = self._embedder.encode_single(chunk_text)
                chunk_emb_arr = np.array(chunk_emb)
                chunk_norm = np.linalg.norm(chunk_emb_arr)

                matches = []
                for i, emb in enumerate(entity_embeddings):
                    emb_arr = np.array(emb)
                    norm = np.linalg.norm(emb_arr)
                    if chunk_norm > 0 and norm > 0:
                        similarity = np.dot(chunk_emb_arr, emb_arr) / (chunk_norm * norm)
                        if similarity >= CONCEPT_SIMILARITY_THRESHOLD:
                            matches.append((entities[i], similarity))

                # 4. Insert relations in Neo4j
                if matches:
                    logger.info(f"Implicit Teachings Concept Connector: Found {len(matches)} matches for chunk above threshold {CONCEPT_SIMILARITY_THRESHOLD}")
                    
                    for entity, sim in matches:
                        rel_type = "RELATED_TO"
                        reason = f"Cosine similarity {sim:.3f}"

                        if sim >= 0.82:
                            system_prompt = (
                                "You are a Theology Conflict & Synergy Detector. "
                                "Analyze these two spiritual teaching segments and determine if they "
                                "CONTRADICT each other (e.g. conflicting timings, opposing steps) or if "
                                "the new teaching EXPANDS_ON the existing one. "
                                "Return exactly 'CONTRADICTS' or 'EXPANDS_ON' or 'RELATED_TO' followed by a short 1-sentence reason. "
                                "Format: <RELATION_TYPE> | <reason>"
                            )
                            user_prompt = (
                                f"New Teaching: {chunk_text}\n\n"
                                f"Existing Teaching: {entity['name']}: {entity['desc']}"
                            )
                            try:
                                response = await self._llm.generate(
                                    system_prompt=system_prompt,
                                    user_prompt=user_prompt
                                )
                                parts = response.strip().split("|")
                                detected_rel = parts[0].strip()
                                if detected_rel in ["CONTRADICTS", "EXPANDS_ON"]:
                                    rel_type = detected_rel
                                    if len(parts) > 1:
                                        reason = parts[1].strip()
                            except Exception as llm_err:
                                logger.warning(f"Failed to run LLM synergy detector: {llm_err}")

                        # Write to Neo4j
                        def _write_relation(target_name, relation, desc, sim_val):
                            driver = self._get_neo4j_driver()
                            with driver.session() as session:
                                # Fix: match on entity_id (the property LightRAG's
                                # Neo4JStorage actually writes), not entity_name.
                                cypher = f"""
                                MATCH (target) WHERE target.entity_id = $target_name
                                MERGE (src:__Chunk__ {{text: $chunk_text}})
                                MERGE (src)-[r:{relation} {{similarity: $similarity, description: $desc, created_at: $timestamp}}]->(target)
                                """
                                session.run(
                                    cypher,
                                    target_name=target_name,
                                    chunk_text=chunk_text[:300],
                                    similarity=float(sim_val),
                                    desc=desc,
                                    timestamp=datetime.utcnow().isoformat()
                                )
                        await asyncio.to_thread(
                            _write_relation,
                            entity["name"],
                            rel_type,
                            reason,
                            sim
                        )
        except Exception as e:
            logger.warning(f"Implicit Teachings Concept Connector failed: {e}")

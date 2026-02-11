"""
Mukthi Guru — Ingestion Pipeline Orchestrator

Design Patterns:
  - Orchestrator Pattern: Coordinates all ingestion sub-components
  - Pipeline Pattern: URL → Load → Clean → Chunk → Embed → Index → RAPTOR
  - Strategy Pattern: Automatically routes to correct loader (video vs image)
  - Observer Pattern: Progress callbacks for frontend status updates

This is the single entry point for ALL content ingestion.
"""

import logging
from typing import Optional, Callable

from langchain.text_splitter import RecursiveCharacterTextSplitter

from app.config import settings
from ingest.youtube_loader import (
    extract_video_id,
    is_playlist_url,
    get_playlist_video_urls,
    fetch_transcript_hybrid,
)
from ingest.image_loader import is_image_url, process_image_url
from ingest.cleaner import clean_transcript
from ingest.raptor import RaptorIndexer
from services.embedding_service import EmbeddingService
from services.ollama_service import OllamaService
from services.qdrant_service import QdrantService
from services.ocr_service import OCRService

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Orchestrates the full content ingestion workflow.
    
    URL → Detect Type → Load Content → Clean → Chunk → Embed → Index → RAPTOR
    
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
        ocr_service: Optional[OCRService] = None,
    ) -> None:
        """
        Dependency Injection: All services are injected, not created internally.
        This makes the pipeline testable and decoupled.
        """
        self._qdrant = qdrant_service
        self._embedder = embedding_service
        self._llm = ollama_service
        self._ocr = ocr_service or OCRService()

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

    async def ingest_url(
        self,
        url: str,
        on_progress: Optional[Callable[[str, float], None]] = None,
    ) -> dict:
        """
        Main entry point: ingest content from any supported URL.
        
        Strategy Pattern: Auto-detect URL type and route to the correct loader.
        
        Args:
            url: YouTube video/playlist URL or image URL
            on_progress: Optional callback(status_message, percent_complete)
            
        Returns:
            Dict with 'chunks_indexed', 'summaries_created', 'source_url', etc.
        """
        self._notify(on_progress, "Detecting content type...", 0.05)

        # === Route to correct loader ===
        if is_playlist_url(url):
            return await self._ingest_playlist(url, on_progress)
        elif is_image_url(url):
            return await self._ingest_image(url, on_progress)
        elif extract_video_id(url):
            return await self._ingest_video(url, on_progress)
        else:
            return {
                "status": "error",
                "message": f"Unsupported URL format: {url}",
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

    async def _ingest_video(
        self,
        url: str,
        on_progress: Optional[Callable] = None,
    ) -> dict:
        """Ingest a single YouTube video."""
        video_id = extract_video_id(url)
        if not video_id:
            return {"status": "error", "message": "Invalid YouTube URL"}

        # Step 1: Fetch transcript
        self._notify(on_progress, "Fetching transcript...", 0.1)
        result = fetch_transcript_hybrid(video_id, title="")
        
        if not result.get("text"):
            return {
                "status": "error",
                "message": f"Could not extract transcript: {result.get('error', 'unknown')}",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        # Step 2: Clean
        self._notify(on_progress, "Cleaning text...", 0.3)
        clean_text = clean_transcript(result["text"])

        # Step 3: Chunk (single split, reused for both index and RAPTOR)
        self._notify(on_progress, "Chunking and indexing...", 0.5)
        chunks = self._split_text(clean_text)
        if not chunks:
            return {
                "status": "error",
                "message": "No meaningful chunks after cleaning",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        video_title = result.get("title", "") or ""

        # Step 4: Embed and index
        chunks_count = self._embed_and_index(
            chunks,
            source_url=url,
            title=video_title,
            content_type="video",
        )

        # Step 5: RAPTOR tree (reuses the same chunks)
        self._notify(on_progress, "Building RAPTOR tree...", 0.8)
        chunk_dicts = [{"text": c, "source_url": url} for c in chunks]
        summaries_count = await self._raptor.build_tree(chunk_dicts)

        self._notify(on_progress, "Complete!", 1.0)
        return {
            "status": "success",
            "source_url": url,
            "method": result.get("method", "unknown"),
            "chunks_indexed": chunks_count,
            "summaries_created": summaries_count,
            "text_length": len(clean_text),
        }

    async def _ingest_playlist(
        self,
        url: str,
        on_progress: Optional[Callable] = None,
    ) -> dict:
        """Ingest all videos in a YouTube playlist."""
        self._notify(on_progress, "Fetching playlist...", 0.05)
        videos = get_playlist_video_urls(url)
        
        if not videos:
            return {"status": "error", "message": "No videos found in playlist"}

        total_chunks = 0
        total_summaries = 0
        processed = 0
        errors = []

        for i, video in enumerate(videos):
            progress = (i + 1) / len(videos)
            self._notify(
                on_progress,
                f"Processing video {i+1}/{len(videos)}: {video.get('title', 'Unknown')[:50]}...",
                progress * 0.9,
            )

            try:
                result = await self._ingest_video(video["url"], None)
                total_chunks += result.get("chunks_indexed", 0)
                total_summaries += result.get("summaries_created", 0)
                processed += 1
            except Exception as e:
                errors.append({"url": video["url"], "error": str(e)})
                logger.error(f"Failed to ingest {video['url']}: {e}")

        self._notify(on_progress, "Complete!", 1.0)
        return {
            "status": "success",
            "source_url": url,
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
    ) -> dict:
        """Ingest text from an image via OCR."""
        self._notify(on_progress, "Extracting text from image...", 0.3)
        result = process_image_url(url, self._ocr)

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
        
        chunks_count = self._chunk_embed_index(
            clean_text,
            source_url=url,
            title=result.get("title", ""),
            content_type="image",
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

    def _embed_and_index(
        self,
        chunks: list[str],
        source_url: str,
        title: str,
        content_type: str,
    ) -> int:
        """
        Embed pre-split chunks and upsert to Qdrant.
        
        Accepts already-split chunks to avoid double-splitting.
        """
        if not chunks:
            return 0

        # Generate embeddings
        vectors = self._embedder.encode(chunks)

        # Build metadata for each chunk
        metadatas = [
            {
                "source_url": source_url,
                "title": title,
                "content_type": content_type,
                "chunk_index": i,
                "raptor_level": 0,  # Leaf node
            }
            for i in range(len(chunks))
        ]

        # Upsert to Qdrant
        return self._qdrant.upsert_chunks(chunks, vectors, metadatas)

    def _chunk_embed_index(
        self,
        text: str,
        source_url: str,
        title: str,
        content_type: str,
    ) -> int:
        """
        Split text → embed → upsert to Qdrant.
        
        Convenience method for content types that don't need the split result.
        """
        chunks = self._split_text(text)
        return self._embed_and_index(chunks, source_url, title, content_type)

    def _split_text(self, text: str) -> list[str]:
        """Split text into chunks using RecursiveCharacterTextSplitter."""
        if not text or len(text.strip()) < 50:
            return []
        return self._splitter.split_text(text)

    @staticmethod
    def _notify(callback: Optional[Callable], message: str, progress: float) -> None:
        """Helper to send progress updates if callback is provided."""
        if callback:
            try:
                callback(message, progress)
            except Exception:
                pass  # Progress callbacks should never crash the pipeline
        logger.info(f"[{progress:.0%}] {message}")

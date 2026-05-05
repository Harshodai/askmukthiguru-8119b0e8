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
from typing import Optional, Callable, Any

from langchain.text_splitter import RecursiveCharacterTextSplitter

from app.config import settings
from ingest.youtube_loader import (
    extract_video_id,
    is_playlist_url,
    is_channel_url,
    get_playlist_video_urls,
    fetch_transcript_hybrid,
    fetch_transcripts_concurrent,
)
from ingest.image_loader import is_image_url, process_image_url
from ingest.cleaner import clean_transcript
from ingest.raptor import RaptorIndexer
from services.embedding_service import EmbeddingService
from services.ollama_service import OllamaService
from services.qdrant_service import QdrantService
from services.ocr_service import OCRService

logger = logging.getLogger(__name__)


from ingest.auditor import DataAuditor
from ingest.corrector import TranscriptCorrector

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
    ) -> None:
        """
        Dependency Injection: All services are injected, not created internally.
        This makes the pipeline testable and decoupled.
        """
        self._qdrant = qdrant_service
        self._embedder = embedding_service
        self._llm = ollama_service
        self._ocr = ocr_service or OCRService()
        self._auditor = DataAuditor(ollama_service)
        self._corrector = TranscriptCorrector(ollama_service)
        self._lightrag = lightrag_service

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
        max_accuracy: bool = False,
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
        if is_playlist_url(url) or is_channel_url(url):
            return await self._ingest_playlist(url, max_accuracy, on_progress)
        elif is_image_url(url):
            return await self._ingest_image(url, on_progress)
        if extract_video_id(url):
            return await self._ingest_video(url, max_accuracy, on_progress)
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
        max_accuracy: bool = False,
        on_progress: Optional[Callable] = None,
    ) -> dict:
        """
        Ingest raw text directly, bypassing any fetching/loaders.
        Useful for migrations or re-processing existing data.
        """
        self._notify(on_progress, "Starting raw text processing...", 0.1)
        
        # Step 1: Clean
        clean_text = clean_transcript(text)

        # Step 2: Chunk (single split, reused for both index and RAPTOR)
        self._notify(on_progress, "Chunking and indexing...", 0.3)
        chunks = self._split_text(clean_text, title=title, speaker=speaker, topic=topic, semantic=max_accuracy)
        
        if not chunks:
            return {"status": "error", "message": "No meaningful chunks", "source_url": source_url}

        # Step 3: Document Augmentation (Ch 11 RAG Made Simple)
        self._notify(on_progress, "Augmenting chunks...", 0.5)
        augmented_chunks = await self._augment_chunks(chunks)

        # Step 4: Proposition Chunking (Phase 2 Improvement)
        if max_accuracy:
            self._notify(on_progress, "Refining propositions...", 0.7)
            proposition_chunks = []
            for chunk in augmented_chunks:
                props = await self._proposition_split(chunk)
                proposition_chunks.extend(props)
            final_chunks = proposition_chunks
        else:
            final_chunks = augmented_chunks

        # Step 5: Embed and index
        chunks_count = self._embed_and_index(
            final_chunks,
            source_url=source_url,
            title=title,
            speaker=speaker,
            topic=topic,
            content_type="migration",
        )

        # Step 6: RAPTOR tree
        self._notify(on_progress, "Building RAPTOR tree...", 0.85)
        chunk_dicts = [
            {"text": c, "source_url": source_url, "title": title, "speaker": speaker, "topic": topic}
            for c in chunks
        ]
        summaries_count = await self._raptor.build_tree(chunk_dicts)

        # Step 7: Graph RAG Extraction (Phase 4 Improvement)
        if self._lightrag:
            self._notify(on_progress, "Extracting knowledge graph...", 0.95)
            await self._lightrag.ainsert(clean_text)

        self._notify(on_progress, "Complete!", 1.0)
        return {
            "status": "success",
            "source_url": source_url,
            "chunks_indexed": chunks_count,
            "summaries_created": summaries_count,
        }

    async def _ingest_video(
        self,
        url: str,
        max_accuracy: bool = False,
        on_progress: Optional[Callable] = None,
    ) -> dict:
        """Ingest a single YouTube video."""
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

        # Step 1.2: Correct Transcript (Council Recommendation)
        # We correct BEFORE auditing to ensure the auditor sees high-quality text.
        self._notify(on_progress, "Correcting transcript (LLM)...", 0.15)
        
        # Security: Sanitize input to prevent injection
        sanitized_text = raw_text.replace("<|begin_of_text|>", "").replace("<|eot_id|>", "")
        raw_text = await self._corrector.correct_transcript(sanitized_text, url)

        # Step 1.5: Audit Content Quality
        self._notify(on_progress, "Auditing content quality...", 0.2)
        is_valid = await self._auditor.audit_transcript(raw_text, url)
        
        if not is_valid:
            return {
                "status": "rejected",
                "message": "Content rejected by Data Auditor (low quality or irrelevant)",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        # Step 2: Clean
        self._notify(on_progress, "Cleaning text...", 0.3)
        clean_text = clean_transcript(raw_text)

        # Step 3: Chunk (single split, reused for both index and RAPTOR)
        self._notify(on_progress, "Chunking and indexing...", 0.5)
        video_title = result.get("title", "") or ""
        video_speaker = result.get("speaker", "Unknown")
        video_topic = result.get("topic", "Spiritual")
        
        chunks = self._split_text(clean_text, title=video_title, speaker=video_speaker, topic=video_topic, semantic=max_accuracy)
        if not chunks:
            return {
                "status": "error",
                "message": "No meaningful chunks after cleaning",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        video_title = result.get("title", "") or ""

        # Step 4: Document Augmentation (Ch 11 RAG Made Simple)
        # Generate hypothetical questions for each chunk to improve retrieval recall.
        self._notify(on_progress, "Augmenting chunks with potential questions...", 0.6)
        augmented_chunks = await self._augment_chunks(chunks)

        # Step 4.5: Proposition Chunking (Phase 2 Improvement)
        # Break down augmented chunks into independent propositions for higher granularity.
        if max_accuracy:
            self._notify(on_progress, "Refining chunks into independent propositions...", 0.65)
            proposition_chunks = []
            for chunk in augmented_chunks:
                props = await self._proposition_split(chunk)
                proposition_chunks.extend(props)
            final_chunks = proposition_chunks
        else:
            final_chunks = augmented_chunks

        # Step 5: Embed and index
        chunks_count = self._embed_and_index(
            final_chunks,
            source_url=url,
            title=video_title,
            speaker=video_speaker,
            topic=video_topic,
            content_type="video",
        )

        # Step 5: RAPTOR tree (reuses the same chunks, passes source metadata)
        self._notify(on_progress, "Building RAPTOR tree...", 0.8)
        chunk_dicts = [
            {"text": c, "source_url": url, "title": video_title, "speaker": video_speaker, "topic": video_topic}
            for c in chunks
        ]
        summaries_count = await self._raptor.build_tree(chunk_dicts)

        # Step 6: Graph RAG Extraction (Phase 4 Improvement)
        if self._lightrag:
            self._notify(on_progress, "Extracting knowledge graph (LightRAG)...", 0.9)
            await self._lightrag.ainsert(clean_text)

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
        max_accuracy: bool = False,
        on_progress: Optional[Callable] = None,
    ) -> dict:
        """Ingest all videos in a YouTube playlist/channel using concurrent extraction."""
        self._notify(on_progress, "Fetching playlist/channel videos...", 0.05)
        videos = get_playlist_video_urls(url)
        
        if not videos:
            return {"status": "error", "message": "No videos found in playlist/channel"}

        # Phase 1: Concurrent transcript extraction (spawns multiple workers)
        self._notify(
            on_progress,
            f"Extracting transcripts for {len(videos)} videos concurrently...",
            0.1,
        )
        
        transcript_results = await fetch_transcripts_concurrent(
            videos,
            on_progress=lambda idx, total, res: self._notify(
                on_progress,
                f"Transcript {idx+1}/{total}: {videos[idx].get('title', '')[:40]}... [{res.get('method', '?')}]",
                0.1 + (idx / total) * 0.4,
            ),
        )

        # Phase 2: Process transcripts (clean, chunk, embed, index)
        total_chunks = 0
        total_summaries = 0
        processed = 0
        errors = []

        for i, (video, transcript) in enumerate(zip(videos, transcript_results)):
            progress = 0.5 + (i / len(videos)) * 0.4
            self._notify(
                on_progress,
                f"Indexing {i+1}/{len(videos)}: {video.get('title', 'Unknown')[:50]}...",
                progress,
            )

            if not transcript.get("text"):
                errors.append({"url": video["url"], "error": transcript.get("error", "No transcript")})
                continue

            try:
                raw_text = transcript["text"]

                # Correct + audit
                sanitized_text = raw_text.replace("<|begin_of_text|>", "").replace("<|eot_id|>", "")
                raw_text = await self._corrector.correct_transcript(sanitized_text, video["url"])
                is_valid = await self._auditor.audit_transcript(raw_text, video["url"])
                if not is_valid:
                    errors.append({"url": video["url"], "error": "Rejected by auditor"})
                    continue

                # Clean, chunk, embed, index
                clean_text = clean_transcript(raw_text)
                video_title = transcript.get("title", "")
                video_speaker = transcript.get("speaker", "Unknown")
                video_topic = transcript.get("topic", "Spiritual")
                
                chunks = self._split_text(clean_text, title=video_title, speaker=video_speaker, topic=video_topic, semantic=max_accuracy)
                if not chunks:
                    continue

                # Phase 2: Proposition Chunking
                if max_accuracy:
                    proposition_chunks = []
                    for chunk in chunks:
                        props = await self._proposition_split(chunk)
                        proposition_chunks.extend(props)
                    final_chunks = proposition_chunks
                else:
                    final_chunks = chunks

                chunks_count = self._embed_and_index(
                    final_chunks,
                    source_url=video["url"],
                    title=video_title,
                    speaker=video_speaker,
                    topic=video_topic,
                    content_type="video",
                )
                total_chunks += chunks_count

                # RAPTOR
                chunk_dicts = [
                    {"text": c, "source_url": video["url"], "title": video_title, "speaker": video_speaker, "topic": video_topic}
                    for c in chunks
                ]
                summaries_count = await self._raptor.build_tree(chunk_dicts)
                total_summaries += summaries_count

                # Step 6: Graph RAG
                await self._lightrag.ainsert(clean_text)
                
                processed += 1

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
    ) -> dict:
        """Ingest text from an image via OCR."""
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
        speaker: str = "Unknown",
        topic: str = "Spiritual",
    ) -> int:
        """
        Embed pre-split chunks (dense + sparse) and upsert to Qdrant.

        Uses encode_batch() to generate both dense and sparse vectors
        in a single pass for hybrid search support.
        """
        if not chunks:
            return 0

        # Check for existing content and delete for clean re-ingestion
        if self._qdrant.check_source_exists(source_url):
            logger.info(f"Source already indexed, overwriting: {source_url}")
            self._qdrant.delete_by_source(source_url)

        # Generate both dense and sparse embeddings in one pass
        embeddings = self._embedder.encode_batch(chunks)

        # Build metadata for each chunk
        metadatas = [
            {
                "source_url": source_url,
                "title": title,
                "speaker": speaker,
                "topic": topic,
                "content_type": content_type,
                "chunk_index": i,
                "raptor_level": 0,  # Leaf node
            }
            for i in range(len(chunks))
        ]

        # Upsert to Qdrant with both dense and sparse vectors
        return self._qdrant.upsert_chunks(
            chunks,
            embeddings['dense'],
            metadatas,
            sparse_vectors=embeddings['sparse'],
        )

    def _chunk_embed_index(
        self,
        text: str,
        source_url: str,
        title: str,
        content_type: str,
        speaker: str = "Unknown",
        topic: str = "Spiritual",
    ) -> int:
        """
        Split text → embed → upsert to Qdrant.
        
        Convenience method for content types that don't need the split result.
        """
        chunks = self._split_text(text, title=title, speaker=speaker, topic=topic)
        return self._embed_and_index(chunks, source_url, title, content_type, speaker=speaker, topic=topic)

    def _split_text(self, text: str, title: str = "", speaker: str = "", topic: str = "", semantic: bool = False) -> list[str]:
        """
        Split text into chunks using either Semantic Chunking or Recursive splitting,
        then prepend Contextual Chunk Headers.
        """
        if not text or len(text.strip()) < 50:
            return []
        
        if semantic:
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

    async def _augment_chunks(self, chunks: list[str]) -> list[str]:
        """
        Document Augmentation (Ch 11 RAG Made Simple).
        Generates hypothetical questions for each chunk and appends them
        to the text to improve retrieval recall.
        """
        if not settings.is_sarvam_cloud:
            return chunks # Skip for local models to save time
            
        augmented = []
        # Process in small batches to avoid rate limits
        for i, chunk in enumerate(chunks):
            try:
                # Only augment every 2nd chunk or if the chunk is long enough
                # to save cost/time while still providing coverage.
                if i % 2 == 0 and len(chunk) > 200:
                    questions = await self._llm.generate(
                        "Generate 2-3 brief hypothetical questions that this spiritual teaching answers.",
                        chunk,
                        max_tokens=100
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
        try:
            # System prompt: extraction instructions
            # User prompt: the actual text to decompose
            response = await self._llm.generate(
                "Decompose the following spiritual teaching into independent, self-contained propositions. Return each on a new line prefixed with '- '.",
                f"Teaching:\n{text}",
                max_tokens=500
            )
            
            # Parse lines starting with '- '
            propositions = []
            for line in response.split('\n'):
                line = line.strip()
                if line.startswith('- '):
                    prop = line[2:].strip()
                    if len(prop) > 20: # Filter out very short noise
                        propositions.append(prop)
                elif line and not line.startswith('#') and len(line) > 30:
                    # Fallback for LLMs that don't follow the format perfectly
                    propositions.append(line)
            
            if not propositions:
                return [text]
                
            return propositions
        except Exception as e:
            logger.error(f"Proposition splitting failed: {e}")
            return [text]

    def _semantic_split(self, text: str) -> list[str]:
        """
        Phase 3 Improvement: Semantic Chunking.
        Splits text into sentences and groups them based on embedding similarity.
        """
        import re
        import numpy as np
        
        # 1. Split into sentences
        sentences = re.split(r'(?<=[.!?]) +', text)
        if len(sentences) < 5:
            return [text]
            
        # 2. Embed sentences
        sentence_embeddings = self._embedder.encode(sentences)
        
        # 3. Calculate similarities between adjacent sentences
        similarities = []
        for i in range(len(sentence_embeddings) - 1):
            s1 = sentence_embeddings[i]
            s2 = sentence_embeddings[i+1]
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
                current_chunk = [sentences[i+1]]
            else:
                current_chunk.append(sentences[i+1])
                
        if current_chunk:
            chunks.append(" ".join(current_chunk))
            
        logger.info(f"Semantic Chunking: Created {len(chunks)} chunks from {len(sentences)} sentences")
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

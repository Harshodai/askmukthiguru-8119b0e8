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

import json
from pathlib import Path
import os

class IngestionCheckpoint:
    def __init__(self, filepath="data/ingest_checkpoint.json"):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(exist_ok=True)
        self.processed_chunks = self._load()

    def _load(self):
        if self.filepath.exists():
            return set(json.loads(self.filepath.read_text()))
        return set()

    def save(self, chunk_id: str):
        self.processed_chunks.add(chunk_id)
        self.filepath.write_text(json.dumps(list(self.processed_chunks)))
        
    def is_processed(self, chunk_id: str) -> bool:
        return chunk_id in self.processed_chunks

from langchain_text_splitters import RecursiveCharacterTextSplitter

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
        
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        elif ext == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        else:
            return {"status": "error", "message": f"Unsupported file type: {ext}"}

        if not text.strip():
            return {"status": "error", "message": "No text extracted from file"}

        # Ingest as raw text
        return await self.ingest_raw_text(
            text=text,
            source_url=os.path.basename(file_path),
            title=os.path.basename(file_path),
            content_type="document",
            max_accuracy=max_accuracy,
            on_progress=on_progress
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
            if max_accuracy:
                return await self._ingest_video_enhanced(url, on_progress)
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
        content_type: str = "migration",
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

        # Step 2: Chunk (Hierarchical or Standard)
        self._notify(on_progress, "Chunking and indexing...", 0.3)
        extra_metadatas = None
        if max_accuracy:
            # Phase 2 Improvement: Parent-Child Hierarchical Chunking
            self._notify(on_progress, "Generating hierarchical parent-child chunks...", 0.4)
            final_chunks, extra_metadatas = self._hierarchical_split(clean_text, title=title, speaker=speaker, topic=topic)
            chunks = final_chunks # For RAPTOR later
        else:
            chunks = self._split_text(clean_text, title=title, speaker=speaker, topic=topic)
            
            # Step 3: Document Augmentation (only for standard mode to avoid blowing up child chunk tokens)
            self._notify(on_progress, "Augmenting chunks...", 0.5)
            final_chunks = await self._augment_chunks(chunks)

        if not final_chunks:
            return {"status": "error", "message": "No meaningful chunks", "source_url": source_url}

        # Step 5: Embed and index
        chunks_count = self._embed_and_index(
            final_chunks,
            source_url=source_url,
            title=title,
            speaker=speaker,
            topic=topic,
            content_type=content_type,
            extra_metadatas=extra_metadatas
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

        # Step 3: Chunk (Hierarchical or Standard)
        self._notify(on_progress, "Chunking and indexing...", 0.5)
        video_title = result.get("title", "") or ""
        video_speaker = result.get("speaker", "Unknown")
        video_topic = result.get("topic", "Spiritual")
        
        extra_metadatas = None
        if max_accuracy:
            self._notify(on_progress, "Generating hierarchical parent-child chunks...", 0.6)
            final_chunks, extra_metadatas = self._hierarchical_split(clean_text, title=video_title, speaker=video_speaker, topic=video_topic)
            chunks = final_chunks
        else:
            chunks = self._split_text(clean_text, title=video_title, speaker=video_speaker, topic=video_topic)
            
            # Step 4: Document Augmentation (Standard only)
            self._notify(on_progress, "Augmenting chunks with potential questions...", 0.6)
            final_chunks = await self._augment_chunks(chunks)
        
        if not final_chunks:
            return {
                "status": "error",
                "message": "No meaningful chunks after cleaning",
                "source_url": url,
                "chunks_indexed": 0,
                "summaries_created": 0,
            }

        # Step 5: Embed and index
        chunks_count = self._embed_and_index(
            final_chunks,
            source_url=url,
            title=video_title,
            speaker=video_speaker,
            topic=video_topic,
            content_type="video",
            extra_metadatas=extra_metadatas
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

    async def _ingest_video_enhanced(
        self,
        url: str,
        on_progress: Optional[Callable] = None,
    ) -> dict:
        """
        Production Ingestion (Phase 3): Enhanced video processing.
        Includes speaker diarization, topic extraction, and partitioned indexing.
        """
        import uuid
        video_id = extract_video_id(url)
        self._notify(on_progress, "Phase 3: Starting enhanced ingestion...", 0.1)

        # 1. Fetch transcript with Diarization (via Sarvam STT)
        self._notify(on_progress, "Extracting audio and diarizing speakers...", 0.2)
        result = fetch_transcript_hybrid(video_id, max_accuracy=True)
        if not result.get("text"):
             return {"status": "error", "message": "Extraction failed", "source_url": url}

        raw_text = result["text"]

        # Step 1.2: Correct Transcript (Council Recommendation)
        self._notify(on_progress, "Correcting transcript (LLM)...", 0.3)
        sanitized_text = raw_text.replace("<|begin_of_text|>", "").replace("<|eot_id|>", "")
        raw_text = await self._corrector.correct_transcript(sanitized_text, url)

        video_title = result.get("title", "")
        
        # 2. Extract key spiritual topics (LLM)
        self._notify(on_progress, "Analyzing spiritual topics...", 0.4)
        topics = await self._extract_topics(raw_text)
        
        # 3. Clean and Partition
        clean_text = clean_transcript(raw_text)
        
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
        
        # Process each topic partition
        topic_index = 0
        for topic, text in sections.items():
            self._notify(on_progress, f"Processing topic: {topic}...", 0.7 + (topic_index * 0.05))
            
            # Split the topic segment into parent chunks
            parent_chunks = parent_splitter.split_text(text)
            
            for parent_chunk in parent_chunks:
                parent_id = str(uuid.uuid4())
                
                # Decompose the parent chunk into propositions (child chunks)
                propositions = await self._proposition_split(parent_chunk)
                augmented = await self._augment_chunks(propositions)
                
                # Prepend contextual header to each child chunk to guarantee UI clarity
                header_parts = [f"Source: {video_title}"]
                if speaker and speaker != "Unknown":
                    header_parts.append(f"Speaker: {speaker}")
                if topic and topic != "Spiritual":
                    header_parts.append(f"Topic: {topic}")
                header = f"[{' | '.join(header_parts)}]\n"
                
                for child_prop in augmented:
                    all_chunks.append(header + child_prop)
                    all_extra_metadatas.append({
                        "parent_id": parent_id,
                        "parent_text": parent_chunk,
                        "is_child": True,
                        "topic": topic,
                    })
            topic_index += 1

        # Embed and index all leaf chunks at once to prevent catastrophic deletion/overwrite
        self._notify(on_progress, "Indexing all extracted topic chunks...", 0.85)
        total_chunks = 0
        if all_chunks:
            total_chunks = self._embed_and_index(
                all_chunks,
                source_url=url,
                title=video_title,
                speaker=speaker,
                topic="Multi-Topic",  # Override by individual chunk's topic in extra_metadatas
                content_type="video_enhanced",
                extra_metadatas=all_extra_metadatas,
            )

        # 5. Build RAPTOR and Graph
        self._notify(on_progress, "Finalizing knowledge structure...", 0.9)
        if all_chunks:
            # Build RAPTOR summaries using the actual compiled leaf chunks
            chunks_data = [{"text": c, "source_url": url, "title": video_title} for c in all_chunks]
            await self._raptor.build_tree(chunks_data)
            
        if self._lightrag:
            await self._lightrag.ainsert(clean_text)

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
        response = await self._llm.generate(prompt, text[:5000], max_tokens=100)
        return [t.strip() for t in response.split(",")]

    def _topic_partition(self, text: str, topics: list[str]) -> dict[str, str]:
        """Simple partition of text based on topic keyword proximity."""
        # For a production version, use LLM to boundary-detect. 
        # Here we do a simplified version for the architecture.
        if not topics: return {"General": text}
        
        sections = {}
        text_len = len(text)
        chunk_size = text_len // len(topics)
        
        for i, topic in enumerate(topics):
            start = i * chunk_size
            end = (i + 1) * chunk_size if i < len(topics) - 1 else text_len
            sections[topic] = text[start:end]
        return sections

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

        # Phase 1: Filter out already processed videos
        checkpoint = IngestionCheckpoint()
        unprocessed_videos = []
        for i, video in enumerate(videos):
            if checkpoint.is_processed(video["url"]):
                self._notify(on_progress, f"Skipping {i+1}/{len(videos)}: {video.get('title', 'Unknown')[:50]}... (already processed)", 0.05 + (i / len(videos)) * 0.05)
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
                f"Transcript {idx+1}/{total}: {unprocessed_videos[idx].get('title', '')[:40]}... [{res.get('method', '?')}]",
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
                
                checkpoint.save(video["url"])
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
        extra_metadatas: Optional[list[dict]] = None,
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
        metadatas = []
        for i in range(len(chunks)):
            base_meta = {
                "source_url": source_url,
                "title": title,
                "speaker": speaker,
                "topic": topic,
                "content_type": content_type,
                "chunk_index": i,
                "raptor_level": 0,  # Leaf node
            }
            if extra_metadatas and i < len(extra_metadatas):
                base_meta.update(extra_metadatas[i])
            metadatas.append(base_meta)

        # Upsert to Qdrant with both dense and sparse vectors
        return self._qdrant.upsert_chunks(
            chunks,
            embeddings['dense'],
            metadatas,
            sparse_vectors=embeddings['sparse'],
        )

    def _hierarchical_split(self, text: str, title: str = "", speaker: str = "", topic: str = "") -> tuple[list[str], list[dict]]:
        """
        Phase 2 Improvement: Parent-Child Hierarchical Chunking.
        Splits text into large Parent Chunks, and then into smaller Child Chunks.
        Returns: (child_texts, child_metadatas) where metadatas contain parent mapping.
        """
        import uuid
        
        # 1. Split into large parent chunks (e.g., 1500 chars)
        parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=200,
            length_function=len,
        )
        parent_chunks = parent_splitter.split_text(text)
        
        # 2. Split into small child chunks (e.g., 400 chars)
        child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=400,
            chunk_overlap=50,
            length_function=len,
        )
        
        all_child_texts = []
        all_child_metadatas = []
        
        for parent_text in parent_chunks:
            parent_id = str(uuid.uuid4())
            children = child_splitter.split_text(parent_text)
            
            for child in children:
                # Add context headers to the child
                header_parts = [f"Source: {title}"]
                if speaker and speaker != "Unknown":
                    header_parts.append(f"Speaker: {speaker}")
                if topic and topic != "Spiritual":
                    header_parts.append(f"Topic: {topic}")
                header = f"[{' | '.join(header_parts)}]\n"
                
                all_child_texts.append(header + child)
                all_child_metadatas.append({
                    "parent_id": parent_id,
                    "parent_text": parent_text,
                    "is_child": True
                })
                
        return all_child_texts, all_child_metadatas

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

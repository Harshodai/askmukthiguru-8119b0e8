"""
Mukthi Guru — Adaptive Chunking Service

Implements dynamic adaptive chunking inspired by ekimetrics/adaptive-chunking.
Evaluates Recursive and Semantic splitting strategies on-the-fly using:
  - Size Compliance (SC): Keeps chunks within optimal length bounds (200 to 1200 characters).
  - Intrachunk Cohesion (ICC): Cosine similarity of sentences to the overall chunk embedding.
Dynamically chooses the highest scoring strategy per document to optimize context quality.
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any

import numpy as np

from app.config import settings

if TYPE_CHECKING:
    from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

class AdaptiveChunkingService:
    """
    Evaluates and dynamically applies the best chunking strategy
    (Recursive vs Semantic) for document ingestion.
    """

    def __init__(self, embedding_service: EmbeddingService) -> None:
        """Initialize the service with the shared embedding service."""
        self.embedding_service = embedding_service
        logger.info("Adaptive Chunking Service initialized")

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences using regex boundary detection."""
        # Split on sentence terminals (.!?), keeping the punctuation, followed by whitespace
        sentence_ends = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentence_ends if s.strip()]

    def _cosine_similarity(self, v1: list[float] | np.ndarray, v2: list[float] | np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        a = np.array(v1)
        b = np.array(v2)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _split_recursively(self, text: str, chunk_size: int = 800, chunk_overlap: int = 150) -> list[str]:
        """Simple recursive character splitter (fallback and baseline)."""
        if not text:
            return []
            
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = []
        current_len = 0
        
        for p in paragraphs:
            p_len = len(p)
            if p_len > chunk_size:
                # If paragraph itself is too large, split by lines
                lines = p.split("\n")
                for line in lines:
                    line_len = len(line)
                    if current_len + line_len > chunk_size and current_chunk:
                        chunks.append("\n".join(current_chunk))
                        # Keep overlap
                        overlap_size = 0
                        overlap_chunk = []
                        for old_line in reversed(current_chunk):
                            if overlap_size + len(old_line) < chunk_overlap:
                                overlap_chunk.insert(0, old_line)
                                overlap_size += len(old_line)
                            else:
                                break
                        current_chunk = overlap_chunk
                        current_len = overlap_size
                    current_chunk.append(line)
                    current_len += line_len
            else:
                if current_len + p_len > chunk_size and current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    # Keep overlap
                    overlap_size = 0
                    overlap_chunk = []
                    for old_p in reversed(current_chunk):
                        if overlap_size + len(old_p) < chunk_overlap:
                            overlap_chunk.insert(0, old_p)
                            overlap_size += len(old_p)
                        else:
                            break
                    current_chunk = overlap_chunk
                    current_len = overlap_size
                current_chunk.append(p)
                current_len += p_len
                
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
            
        return [c.strip() for c in chunks if c.strip()]

    def _split_semantically(self, text: str, threshold: float = 0.72) -> list[str]:
        """Split text semantically based on sentence embedding similarities."""
        sentences = self._split_into_sentences(text)
        if len(sentences) <= 1:
            return sentences

        try:
            # Batch encode all sentences for efficiency
            sentence_embeddings = self.embedding_service.encode(sentences)
            
            # Compute similarities between consecutive sentences
            similarities = []
            for i in range(len(sentences) - 1):
                sim = self._cosine_similarity(sentence_embeddings[i], sentence_embeddings[i+1])
                similarities.append(sim)
                
            # Form chunks based on similarity threshold splits
            chunks = []
            current_sentences = [sentences[0]]
            
            for i, sim in enumerate(similarities):
                # If similarity is below threshold, start a new chunk
                # Also cap individual chunk size to avoid building massive single-chunk structures
                current_length = sum(len(s) for s in current_sentences)
                if sim < threshold or current_length > 1500:
                    chunks.append(" ".join(current_sentences))
                    current_sentences = []
                current_sentences.append(sentences[i + 1])
                
            if current_sentences:
                chunks.append(" ".join(current_sentences))
                
            # Merge tiny chunks to preserve context
            merged_chunks = []
            current_chunk = ""
            for chunk in chunks:
                if not current_chunk:
                    current_chunk = chunk
                elif len(current_chunk) + len(chunk) < 250:
                    current_chunk += " " + chunk
                else:
                    merged_chunks.append(current_chunk)
                    current_chunk = chunk
            if current_chunk:
                merged_chunks.append(current_chunk)
                
            return merged_chunks

        except Exception as e:
            logger.error(f"Semantic chunking failed, falling back to recursive: {e}")
            return self._split_recursively(text)

    def _score_chunks(self, chunks: list[str]) -> float:
        """
        Evaluate quality of chunks based on Size Compliance (SC) and Intrachunk Cohesion (ICC).
        Returns a combined score in range [0, 1].
        """
        if not chunks:
            return 0.0

        # 1. Size Compliance (SC): ratio of chunks between 200 and 1200 characters
        sc_scores = [1.0 if 200 <= len(c) <= 1200 else 0.3 for c in chunks]
        sc = float(np.mean(sc_scores))

        # 2. Intrachunk Cohesion (ICC): sentence similarity to the chunk overall
        cohesions = []
        for chunk in chunks:
            sentences = self._split_into_sentences(chunk)
            if len(sentences) <= 1:
                cohesions.append(1.0)
                continue
                
            try:
                # Get embeddings for chunk's sentences
                sent_embs = self.embedding_service.encode(sentences)
                # Chunk embedding is the centroid of sentence embeddings
                chunk_emb = np.mean(sent_embs, axis=0)
                
                # Cohesion is average similarity of each sentence to chunk centroid
                chunk_cohesion = np.mean([
                    self._cosine_similarity(emb, chunk_emb) for emb in sent_embs
                ])
                cohesions.append(float(chunk_cohesion))
            except Exception as e:
                logger.warning(f"Error calculating cohesion for chunk: {e}")
                cohesions.append(0.5)

        icc = float(np.mean(cohesions)) if cohesions else 0.5

        # Weighted average: 40% size constraints, 60% semantic cohesion
        total_score = (0.4 * sc) + (0.6 * icc)
        logger.debug(f"Chunk set evaluated: size={len(chunks)}, SC={sc:.4f}, ICC={icc:.4f}, Score={total_score:.4f}")
        return total_score

    def chunk_document(self, text: str) -> list[str]:
        """
        Dynamically chooses the best chunking strategy for the text.
        
        Args:
            text: Entire text of the document to be split.

        Returns:
            List of text chunks.
        """
        if not text or not text.strip():
            return []

        doc_len = len(text)

        # Baseline fast-path for short documents or if disabled
        if doc_len < settings.adaptive_chunking_min_chars or not settings.use_adaptive_chunking:
            logger.info(f"Skipping adaptive chunking evaluation (length={doc_len} chars). Defaulting to Recursive Splitter.")
            return self._split_recursively(text, settings.rag_chunk_size, settings.rag_chunk_overlap)

        logger.info(f"Running Adaptive Chunking evaluation on document (length={doc_len} chars)...")
        start_time = time.perf_counter()

        # Sample the first 10,000 characters to evaluate candidate strategies efficiently without excessive cost
        sample_size = min(doc_len, 10000)
        sample_text = text[:sample_size]

        # Generate candidates on sample
        recursive_chunks = self._split_recursively(sample_text, 700, 120)
        semantic_chunks = self._split_semantically(sample_text, threshold=0.72)

        # Score candidates
        logger.info("Scoring Recursive splitter candidate set...")
        recursive_score = self._score_chunks(recursive_chunks)
        
        logger.info("Scoring Semantic splitter candidate set...")
        semantic_score = self._score_chunks(semantic_chunks)

        logger.info(f"Scores: Recursive={recursive_score:.4f} | Semantic={semantic_score:.4f}")

        # Choose the best strategy and apply to entire document
        if semantic_score >= recursive_score:
            logger.info("✅ Selected: SEMANTIC splitter.")
            result_chunks = self._split_semantically(text, threshold=0.72)
        else:
            logger.info("✅ Selected: RECURSIVE splitter.")
            result_chunks = self._split_recursively(text, settings.rag_chunk_size, settings.rag_chunk_overlap)

        duration = time.perf_counter() - start_time
        logger.info(f"Document chunking completed in {duration:.4f}s. Total chunks: {len(result_chunks)}")
        
        return result_chunks

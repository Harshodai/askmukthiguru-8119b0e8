"""
Mukthi Guru — Contextual Compression (Ch 10 RAG Made Simple)

Strips irrelevant sentences from retrieved chunks based on their 
semantic similarity to the query. 
Reduces noise and improves LLM focus.
"""

import logging
import re
from typing import Any, List, Optional
import numpy as np
from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

class ContextualCompressor:
    def __init__(self, embedding_service: EmbeddingService, threshold: float = 0.5):
        self._embedder = embedding_service
        self._threshold = threshold

    def _cosine_similarity(self, a, b):
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return np.dot(a, b) / (norm_a * norm_b)

    def compress(self, query: str, document_text: str) -> str:
        """
        Compress a document to only its most relevant sentences.
        """
        # Split into sentences (simple regex)
        sentences = re.split(r'(?<=[.!?]) +', document_text)
        if len(sentences) <= 2:
            return document_text

        # Embed query and sentences
        query_enc = self._embedder.encode_single_full(query)
        query_vec = query_enc['dense']
        
        sentence_encs = self._embedder.encode_batch(sentences)
        sentence_vecs = sentence_encs['dense']

        relevant_sentences = []
        for i, sent_vec in enumerate(sentence_vecs):
            score = self._cosine_similarity(query_vec, sent_vec)
            if score >= self._threshold:
                relevant_sentences.append(sentences[i])

        if not relevant_sentences:
            # Fallback: keep the first and last sentence if none are "relevant"
            return sentences[0] + " ... " + sentences[-1]

        compressed = " ".join(relevant_sentences)
        reduction = 1 - (len(compressed) / len(document_text))
        logger.info(f"Compressed doc: {len(document_text)} -> {len(compressed)} chars ({reduction:.1%} reduction)")
        
        return compressed

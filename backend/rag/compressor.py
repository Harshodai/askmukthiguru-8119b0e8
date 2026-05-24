"""
Mukthi Guru — Contextual Compression & Token Budget Allocation

Compresses retrieved documents by extracting only the most relevant
sentences using Microsoft LLMLingua (if available) or the CrossEncoder reranker.
Enforces strict Token Budget Allocation to stay within optimal context windows.

Token Budget Limits:
  - System/Core Instructions: 512 tokens (~400 words)
  - Context (Retrieved Docs): 2048 tokens (~1500 words)
  - Chat History: 1024 tokens (~800 words)
  - User Query: 512 tokens (~400 words)
"""

import logging
import re

logger = logging.getLogger(__name__)

# Minimum score threshold for a sentence to be considered relevant
_SENTENCE_THRESHOLD = 0.3

# Try importing LLMLingua optionally for advanced 20x compression
try:
    from llmlingua import PromptCompressor
    _HAS_LLMLINGUA = True
except ImportError:
    _HAS_LLMLINGUA = False
    PromptCompressor = None


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using regex-based boundary detection."""
    # Split on sentence-ending punctuation followed by space or newline
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    # Filter out very short fragments
    return [s.strip() for s in sentences if len(s.strip()) > 20]


def cap_to_token_budget(text: str, max_tokens: int) -> str:
    """
    Cap text to a strict token budget using a fast word-count proxy.
    Assumes 1 word ~ 1.3 tokens (approximate for English/Indic text mixed).
    """
    if not text:
        return ""
    
    words = text.split()
    max_words = int(max_tokens / 1.3)
    
    if len(words) <= max_words:
        return text
        
    logger.info(f"Token Budget: Capping text from {len(words)} to {max_words} words ({max_tokens} token budget).")
    return " ".join(words[:max_words])


def compress_documents(
    query: str,
    documents: list[dict],
    reranker,
    threshold: float = _SENTENCE_THRESHOLD,
    min_sentences: int = 2,
    context_budget: int = 2048,
) -> list[dict]:
    """
    Compress documents by extracting only relevant sentences and enforcing budget.

    If LLMLingua is installed, uses it for advanced prompt-level compression.
    Otherwise, falls back to highly-optimized sentence-level CrossEncoder compression.

    Args:
        query: The user's question
        documents: List of document dicts with 'text' key
        reranker: CrossEncoder model (from EmbeddingService)
        threshold: Minimum relevance score for a sentence
        min_sentences: Keep at least this many sentences per doc
        context_budget: Strict token budget for the entire context

    Returns:
        List of compressed document dicts (same structure, shorter text)
    """
    if not documents:
        return []

    # LLMLingua Advanced Compression Path
    if _HAS_LLMLINGUA:
        try:
            logger.info("LLMLingua: Compressing context using Microsoft LLMLingua...")
            compressor = PromptCompressor(
                model_name="microsoft/llmlingua-2-bert-base-multilingual-cased-meeting",
                use_llmlingua2=True,
            )
            
            compressed_docs = []
            for doc in documents:
                text = doc.get("text", "")
                if len(text.split()) < 50:
                    compressed_docs.append(doc)
                    continue

                res = compressor.compress_prompt(
                    context=[text],
                    instruction="",
                    question=query,
                    rate=0.4,  # Target 60% compression rate
                    force_tokens=["Sri Preethaji", "Sri Krishnaji", "Beautiful State", "Serene Mind"],
                )
                compressed_text = res.get("compressed_prompt", text)
                compressed_docs.append({**doc, "text": compressed_text})
            
            documents = compressed_docs
        except Exception as e:
            logger.warning(f"LLMLingua compression failed ({e}), falling back to CrossEncoder.")

    # CrossEncoder Sentence-level Compression Path (Default / Fallback)
    compressed = []
    total_original = 0
    total_compressed = 0

    for doc in documents:
        text = doc.get("text", "")
        sentences = _split_into_sentences(text)

        if len(sentences) <= min_sentences:
            # Too few sentences to compress — keep as-is
            compressed.append(doc)
            continue

        total_original += len(text)

        # Score each sentence against the query
        pairs = [(query, sent) for sent in sentences]
        try:
            scores = reranker.predict(pairs)
        except Exception as e:
            logger.warning(f"Compression scoring failed: {e}")
            compressed.append(doc)
            continue

        # Sort sentences by score and keep those above threshold
        scored = sorted(
            zip(sentences, scores),
            key=lambda x: x[1],
            reverse=True,
        )

        # Keep sentences above threshold, but ensure minimum count
        relevant = [s for s, score in scored if score >= threshold]
        if len(relevant) < min_sentences:
            relevant = [s for s, _ in scored[:min_sentences]]

        # Reconstruct in original order
        original_order = [s for s in sentences if s in relevant]

        compressed_text = " ".join(original_order)
        total_compressed += len(compressed_text)

        compressed_doc = {**doc, "text": compressed_text}
        compressed.append(compressed_doc)

    # Log compression performance
    if total_original > 0:
        ratio = total_compressed / total_original
        logger.info(
            f"Contextual compression: {total_original} → {total_compressed} chars "
            f"({ratio:.0%} of original)"
        )

    # Enforce strict Token Budget Allocation on the entire merged context
    total_context_words = sum(len(d["text"].split()) for d in compressed)
    max_context_words = int(context_budget / 1.3)
    
    if total_context_words > max_context_words:
        logger.info(f"Token Budget: Merged context ({total_context_words} words) exceeds budget. Truncating chunks.")
        budget_per_doc = int(max_context_words / len(compressed))
        for doc in compressed:
            doc["text"] = cap_to_token_budget(doc["text"], int(budget_per_doc * 1.3))

    return compressed

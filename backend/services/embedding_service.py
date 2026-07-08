"""
Mukthi Guru — Embedding & Reranking Service

Models:
  - Encoder: BAAI/bge-m3 (1024 dims, multilingual, native dense+sparse+ColBERT)
  - Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2 (CPU)

bge-m3 produces dense, sparse (lexical), and ColBERT vectors in a single encode() call,
enabling native hybrid search without a separate BM25/sparse encoder. Supports 100+
languages including all 10 target Indian languages.

Async API (GIL escape via asyncio.to_thread):
  - All encode_*/rerank methods have ``async def`` siblings named encode_async /
    encode_batch_async / rerank_async / cascaded_rerank_async.
  - These run the CPU-bound sync method in a background thread, keeping the
    FastAPI event loop non-blocking under concurrent requests.
  - Thread-pool size: EMBED_THREAD_WORKERS env var (default: auto-detect via
    ``min(2, os.cpu_count() // 2 or 1)``).
    Docker single-node → 1 worker; Railway/K8s multi-CPU → 2 workers.
  - Model stays in-process (no ProcessPoolExecutor re-load overhead).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

# Silence Hugging Face tokenizer advisory warnings in logs
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "true"

from app.config import settings
from app.metrics import (
    EMBEDDING_CACHE_OPS,
    EMBEDDING_CACHE_SIZE,
    EMBEDDING_ERRORS,
    EMBEDDING_LATENCY,
    EMBEDDING_MODEL_FALLBACK,
)

logger = logging.getLogger(__name__)


def _apply_query_expansion(text: str) -> str:
    """Rule-based query expansion for geographic/biographical terms.

    Aids dense retrieval for known entity patterns ("where ekam",
    "who preethaji"). Applied before encoding so the augmented text
    participates in the embedding. Shared by `encode_single_full`
    and the retrieval node's batched-encode path.
    """
    low = text.lower()
    if "where" in low and ("ekam" in low or "akam" in low):
        return f"{text} temple location Tirupati Chennai"
    if "who" in low and ("preethaji" in low or "krishnaji" in low):
        return f"{text} founders Ekam one world academy"
    return text


class EmbeddingService:
    """
    Multilingual embedding service with native hybrid search support.

    bge-m3 produces three vector types in one forward pass:
    - Dense (1024d): For semantic similarity search
    - Sparse (lexical weights): For keyword/BM25-style matching
    - ColBERT (token-level): For fine-grained late interaction (optional)

    This eliminates the need for a separate sparse encoder and enables
    true hybrid search across 100+ languages.
    """

    def __init__(self) -> None:
        """Initialize with None models — will be loaded on first use."""
        import threading

        self._encoder = None
        self._reranker = None
        self._colbert = None
        self._lock = threading.Lock()
        self._inference_lock = threading.RLock()
        # REQUIRED for multilingual-e5-large-instruct
        self.instruction = "Given a spiritual teaching, retrieve relevant passages: "
        # Embedding cache to avoid redundant encodes
        from app.config import settings
        from services.cache_service import EmbeddingCache

        self._embed_cache = EmbeddingCache(max_size=settings.embedding_cache_size)
        EMBEDDING_CACHE_SIZE.set(self._embed_cache.max_size)
        logger.info("Embedding service initialized (lazy load)")

    def _thread_setup(self) -> None:
        """Common PyTorch/CPU thread setup to keep memory low."""
        import os
        os.environ["OMP_NUM_THREADS"] = "1"
        os.environ["MKL_NUM_THREADS"] = "1"
        os.environ["OPENBLAS_NUM_THREADS"] = "1"
        os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
        os.environ["NUMEXPR_NUM_THREADS"] = "1"
        import torch
        torch.set_num_threads(1)

    def _get_device(self) -> str:
        import torch
        device = "cpu"
        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        return device

    def _load_encoder(self, model_name: str, device: str) -> None:
        """Helper to load a specific encoder model into memory."""
        is_bge_m3 = (model_name == "BAAI/bge-m3")
        if is_bge_m3:
            # Apply monkeypatch to fix transformers/FlagEmbedding dtype incompatibility
            try:
                from transformers import AutoModel
                if not hasattr(AutoModel, "_original_from_pretrained_patched"):
                    original_from_pretrained = AutoModel.from_pretrained
                    @classmethod
                    def patched_from_pretrained(cls, *args, **kwargs):
                        if "dtype" in kwargs:
                            kwargs["torch_dtype"] = kwargs.pop("dtype")
                        return original_from_pretrained.__func__(cls, *args, **kwargs)
                    AutoModel.from_pretrained = patched_from_pretrained
                    AutoModel._original_from_pretrained_patched = True
                    logger.info("Monkeypatched AutoModel.from_pretrained to support 'dtype' parameter.")
            except Exception as e:
                logger.warning(f"Failed to patch AutoModel.from_pretrained: {e}")

            from FlagEmbedding import BGEM3FlagModel

            logger.info(f"Loading encoder: {model_name} on device: {device}")
            self._encoder = BGEM3FlagModel(
                model_name,
                use_fp16=(device == "cuda"),
                device=device,
            )

            # Monkeypatch to catch and diagnose PyTorch model forward pass crashes
            try:
                original_forward = self._encoder.model.forward

                def custom_forward(*args, **kwargs):
                    try:
                        return original_forward(*args, **kwargs)
                    except Exception as e:
                        logger.error(
                            f"❌ ROOT CAUSE: BGE-M3 model forward pass failed: {e}",
                            exc_info=True,
                        )
                        raise e

                self._encoder.model.forward = custom_forward

                original_pad = self._encoder.tokenizer.pad

                def custom_pad(encoded_inputs, *args, **kwargs):
                    if not encoded_inputs:
                        raise ValueError(
                            "tokenizer.pad received empty encoded_inputs. This is caused by the BGE-M3 "
                            "batch_size loop degrading to 0 because of persistent model forward pass failures."
                        )
                    return original_pad(encoded_inputs, *args, **kwargs)

                self._encoder.tokenizer.pad = custom_pad
                logger.info(
                    "Successfully monkeypatched BGEM3FlagModel for robust error tracing."
                )
            except Exception as e:
                logger.warning(f"Failed to apply BGEM3FlagModel monkeypatch: {e}")
        else:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading SentenceTransformer: {model_name} on device: {device}")
            self._encoder = SentenceTransformer(
                model_name,
                device=device,
                model_kwargs={"low_cpu_mem_usage": True},
            )

    def _ensure_encoder(self) -> None:
        """Lazy-load the encoder model with multi-tier fallback support."""
        if self._encoder is not None:
            return
        with self._lock:
            if self._encoder is not None:
                return
            self._thread_setup()
            device = self._get_device()
            logger.info(f"Dynamic device selection: using {device} for local models")

            FALLBACK_CHAIN = [
                settings.embedding_model,
                "intfloat/multilingual-e5-small",
                "BAAI/bge-small-en-v1.5",
                "sentence-transformers/all-MiniLM-L6-v2",
            ]
            FALLBACK_DIMS = {
                "intfloat/multilingual-e5-small": 384,
                "intfloat/multilingual-e5-large-instruct": 1024,
                "BAAI/bge-small-en-v1.5": 384,
                "sentence-transformers/all-MiniLM-L6-v2": 384,
            }

            last_error = None
            for i, model_name in enumerate(FALLBACK_CHAIN):
                try:
                    self._load_encoder(model_name, device)
                    logger.info(
                        f"Successfully loaded embedding model '{model_name}'"
                    )
                    if model_name != settings.embedding_model:
                        settings.embedding_model = model_name
                        if model_name in FALLBACK_DIMS:
                            settings.embedding_dimension = FALLBACK_DIMS[model_name]
                        logger.info(
                            f"Config updated: model={model_name}, "
                            f"dim={settings.embedding_dimension}"
                        )
                    return
                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"Failed to load embedding model '{model_name}': {e}."
                    )
                    if i + 1 < len(FALLBACK_CHAIN):
                        EMBEDDING_MODEL_FALLBACK.labels(
                            from_model=model_name,
                            to_model=FALLBACK_CHAIN[i + 1],
                        ).inc()

            logger.error(
                f"Failed to load all {len(FALLBACK_CHAIN)} embedding models. "
                f"Tried: {', '.join(FALLBACK_CHAIN)}. Last error: {last_error}",
                exc_info=True,
            )
            raise last_error

    def _ensure_reranker(self) -> None:
        """Lazy-load the reranker model."""
        if self._reranker is not None:
            return
        with self._lock:
            if self._reranker is not None:
                return
            self._thread_setup()
            device = self._get_device()
            from sentence_transformers import CrossEncoder

            logger.info(f"Loading reranker: {settings.reranker_model} on device: {device}")
            self._reranker = CrossEncoder(
                settings.reranker_model,
                device=device,
            )
            model_name = (settings.reranker_model or "").lower()
            if "jina" in model_name or "jina-reranker" in model_name:
                self._reranker_outputs_probs = True
                logger.info(
                    f"Reranker '{settings.reranker_model}' emits probabilities; skipping sigmoid normalization."
                )
            else:
                self._reranker_outputs_probs = False

    def _ensure_colbert(self) -> None:
        """Lazy-load the ColBERT model.

        Fallback behavior (pre-existing): if RAGatouille is not installed, or
        the ``colbert-ir/colbertv2.0`` model fails to load (offline, no HF
        cache, network error, etc.), ``_colbert`` is set to ``False`` and the
        cascaded rerank path degrades to pure CrossEncoder. This is intentional
        — ColBERTv2 is an optional quality boost, not a hard dependency. The
        warning below is logged loudly (not silently) so operators know the
        fallback is active and can pre-download the model if they want it.

        If the primary ColBERT model fails, an alternative (``colbert-ir/colbertv2.0``
        → ``jina-colbert/v1-base-en``) is attempted before degrading to CrossEncoder.
        """
        if self._colbert is not None:
            return
        with self._lock:
            if self._colbert is not None:
                return
            self._thread_setup()
            for model_name in ("colbert-ir/colbertv2.0", "jina-colbert/v1-base-en"):
                try:
                    from ragatouille import RAGPretrainedModel

                    logger.info(f"Loading ColBERTv2 reranker (RAGatouille): {model_name}")
                    self._colbert = RAGPretrainedModel.from_pretrained(model_name)
                    return
                except (ImportError, ModuleNotFoundError):
                    logger.info(
                        "ColBERTv2 (RAGatouille) is not installed (optional). "
                        "Cascaded reranking will fallback to pure CrossEncoder."
                    )
                    self._colbert = False
                    break
                except Exception as e:
                    logger.warning(
                        f"Failed to load RAGatouille ColBERT model '{model_name}': {e}. "
                        f"Attempting next ColBERT model alternative if available."
                    )
                    self._colbert = False
            if self._colbert is False:
                logger.warning(
                    "ColBERTv2 unavailable — all model attempts failed. "
                    "Falling back to pure CrossEncoder reranking (active path). "
                    "To enable ColBERTv2, run: pip install ragatouille>=2.0.0 && "
                    "python -c 'from ragatouille import RAGPretrainedModel; "
                    "RAGPretrainedModel.from_pretrained(\"colbert-ir/colbertv2.0\")'"
                )

    def _ensure_models(self) -> None:
        """Lazy-load all models (backward compatibility)."""
        self._ensure_encoder()
        self._ensure_reranker()
        self._ensure_colbert()

    def encode(self, texts: list[str]) -> list[list[float]]:
        """
        Encode texts into dense vectors only (backward compatible).

        Used for clustering (RAPTOR) and simple comparisons where
        sparse vectors are not needed.

        Returns:
            List of dense embedding vectors (1024 dims each)
        """
        if not texts:
            return []

        start_time = time.monotonic()
        with self._inference_lock:
            self._ensure_encoder()
            is_bge_m3 = (settings.embedding_model == "BAAI/bge-m3")

            max_retries = 3
            last_err = None
            for attempt in range(1, max_retries + 1):
                try:
                    import torch
                    with torch.inference_mode():
                        if is_bge_m3:
                            output = self._encoder.encode(
                                texts,
                                return_dense=True,
                                return_sparse=False,
                                return_colbert_vecs=False,
                            )
                            result = output["dense_vecs"].tolist()
                        else:
                            output = self._encoder.encode(
                                texts,
                                normalize_embeddings=True,
                            )
                            if isinstance(output, list):
                                result = output
                            else:
                                result = output.tolist()
                    EMBEDDING_LATENCY.labels(operation="encode").observe(
                        time.monotonic() - start_time
                    )
                    return result
                except Exception as e:
                    last_err = e
                    EMBEDDING_ERRORS.labels(operation="encode").inc()
                    logger.warning(
                        f"Dense embedding failed on attempt {attempt}/{max_retries}: {e}. "
                        f"Performing garbage collection and retrying in 2 seconds..."
                    )
                    import gc

                    gc.collect()
                    time.sleep(2)

            logger.error(
                f"All {max_retries} attempts to encode dense failed. "
                f"Raising last error: {last_err}"
            )
            raise last_err

    async def encode_async(self, texts: list[str]) -> list[list[float]]:
        """Async GIL-escape wrapper for encode(). Safe to await in FastAPI handlers."""
        return await asyncio.to_thread(self.encode, texts)

    def encode_single(self, text: str) -> list[float]:
        """Encode a single text into a dense vector."""
        return self.encode([text])[0]

    async def encode_single_async(self, text: str) -> list[float]:
        """Async GIL-escape wrapper for encode_single()."""
        return await asyncio.to_thread(self.encode_single, text)

    def encode_batch(self, texts: list[str]) -> dict:
        """
        Encode a batch of texts into both dense and sparse vectors.

        Used at ingestion time and for query encoding in hybrid search.

        Returns:
            dict with:
              - 'dense': list of dense vectors (1024d each)
              - 'sparse': list of sparse dicts {token_id: weight}
        """
        if not texts:
            return {"dense": [], "sparse": []}

        # Check cache for each text (using prefixed text as cache key)
        cached_embeddings = []
        uncached_indices = []
        uncached_prefixed_texts = []

        for i, text in enumerate(texts):
            prefixed_text = f"{self.instruction}{text}"
            cached = self._embed_cache.get(prefixed_text)
            if cached is not None:
                cached_embeddings.append((i, cached))
                EMBEDDING_CACHE_OPS.labels(result="hit").inc()
            else:
                uncached_indices.append(i)
                uncached_prefixed_texts.append(prefixed_text)
                EMBEDDING_CACHE_OPS.labels(result="miss").inc()

        # If all are cached, return immediately
        if not uncached_prefixed_texts:
            # Reorder cached results to match original order
            dense_results = [None] * len(texts)
            sparse_results = [None] * len(texts)
            for idx, emb in cached_embeddings:
                dense_results[idx] = emb["dense"]
                sparse_results[idx] = emb["sparse"]
            return {
                "dense": dense_results,
                "sparse": sparse_results,
            }

        start_time = time.monotonic()
        with self._inference_lock:
            self._ensure_encoder()
            is_bge_m3 = (settings.embedding_model == "BAAI/bge-m3")

            max_retries = 3
            last_err = None
            for attempt in range(1, max_retries + 1):
                try:
                    import torch
                    with torch.inference_mode():
                        if is_bge_m3:
                            output = self._encoder.encode(
                                uncached_prefixed_texts,
                                return_dense=True,
                                return_sparse=True,
                                return_colbert_vecs=False,
                            )
                            dense_vecs = output["dense_vecs"].tolist()
                            sparse_weights = output["lexical_weights"]
                        else:
                            # E5 models: explicitly disable sparse/ColBERT to avoid
                            # random-weight projection head initialization warning
                            try:
                                output = self._encoder.encode(
                                    uncached_prefixed_texts,
                                    return_dense=True,
                                    return_sparse=False,
                                    return_colbert_vecs=False,
                                )
                                dense_vecs = output["dense_vecs"].tolist()
                            except Exception:
                                # Fallback for models that don't support BGE-M3-specific flags
                                output = self._encoder.encode(
                                    uncached_prefixed_texts,
                                    normalize_embeddings=True,
                                )
                                if isinstance(output, list):
                                    dense_vecs = output
                                else:
                                    dense_vecs = output.tolist()
                            sparse_weights = [{} for _ in uncached_prefixed_texts]

                    # Build results in original order
                    dense_results = [None] * len(texts)
                    sparse_results = [None] * len(texts)
  
                    # Fill cached results
                    for idx, emb in cached_embeddings:
                        dense_results[idx] = emb["dense"]
                        sparse_results[idx] = emb["sparse"]
  
                    # Fill newly computed results
                    for i, idx in enumerate(uncached_indices):
                        dense_results[idx] = dense_vecs[i]
                        sparse_results[idx] = sparse_weights[i]

                    # Cache the newly computed embeddings (using prefixed text as key)
                    for i, _idx in enumerate(uncached_indices):
                        prefixed_text = uncached_prefixed_texts[i]
                        embedding_result = {
                            "dense": dense_vecs[i],
                            "sparse": sparse_weights[i],
                        }
                        self._embed_cache.put(prefixed_text, embedding_result)

                    EMBEDDING_LATENCY.labels(operation="encode_batch").observe(
                        time.monotonic() - start_time
                    )
                    return {
                        "dense": dense_results,
                        "sparse": sparse_results,
                    }
                except Exception as e:
                    last_err = e
                    EMBEDDING_ERRORS.labels(operation="encode_batch").inc()
                    logger.warning(
                        f"Embedding failed on attempt {attempt}/{max_retries}: {e}. "
                        f"Performing garbage collection and retrying in 2 seconds..."
                    )
                    import gc

                    gc.collect()
                    time.sleep(2)

            logger.error(
                f"All {max_retries} attempts to encode batch failed. "
                f"Raising last error: {last_err}"
            )
            raise last_err

    async def encode_batch_async(self, texts: list[str]) -> dict:
        """Async GIL-escape wrapper for encode_batch(). Frees event loop during encoding."""
        return await asyncio.to_thread(self.encode_batch, texts)

    def encode_single_full(self, text: str) -> dict:
        """
        Encode a single query text into both dense and sparse vectors.
        Uses the instruction prefix required for e5 models.
        """
        text = _apply_query_expansion(text)

        # encode_batch naturally prepends self.instruction and handles caching
        result = self.encode_batch([text])
        return {
            "dense": result["dense"][0],
            "sparse": result["sparse"][0],
        }

    async def encode_single_full_async(self, text: str) -> dict:
        """Async GIL-escape wrapper for encode_single_full(). Use in retrieval nodes."""
        return await asyncio.to_thread(self.encode_single_full, text)

    def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
    ) -> list[dict]:
        """
        Rerank documents using CrossEncoder for maximum precision.

        Pipeline: Qdrant returns 20 docs (from hybrid search)
                  -> CrossEncoder deeply scores each (query, doc) pair
                  -> Sigmoid-normalize raw logits to [0,1] probabilities
                  -> Filter by minimum score threshold (rerank_min_score)
                  -> Return only the top-k most semantically relevant
        """
        if top_k is None:
            top_k = settings.rag_top_k_rerank

        if not documents:
            return []

        with self._inference_lock:
            self._ensure_reranker()
            import gc

            import torch
            gc.collect()
            pairs = [(query, doc["text"]) for doc in documents]
            with torch.inference_mode():
                raw_scores = self._reranker.predict(pairs)

            # CrossEncoder ms-marco-MiniLM-L-6-v2 returns raw logits (range ~-11 to +4).
            # Apply sigmoid to normalize to [0,1] probabilities for consistent thresholding.
            # PHASE-2 / Truth-3: jina-reranker-v2 already returns [0,1] probabilities;
            # detected at model-load time and stored in self._reranker_outputs_probs.
            import numpy as np

            def _sigmoid(x):
                return 1.0 / (1.0 + np.exp(-x))

            outputs_probs = getattr(self, "_reranker_outputs_probs", False)
            for doc, raw_score in zip(documents, raw_scores):
                rs = float(raw_score)
                doc["rerank_score"] = rs if outputs_probs else float(_sigmoid(rs))
                doc["rerank_raw_logit"] = rs

            # Score distribution logging for debugging
            if raw_scores is not None and len(raw_scores) > 0:
                if outputs_probs:
                    score_arr = np.array([float(s) for s in raw_scores])
                else:
                    score_arr = np.array([float(_sigmoid(s)) for s in raw_scores])
                raw_arr = np.array([float(s) for s in raw_scores])
                logger.info(
                    f"Reranker scores ({'native' if outputs_probs else 'sigmoid'}): "
                    f"min={score_arr.min():.4f}, max={score_arr.max():.4f}, "
                    f"mean={score_arr.mean():.4f}, median={float(np.median(score_arr)):.4f} | "
                    f"raw: min={raw_arr.min():.4f}, max={raw_arr.max():.4f}"
                )

            ranked = sorted(documents, key=lambda d: d["rerank_score"], reverse=True)

            # Apply minimum score threshold
            effective_min_score = min_score if min_score is not None else settings.rerank_min_score
            above_threshold = [d for d in ranked if d["rerank_score"] >= effective_min_score]

            if not above_threshold and ranked:
                # If ALL docs are below threshold, keep the top 1 as minimum
                above_threshold = ranked[:1]
                logger.warning(
                    f"All {len(ranked)} docs scored below threshold {effective_min_score}. "
                    f"Keeping top-1 (score={ranked[0]['rerank_score']:.4f})"
                )

            filtered_count = len(ranked) - len(above_threshold)
            if filtered_count > 0:
                logger.info(
                    f"Reranker threshold {effective_min_score}: filtered {filtered_count} docs below threshold"
                )

            top_docs = above_threshold[:top_k]

            logger.info(
                f"Reranked {len(documents)} → {len(top_docs)} docs"
                + (f". Top score: {top_docs[0]['rerank_score']:.4f}" if top_docs else "")
            )

            return top_docs

    async def rerank_async(
        self,
        query: str,
        documents: list[dict],
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
    ) -> list[dict]:
        """Async GIL-escape wrapper for rerank(). Frees event loop during CrossEncoder scoring."""
        return await asyncio.to_thread(self.rerank, query, documents, top_k, min_score)

    def cascaded_rerank(
        self,
        query: str,
        documents: list[dict],
        colbert_top_k: int = 15,
        cross_top_k: int = 5,
        min_score: Optional[float] = None,
    ) -> list[dict]:
        """
        Cascaded Pipeline:
        1. ColBERTv2 rapidly narrows down the pool (e.g. 100 -> 15).
        2. CrossEncoder performs ultra-precise scoring (15 -> 5).
        Skips CrossEncoder when candidate count < 10 to save latency.
        """
        if not documents:
            return []

        # Skip full cascade for small candidate sets - CrossEncoder adds ~200-500ms
        if len(documents) < 10:
            logger.debug(f"cascaded_rerank: {len(documents)} docs < 10, skipping CrossEncoder, using ColBERT only")
            return self._colbert_only_rerank(query, documents, top_k=min(cross_top_k, len(documents)))

        with self._inference_lock:
            self._ensure_reranker()
            self._ensure_colbert()

            # Step 1: ColBERT Reranking
            colbert_docs = documents
            if self._colbert and len(documents) > colbert_top_k:
                texts = [doc["text"] for doc in documents]
                # RAGatouille rerank returns list of dicts: [{'content': text, 'score': score, 'rank': int}, ...]
                try:
                    colbert_results = self._colbert.rerank(
                        query=query, documents=texts, k=colbert_top_k
                    )

                    # Map back to original document dicts
                    mapped_docs = []
                    for res in colbert_results:
                        # Find matching doc by content
                        for doc in documents:
                            if doc["text"] == res["content"]:
                                doc_copy = doc.copy()
                                doc_copy["colbert_score"] = res["score"]
                                mapped_docs.append(doc_copy)
                                break
                    colbert_docs = mapped_docs
                    logger.info(f"ColBERT narrowed {len(documents)} -> {len(colbert_docs)} docs")
                except Exception as e:
                    logger.error(
                        f"ColBERT reranking failed: {e}. Falling back to straight CrossEncoder."
                    )
                    colbert_docs = documents[: colbert_top_k * 2]  # Fallback rough slice

            # Step 2: CrossEncoder Polish
            return self.rerank(query, colbert_docs, top_k=cross_top_k, min_score=min_score)

    async def cascaded_rerank_async(
        self,
        query: str,
        documents: list[dict],
        colbert_top_k: int = 15,
        cross_top_k: int = 5,
        min_score: Optional[float] = None,
    ) -> list[dict]:
        """Async GIL-escape wrapper for cascaded_rerank(). Use in async retrieval nodes."""
        return await asyncio.to_thread(
            self.cascaded_rerank, query, documents, colbert_top_k, cross_top_k, min_score
        )

    def _colbert_only_rerank(self, query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
        """ColBERT-only reranking for small candidate sets."""
        if not documents or not self._colbert:
            return documents[:top_k]

        with self._inference_lock:
            self._ensure_colbert()
            texts = [doc["text"] for doc in documents]
            try:
                colbert_results = self._colbert.rerank(query=query, documents=texts, k=top_k)
                mapped_docs = []
                for res in colbert_results:
                    for doc in documents:
                        if doc["text"] == res["content"]:
                            doc_copy = doc.copy()
                            doc_copy["colbert_score"] = res["score"]
                            mapped_docs.append(doc_copy)
                            break
                logger.info(f"ColBERT-only reranked {len(documents)} -> {len(mapped_docs)} docs")
                return mapped_docs
            except Exception as e:
                logger.error(f"ColBERT-only reranking failed: {e}")
                return documents[:top_k]

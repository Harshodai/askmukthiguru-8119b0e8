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
import json
import logging
import os
import time
from pathlib import Path
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
from services.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitOpenException,
    DefaultCircuitBreaker,
)

logger = logging.getLogger(__name__)


def _apply_hf_env_bounds() -> None:
    """Bound HuggingFace download concurrency + disable hf_transfer.

    Sets HF_HUB_DOWNLOAD_TIMEOUT (cap stalled downloads) and disables
    hf_transfer (which can spike memory during parallel chunk downloads).
    Uses setdefault so explicit operator overrides win. Valid for the pinned
    huggingface_hub>=0.20 line. Invoke before any model-loading operation.
    """
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")


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

    _ONNX_CANDIDATE = "gpahal/bge-m3-onnx-int8"

    def __init__(self) -> None:
        """Initialize with None models — will be loaded on first use or warm_up()."""
        import threading

        self._encoder = None
        self._reranker = None
        self._colbert = None
        self._onnx_session = None
        self._onnx_tokenizer = None
        # Dedicated torch backbone for late chunking (see _torch_backbone) —
        # separate from self._encoder so encode_batch can stay on ONNX INT8.
        self._late_chunk_transformer = None
        self._late_chunk_tokenizer = None
        self._lock = threading.Lock()
        self._inference_lock = threading.RLock()
        # REQUIRED for multilingual-e5-large-instruct
        self.instruction = "Given a spiritual teaching, retrieve relevant passages: "
        # Embedding cache to avoid redundant encodes
        from app.config import settings
        from services.cache_service import EmbeddingCache

        self._embed_cache = EmbeddingCache(max_size=settings.embedding_cache_size)
        EMBEDDING_CACHE_SIZE.set(self._embed_cache.max_size)
        # Provider-agnostic circuit breaker (same pattern as the LLM services).
        # "embedding" has no entry in CIRCUIT_BREAKER_CONFIGS, so from_provider()
        # falls back to its dataclass defaults (threshold=5, recovery=90s).
        self._circuit = DefaultCircuitBreaker(CircuitBreakerConfig.from_provider("embedding"))
        from services.circuit_breaker import get_circuit_breaker_registry

        get_circuit_breaker_registry().register("embedding", self._circuit)
        logger.info("Embedding service initialized (lazy load)")

    def warm_up(self) -> None:
        """Eagerly load all models at startup to avoid latency spikes on first request."""
        logger.info("Warming up embedding service — loading all models...")
        self._ensure_encoder()
        self._ensure_reranker()
        self._ensure_colbert()
        logger.info("Embedding service warm-up complete")

    def _thread_setup(self) -> None:
        """Pin PyTorch CPU thread pools to ``settings.embed_torch_threads`` (default 1).

        One thread is the right default for the API server: many concurrent
        requests each spawning a full BLAS thread pool multiplies memory and
        thrashes the scheduler, so the cap keeps a serving pod predictable.
        """
        import torch

        threads = settings.embed_torch_threads
        torch.set_num_threads(threads)
        try:
            torch.set_num_interop_threads(threads)
        except RuntimeError:
            # Gracefully ignore when logger/socket is closed or interop threads already set
            pass

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
        # Bound HF download concurrency before any model load.
        _apply_hf_env_bounds()

        if settings.embedding_backend == "onnx_int8":
            self._load_onnx_encoder(model_name)
            return

        is_bge_m3 = model_name == "BAAI/bge-m3"
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
                    logger.info(
                        "Monkeypatched AutoModel.from_pretrained to support 'dtype' parameter."
                    )
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
                logger.info("Successfully monkeypatched BGEM3FlagModel for robust error tracing.")
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

    # The 3a90cc8b hash this used to carry 404s on HuggingFace — CLAUDE.md still
    # claimed it was "pinned" and working, and Dockerfile.railway still baked the
    # image against it, discovered 2026-08-01 while verifying the ONNX path for
    # the corpus-remediation pilot (`EMBEDDING_BACKEND=onnx_int8` was broken in
    # every local environment this session touched it in). Re-resolved live via
    # `HfApi().model_info('gpahal/bge-m3-onnx-int8').sha` on 2026-08-01;
    # last_modified 2025-06-25, i.e. the repo has been static since — the SHA
    # is a real pin, not a moving target. `HF_REVISION` env still overrides this
    # for a future re-pin. Do not bump to a repo head.
    _ONNX_ENCODER_REVISION: str | None = "2b34e84df040034d4b9eabb62383a87c18955822"

    # Immutable commit SHA of BAAI/bge-m3, resolved from the HF API on
    # 2026-08-01 and cross-checked against the gpahal/bge-m3-onnx-int8 encoder
    # snapshot (same upstream weights, 1024-dim). The tokenizer must be pinned
    # separately from the encoder: it is loaded from the mutable upstream repo,
    # not from the ONNX snapshot. Do not bump to a repo head.
    _ONNX_TOKENIZER_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"

    def _load_onnx_encoder(self, model_name: str) -> None:
        """Load the ONNX INT8 quantized BGE-M3 encoder.

        Resolves the pre-cached snapshot under HF_HOME (matches the Dockerfile
        pre-bake at {HF_HOME}/hub/models--gpahal--bge-m3-onnx-int8) so Railway pod
        restarts reuse the baked model instead of re-downloading. Falls back to a
        snapshot_download into the same HF_HOME-aware path when the cache is cold
        (local dev, fresh container). Pinned revision matches the Dockerfile bake
        so the digest is immutable across rebuilds.

        Validates output dimension against the configured Qdrant collection
        dimension — raises loud on mismatch, never silent.

        Sets self._encoder = session as a marker so _ensure_encoder's short-circuit
        fires on subsequent calls (the encode paths check self._onnx_session, not
        self._encoder, so this is safe).
        """
        import os
        import re

        import onnxruntime as ort
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer

        onnx_model_id = self._ONNX_CANDIDATE
        hf_home = os.environ.get("HF_HOME") or os.path.join(
            os.path.expanduser("~"), ".cache", "huggingface"
        )
        safe = "models--" + onnx_model_id.replace("/", "--")
        cache_dir = Path(hf_home) / "hub" / safe
        cache_dir.mkdir(parents=True, exist_ok=True)

        revision = (
            settings.hf_revision or os.environ.get("HF_REVISION") or self._ONNX_ENCODER_REVISION
        )
        if revision is None:
            raise RuntimeError(
                "ONNX encoder requires a pinned revision. "
                "Set HF_REVISION env var to a verified commit hash, or restore "
                "_ONNX_ENCODER_REVISION in embedding_service.py. "
                "Refusing to download an unversioned HEAD checkpoint."
            )
        # Fail-closed: HF_REVISION must be a full 40-hex commit SHA. A short
        # hash, branch name, or tag is mutable (resolves to a repo head) and
        # is rejected before any download happens.
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError(
                f"HF_REVISION must be a full 40-hex commit SHA, got {revision!r}. "
                "Resolve a commit hash from the HF API and pin it; refusing to "
                "load a mutable revision."
            )

        try:
            local_path = snapshot_download(
                repo_id=onnx_model_id,
                revision=revision,
                local_dir=str(cache_dir),
                local_dir_use_symlinks=False,
                resume_download=True,
                ignore_patterns=["*.md", "*.py", "requirements.txt"],
            )
            model_file = os.path.join(local_path, "model_quantized.onnx")
            if not os.path.exists(model_file):
                raise FileNotFoundError(
                    f"ONNX model file not found at {model_file} for '{onnx_model_id}'"
                )

            session = ort.InferenceSession(
                model_file,
                providers=["CPUExecutionProvider"],
            )

            # Validate output dimension (fail-loud discipline, ref 2026-07-16 incident)
            outputs = session.get_outputs()
            dense_output = next((o for o in outputs if "dense" in o.name.lower()), outputs[0])
            output_dim = dense_output.shape[1]
            required_dim = settings.embedding_dimension
            if output_dim != required_dim:
                raise ValueError(
                    f"ONNX model '{onnx_model_id}' outputs {output_dim}-dim dense vectors, "
                    f"but Qdrant collection requires {required_dim}-dim. "
                    f"This would cause silent retrieval degradation — refusing to load."
                )

            self._onnx_session = session
            # Tokenizer loaded from BAAI/bge-m3 at the immutable revision
            # _ONNX_TOKENIZER_REVISION — never a repo head. The encoder snapshot
            # above is separately revision-pinned (HF_REVISION / _ONNX_ENCODER_REVISION).
            self._onnx_tokenizer = AutoTokenizer.from_pretrained(
                "BAAI/bge-m3",
                revision=self._ONNX_TOKENIZER_REVISION,
                model_max_length=8192,
            )
            self._encoder = session
            logger.info(
                f"Loaded ONNX INT8 encoder: {onnx_model_id} "
                f"(dims={output_dim}, outputs={len(outputs)}: "
                f"{[o.name for o in outputs]})"
            )
        except Exception:
            raise

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
            # Qdrant's collection is created once at container startup with this
            # dimension (app/container.py, before any encoder loads). A fallback
            # model of a DIFFERENT dimension can't search that collection — every
            # dense query 400s ("Vector dimension error") while this function
            # reports success. Never swap to one silently (2026-07-16 production
            # incident: bge-m3's HF cache was corrupted, silently fell back to a
            # 384-dim model against the 1024-dim collection — see handoff.md).
            required_dim = settings.embedding_dimension

            last_error = None
            for i, model_name in enumerate(FALLBACK_CHAIN):
                try:
                    try:
                        self._load_encoder(model_name, device)
                    except Exception as first_err:
                        # A corrupted/truncated HF cache (e.g. an earlier OOM-kill
                        # mid-download) throws the same kind of error as a real
                        # incompatibility. Clear and retry once — cheap, and
                        # fixes the common case outright instead of degrading.
                        logger.warning(
                            f"Failed to load embedding model '{model_name}': {first_err}. "
                            f"Clearing HF cache and retrying once."
                        )
                        self._clear_hf_cache_for(model_name)
                        self._load_encoder(model_name, device)
                        logger.info(f"Recovered '{model_name}' after clearing HF cache")

                    # S7: ask the LOADED encoder its real output dimension rather
                    # than trusting config for the primary. The old check set
                    # model_dim = required_dim for the primary — comparing a value
                    # to itself — so a primary that loaded at the wrong size (bad
                    # revision, partial cache, swapped artifact) passed cleanly
                    # while every dense search 400s. That is the 2026-07-16 residual.
                    actual_dim = None
                    enc = self._encoder
                    if enc is not None and hasattr(enc, "get_sentence_embedding_dimension"):
                        try:
                            _d = enc.get_sentence_embedding_dimension()
                            # Only trust a concrete int (a real encoder). A mock or
                            # odd return falls back to the declared-dim behavior.
                            actual_dim = int(_d) if isinstance(_d, int) else None
                        except Exception:
                            actual_dim = None
                    if actual_dim is None:
                        # Encoders that don't expose the accessor (ONNX/other) keep
                        # the declared-dimension behavior.
                        actual_dim = (
                            required_dim
                            if model_name == settings.embedding_model
                            else FALLBACK_DIMS.get(model_name)
                        )
                    if actual_dim != required_dim:
                        raise ValueError(
                            f"'{model_name}' loaded at {actual_dim}-dim, Qdrant collection is "
                            f"{required_dim}-dim — refusing silent dimension swap"
                        )

                    logger.info(f"Successfully loaded embedding model '{model_name}'")
                    self._prune_unused_hf_variants(model_name)
                    if model_name != settings.embedding_model:
                        settings.embedding_model = model_name
                        logger.info(
                            f"Config updated: model={model_name}, "
                            f"dim={settings.embedding_dimension}"
                        )
                    return
                except Exception as e:
                    self._encoder = None
                    last_error = e
                    logger.warning(f"Failed to load embedding model '{model_name}': {e}.")
                    if i + 1 < len(FALLBACK_CHAIN):
                        EMBEDDING_MODEL_FALLBACK.labels(
                            from_model=model_name,
                            to_model=FALLBACK_CHAIN[i + 1],
                        ).inc()

            logger.error(
                f"Failed to load a {required_dim}-dim-compatible embedding model. "
                f"Tried: {', '.join(FALLBACK_CHAIN)}. Last error: {last_error}",
                exc_info=True,
            )
            if last_error is not None:
                raise last_error
            raise RuntimeError(
                f"Failed to load a {required_dim}-dim-compatible embedding model. "
                f"Tried: {', '.join(FALLBACK_CHAIN)}"
            )

    def _prune_unused_hf_variants(self, model_name: str) -> None:
        """Remove unused model variants from the serving cache after load.

        FlagEmbedding loads the PyTorch BGE-M3 weights. The upstream snapshot also
        contains a roughly 2.2 GB ONNX data blob, but ONNX INT8 is intentionally
        gated and must not be selected by this path. Removing only the ONNX
        snapshot links and blobs that are no longer referenced reduces volume and
        page-cache pressure; it never changes the loaded encoder or Qdrant vectors.
        Set ``PRUNE_UNUSED_HF_VARIANTS=false`` to disable this maintenance action,
        or keep it disabled automatically when ``onnx_int8`` is selected.
        """
        if model_name != "BAAI/bge-m3" or settings.embedding_backend == "onnx_int8":
            return
        enabled = os.getenv("PRUNE_UNUSED_HF_VARIANTS", "true").strip().casefold()
        if enabled not in {"1", "true", "yes", "on"}:
            return
        hf_home = os.getenv("HF_HOME")
        if not hf_home:
            return
        model_root = Path(hf_home) / "hub" / "models--BAAI--bge-m3"
        snapshots = model_root / "snapshots"
        if not snapshots.is_dir():
            return

        import shutil

        removed_blobs: list[Path] = []
        removed_bytes = 0
        for snapshot in snapshots.iterdir():
            onnx_dir = snapshot / "onnx"
            if not onnx_dir.is_dir():
                continue
            for item in onnx_dir.rglob("*"):
                if item.is_symlink():
                    try:
                        removed_blobs.append(item.resolve(strict=True))
                    except FileNotFoundError:
                        # Gracefully ignore when logger/socket is closed or file missing
                        pass
                elif item.is_file():
                    try:
                        removed_bytes += item.stat().st_size
                    except OSError:
                        # Gracefully ignore when logger/socket is closed or stat fails
                        pass
            try:
                shutil.rmtree(onnx_dir)
            except OSError as exc:
                logger.warning("Could not prune unused BGE-M3 ONNX snapshot: %s", exc)
                continue

        if not removed_blobs:
            return

        still_linked: set[Path] = set()
        for link in snapshots.rglob("*"):
            if link.is_symlink():
                try:
                    still_linked.add(link.resolve(strict=True))
                except FileNotFoundError:
                    # Gracefully ignore when logger/socket is closed or link broken
                    continue
        for blob in set(removed_blobs):
            if blob in still_linked or not blob.is_file():
                continue
            try:
                removed_bytes += blob.stat().st_size
                blob.unlink()
            except OSError as exc:
                logger.debug("Could not remove orphaned HF blob %s: %s", blob.name, exc)

        if removed_bytes:
            logger.info(
                "Pruned unused BGE-M3 ONNX cache variant: %.1f MB reclaimed",
                removed_bytes / (1024 * 1024),
            )

    def _clear_hf_cache_for(self, model_id: str) -> None:
        """Remove cached files for a model from HuggingFace cache directories."""
        import glob
        import shutil

        cache_dirs = [
            os.environ.get("SENTENCE_TRANSFORMERS_HOME", ""),
            os.environ.get("HF_HOME", ""),
            os.environ.get("TRANSFORMERS_CACHE", ""),
        ]
        cache_dirs = [d for d in cache_dirs if d]
        hf_home = os.environ.get("HF_HOME", "")
        if hf_home:
            cache_dirs.append(os.path.join(hf_home, "sentence_transformers"))
        safe_name = model_id.replace("/", "--")
        for cache_dir in cache_dirs:
            for pattern in (f"models--{safe_name}", f"*{safe_name}*", model_id.replace("/", "_")):
                matches = glob.glob(os.path.join(cache_dir, "**", pattern), recursive=True)
                for match in matches:
                    if os.path.isdir(match):
                        # Propagate deletion failures instead of suppressing — a
                        # leftover corrupted cache entry would cause the retry to
                        # fail again, so surface the error for diagnosis.
                        shutil.rmtree(match)
                        logger.info(f"Cleared HF cache: {match}")

    def _ensure_reranker(self) -> None:
        """Lazy-load the reranker model."""
        if self._reranker is not None:
            return
        with self._lock:
            if self._reranker is not None:
                return
            _apply_hf_env_bounds()
            self._thread_setup()
            device = self._get_device()

            # Phase 1 optimisation: prefer ONNX INT8 reranker (~23 MB, ~2x faster).
            # Rollback: set RERANKER_BACKEND=flagembedding in .env and restart.
            if settings.reranker_backend == "onnx_int8":
                try:
                    from services.onnx_reranker import OnnxReranker

                    self._reranker = OnnxReranker(model_id=settings.reranker_onnx_model)
                    # OnnxReranker.predict() already applies sigmoid internally.
                    # Setting this flag tells rerank() not to apply it again.
                    self._reranker_outputs_probs = True
                    logger.info("Loaded ONNX INT8 reranker: %s", settings.reranker_onnx_model)
                    return
                except Exception as e:
                    logger.warning(
                        "ONNX reranker load failed (%s); falling back to PyTorch CrossEncoder",
                        e,
                    )

            from sentence_transformers import CrossEncoder

            # CPU can't afford bge-reranker-v2-m3 (~4s/doc -> 88s for 19 docs). Use the
            # light CPU model there; heavy multilingual reranker only on GPU/MPS.
            model_id = settings.reranker_model_cpu if device == "cpu" else settings.reranker_model
            logger.info(f"Loading reranker: {model_id} on device: {device}")
            try:
                self._reranker = CrossEncoder(model_id, device=device)
            except json.JSONDecodeError as e:
                logger.warning(f"Corrupted HF cache for {model_id}, clearing and retrying: {e}")
                self._clear_hf_cache_for(model_id)
                self._reranker = CrossEncoder(model_id, device=device)
            model_name = (model_id or "").lower()
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
        if not settings.enable_colbert:
            self._colbert = False
            return

        if self._colbert is not None:
            return
        with self._lock:
            if self._colbert is not None:
                return
            _apply_hf_env_bounds()
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
                    'RAGPretrainedModel.from_pretrained("colbert-ir/colbertv2.0")\''
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

        if not self._circuit.can_execute():
            exc = CircuitOpenException(
                provider="embedding",
                message="Circuit breaker OPEN for embedding — failing fast",
            )
            logger.warning(str(exc))
            raise exc

        start_time = time.monotonic()
        with self._inference_lock:
            self._ensure_encoder()
            use_onnx = self._onnx_session is not None

            max_retries = 3
            last_err = None
            for attempt in range(1, max_retries + 1):
                try:
                    if use_onnx:
                        inputs = self._onnx_tokenizer(
                            texts,
                            padding=True,
                            truncation=True,
                            return_tensors="np",
                        )
                        ort_out = self._onnx_session.run(
                            None,
                            {
                                "input_ids": inputs["input_ids"].astype("int64"),
                                "attention_mask": inputs["attention_mask"].astype("int64"),
                            },
                        )
                        result = ort_out[0].tolist()
                    else:
                        import torch

                        with torch.inference_mode():
                            is_bge_m3 = settings.embedding_model == "BAAI/bge-m3"
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
                    self._circuit.record_success()
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
                    # time.sleep is intentionally used here: encode() is a sync
                    # method, always called via encode_async() -> asyncio.to_thread().
                    # The sleep runs in a worker thread, NOT the event loop.
                    time.sleep(2)

            logger.error(
                f"All {max_retries} attempts to encode dense failed. Raising last error: {last_err}"
            )
            self._circuit.record_failure()
            if last_err is not None:
                raise last_err
            raise RuntimeError(f"All {max_retries} attempts to encode dense failed.")

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

        if not self._circuit.can_execute():
            exc = CircuitOpenException(
                provider="embedding",
                message="Circuit breaker OPEN for embedding — failing fast",
            )
            logger.warning(str(exc))
            raise exc

        start_time = time.monotonic()
        with self._inference_lock:
            self._ensure_encoder()
            use_onnx = self._onnx_session is not None

            max_retries = 3
            last_err = None
            for attempt in range(1, max_retries + 1):
                try:
                    if use_onnx:
                        from collections import defaultdict

                        inputs = self._onnx_tokenizer(
                            uncached_prefixed_texts,
                            padding=True,
                            truncation=True,
                            return_tensors="np",
                        )
                        ort_out = self._onnx_session.run(
                            None,
                            {
                                "input_ids": inputs["input_ids"].astype("int64"),
                                "attention_mask": inputs["attention_mask"].astype("int64"),
                            },
                        )
                        dense_vecs = ort_out[0].tolist()
                        sparse_raw = ort_out[1]
                        input_ids = inputs["input_ids"].tolist()
                        sparse_weights = []
                        unused_tokens = {
                            self._onnx_tokenizer.cls_token_id,
                            self._onnx_tokenizer.eos_token_id,
                            self._onnx_tokenizer.pad_token_id,
                            self._onnx_tokenizer.unk_token_id,
                        }
                        for row_idx, token_ids in enumerate(input_ids):
                            weights = sparse_raw[row_idx, :, 0]
                            result = defaultdict(int)
                            for w, tid in zip(weights, token_ids):
                                if tid not in unused_tokens and w > 0:
                                    key = str(tid)
                                    if w > result[key]:
                                        result[key] = w
                            sparse_weights.append(dict(result))
                    else:
                        import torch

                        with torch.inference_mode():
                            is_bge_m3 = settings.embedding_model == "BAAI/bge-m3"
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
                    self._circuit.record_success()
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
                    # time.sleep is intentionally used here: encode_batch() is a sync
                    # method, always called via encode_batch_async() -> asyncio.to_thread().
                    # The sleep runs in a worker thread, NOT the event loop.
                    time.sleep(2)

            logger.error(
                f"All {max_retries} attempts to encode batch failed. Raising last error: {last_err}"
            )
            self._circuit.record_failure()
            if last_err is not None:
                raise last_err
            raise RuntimeError(f"All {max_retries} attempts to encode batch failed.")

    async def encode_batch_async(self, texts: list[str]) -> dict:
        """Async GIL-escape wrapper for encode_batch(). Frees event loop during encoding."""
        return await asyncio.to_thread(self.encode_batch, texts)

    def encode_with_colbert(self, texts: list[str]) -> dict:
        """Return dense, sparse, AND colbert token embeddings in one batched ONNX call.

        ColBERT vectors are L2-normalized per token (BGE-M3 default). CLS token
        is excluded per FlagEmbedding convention (colbert_vecs[:tokens_num - 1]).
        Right-padding assumed (XLM-R default for sequence classification: valid
        tokens at start, padding at end).

        LRU cache deferred — batched caller in _colbert_maxsim_rerank makes
        per-text caching marginal. Add if profiling shows reuse.

        Returns:
            dict with keys 'dense' (list[list[float]]), 'sparse' (list[dict]),
            'colbert' (list[np.ndarray], each shape [n_valid_tokens, 1024]).
        """
        import numpy as np

        if not texts:
            return {"dense": [], "sparse": [], "colbert": []}

        start_time = time.monotonic()
        with self._inference_lock:
            self._ensure_encoder()
            use_onnx = self._onnx_session is not None

            max_retries = 3
            last_err = None
            for attempt in range(1, max_retries + 1):
                try:
                    if use_onnx:
                        from collections import defaultdict

                        inputs = self._onnx_tokenizer(
                            texts, padding=True, truncation=True, return_tensors="np"
                        )
                        ort_out = self._onnx_session.run(
                            None,
                            {
                                "input_ids": inputs["input_ids"].astype("int64"),
                                "attention_mask": inputs["attention_mask"].astype("int64"),
                            },
                        )
                        dense_vecs = ort_out[0].tolist()
                        sparse_raw = ort_out[1]
                        input_ids = inputs["input_ids"].tolist()
                        sparse_weights = []
                        unused_tokens = {
                            self._onnx_tokenizer.cls_token_id,
                            self._onnx_tokenizer.eos_token_id,
                            self._onnx_tokenizer.pad_token_id,
                            self._onnx_tokenizer.unk_token_id,
                        }
                        for row_idx, token_ids in enumerate(input_ids):
                            weights = sparse_raw[row_idx, :, 0]
                            result = defaultdict(int)
                            for w, tid in zip(weights, token_ids):
                                if tid not in unused_tokens and w > 0:
                                    key = str(tid)
                                    if w > result[key]:
                                        result[key] = w
                            sparse_weights.append(dict(result))

                        colbert_raw = ort_out[2]
                        attention_mask = inputs["attention_mask"]
                        colbert_vecs = []
                        for i in range(len(texts)):
                            tokens_num_i = int(attention_mask[i].sum())
                            n_valid = tokens_num_i - 1
                            if n_valid <= 0:
                                colbert_vecs.append(np.zeros((0, 1024), dtype=np.float32))
                                continue
                            colbert_i = colbert_raw[i][:n_valid].astype(np.float32)
                            colbert_vecs.append(colbert_i)
                    else:
                        import torch

                        with torch.inference_mode():
                            output = self._encoder.encode(
                                texts,
                                return_dense=True,
                                return_sparse=True,
                                return_colbert_vecs=True,
                            )
                            dense_vecs = output["dense_vecs"].tolist()
                            sparse_weights = output["lexical_weights"]
                            colbert_vecs = [
                                np.array(v, dtype=np.float32) for v in output["colbert_vecs"]
                            ]

                    EMBEDDING_LATENCY.labels(operation="encode_with_colbert").observe(
                        time.monotonic() - start_time
                    )
                    return {
                        "dense": dense_vecs,
                        "sparse": sparse_weights,
                        "colbert": colbert_vecs,
                    }
                except Exception as e:
                    last_err = e
                    EMBEDDING_ERRORS.labels(operation="encode_with_colbert").inc()
                    logger.warning(
                        f"encode_with_colbert failed on attempt {attempt}/{max_retries}: {e}. "
                        f"Performing garbage collection and retrying in 2 seconds..."
                    )
                    import gc

                    gc.collect()
                    # time.sleep is intentionally used here: encode_with_colbert() is a
                    # sync method, always called via an asyncio.to_thread() wrapper.
                    # The sleep runs in a worker thread, NOT the event loop.
                    time.sleep(2)

            logger.error(
                f"All {max_retries} attempts to encode_with_colbert failed. "
                f"Raising last error: {last_err}"
            )
            if last_err is not None:
                raise last_err
            raise RuntimeError(f"All {max_retries} attempts to encode_with_colbert failed.")

    # ------------------------------------------------------------------
    # Late chunking (plan §6.3 / arXiv:2409.04701)
    #
    # Embed the WHOLE document once, then mean-pool token vectors per chunk
    # span. Every chunk embedding then carries the surrounding discourse with
    # zero extra LLM calls — which matters for transcripts, where a chunk's
    # referents ("this", "that state", "he said") live in neighbouring chunks.
    #
    # Two things measured on 2026-08-01 constrain the implementation:
    #
    #  1. `encode_with_colbert` looks like the right input — it already returns
    #     per-token vectors of shape [n_valid, 1024] — but it is NOT. The
    #     ColBERT head is a separate linear projection: pooling it lands at
    #     cosine -0.041 to the dense query space, i.e. orthogonal. It would
    #     produce plausible floats and near-random retrieval, with no error.
    #     The correct source is `last_hidden_state`, whose CLS token IS the
    #     dense vector (measured cosine 0.914 against the production encoder).
    #
    #  2. The ONNX export emits only dense/sparse/colbert — no
    #     `last_hidden_state` — so late chunking requires the PyTorch path.
    #     This method raises rather than silently falling back to a vector
    #     space the caller did not ask for.
    #
    # BGE-M3 pools with CLS while late chunking pools with mean (cosine 0.757
    # between them), so queries must ALSO be mean-pooled — see
    # `encode_query_mean_pooled`. Late-chunked and CLS-chunked vectors cannot
    # share a collection.
    # ------------------------------------------------------------------

    # Window size for late chunking, in tokens. NOT the model's 8192 limit —
    # transformer attention is O(n^2) in memory, and 8192 tokens is ~4.3 GB for a
    # single attention matrix (8192^2 x 16 heads x 4 bytes). A 2026-08-01 pilot run
    # with an 8190-token window was SIGKILLed by the OOM killer partway through
    # embedding: no traceback, no result file, just a vanished process — the
    # failure mode that looks like a hang.
    #
    # 2048 keeps peak attention near 270 MB while still giving each chunk ~5
    # chunks' worth of surrounding discourse (a 1500-char chunk is ~375 tokens),
    # which is where most of late chunking's benefit lives. Raise it only with
    # headroom measured on the target host.
    @property
    def _LATE_CHUNK_MAX_TOKENS(self) -> int:
        return settings.late_chunk_window_tokens

    def _torch_backbone(self):
        """Return (transformer, tokenizer) for a DEDICATED PyTorch BGE-M3 backbone.

        Loaded independently of ``self._encoder`` / ``self._onnx_session`` — those
        follow ``settings.embedding_backend`` (ONNX INT8 in production, ~570MB,
        3.08x faster per a 2026-08-01 measurement) and stay on that path for
        ``encode_batch``. Late chunking's only requirement is ``last_hidden_state``,
        which no ONNX export here emits, so it gets its own small torch instance
        (~2.3GB) rather than forcing the whole service onto the slower backend.
        Loaded once and cached; both backbones coexisting is ~2.9GB, which fits
        the memory budget that OOM-killed earlier all-torch pilot runs.
        """
        if self._late_chunk_transformer is not None:
            return self._late_chunk_transformer, self._late_chunk_tokenizer

        with self._lock:
            if self._late_chunk_transformer is not None:
                return self._late_chunk_transformer, self._late_chunk_tokenizer

            _apply_hf_env_bounds()
            from FlagEmbedding import BGEM3FlagModel
            from huggingface_hub import snapshot_download

            logger.info(
                "Loading dedicated torch backbone for late chunking: BAAI/bge-m3@%s",
                self._ONNX_TOKENIZER_REVISION,
            )
            local_path = snapshot_download(
                repo_id="BAAI/bge-m3",
                revision=self._ONNX_TOKENIZER_REVISION,
            )
            model = BGEM3FlagModel(local_path, use_fp16=False, device="cpu")
            transformer = getattr(getattr(model, "model", None), "model", None)
            tokenizer = getattr(getattr(model, "model", None), "tokenizer", None) or getattr(
                model, "tokenizer", None
            )
            if transformer is None or tokenizer is None:
                raise RuntimeError(
                    "Could not reach the BGE-M3 PyTorch backbone — late chunking unavailable."
                )
            self._late_chunk_transformer = transformer
            self._late_chunk_tokenizer = tokenizer
            return transformer, tokenizer

    def _stream_pooled_spans(
        self, document: str, spans: list[tuple[int, int]]
    ) -> list[list[float]]:
        """Mean-pool token vectors per char span, one window at a time.

        Memory is O(len(spans)) rather than O(document tokens): only the running
        per-span sum is retained, and each window's hidden states are released
        as soon as they have been folded in. Holding the whole document's token
        vectors — an [n_tokens, dim] float32 array — is what OOM-killed the
        2026-08-01 pilot container (exit 137) on a long transcript. For ~300
        chunks the accumulator is ~1.2 MB regardless of transcript length.

        Windows overlap by 25% so a chunk sitting on a seam still draws context
        from both sides instead of being truncated at the boundary.
        """
        import numpy as np
        import torch

        dim = settings.embedding_dimension
        max_tokens = settings.late_chunk_window_tokens
        window = max_tokens - 2  # room for CLS/EOS
        if window <= 0:
            raise ValueError(
                f"Invalid late chunk window tokens size {max_tokens} "
                f"(window after CLS/EOS overhead is {window} <= 0). Must be > 2."
            )

        transformer, tokenizer = self._torch_backbone()
        enc = tokenizer(
            document,
            return_offsets_mapping=True,
            add_special_tokens=False,
            truncation=False,
            return_tensors=None,
        )
        ids = enc["input_ids"]
        offsets = enc["offset_mapping"]
        n = len(ids)
        if n == 0 or not spans:
            return [[0.0] * dim for _ in spans]

        tok_starts = np.fromiter((o[0] for o in offsets), dtype=np.int64, count=n)
        tok_ends = np.fromiter((o[1] for o in offsets), dtype=np.int64, count=n)

        acc = np.zeros((len(spans), dim), dtype=np.float32)
        counts = np.zeros(len(spans), dtype=np.float32)

        stride = max(1, int(window * 0.75))
        cls_id = tokenizer.cls_token_id
        eos_id = tokenizer.eos_token_id
        pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else eos_id
        window_bounds = [(s, min(s + window, n)) for s in range(0, n, stride)]
        n_windows = len(window_bounds)
        window_start_time = time.monotonic()

        # Batch windows together instead of one forward pass per window. A lone
        # window is [1, seq_len] — the CPU does one matmul per call, paying full
        # dispatch/thread-pool setup overhead each time for work BLAS could fuse
        # into one larger call. Grouping WINDOW_BATCH windows into a single
        # [B, max_len] padded tensor turns N small matmuls into N/B larger ones,
        # which is the standard throughput lever for CPU transformer inference
        # (same principle as encode_batch's own batching, applied one level down).
        #
        # Bounded to 4, not "as many as fit": attention is O(seq_len^2) per item,
        # so batching multiplies that memory by the batch size — 4 * ~270MB (the
        # 2048-token budget from the OOM postmortem above) is ~1.1GB, still well
        # inside the headroom this run has after the 2026-08-01 all-torch OOM.
        window_batch_size = max(1, int(getattr(settings, "late_chunk_window_batch_size", 4)))

        for wb_start in range(0, n_windows, window_batch_size):
            wb = window_bounds[wb_start : wb_start + window_batch_size]
            lengths = [(e - s) + 2 for s, e in wb]  # +2 for CLS/EOS
            max_len = max(lengths)

            input_ids = torch.full((len(wb), max_len), pad_id, dtype=torch.long)
            attn = torch.zeros((len(wb), max_len), dtype=torch.long)
            for row, ((s, e), length) in enumerate(zip(wb, lengths)):
                seq = [cls_id] + ids[s:e] + [eos_id]
                input_ids[row, :length] = torch.tensor(seq, dtype=torch.long)
                attn[row, :length] = 1

            with torch.inference_mode():
                hidden = transformer(input_ids=input_ids, attention_mask=attn).last_hidden_state

            for row, ((s, e), length) in enumerate(zip(wb, lengths)):
                body = hidden[row, 1 : length - 1].to(torch.float32).cpu().numpy()  # strip CLS/EOS
                w_starts = tok_starts[s:e]
                w_ends = tok_ends[s:e]
                for si, (span_start, span_end) in enumerate(spans):
                    mask = (w_ends > span_start) & (w_starts < span_end)
                    hit = int(mask.sum())
                    if hit:
                        acc[si] += body[mask].sum(axis=0)
                        counts[si] += hit
            del hidden

            # Silent otherwise between "start" and "done" — the embed batch loop
            # got the same treatment earlier for the same reason: elapsed + ETA
            # beats inferring progress from memory drift.
            logger.info(
                "Late chunking: windows %d-%d/%d (%d tokens total, %.1fs elapsed)",
                wb_start + 1,
                wb_start + len(wb),
                n_windows,
                n,
                time.monotonic() - window_start_time,
            )

        out: list[list[float]] = []
        for si in range(len(spans)):
            if counts[si] == 0:
                out.append([0.0] * dim)
                continue
            pooled = acc[si] / counts[si]
            norm = float(np.linalg.norm(pooled))
            out.append((pooled / norm).tolist() if norm > 0 else [0.0] * dim)
        return out

    def encode_late_chunked(self, document: str, spans: list[tuple[int, int]]) -> list[list[float]]:
        """Embed ``document`` once, then mean-pool per ``(start, end)`` char span.

        Returns one L2-normalized dim-vector per span, in the same order.
        A span with no overlapping tokens yields a zero vector — the caller
        should drop it rather than index a meaningless point.
        """
        if not spans:
            return []
        with self._inference_lock:
            return self._stream_pooled_spans(document, spans)

    def encode_query_mean_pooled(self, query: str) -> list[float]:
        """Mean-pooled query vector, for searching a late-chunked collection.

        BGE-M3's normal dense vector is CLS-pooled; late-chunked documents are
        mean-pooled, and the two sit ~0.757 cosine apart. Querying a
        late-chunked collection with a CLS vector compares across that gap on
        every single search, so the query side must pool the same way.
        """
        dim = settings.embedding_dimension
        if not query:
            return [0.0] * dim
        # One span covering the whole query is the same mean pool, and reuses
        # the streaming path so both sides share one implementation.
        with self._inference_lock:
            pooled = self._stream_pooled_spans(query, [(0, len(query))])
        return pooled[0] if pooled else [0.0] * dim

    async def encode_with_colbert_async(self, texts: list[str]) -> dict:
        """Async GIL-escape wrapper for encode_with_colbert()."""
        return await asyncio.to_thread(self.encode_with_colbert, texts)

    def _colbert_maxsim_rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: int = 15,
    ) -> list[dict]:
        """Rerank documents using BGE-M3 ColBERT MaxSim (ONNX-native, multilingual).

        Batched: encodes query + ALL docs in ONE encode_with_colbert call,
        then scores via batch_maxsim. This replaces the old RAGatouille
        (ColBERTv2, English-only) path with a multilingual 100+ language
        scorer that reuses the already-loaded ONNX BGE-M3 session.

        Gate: only runs when settings.enable_colbert=True. When False,
        returns documents[:top_k] unchanged (Phase 2 ships disabled).
        """
        if not documents:
            return []
        if not settings.enable_colbert:
            return documents[:top_k]

        import numpy as np

        from services.colbert_maxsim import batch_maxsim

        all_texts = [query] + [doc.get("text", "") for doc in documents]
        encoded = self.encode_with_colbert(all_texts)
        query_tokens = np.array(encoded["colbert"][0], dtype=np.float32)
        doc_tokens_list = [np.array(v, dtype=np.float32) for v in encoded["colbert"][1:]]

        scores = batch_maxsim(query_tokens, doc_tokens_list)

        dense_vecs = encoded["dense"][1:]  # skip query at index 0

        scored = []
        for doc, score, dense_vec in zip(documents, scores, dense_vecs):
            doc_copy = doc.copy()
            doc_copy["colbert_score"] = float(score)
            doc_copy["_dense_embedding"] = dense_vec  # ponytail: reused by MMR to skip re-encoding
            scored.append(doc_copy)
        scored.sort(key=lambda d: d["colbert_score"], reverse=True)
        logger.info(f"ColBERT MaxSim reranked {len(documents)} -> {len(scored[:top_k])} docs")
        return scored[:top_k]

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
        """Cascaded Pipeline:
        1. ColBERT rapidly narrows the pool (e.g. 100 -> 15).
        2. CrossEncoder performs ultra-precise scoring (15 -> 5).
        Skips CrossEncoder when candidate count < 10 to save latency.

        ColBERT stage branches on settings.enable_colbert:
        - True: ONNX-native BGE-M3 MaxSim (multilingual, reuses loaded session).
          If that path raises, falls back to a rough slice then CrossEncoder.
        - False: deprecated RAGatouille ColBERTv2 path (English-only).
        """
        if not documents:
            return []

        if len(documents) < 10:
            logger.debug(f"cascaded_rerank: {len(documents)} docs < 10, skipping CrossEncoder")
            if settings.enable_colbert:
                return self._colbert_maxsim_rerank(
                    query, documents, top_k=min(cross_top_k, len(documents))
                )
            return self._colbert_only_rerank(
                query, documents, top_k=min(cross_top_k, len(documents))
            )

        with self._inference_lock:
            self._ensure_reranker()

            colbert_docs = documents
            if settings.enable_colbert:
                try:
                    colbert_docs = self._colbert_maxsim_rerank(
                        query, documents, top_k=colbert_top_k
                    )
                except Exception as e:
                    logger.error(
                        f"ColBERT MaxSim rerank failed: {e}. Falling back to RAGatouille path."
                    )
                    colbert_docs = documents[: colbert_top_k * 2]
            elif len(documents) > colbert_top_k:
                self._ensure_colbert()
                texts = [doc["text"] for doc in documents]
                try:
                    colbert_results = self._colbert.rerank(
                        query=query, documents=texts, k=colbert_top_k
                    )
                    mapped_docs = []
                    for res in colbert_results:
                        for doc in documents:
                            if doc["text"] == res["content"]:
                                doc_copy = doc.copy()
                                doc_copy["colbert_score"] = res["score"]
                                mapped_docs.append(doc_copy)
                                break
                    colbert_docs = mapped_docs
                    logger.info(
                        f"ColBERT (RAGatouille) narrowed {len(documents)} -> {len(colbert_docs)} docs"
                    )
                except Exception as e:
                    logger.error(
                        f"RAGatouille ColBERT failed: {e}. Falling back to straight CrossEncoder."
                    )
                    colbert_docs = documents[: colbert_top_k * 2]

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
                # ponytail: rerank() returns result_index into `texts`/`documents` per RAGatouille's
                # rerank() contract; lookup by index avoids the O(n^2) full-text equality scan.
                mapped_docs = []
                for res in colbert_results:
                    idx = res.get("result_index")
                    if idx is None or not (0 <= idx < len(documents)):
                        continue
                    doc_copy = documents[idx].copy()
                    doc_copy["colbert_score"] = res["score"]
                    mapped_docs.append(doc_copy)
                logger.info(f"ColBERT-only reranked {len(documents)} -> {len(mapped_docs)} docs")
                return mapped_docs
            except Exception as e:
                logger.error(f"ColBERT-only reranking failed: {e}")
                return documents[:top_k]

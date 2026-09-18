"""
ONNX INT8 CrossEncoder reranker for mmarco-mMiniLMv2-L12-H384-v1.

Drop-in replacement for sentence_transformers.CrossEncoder on CPU.

Critical correctness note
--------------------------
CrossEncoder models are fine-tuned on *paired* input:
    [CLS] query [SEP] document [SEP]
with token_type_ids=[0,...,0, 1,...,1] separating the two segments.

The original plan draft concatenated query+document into a single string
before tokenising — this destroys the [SEP] boundary and discards all
type IDs, producing a different input distribution the model never saw.
This implementation calls the tokeniser correctly:
    tokenizer(queries, docs, padding=True, truncation=True, max_length=512)

Cache path note
---------------
The original draft used tempfile.mkdtemp() — a new directory per process,
causing a full HF Hub re-download on every container restart.
This implementation resolves the model into HF_HOME (or a fixed fallback)
so Railway pod restarts reuse the existing download.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ONNX_RERANKER_MODEL_ID = "temsa/mmarco-mMiniLMv2-L12-H384-v1-onnx-cpu-qint8"
# Immutable commit SHA of the temsa repo, resolved from the HF API on
# 2026-08-01 and validated by scripts/validate_onnx_reranker.py (Spearman
# >0.90 gate). Never download a repo head. The tokenizer ships in this same
# repo and is loaded from the snapshot dir, so one revision pins both.
_ONNX_RERANKER_REVISION = "59d3305e534a9abf92f6eb6238c34b748a89dc83"
# Tokeniser ships IN the temsa repo (tokenizer.json, tokenizer_config.json,
# special_tokens_map.json, sentencepiece.bpe.model). Load it from the same
# repo as the ONNX model to avoid silent tokenization drift if temsa's
# tokenizer files ever diverge from the upstream cross-encoder/ repo.


# Pairs scored per session.run(). See OnnxReranker.predict for why an
# unbounded batch is what broke production on 2026-09-17.
_DEFAULT_RERANK_BATCH_SIZE = 8


def _resolve_batch_size() -> int:
    """Read the batch size from settings, tolerating an absent setting.

    Imported lazily and defensively: scripts/validate_onnx_reranker.py and the
    __main__ self-check below construct an OnnxReranker without a fully
    populated app.config (no LLM creds), and a reranker must not become
    unloadable because a settings import failed.
    """
    try:
        from app.config import settings

        return max(1, int(getattr(settings, "reranker_batch_size", _DEFAULT_RERANK_BATCH_SIZE)))
    except Exception:  # pragma: no cover - config-less contexts only
        return _DEFAULT_RERANK_BATCH_SIZE


def _hf_cache_dir(model_id: str) -> Path:
    """Return a stable, HF_HOME-aware directory for a model.

    Mirrors how huggingface_hub resolves its own cache so we do not fight it.
    """
    hf_home = os.environ.get("HF_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache", "huggingface"
    )
    safe = "models--" + model_id.replace("/", "--")
    return Path(hf_home) / "hub" / safe


class OnnxReranker:
    """ONNX INT8 CrossEncoder for document reranking.

    Loads pre-quantised mmarco-mMiniLMv2-L12-H384-v1 via onnxruntime
    CPUExecutionProvider. Thread-safe. Falls back to PyTorch if load fails
    (caller decides whether to raise or swallow the exception).

    Usage::

        reranker = OnnxReranker()
        scores = reranker.predict([("what is karma?", "Karma is ..."), ...])
    """

    def __init__(self, model_id: Optional[str] = None, batch_size: Optional[int] = None) -> None:
        self._session = None
        self._tokenizer = None
        self._has_token_type_ids: bool = False
        self._lock = threading.Lock()
        self._batch_size = batch_size or _resolve_batch_size()
        self._load(model_id or _ONNX_RERANKER_MODEL_ID)

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load(self, model_id: str) -> None:
        """Download (once) and load the ONNX session + tokeniser."""
        import onnxruntime as ort
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer

        # 2026-09-16: bound HF download concurrency/backend before any
        # snapshot_download, same guard embedding_service.py applies before
        # its own model loads. Without it a cold cache (missing/incomplete
        # build-time pre-bake) falls through to huggingface_hub's Xet
        # downloader, whose concurrent chunked transfer OOM-aborted the prod
        # backend process once already (see docs/PROD_HARDENING_STATUS.md).
        from services.embedding_service import _apply_hf_env_bounds

        _apply_hf_env_bounds()

        # Fail-closed: only the validated model id may be loaded. A
        # from_pretrained/snapshot_download call for an arbitrary repo would
        # download and execute unvetted model code (CVE-2024-0791 class).
        if model_id != _ONNX_RERANKER_MODEL_ID:
            raise ValueError(
                f"Refusing to load unvetted reranker model id '{model_id}'. "
                f"Only '{_ONNX_RERANKER_MODEL_ID}' (revision "
                f"{_ONNX_RERANKER_REVISION}) is allowed."
            )

        # Use a stable, HF_HOME-aware cache dir — not a tempdir.
        cache_dir = _hf_cache_dir(model_id)
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Pinned model id + immutable revision (temsa ONNX INT8 reranker),
        # validated by scripts/validate_onnx_reranker.py (Spearman >0.90 gate).
        local_path = snapshot_download(
            repo_id=model_id,
            revision=_ONNX_RERANKER_REVISION,
            local_dir=str(cache_dir),
            local_dir_use_symlinks=False,
            resume_download=True,
            ignore_patterns=["*.md", "*.py", "requirements.txt"],
        )

        onnx_files = sorted(Path(local_path).glob("*.onnx"))
        if not onnx_files:
            raise FileNotFoundError(f"No .onnx file in {local_path} for model '{model_id}'")

        # Prefer a quantised file if multiple exist (e.g. model_qint8.onnx vs model.onnx)
        onnx_path = next(
            (f for f in onnx_files if "qint8" in f.name or "int8" in f.name),
            onnx_files[0],
        )

        # Bound thread count: default (0=all cores) oversubscribes when
        # multiple predict() calls run concurrently via asyncio.to_thread.
        # os.cpu_count() reads the HOST/VM core count inside a container, not
        # the cgroup quota (measured 10 vs cgroup 4.0) -- same defect class as
        # L-DOCKER-9 (MKL/OpenBLAS/OMP), already fixed for
        # services/embedding_service.py:385-391. ORT ignores OMP_NUM_THREADS
        # in Eigen builds, so reuse settings.omp_num_threads as the same
        # operator-tunable budget instead of re-deriving one from cpu_count().
        from app.config import settings

        so = ort.SessionOptions()
        # settings.omp_num_threads is `int = Field(default=2, ge=1)`, so it is
        # already a validated positive int -- no clamp, no cpu_count() cap. An
        # earlier version of this line kept a `min(budget, cpu_count()//2)`
        # ceiling, which re-derived the host-core budget the comment above
        # says not to derive.
        so.intra_op_num_threads = settings.omp_num_threads
        so.inter_op_num_threads = 1
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        session = ort.InferenceSession(
            str(onnx_path),
            sess_options=so,
            providers=["CPUExecutionProvider"],
        )

        # Validate: must have at least one output (the logit)
        outputs = session.get_outputs()
        if not outputs:
            raise RuntimeError(f"ONNX model '{model_id}' has no outputs")

        # Detect whether the graph accepts token_type_ids (some ONNX exports
        # strip them; passing them to a graph that does not expect them raises).
        input_names = {inp.name for inp in session.get_inputs()}
        self._has_token_type_ids = "token_type_ids" in input_names

        self._session = session
        # Tokenizer files ship in the pinned snapshot dir (same revision as the
        # ONNX graph) — load from local_path, never from a mutable repo head.
        # nosec B615: local_path is a locally pinned snapshot_download dir, not
        # a repo-head model id — the pinned-revision requirement is already
        # enforced in _load() via snapshot_download(revision=...).
        self._tokenizer = AutoTokenizer.from_pretrained(
            local_path,
            use_fast=True,
        )  # nosec B615
        logger.info(
            "Loaded ONNX INT8 reranker: %s  (file=%s, inputs=%s, token_type_ids=%s, outputs=%s)",
            model_id,
            onnx_path.name,
            sorted(input_names),
            self._has_token_type_ids,
            [o.name for o in outputs],
        )

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Score query-document pairs.

        Returns a list of floats in [0, 1] (sigmoid-normalised logits).
        Order matches the input pairs.

        Scored in fixed-size batches. Scoring a whole candidate list in one
        session.run() allocates a self-attention buffer proportional to
        batch x heads x seq x seq: at 12 heads and the 512-token max length
        that is ~12.6MB PER PAIR, so an ordinary 13-24 document candidate set
        asks onnxruntime's arena for one 150-160MB buffer and it refuses:

            Failed to allocate memory for requested buffer of size 163577856

        Measured live 2026-09-17 -- every rerank_documents node in a
        golden_qa_bank run died this way in under 100ms, and the "fallback to
        FlashRank" path in reranker_service._run_cross_encoder re-entered this
        same method, so the retry failed identically and the node raised.
        Batching bounds the largest single allocation no matter how many
        candidates retrieval hands over. Scores are unchanged: each pair is
        independent, so batching affects only padding width, and padded
        positions are masked out by attention_mask.
        """
        import numpy as np

        if not pairs:
            return []

        batch_size = max(1, int(self._batch_size))
        if len(pairs) > batch_size:
            scores: list[float] = []
            for start in range(0, len(pairs), batch_size):
                scores.extend(self.predict(pairs[start : start + batch_size]))
            return scores

        queries = [q for q, _ in pairs]
        docs = [d for _, d in pairs]

        # CRITICAL: tokenise as *pairs*, not concatenated strings.
        # This produces:   [CLS] query [SEP] document [SEP]
        # with token_type_ids=[0,...,0, 1,...,1] — exactly the input
        # format the model was fine-tuned on.
        inputs = self._tokenizer(
            queries,
            docs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="np",
        )

        feed = {
            "input_ids": inputs["input_ids"].astype("int64"),
            "attention_mask": inputs["attention_mask"].astype("int64"),
        }
        if self._has_token_type_ids and "token_type_ids" in inputs:
            feed["token_type_ids"] = inputs["token_type_ids"].astype("int64")

        # ONNX InferenceSession.run() IS thread-safe for concurrent reads,
        # but we hold the lock conservatively to match the BGE-M3 encoder pattern.
        with self._lock:
            logits = self._session.run(None, feed)[0]  # shape: [batch, 1]

        # Apply sigmoid to convert raw logits -> [0, 1] probabilities.
        scores = 1.0 / (1.0 + np.exp(-logits[:, 0]))
        return scores.tolist()

    def predict_single(self, query: str, doc: str) -> float:
        """Convenience wrapper for a single pair."""
        return self.predict([(query, doc)])[0]


if __name__ == "__main__":
    # Quick smoke-test — run from backend/ directory.
    import sys

    logging.basicConfig(level=logging.INFO)
    print("Loading OnnxReranker...")
    reranker = OnnxReranker()

    pairs = [
        ("what is karma?", "Karma is the law of cause and effect in Vedic philosophy."),
        ("what is karma?", "The weather today is sunny with light breeze."),
        ("what is karma?", "Karma determines future birth according to actions in past lives."),
    ]
    scores = reranker.predict(pairs)
    print("Scores:")
    for (_q, d), s in zip(pairs, scores):
        print(f"  {s:.4f}  {d[:60]}")

    if scores[0] < scores[1]:
        print("FAIL: irrelevant doc scored higher than relevant doc", file=sys.stderr)
        sys.exit(1)
    print("PASS — monotonic scoring verified")

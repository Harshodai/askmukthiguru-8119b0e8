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

    def __init__(self, model_id: Optional[str] = None) -> None:
        self._session = None
        self._tokenizer = None
        self._has_token_type_ids: bool = False
        self._lock = threading.Lock()
        self._load(model_id or _ONNX_RERANKER_MODEL_ID)

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load(self, model_id: str) -> None:
        """Download (once) and load the ONNX session + tokeniser."""
        import onnxruntime as ort
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer

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
        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
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
        """
        import numpy as np

        if not pairs:
            return []

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

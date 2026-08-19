"""
validate_onnx_embedding.py — Phase 2: Cosine Similarity Validation

Compares fp32 (FlagEmbedding BGEM3FlagModel) vs ONNX INT8 (gpahal/bge-m3-onnx-int8)
embeddings on the entire question_bank.py corpus.

Pass threshold: mean cos >= 0.985, no single query below 0.95.
Also validates against 15 hand-paraphrased query variants to prevent overfitting.

Usage:
    .venv/bin/python3 scripts/validate_onnx_embedding.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import numpy as np

# Force CPU for baseline (matches production Railway deployment),
# and disable MPS memory limit to avoid OOM on Apple Silicon.
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")

BATCH_SIZE = 32

SCRATCH = Path(tempfile.mkdtemp(prefix="onnx_phase2_"))
ONNX_CANDIDATE = "gpahal/bge-m3-onnx-int8"

# Immutable revisions (commit SHAs), resolved from the HF API on 2026-08-01.
# No repo heads: BGEM3FlagModel has no revision= kwarg, so the fp32 baseline
# is loaded from a pinned local snapshot dir (see BaselineEncoder.load).
BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
ONNX_CANDIDATE_REVISION = "2b34e84df040034d4b9eabb62383a87c18955822"

# ── Thresholds (hard, per plan) ──
MEAN_COS_THRESHOLD = 0.985
MIN_COS_THRESHOLD = 0.95

# ── 15 hand-paraphrased variants for overfit check ──
PARAPHRASED = [
    "Tell me about the four sacred secrets",
    "What are the main teachings in the four sacred secrets book?",
    "Who founded Ekam and what do they teach?",
    "Tell me about Sri Preethaji and Sri Krishnaji",
    "What is Manifest 2026 and its monthly powers?",
    "List the 12 powers of Manifest 2026",
    "How do I practice the Soul Sync meditation?",
    "Walk me through the steps of Soul Sync",
    "What is Deeksha and how does it affect the brain?",
    "Explain the neuroscience behind Deeksha",
    "Where is the Ekam temple located?",
    "What is the address of Ekam in Tirupati?",
    "How can I find inner peace through meditation?",
    "What does Sri Preethaji say about letting go?",
    "Can you explain the power of gratitude from Manifest 2026?",
]

# ── Original query pairs to test exact phrasing stability ──
ORIGINAL_PARAPHRASE_MAP = [
    ("What are the Four Sacred Secrets?", PARAPHRASED[0]),
    ("Who are Sri Preethaji and Sri Krishnaji?", PARAPHRASED[3]),
    ("What is Manifest 2026?", PARAPHRASED[4]),
    ("What is Soul Sync?", PARAPHRASED[6]),
    ("What is Deeksha?", PARAPHRASED[8]),
    ("Where is Ekam located?", PARAPHRASED[10]),
]


def _extract_queries() -> list[dict]:
    """Extract all queries from question_bank.py.

    Returns list of dicts with keys: q, category, index.
    Handles multi_turn's nested turns structure.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from benchmarks.question_bank import QUERIES

    queries = []
    for category, items in QUERIES.items():
        if not isinstance(items, list):
            continue
        for i, item in enumerate(items):
            if isinstance(item, dict) and "q" in item:
                queries.append(
                    {
                        "q": item["q"],
                        "category": category,
                        "index": i,
                    }
                )
            elif isinstance(item, dict) and "turns" in item:
                # multi_turn scenario
                for j, turn in enumerate(item["turns"]):
                    if "q" in turn:
                        queries.append(
                            {
                                "q": turn["q"],
                                "category": f"{category}_turn",
                                "index": j,
                            }
                        )
    return queries


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


class BaselineEncoder:
    """FP32 FlagEmbedding BGEM3FlagModel — current production path."""

    def __init__(self):
        self._encoder = None

    def load(self):
        print("Loading baseline (fp32 BGEM3FlagModel)...")
        from FlagEmbedding import BGEM3FlagModel
        from huggingface_hub import snapshot_download

        t0 = time.monotonic()
        # Pinned local snapshot of BAAI/bge-m3 (BGEM3FlagModel has no
        # revision= kwarg; a local dir cannot drift from a repo head).
        bge_local = snapshot_download(
            repo_id="BAAI/bge-m3",
            revision=BGE_M3_REVISION,
            local_dir=str(SCRATCH / "bge_m3_fp32"),
            local_dir_use_symlinks=False,
            resume_download=True,
            ignore_patterns=["*.md", "*.py", "requirements.txt"],
        )
        self._encoder = BGEM3FlagModel(bge_local, use_fp16=False, device="cpu")
        print(f"  Loaded in {time.monotonic() - t0:.1f}s")

    def encode_dense(self, texts: list[str]) -> np.ndarray:
        all_vecs = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            output = self._encoder.encode(
                batch, return_dense=True, return_sparse=False, return_colbert_vecs=False
            )
            all_vecs.append(np.array(output["dense_vecs"]))
        return np.concatenate(all_vecs, axis=0)


class OnnxEncoder:
    """ONNX INT8 encoder via raw onnxruntime (optimum not installed)."""

    def __init__(self, model_path: Optional[str] = None):
        self._session = None
        self._tokenizer = None
        self._model_path = model_path

    def load(self):
        import onnxruntime as ort
        from transformers import AutoTokenizer

        if self._model_path:
            model_file = self._model_path
        else:
            model_file = self._download()

        print("Loading ONNX INT8 encoder...")
        t0 = time.monotonic()
        self._session = ort.InferenceSession(
            model_file,
            providers=["CPUExecutionProvider"],
        )
        self._tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3", revision=BGE_M3_REVISION)
        print(f"  Loaded in {time.monotonic() - t0:.1f}s")

    def _download(self) -> str:
        from huggingface_hub import snapshot_download

        print(f"Downloading {ONNX_CANDIDATE}...")
        t0 = time.monotonic()
        # Pinned candidate + immutable revision (validated in-process).
        local_path = snapshot_download(
            repo_id=ONNX_CANDIDATE,
            revision=ONNX_CANDIDATE_REVISION,
            local_dir=str(SCRATCH),
            local_dir_use_symlinks=False,
            resume_download=True,
            ignore_patterns=["*.md", "*.py", "requirements.txt"],
        )
        print(f"  Downloaded in {time.monotonic() - t0:.1f}s")
        return os.path.join(local_path, "model_quantized.onnx")

    def encode_dense(self, texts: list[str]) -> np.ndarray:
        all_vecs = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            inputs = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                return_tensors="np",
            )
            ort_inputs = {
                "input_ids": inputs["input_ids"].astype(np.int64),
                "attention_mask": inputs["attention_mask"].astype(np.int64),
            }
            outputs = self._session.run(None, ort_inputs)
            # output[0] = dense_vecs
            all_vecs.append(outputs[0])
        return np.concatenate(all_vecs, axis=0)


def _score_and_report(
    baseline: BaselineEncoder, onnx: OnnxEncoder, queries: list[dict], label: str
) -> dict:
    """Compute per-query cosine similarity, report stats, return results."""
    texts = [q["q"] for q in queries]
    print(f"\n{'=' * 60}")
    print(f"Scoring {len(texts)} queries ({label})")
    print("=" * 60)

    # Encode
    t0 = time.monotonic()
    baseline_vecs = baseline.encode_dense(texts)
    t_baseline = time.monotonic() - t0

    t0 = time.monotonic()
    onnx_vecs = onnx.encode_dense(texts)
    t_onnx = time.monotonic() - t0

    print(f"  Baseline encode: {t_baseline:.2f}s ({t_baseline / len(texts) * 1000:.1f}ms/q)")
    print(f"  ONNX INT8 encode: {t_onnx:.2f}s ({t_onnx / len(texts) * 1000:.1f}ms/q)")

    # Normalize ONNX outputs if not already (bge-m3 produces normalized dense by default,
    # but ONNX path may produce unnormalized)
    onnx_norms = np.linalg.norm(onnx_vecs, axis=1, keepdims=True)
    onnx_vecs = onnx_vecs / np.where(onnx_norms > 0, onnx_norms, 1.0)

    # Per-query cosine
    cos_sims = []
    outliers = []
    for i, (bv, ov) in enumerate(zip(baseline_vecs, onnx_vecs)):
        cs = _cosine_similarity(bv, ov)
        cos_sims.append(cs)
        if cs < MIN_COS_THRESHOLD:
            outliers.append(
                {
                    "index": i,
                    "category": queries[i].get("category", "?"),
                    "text": texts[i][:100],
                    "cosine": cs,
                }
            )

    cos_arr = np.array(cos_sims)
    mean_cos = float(cos_arr.mean())
    min_cos = float(cos_arr.min())
    p5 = float(np.percentile(cos_arr, 5))
    p50 = float(np.percentile(cos_arr, 50))

    print("\n  Results:")
    print(f"    Mean cosine: {mean_cos:.6f}  (threshold: >= {MEAN_COS_THRESHOLD})")
    print(f"    Min cosine:  {min_cos:.6f}  (threshold: >= {MIN_COS_THRESHOLD})")
    print(f"    P5 cosine:   {p5:.6f}")
    print(f"    P50 cosine:  {p50:.6f}")
    print(f"    Std dev:     {float(cos_arr.std()):.6f}")

    passed = mean_cos >= MEAN_COS_THRESHOLD and min_cos >= MIN_COS_THRESHOLD

    if outliers:
        print(f"\n  ⚠ {len(outliers)} queries below {MIN_COS_THRESHOLD} threshold:")
        outliers.sort(key=lambda x: x["cosine"])
        for o in outliers[:10]:
            print(f"    [{o['cosine']:.4f}] ({o['category']}) {o['text']}")
    else:
        print(f"\n  ✓ No queries below {MIN_COS_THRESHOLD} threshold")

    print(f"\n  >> VERDICT: {'PASS' if passed else 'FAIL'} ({label})")

    return {
        "label": label,
        "count": len(texts),
        "mean": mean_cos,
        "min": min_cos,
        "p5": p5,
        "p50": p50,
        "std": float(cos_arr.std()),
        "passed": passed,
        "outliers": outliers,
        "baseline_time_s": t_baseline,
        "onnx_time_s": t_onnx,
    }


def main():
    # Extract queries
    queries = _extract_queries()
    print(f"Total queries extracted: {len(queries)}")

    # Load models
    baseline = BaselineEncoder()
    baseline.load()

    onnx = OnnxEncoder()
    onnx.load()

    # 1. Score on all literal queries
    literal_results = _score_and_report(baseline, onnx, queries, "literal queries")

    # 2. Score on paraphrased variants
    para_queries = [
        {"q": p, "category": "paraphrased", "index": i} for i, p in enumerate(PARAPHRASED)
    ]
    para_results = _score_and_report(baseline, onnx, para_queries, "paraphrased variants")

    # 3. Verify that original ↔ paraphrase pairs are stable
    print(f"\n{'=' * 60}")
    print("Original ↔ Paraphrase Pair Stability Check")
    print("=" * 60)
    pair_instabilities = []
    for orig_text, para_text in ORIGINAL_PARAPHRASE_MAP:
        orig_vec_b = baseline.encode_dense([orig_text])
        orig_vec_o = onnx.encode_dense([orig_text])
        para_vec_b = baseline.encode_dense([para_text])
        para_vec_o = onnx.encode_dense([para_text])

        # Cosine between fp32 and ONNX for original
        cs_orig = _cosine_similarity(orig_vec_b[0], orig_vec_o[0])
        # Cosine between fp32 and ONNX for paraphrase
        cs_para = _cosine_similarity(para_vec_b[0], para_vec_o[0])
        delta = abs(cs_orig - cs_para)

        if delta > 0.01:
            pair_instabilities.append(
                {
                    "orig": orig_text[:60],
                    "para": para_text[:60],
                    "cs_orig": cs_orig,
                    "cs_para": cs_para,
                    "delta": delta,
                }
            )
            print(f"  ⚠ Delta={delta:.4f}: orig={cs_orig:.4f} para={cs_para:.4f}")
        else:
            print(f"  ✓ Delta={delta:.4f}: orig={cs_orig:.4f} para={cs_para:.4f}")

    pair_stable = len(pair_instabilities) == 0

    # Final verdict
    print(f"\n{'=' * 60}")
    print("FINAL VERDICT — Phase 2: Cosine Similarity Validation")
    print("=" * 60)

    overall_pass = literal_results["passed"] and para_results["passed"] and pair_stable

    print(
        f"  Literal queries:     {'PASS' if literal_results['passed'] else 'FAIL'}"
        f"  (mean={literal_results['mean']:.4f}, min={literal_results['min']:.4f})"
    )
    print(
        f"  Paraphrased queries: {'PASS' if para_results['passed'] else 'FAIL'}"
        f"  (mean={para_results['mean']:.4f}, min={para_results['min']:.4f})"
    )
    print(
        f"  Pair stability:      {'PASS' if pair_stable else 'FAIL'}"
        f"  ({len(pair_instabilities)} unstable pairs)"
    )
    print(f"  Overall:             {'PASS' if overall_pass else 'FAIL'}")

    if not overall_pass:
        print("\n  ❌ Phase 2 FAILED — do not proceed to Phase 3 without resolving.")
        sys.exit(1)
    else:
        print("\n  ✅ Phase 2 PASSED — proceed to Phase 3.")


def _cleanup():
    import shutil

    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
        print(f"Cleaned up: {SCRATCH}")


if __name__ == "__main__":
    try:
        main()
    finally:
        _cleanup()

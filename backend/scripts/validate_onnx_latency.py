"""
validate_onnx_latency.py — Phase 4: Latency Benchmark

Measures p50/p95 single-query embedding latency for fp32 vs ONNX INT8.
Matches production thread setup (OMP_NUM_THREADS=1, etc.).

Pass threshold: ONNX INT8 p95 ≤ fp32 p95 × 1.10.

Usage:
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python3 scripts/validate_onnx_latency.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")

ONNX_CANDIDATE = "gpahal/bge-m3-onnx-int8"
SCRATCH = Path(tempfile.mkdtemp(prefix="onnx_phase4_"))

# Production thread setup (copied from embedding_service.py._thread_setup)
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

N_ITERATIONS = 100  # number of single-query timing samples
WARMUP = 10          # warmup iterations before timing

# Representative test queries covering different lengths
TEST_QUERIES = [
    "What is the Four Sacred Secrets?",
    "How do I practice Soul Sync meditation?",
    "What does Sri Preethaji say about the power of letting go and finding inner peace through universal intelligence?",
    "Explain the neurobiological effects of Deeksha on the frontal lobe and parietal lobe during deep meditation states.",
    "నాలుగు పవిత్ర రహస్యాలు ఏమిటి?",  # Telugu
    "आत्मा समक्रमण का अभ्यास कैसे करें?",  # Hindi
]


def _thread_setup():
    import torch
    torch.set_num_threads(1)


def _setup_baseline():
    from FlagEmbedding import BGEM3FlagModel
    _thread_setup()
    return BGEM3FlagModel("BAAI/bge-m3", use_fp16=False, device="cpu")


def _setup_onnx():
    import onnxruntime as ort
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer
    _thread_setup()
    local_path = snapshot_download(
        repo_id=ONNX_CANDIDATE,
        local_dir=str(SCRATCH),
        local_dir_use_symlinks=False,
        resume_download=True,
        ignore_patterns=["*.md", "*.py", "requirements.txt"],
    )
    session = ort.InferenceSession(
        os.path.join(local_path, "model_quantized.onnx"),
        providers=["CPUExecutionProvider"],
    )
    tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")
    return session, tokenizer


def _measure_latency(encode_fn, queries: list[str], label: str) -> dict:
    """Measure p50/p95 single-query latency."""
    print(f"\n--- {label} ---")

    # Warmup
    for q in queries[:WARMUP]:
        encode_fn([q])

    # Timing
    latencies = []
    for i in range(N_ITERATIONS):
        q = queries[i % len(queries)]
        t0 = time.perf_counter()
        encode_fn([q])
        elapsed = (time.perf_counter() - t0) * 1000  # ms
        latencies.append(elapsed)

    arr = np.array(latencies)
    p50 = float(np.percentile(arr, 50))
    p95 = float(np.percentile(arr, 95))
    mean = float(arr.mean())
    std = float(arr.std())

    print(f"  Samples: {len(latencies)}")
    print(f"  Mean:    {mean:.2f}ms")
    print(f"  Std:     {std:.2f}ms")
    print(f"  P50:     {p50:.2f}ms")
    print(f"  P95:     {p95:.2f}ms")
    print(f"  Min:     {arr.min():.2f}ms")
    print(f"  Max:     {arr.max():.2f}ms")

    return {"p50": p50, "p95": p95, "mean": mean, "std": float(std)}


def main():
    print("=== Phase 4: Latency Benchmark ===\n")
    print(f"Thread setup: OMP_NUM_THREADS={os.environ['OMP_NUM_THREADS']}, "
          f"MKL_NUM_THREADS={os.environ['MKL_NUM_THREADS']}")
    print(f"Iterations: {N_ITERATIONS} (after {WARMUP} warmup)")
    print(f"Queries: {len(TEST_QUERIES)} (rotated through)")

    # Load models
    print("\nLoading models...")
    t0 = time.monotonic()
    baseline = _setup_baseline()
    print(f"  Baseline loaded in {time.monotonic() - t0:.1f}s")

    t0 = time.monotonic()
    onnx_session, onnx_tokenizer = _setup_onnx()
    print(f"  ONNX loaded in {time.monotonic() - t0:.1f}s")

    # Define encode functions
    def baseline_encode(texts):
        out = baseline.encode(texts, return_dense=True, return_sparse=False,
                              return_colbert_vecs=False)
        return out["dense_vecs"]

    def onnx_encode(texts):
        inputs = onnx_tokenizer(
            texts, padding=True, truncation=True, return_tensors="np",
        )
        ort_in = {
            "input_ids": inputs["input_ids"].astype(np.int64),
            "attention_mask": inputs["attention_mask"].astype(np.int64),
        }
        out = onnx_session.run(None, ort_in)[0]
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms > 0, norms, 1.0)

    # Measure
    fp32_stats = _measure_latency(baseline_encode, TEST_QUERIES, "fp32 BGEM3FlagModel")
    onnx_stats = _measure_latency(onnx_encode, TEST_QUERIES, "ONNX INT8")

    # Verdict
    print(f"\n{'=' * 60}")
    print("FINAL VERDICT — Phase 4: Latency")
    print('=' * 60)
    print(f"  fp32 P95:   {fp32_stats['p95']:.2f}ms")
    print(f"  ONNX P95:   {onnx_stats['p95']:.2f}ms")
    print(f"  Threshold:  ONNX P95 <= fp32 P95 × 1.10 = {fp32_stats['p95'] * 1.10:.2f}ms")

    speed_ratio = onnx_stats['p95'] / fp32_stats['p95']
    if speed_ratio <= 1.10:
        print(f"  Ratio: {speed_ratio:.4f} (PASS)")
        print(f"\n  ✅ Phase 4 PASSED — proceed to Phase 5.")
    else:
        print(f"  Ratio: {speed_ratio:.4f} (FAIL)")
        print(f"\n  ❌ Phase 4 FAILED — ONNX is slower than threshold.")
        sys.exit(1)


def _cleanup():
    import shutil
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)


if __name__ == "__main__":
    try:
        main()
    finally:
        _cleanup()

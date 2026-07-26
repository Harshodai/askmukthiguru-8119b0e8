"""
validate_onnx_retrieval.py — Phase 3: Retrieval-Agreement (Direct NN Overlap)

Instead of splitting into two Qdrant collections, this computes nearest-neighbor
overlap directly from in-memory vectors — removing Qdrant indexing as a variable.
Uses a combined corpus of OKF entries + question_bank constants + LightRAG chunks.

Pass threshold: mean top-10 overlap across queries >= 0.85.

Usage:
    .venv/bin/python3 scripts/validate_onnx_retrieval.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import numpy as np

os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")

BATCH_SIZE = 32
ONNX_CANDIDATE = "gpahal/bge-m3-onnx-int8"
SCRATCH = Path(tempfile.mkdtemp(prefix="onnx_phase3_"))

TOP_K = 10
OVERLAP_THRESHOLD = 0.85


def _build_corpus() -> list[str]:
    """Build a clean, representative test corpus."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    texts = []
    seen = set()

    def add(t: str):
        t = t.strip()
        if t and len(t) > 20 and t not in seen:
            seen.add(t)
            texts.append(t)

    # 1. Question bank constants (clean, domain-relevant)
    from benchmarks.question_bank import (
        FOUR_SACRED_SECRETS, MANIFEST_2026_POWERS, SOUL_SYNC_STEPS_VERIFIED,
        SERENE_MIND_KNOWN, DEEKSHA_NEUROSCIENCE,
    )
    for secret in FOUR_SACRED_SECRETS:
        add(f"The Four Sacred Secrets include: {secret}.")
    for month, power in MANIFEST_2026_POWERS.items():
        add(f"Manifest 2026 {month.title()}: {power}.")
    for step in SOUL_SYNC_STEPS_VERIFIED:
        add(f"Soul Sync: {step}.")
    for term in SERENE_MIND_KNOWN:
        add(f"Serene Mind: {term}.")
    for term in DEEKSHA_NEUROSCIENCE:
        add(f"Deeksha neuroscience: {term}.")

    # 2. OKF entries (curated doctrine)
    try:
        from services.memory.okf_store import OKFStore
        store = OKFStore()
        for entry in store.list_entries():
            add(f"{entry.title}: {entry.description}" if entry.description else entry.title)
    except Exception:
        pass

    # 3. Clean LightRAG chunks (filtered, truncated)
    import requests
    try:
        resp = requests.post(
            "http://localhost:6333/collections/lightrag_vdb_chunks_baai_bge_m3_1024d/points/scroll",
            json={"limit": 200, "with_payload": ["content"], "with_vector": False},
            timeout=30,
        )
        for p in resp.json()["result"]["points"]:
            t = p["payload"].get("content", "")
            if t and len(t) > 40 and "[RAPTOR" not in t:
                # Clean up transcription artifacts
                t = t.replace("[Source: ", "").replace("]", "")
                add(t[:1500])
    except Exception:
        pass

    print(f"Corpus built: {len(texts)} passages")
    return texts


def _get_eval_queries() -> list[dict]:
    """Extract doctrine queries with must_mention/min_cites signal."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from benchmarks.question_bank import QUERIES

    eval_categories = [
        "doctrine_four_secrets", "doctrine_founders", "doctrine_manifest",
        "doctrine_deeksha", "doctrine_soul_sync", "doctrine_ekam_architecture",
        "complex_multi_hop",
    ]
    queries = []
    for cat in eval_categories:
        for item in QUERIES.get(cat, []):
            if "q" in item:
                queries.append({"q": item["q"], "category": cat})
    return queries


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    dot = np.dot(a, b)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    return float(dot / (na * nb)) if na > 0 and nb > 0 else 0.0


def _top_k_overlap(fp32_sims: list[float], onnx_sims: list[float], k: int = TOP_K) -> float:
    """Jaccard overlap of top-k items from two similarity lists."""
    n = len(fp32_sims)
    fp32_top = set(np.argsort(fp32_sims)[-k:])
    onnx_top = set(np.argsort(onnx_sims)[-k:])
    intersection = fp32_top & onnx_top
    return len(intersection) / k  # Jaccard using k as union (since both have k items)


class EncodeBoth:
    """Load both models and encode with both."""

    def __init__(self):
        self._baseline = None
        self._onnx_session = None
        self._tokenizer = None

    def load(self):
        from FlagEmbedding import BGEM3FlagModel
        import onnxruntime as ort
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer

        t0 = time.monotonic()
        self._baseline = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False, device="cpu")
        print(f"  Baseline loaded in {time.monotonic() - t0:.1f}s")

        t0 = time.monotonic()
        local_path = snapshot_download(
            repo_id=ONNX_CANDIDATE,
            local_dir=str(SCRATCH),
            local_dir_use_symlinks=False,
            resume_download=True,
            ignore_patterns=["*.md", "*.py", "requirements.txt"],
        )
        self._onnx_session = ort.InferenceSession(
            os.path.join(local_path, "model_quantized.onnx"),
            providers=["CPUExecutionProvider"],
        )
        self._tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")
        print(f"  ONNX loaded in {time.monotonic() - t0:.1f}s")

    def encode_both(self, texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """Return (fp32_vecs, onnx_vecs) for a list of texts."""
        # fp32
        fp32_all = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            out = self._baseline.encode(
                batch, return_dense=True, return_sparse=False, return_colbert_vecs=False,
            )
            fp32_all.append(out["dense_vecs"])
        fp32_vecs = np.concatenate(fp32_all, axis=0)

        # ONNX
        onnx_all = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            inputs = self._tokenizer(
                batch, padding=True, truncation=True, return_tensors="np",
            )
            ort_in = {
                "input_ids": inputs["input_ids"].astype(np.int64),
                "attention_mask": inputs["attention_mask"].astype(np.int64),
            }
            out = self._onnx_session.run(None, ort_in)[0]
            norms = np.linalg.norm(out, axis=1, keepdims=True)
            out = out / np.where(norms > 0, norms, 1.0)
            onnx_all.append(out)
        onnx_vecs = np.concatenate(onnx_all, axis=0)

        return fp32_vecs, onnx_vecs


def main():
    print("=== Phase 3: Retrieval-Agreement (Direct NN Overlap) ===\n")

    corpus = _build_corpus()
    queries = _get_eval_queries()
    print(f"Eval queries: {len(queries)}")

    print("\nLoading encoders...")
    encoder = EncodeBoth()
    encoder.load()

    # Encode corpus with both models
    print(f"\nEncoding corpus ({len(corpus)} passages)...")
    t0 = time.monotonic()
    corpus_fp32, corpus_onnx = encoder.encode_both(corpus)
    print(f"  Encoded in {time.monotonic() - t0:.1f}s")

    # Encode queries with both models
    q_texts = [q["q"] for q in queries]
    q_fp32, q_onnx = encoder.encode_both(q_texts)

    # Per-query overlap
    print(f"\n{'=' * 60}")
    print(f"Per-Query Similarity & Top-{TOP_K} Overlap")
    print(f"{'=' * 60}")

    categories = {}
    total_overlaps = []
    total_cosines = []

    for i, q in enumerate(queries):
        cat = q["category"]
        if cat not in categories:
            categories[cat] = {"overlaps": [], "cosines": []}

        qv_fp32 = q_fp32[i]
        qv_onnx = q_onnx[i]

        # Cosine similarity between this query's embeddings
        q_cos = _cosine_similarity(qv_fp32, qv_onnx)
        categories[cat]["cosines"].append(q_cos)

        # Compute similarities to all corpus passages
        fp32_sims = [float(np.dot(cv, qv_fp32)) for cv in corpus_fp32]
        onnx_sims = [float(np.dot(cv, qv_onnx)) for cv in corpus_onnx]

        overlap = _top_k_overlap(fp32_sims, onnx_sims, TOP_K)
        categories[cat]["overlaps"].append(overlap)
        total_overlaps.append(overlap)
        total_cosines.append(q_cos)

    # Report by category
    print(f"\n{'Category':<28} {'AvgOverlap':<12} {'MinOverlap':<12} {'AvgCosine':<12} {'Pass?'}")
    print("-" * 76)
    all_pass = True
    for cat in sorted(categories.keys()):
        d = categories[cat]
        avg_o = sum(d["overlaps"]) / len(d["overlaps"])
        min_o = min(d["overlaps"])
        avg_c = sum(d["cosines"]) / len(d["cosines"])
        passed = avg_o >= OVERLAP_THRESHOLD
        if not passed:
            all_pass = False
        print(f"{cat:<28} {avg_o:<12.4f} {min_o:<12.4f} {avg_c:<12.4f} {'PASS' if passed else 'FAIL'}")

    overall_avg = sum(total_overlaps) / len(total_overlaps)
    overall_min = min(total_overlaps)
    print(f"\n{'OVERALL':<28} {overall_avg:<12.4f} {overall_min:<12.4f} "
          f"{sum(total_cosines)/len(total_cosines):<12.4f} {'PASS' if all_pass else 'FAIL'}")

    # Cross-config validation
    print(f"\n{'=' * 60}")
    print("Cross-Config Check (ONNX query → fp32 passage NN overlap)")
    print('=' * 60)
    cross_overlaps = []
    for i, q in enumerate(queries):
        qv_onnx = q_onnx[i]
        fp32_sims = [float(np.dot(cv, qv_onnx)) for cv in corpus_fp32]
        onnx_sims = [float(np.dot(cv, qv_onnx)) for cv in corpus_onnx]
        overlap = _top_k_overlap(fp32_sims, onnx_sims, TOP_K)
        cross_overlaps.append(overlap)

    cross_avg = sum(cross_overlaps) / len(cross_overlaps)
    print(f"  Cross-config avg overlap: {cross_avg:.4f}")
    print(f"  Same-model avg overlap:   {overall_avg:.4f}")

    if cross_avg > overall_avg + 0.02:
        print(f"  ⚠ Cross-config > same-model (Δ={cross_avg - overall_avg:.4f})")
        print(f"  → ONNX passage embeddings are less discriminative than fp32")
        all_pass = False
    else:
        print(f"  ✓ Cross-config <= same-model (Δ={cross_avg - overall_avg:.4f})")

    # Zero-overlap queries
    zero_qs = [(queries[i], total_overlaps[i]) for i in range(len(queries)) if total_overlaps[i] == 0]
    if zero_qs:
        print(f"\n  ⚠ {len(zero_qs)} queries with zero overlap:")
        for q, _ in zero_qs[:5]:
            print(f"    [{q['category']}] {q['q'][:80]}")
    else:
        print(f"\n  ✓ No zero-overlap queries")

    # Final verdict
    print(f"\n{'=' * 60}")
    print("FINAL VERDICT — Phase 3: Retrieval Agreement")
    print('=' * 60)
    print(f"  Top-{TOP_K} overlap threshold: >= {OVERLAP_THRESHOLD}")
    print(f"  Achieved: avg={overall_avg:.4f}, min={overall_min:.4f}")
    print(f"  Result: {'PASS ✅' if all_pass else 'FAIL ❌'}")

    if all_pass:
        print(f"\n  Phase 3 PASSED — proceed to Phase 4.")
    else:
        print(f"\n  Phase 3 FAILED.")
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

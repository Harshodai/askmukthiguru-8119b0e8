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
from urllib.parse import urlparse

import numpy as np

os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")

BATCH_SIZE = 32
ONNX_CANDIDATE = "gpahal/bge-m3-onnx-int8"
SCRATCH = Path(tempfile.mkdtemp(prefix="onnx_phase3_"))

# Immutable revisions (commit SHAs), resolved from the HF API on 2026-08-01.
# No repo heads: BGEM3FlagModel has no revision= kwarg, so the fp32 baseline
# is loaded from a pinned local snapshot dir (see EncodeBoth.load).
BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
ONNX_CANDIDATE_REVISION = "2b34e84df040034d4b9eabb62383a87c18955822"

TOP_K = 10
OVERLAP_THRESHOLD = 0.85

# Corpus sources that could not be loaded. A reduced corpus must never pass
# the Phase-3 overlap gate, so main() fails the run when this is non-empty.
CORPUS_MISSING: list[str] = []


def _qdrant_scroll_url() -> tuple[str, dict[str, str]]:
    base_url = os.environ.get("QDRANT_URL", "http://localhost:6333").rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("QDRANT_URL must be an absolute http(s) URL")
    api_key = os.environ.get("QDRANT_API_KEY", "").strip()
    if api_key and parsed.scheme != "https" and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "qdrant",
        "qdrant.railway.internal",
    }:
        raise RuntimeError("QDRANT_API_KEY requires HTTPS or an explicitly trusted private host")
    headers = {"api-key": api_key} if api_key else {}
    url = f"{base_url}/collections/lightrag_vdb_chunks_baai_bge_m3_1024d/points/scroll"
    return url, headers


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
        DEEKSHA_NEUROSCIENCE,
        FOUR_SACRED_SECRETS,
        MANIFEST_2026_POWERS,
        SERENE_MIND_KNOWN,
        SOUL_SYNC_STEPS_VERIFIED,
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
    except Exception as e:
        CORPUS_MISSING.append("OKF entries")
        print(f"WARN: OKF corpus unavailable ({e}) — continuing without it")

    # 3. Clean LightRAG chunks (filtered, truncated)
    import requests

    try:
        scroll_url, headers = _qdrant_scroll_url()
        resp = requests.post(
            scroll_url,
            headers=headers,
            json={"limit": 200, "with_payload": ["content"], "with_vector": False},
            timeout=30,
            allow_redirects=False,
        )
        for p in resp.json()["result"]["points"]:
            t = p["payload"].get("content", "")
            if t and len(t) > 40 and "[RAPTOR" not in t:
                # Clean up transcription artifacts
                t = t.replace("[Source: ", "").replace("]", "")
                add(t[:1500])
    except Exception as e:
        CORPUS_MISSING.append("LightRAG chunks")
        print(f"WARN: LightRAG chunks unavailable ({e}) — continuing without them")

    print(f"Corpus built: {len(texts)} passages")
    return texts


def _get_eval_queries() -> list[dict]:
    """Extract doctrine queries with must_mention/min_cites signal."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from benchmarks.question_bank import QUERIES

    eval_categories = [
        "doctrine_four_secrets",
        "doctrine_founders",
        "doctrine_manifest",
        "doctrine_deeksha",
        "doctrine_soul_sync",
        "doctrine_ekam_architecture",
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
    len(fp32_sims)
    fp32_top = set(np.argsort(fp32_sims)[-k:])
    onnx_top = set(np.argsort(onnx_sims)[-k:])
    intersection = fp32_top & onnx_top
    return len(intersection) / k  # Jaccard using k as union (since both have k items)


def _cross_config_overlap(
    qv: np.ndarray,
    corpus_a: np.ndarray,
    corpus_b: np.ndarray,
    k: int = TOP_K,
) -> float:
    """Top-k overlap of two passage corpora ranked with the SAME query vector.

    Isolates passage-side drift: query-only drift cannot change this score,
    because one shared query embedding produces both rankings.
    """
    sims_a = [float(np.dot(cv, qv)) for cv in corpus_a]
    sims_b = [float(np.dot(cv, qv)) for cv in corpus_b]
    return _top_k_overlap(sims_a, sims_b, k)


def _evaluate_cross_config(cross_avg: float, threshold: float = OVERLAP_THRESHOLD) -> bool:
    """Cross-config gate: fail only when shared-query overlap is below baseline.

    The legacy gate (``cross_avg > same-model avg + 0.02``) fired on QUERY-only
    drift — where cross-config overlap is legitimately HIGH — and missed
    PASSAGE-only drift, where it is low. The threshold is the calibrated
    Phase-3 baseline (>= 0.85) applied to the shared-query passage overlap.
    """
    return cross_avg >= threshold


class EncodeBoth:
    """Load both models and encode with both."""

    def __init__(self):
        self._baseline = None
        self._onnx_session = None
        self._tokenizer = None

    def load(self):
        import onnxruntime as ort
        from FlagEmbedding import BGEM3FlagModel
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer

        t0 = time.monotonic()
        # fp32 baseline loads from a pinned local snapshot of BAAI/bge-m3
        # (BGEM3FlagModel has no revision= kwarg; a local dir cannot drift).
        bge_local = snapshot_download(
            repo_id="BAAI/bge-m3",
            revision=BGE_M3_REVISION,
            local_dir=str(SCRATCH / "bge_m3_fp32"),
            local_dir_use_symlinks=False,
            resume_download=True,
            ignore_patterns=["*.md", "*.py", "requirements.txt"],
        )
        self._baseline = BGEM3FlagModel(bge_local, use_fp16=False, device="cpu")
        print(f"  Baseline loaded in {time.monotonic() - t0:.1f}s")

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
        self._onnx_session = ort.InferenceSession(
            os.path.join(local_path, "model_quantized.onnx"),
            providers=["CPUExecutionProvider"],
        )
        self._tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3", revision=BGE_M3_REVISION)
        print(f"  ONNX loaded in {time.monotonic() - t0:.1f}s")

    def encode_both(self, texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """Return (fp32_vecs, onnx_vecs) for a list of texts."""
        # fp32
        fp32_all = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            out = self._baseline.encode(
                batch,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            fp32_all.append(out["dense_vecs"])
        fp32_vecs = np.concatenate(fp32_all, axis=0)

        # ONNX
        onnx_all = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            inputs = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                return_tensors="np",
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
        print(
            f"{cat:<28} {avg_o:<12.4f} {min_o:<12.4f} {avg_c:<12.4f} {'PASS' if passed else 'FAIL'}"
        )

    overall_avg = sum(total_overlaps) / len(total_overlaps)
    overall_min = min(total_overlaps)
    print(
        f"\n{'OVERALL':<28} {overall_avg:<12.4f} {overall_min:<12.4f} "
        f"{sum(total_cosines) / len(total_cosines):<12.4f} {'PASS' if all_pass else 'FAIL'}"
    )

    # Cross-config validation
    print(f"\n{'=' * 60}")
    print("Cross-Config Check (ONNX query → fp32 passage NN overlap)")
    print("=" * 60)
    cross_overlaps = [
        _cross_config_overlap(q_onnx[i], corpus_fp32, corpus_onnx, TOP_K)
        for i in range(len(queries))
    ]

    cross_avg = sum(cross_overlaps) / len(cross_overlaps)
    print(f"  Cross-config avg overlap: {cross_avg:.4f}")
    print(f"  Same-model avg overlap:   {overall_avg:.4f}")

    if not _evaluate_cross_config(cross_avg):
        print(f"  ⚠ Cross-config overlap {cross_avg:.4f} < baseline {OVERLAP_THRESHOLD}")
        print("  → ONNX passage embeddings diverge from fp32 — discriminative quality degraded")
        all_pass = False
    else:
        print(f"  ✓ Cross-config overlap >= baseline (Δ={cross_avg - overall_avg:.4f})")

    # Zero-overlap queries
    zero_qs = [
        (queries[i], total_overlaps[i]) for i in range(len(queries)) if total_overlaps[i] == 0
    ]
    if zero_qs:
        print(f"\n  ⚠ {len(zero_qs)} queries with zero overlap:")
        for q, _ in zero_qs[:5]:
            print(f"    [{q['category']}] {q['q'][:80]}")
    else:
        print("\n  ✓ No zero-overlap queries")

    # A reduced corpus cannot validate the Phase-3 gate: any source that was
    # unavailable must fail the run, regardless of the overlap numbers.
    if CORPUS_MISSING:
        print("\n  ⚠ Corpus degraded — unavailable sources: " + ", ".join(CORPUS_MISSING))
        print("  → Phase-3 overlap measured on a reduced corpus; treated as FAIL.")
        all_pass = False

    # Final verdict
    print(f"\n{'=' * 60}")
    print("FINAL VERDICT — Phase 3: Retrieval Agreement")
    print("=" * 60)
    print(f"  Top-{TOP_K} overlap threshold: >= {OVERLAP_THRESHOLD}")
    print(f"  Achieved: avg={overall_avg:.4f}, min={overall_min:.4f}")
    print(f"  Result: {'PASS ✅' if all_pass else 'FAIL ❌'}")

    if all_pass:
        print("\n  Phase 3 PASSED — proceed to Phase 4.")
    else:
        print("\n  Phase 3 FAILED.")
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

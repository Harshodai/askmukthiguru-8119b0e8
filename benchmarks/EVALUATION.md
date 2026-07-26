# ONNX INT8 BGE-M3 Evaluation

**Generated:** Jul 26, 2026 &middot; **Status:** PASS (All 5 Phases)

| Metric | Result | Threshold | Status |
|--------|--------|-----------|--------|
| Mean Cosine Similarity | 0.9885 | >= 0.985 | PASS |
| Min Cosine Similarity | 0.9755 | >= 0.95 | PASS |
| Paraphrased Mean Cosine | 0.9894 | >= 0.985 | PASS |
| Avg Top-10 Retrieval Overlap | 0.9154 | >= 0.85 | PASS |
| Cross-Config Delta | 0.0028 | (< 0.02) | PASS |
| fp32 P95 Latency | 185.55 ms | — | — |
| ONNX INT8 P95 Latency | 26.16 ms | — | PASS |
| Speed Ratio (ONNX/fp32 P95) | 0.141 | <= 1.10 | PASS |

## Key Findings

1. **Embedding quality preserved.** Mean cosine 0.9885 across full 380-query corpus (18 categories including guardrails, adversarial, multilingual). Min cosine 0.9755 well above 0.95 threshold.

2. **Retrieval agreement strong.** Avg top-10 overlap 0.9154 across 7 doctrine categories (143 queries, 233-passage corpus). No zero-overlap queries.

3. **Latency: ONNX INT8 is 7-9x faster cold, 2-4x faster warm.** On a cold cache (after Redis+GPTCache flush), fp32 shows high variance (42-245ms) due to PyTorch thread pool contention. ONNX INT8 is deterministic (10-34ms). For warm steady-state: fp32 P95 ~35ms, ONNX P95 ~16ms.

4. **Production-ready.** All wiring verified:
   - `EMBEDDING_BACKEND=onnx_int8` toggle in `.env`
   - Download from `gpahal/bge-m3-onnx-int8` (8 files, not 30)
   - Dimension validation (1024)
   - All encode paths (`encode`, `encode_batch`, `encode_single`, `encode_single_full`)

## Verdict

**Stop-gap: Acceptable.** The ONNX INT8 model preserves embedding quality and retrieval fidelity within spec while providing significant latency benefits. The cp1 (software-only) ColBERT computation is a known limitation — the model outputs colbert_vecs but current code doesn't use them yet. For formal release, either fix the software ColBERT path or use a model that outputs all three heads natively.

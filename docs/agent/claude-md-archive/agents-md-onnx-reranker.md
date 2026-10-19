<!-- Archived verbatim from root AGENTS.md on 2026-10-19 to cut context cost. Not auto-loaded. Text is dated: verify against code and lessons.md before relying on it. -->

# Archived from AGENTS.md: agents-md-onnx-reranker

## ONNX Reranker + ColBERT MaxSim (Jul 27, 2026)

### Phase 1 — ONNX INT8 CrossEncoder (shipped)
- **Reranker backend**: `temsa/mmarco-mMiniLMv2-L12-H384-v1-onnx-cpu-qint8` (23MB ONNX INT8, dynamic quantization of MatMul/Gemm/Attention). Replaces PyTorch `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (91MB).
- **Toggle**: `RERANKER_BACKEND=onnx_int8` (default, already in config.py). Rollback: `RERANKER_BACKEND=flagembedding` in `.env` and restart.
- **Tokenizer source**: loaded from the temsa repo (not upstream) to match the ONNX model's own tokenizer files. See lessons.md "Tokenizer source = model repo".
- **Validation**: `backend/scripts/validate_onnx_reranker.py` — P0 env_parse, P1 capability, P2 Spearman >0.90 (passes at 0.976), P3 latency (warm P95 449ms). Run: `cd backend && python3 scripts/validate_onnx_reranker.py`.

### Phase 2 — ONNX-Native ColBERT MaxSim (shipped, disabled by default)
- **What**: Multilingual late-interaction reranking using BGE-M3's colbert_vecs output (ort_out[2], 1024d per token, L2-normalized). Replaces the English-only RAGatouille ColBERTv2 path. 100+ languages.
- **Toggle**: `ENABLE_COLBERT=true` in `.env` (defaults False — Phase 2 ships disabled). When True, `cascaded_rerank()` uses `_colbert_maxsim_rerank()` (ONNX-native, batched); when False, keeps the deprecated RAGatouille fallback.
- **Batched**: `_colbert_maxsim_rerank` encodes query + ALL docs in ONE `encode_with_colbert` call, then scores via `batch_maxsim` (pure NumPy matmul). No per-doc loop.
- **CLS exclusion**: `encode_with_colbert` slices `colbert_vecs[:tokens_num - 1]` per doc, matching FlagEmbedding's `_process_colbert_vecs`. See lessons.md.
- **Validation**: `backend/scripts/validate_colbert_maxsim.py` — P0 env_parse, P1 capability, P2 latency (warm P95 248ms < 2000ms gate), P3 multilingual (en/hi/te/mr all pass), P4 ColBERT-vs-CrossEncoder Spearman 0.89 > 0.85 gate. Run: `cd backend && python3 scripts/validate_colbert_maxsim.py`.
- **RAGatouille**: kept in `requirements.txt` with a TODO comment marking it deprecated. Do NOT remove until the RAGatouille path is confirmed dead in `cascaded_rerank`.

### Pre-existing bug fixed: ONNX encoder re-download
- `_load_onnx_encoder` was not setting `self._encoder`, so `_ensure_encoder()`'s short-circuit (`if self._encoder is not None: return`) never fired on the ONNX path. Every `encode()`/`encode_batch()`/`encode_with_colbert()` call re-downloaded the 570MB ONNX model (~30s per call). Fix: `self._encoder = session` at the end of `_load_onnx_encoder` — a marker that makes the short-circuit fire. 30657ms → 46ms per call (660× improvement). This was a silent production bug since cp1 shipped (Jul 26). See lessons.md.

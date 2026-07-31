# Task 4 Report — `_colbert_maxsim_rerank()` + `cascaded_rerank()` wiring

**Branch:** `onnx-reranker-colbert-v2`
**Commit:** `76d23cde`
**Files changed:** 2 (backend/services/embedding_service.py, backend/requirements.txt)
**Diff stat:** +65 / −19

## What changed

### Part 1: Added `_colbert_maxsim_rerank()` to `EmbeddingService`

**Location:** `backend/services/embedding_service.py`, inserted between `encode_with_colbert_async` (line 879-881) and `encode_single_full` (now ~line 924).

**Signature:** `_colbert_maxsim_rerank(self, query: str, documents: list[dict], top_k: int = 15) -> list[dict]`

**Behavior:**
- Early-returns `[]` if no documents, or `documents[:top_k]` if `settings.enable_colbert` is False (Phase 2 ships disabled).
- Lazy imports `numpy` and `services.colbert_maxsim.batch_maxsim` (Ponytail — keeps module-level imports clean).
- **Batched**: builds `all_texts = [query] + [doc.get("text", "") for doc in documents]` and calls `encode_with_colbert(all_texts)` exactly ONCE — single forward pass for query + every doc.
- Extracts `query_tokens = encoded["colbert"][0]` and `doc_tokens_list = [v for v in encoded["colbert"][1:]]`.
- Scores via `batch_maxsim(query_tokens, doc_tokens_list)` (pure NumPy matmul — no inference lock needed).
- Adds `colbert_score` to each doc copy, sorts descending, returns top-k.
- Logs: `ColBERT MaxSim reranked N -> K docs`.

**Lock note:** No outer `with self._inference_lock` — `encode_with_colbert` already acquires it internally (it's an RLock so re-entry is safe, but the matmul needs no lock). Verified `self._inference_lock = threading.RLock()` at line 101.

### Part 2: Wired `cascaded_rerank()` to branch on `enable_colbert`

**Location:** `backend/services/embedding_service.py` ~lines 1001-1057 (method body replaced).

**Key changes:**
1. **Small-candidate short-circuit** (`len(documents) < 10`): branches on `settings.enable_colbert` — uses `_colbert_maxsim_rerank` when True, otherwise the deprecated `_colbert_only_rerank` (RAGatouille).
2. **Main ColBERT stage** (inside `with self._inference_lock`):
   - `if settings.enable_colbert:` → tries `_colbert_maxsim_rerank` (ONNX batched). On any `Exception`, logs error and falls back to a rough slice `documents[:colbert_top_k * 2]`.
   - `elif len(documents) > colbert_top_k:` → keeps the RAGatouille path (calls `self._ensure_colbert()` then `self._colbert.rerank(...)`). Backward-compat fallback for when the new path is disabled or unavailable.
3. **CrossEncoder polish** unchanged: `self.rerank(query, colbert_docs, top_k=cross_top_k, min_score=min_score)`.
4. `_ensure_colbert()` only called inside the `elif` branch — no longer always-triggered (it was previously called unconditionally at line 1025, which lazy-loaded RAGatouille even when enable_colbert=True).

### Part 3: TODO comment in `backend/requirements.txt`

**Location:** lines 42-46 (above the `ragatouille>=0.0.8` line, now at line 47).

```
# TODO(onnx-reranker-colbert): ragatouille is now deprecated — the ONNX-native
# ColBERT MaxSim path (services/colbert_maxsim.py + EmbeddingService._colbert_maxsim_rerank)
# replaces it for multilingual reranking. Keep until the RAGatouille path is
# confirmed dead and removed from cascaded_rerank. Removal tracked in
# .claude/plans/onnx-reranker-colbert-optimization.plan.md.
ragatouille>=0.0.8
```

## Batched call structure (confirmed)

ONE `encode_with_colbert(all_texts)` call for query + ALL docs. No per-doc loop.

```python
all_texts = [query] + [doc.get("text", "") for doc in documents]
encoded = self.encode_with_colbert(all_texts)        # single ONNX forward pass
query_tokens = np.array(encoded["colbert"][0], ...)
doc_tokens_list = [np.array(v, ...) for v in encoded["colbert"][1:]]
scores = batch_maxsim(query_tokens, doc_tokens_list)  # pure NumPy
```

## Verification outputs

### 1. AST parse
```
AST OK
```

### 2. Method existence + wiring
```
sig: (self, query: 'str', documents: 'list[dict]', top_k: 'int' = 15) -> 'list[dict]'
wiring OK
```
(Run with `LLM_PROVIDER=ollama` to avoid the `sarvam_api_key` validator in `app.config`.)

### 3. requirements.txt `ragatouille` count
`grep -c "ragatouille" backend/requirements.txt` → **2** (see Concern #1).

### 4. TODO comment context
```
# TODO(onnx-reranker-colbert): ragatouille is now deprecated — the ONNX-native
# ColBERT MaxSim path (services/colbert_maxsim.py + EmbeddingService._colbert_maxsim_rerank)
# replaces it for multilingual reranking. Keep until the RAGatouille path is
# confirmed dead and removed from cascaded_rerank. Removal tracked in
# .claude/plans/onnx-reranker-colbert-optimization.plan.md.
ragatouille>=0.0.8
```

### 5. Smoke test (ONNX runtime, `enable_colbert=True`)
```
top doc: Karma is the law of cause and effect. score: 0.7544946074485779
PASS
```
Karma doc ranked first above weather/sunny and moksha docs. The ONNX BGE-M3 INT8 session loaded fresh (downloads seen in stderr) and the batched encode + `batch_maxsim` returned a sensible ranking.

## Concerns

### 1. `grep -c "ragatouille"` returns 2, not 1
The task spec said verification #3 should return 1. The prescribed TODO comment literally contains the word "ragatouille" ("ragatouille is now deprecated"), so `grep -c "ragatouille"` matches both the comment line AND the actual `ragatouille>=0.0.8` dependency line, returning 2. The **dependency declaration itself** still appears exactly once — `grep -E "^ragatouille" backend/requirements.txt` returns 1. No action taken; this is a self-inconsistent verification criterion in the task spec, not a bug.

### 2. RAGatouille `_ensure_colbert()` lazy-load moved into the elif branch
Previously `_ensure_colbert()` was called unconditionally at the top of `cascaded_rerank` (line 1025), which lazy-loaded RAGatouille even when `enable_colbert=True`. I moved it inside the `elif` branch (RAGatouille path only). This is a small behavioral change: callers using RAGatouille (when `enable_colbert=False`) will still load it, but ONNX-first callers (`enable_colbert=True`) no longer pay the RAGatouille import cost. This aligns with the plan's intent ("keep RAGatouille path as deprecated fallback") and is harmless — `_ensure_colbert()` is idempotent and is still called from `_colbert_only_rerank` and the constructor's no-op path.

### 3. Smoke test pulled the model fresh
First run triggered HF downloads for the BGE-M3 ONNX INT8 model files (8 files, ~30s). Subsequent runs will use the cache. This is expected first-use behavior, not a regression.

### 4. `encode_with_colbert` returns a list of lists, not list of np.ndarray
Task 3's contract returns `encoded["colbert"]` as a list (per the spec `{"dense": [...], "sparse": [...], "colbert": [np.ndarray, ...]}`). `_colbert_maxsim_rerank` defensively wraps each element with `np.array(v, dtype=np.float32)` so it works whether they arrive as ndarrays or nested lists. Verified working in smoke test.
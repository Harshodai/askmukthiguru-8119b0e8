# Qdrant First-Person Pipeline — Storage & Retrieval Research (2026-10-04)

**Scope:** Qdrant collection `first_person_v7` (~1,270 pts → ~2,500 clips), FP verbatim pipeline.
**Method:** read-only code/config verification + web research (2024–2026 sources, URLs cited).
No code changes, no Qdrant writes, 0 LLM calls. Synthesis from search results + code reads.

---

## 0. Verified setup (corrections to the task brief included)

| Claim in brief | Verified reality | Hook |
|---|---|---|
| vectors `passage_dense` + `question_dense`, 1024d BGE-M3, cosine, on_disk=false | **Confirmed for dense.** Both named dense vectors COSINE/1024, `on_disk=False` | `backend/services/first_person_store.py:224-237` |
| "no sparse vectors on this collection" | **WRONG — sparse EXISTS.** `passage_sparse: SparseVectorParams(index=SparseIndexParams(on_disk=True))` created in `init_collection`, written in `upsert_clips` (`:313-325`), fused in `search_hybrid` via RRF prefetch (`:475-496`) | `first_person_store.py:238-240, 313-325, 442-505` |
| `question_dense` | Schema-declared but **deliberately unwritten and unfused**: `apply_indexable_clips` passes `None` for question vectors (`build_first_person_index.py:451`), `upsert_clips` skips falsy entries to avoid "double-count in RRF" (`first_person_store.py:303-311`), `search_hybrid` prefetches only passage_dense + passage_sparse (`:471-474`) | as cited |
| exact-match + vector search via `FirstPersonStore` | Confirmed: `search_hybrid` (hybrid RRF) + `points_servable` retrieve + `count` | `first_person_store.py:442-528` |
| follow-up via `resolve_followup.py` | Exists as graph node (`backend/rag/resolve_followup.py:127`) but note: fast-path strategy **removed** it for speed (`backend/rag/graph_strategies.py:462`) — verify FP route actually calls it before investing in follow-up rewriting | `graph_strategies.py:284, 332-346, 462` |
| 8s clip snapping (`MIN_CLIP_DURATION_S=8.0`), 2.0s floor for interview clips with `question_context` | Confirmed | `build_first_person_index.py:80-86, 582-588` |
| timestamped shadow collections + alias pattern | Confirmed: `QdrantAliasManager` — `create_shadow_collection` (schema-inheriting), `atomic_alias_swap`, `rollback_alias` (ledger), `cleanup_old_collections` (protects all alias targets, `keep_last_n>=1`) | `backend/services/qdrant_aliases.py:122-387` |
| snapshot backups | Confirmed standalone script, REST snapshot → local + S3, retention prune; default collection `spiritual_wisdom` (NOT fp — FP coverage gap, see §10) | `scripts/ops/qdrant_backup.py:1-60` |
| HNSW defaults, no quantization | Confirmed: `create_collection` passes **no** `hnsw_config`/`quantization_config` → server defaults (m=16, ef_construct=100, full_scan_threshold=10000, indexing_threshold=20000) | `first_person_store.py:224-241`; defaults per https://qdrant.tech/documentation/manage-data/indexing/ |
| payload indexes | 15 declared (`PAYLOAD_INDEXES`, `first_person_store.py:172-188`): keyword video_id/speaker/transcript_hash/group_id/source_url/teacher_id(s)/provenance_kind/quality_status/first_person_eligible/is_verbatim + text verbatim_text/question_text + integer start_ms/end_ms | as cited |
| **GAP: `rights_cleared` filtered but NOT indexed** | `search_hybrid` adds `rights_cleared==True` to EVERY query filter (`:460-463`) and `points_servable` reads it (`:427-440`), but `PAYLOAD_INDEXES` has **no** `rights_cleared` entry. Same for `channel`, `duration_ms`, `layer_sha256`, `asr_disputed_rate` (latter two are written by `build_store_clip`/`build_index` but never indexed — fine unless filtered) | `first_person_store.py:172-188` vs `:460-463` |
| golden-25 floors | `TOP1_MIN=0.12`, `SAME_VIDEO=0.0`, `SAME_CLIP=0.0` — measured floors on 144→177-pt pilot index, re-measure due post-ingest in the SAME change as provenance comment | `.github/workflows/golden25-gate.yml:48-55`; `HANDOFF_2026_10_03.md:164` |
| calibration | v7 profile is demoted/operational (`threshold 0.45`, `claims none`, n=14 pilot, no conformal guarantees) | `config/first_person_calibration_v7.json:1-7`; loader accepts demoted form `first_person_pipeline.py:115-144` |
| exact cache | 24h TTL (`EXACT_CACHE_TTL=86400`), language+collection+fitted_at+rerank+answerability key, integrity re-check + 5-min servable cache on hits | `first_person_pipeline.py:52-53, 800-941` |
| host-side BGE-M3 | `EmbeddingService`: BGE-M3 (dense+sparse+ColBERT in one call), ONNX INT8 candidate `gpahal/bge-m3-onnx-int8`, `encode_batch`/`encode_with_colbert` | `backend/services/embedding_service.py:5-9, 160, 207+` |

---

## 1. HNSW tuning (m, ef_construct, ef) for <100k collections

**Findings.**
- Qdrant defaults: `m=16, ef_construct=100, full_scan_threshold=10000` (KB of vectors; 1KB ≈ one 256-dim vector — so for 1024d vectors the threshold trips at ~2,500 points).
  https://qdrant.tech/documentation/manage-data/indexing/
- Official guidance: raise `ef_construct` (100→200→400) = better graph, slower build; raise `m` (8/16/32) = better recall, more RAM/build; `hnsw_ef` (search-time `SearchParams(hnsw_ef=…)`: 32 fast / 128 balanced / 256 accurate) trades recall vs latency per query.
  https://qdrant.tech/course/essentials/day-2/what-is-hnsw/ ; https://qdrant.tech/articles/vector-search-resource-optimization/
- Empirical note: doubling `ef_construct` buys ~2–3% recall but ~3× ingestion latency (byteforth guide; treat as directional, not gospel).
  https://byteforth.com/blog/qdrant-vector-database-delete-the-slow-lookups
- For tiny collections the HNSW graph may never build: `indexing_threshold` default 20000 means segments stay unindexed (brute force) below that — correct and desirable at 1–3k points; forcing early indexing (`indexing_threshold=100`) is a demo trick, not a prod recommendation.
  https://qdrant.tech/course/essentials/day-2/pitstop-project/ ; collection-info example https://qdrant.tech/documentation/manage-data/collections/
- Our prefetch depth (`RRF_PREFETCH_DEPTH=60`, `limit=max(limit*2,60)`) with `dedup_limit` up to 16 and `limit=max(50, max_clips*8)` is generous for a 1–3k collection — recall-friendly, latency-cheap at this scale.

**Applies to us.**
- At 1,270→2,500 × 1024d, full HNSW tuning is a **second-order lever**: exact/brute-force region already gives near-perfect recall; graph quality is not our bottleneck (golden SAME_VIDEO 0.0 is a semantic/chunking problem, not an ANN-recall problem).
- Concrete hooks: `FirstPersonStore.init_collection` (`first_person_store.py:213-255`) passes no `hnsw_config`; `search_hybrid` passes no `search_params` (`:498-505`).
- Cheap, safe experiment when evidence-gated: set `ef_construct=200` on the next shadow collection + `hnsw_ef=128` at query time, measure golden-25 delta. Expect ~0 measurable gain at this scale — that null result is itself useful (rules out ANN as the cause).

## 2. Quantization (scalar/binary/TurboQuant/PQ) — recall vs RAM

**Findings.**
- Ladder (2026 docs): float32 baseline → **Scalar int8** 4× compression, recall ≈ indistinguishable (~0.99) → **TurboQuant 4-bit** 8× at SQ-competitive recall (within ~1–2pp, sometimes ahead) → BQ/PQ 16–32× with rescore to recover recall.
  https://qdrant.tech/documentation/manage-data/quantization/ ; https://qdrant.tech/articles/turboquant-quantization/ (May 2026) ; https://qdrant.tech/documentation/search-tuning/when-your-collection-outgrows-ram/
- Independent repro: SQ 4× smaller, recall ~0.90+ without rescore; BQ 32× (~19MB vs 608MB) needs 8× oversample-rescore to reach 0.990; PQ 16× + 2× rescore ≈ baseline. Qdrant rescores BQ by default, not SQ/PQ.
  https://medium.com/@mohammedarbinsibi/16-smaller-vectors-in-qdrant-memory-recall-and-latency-results-6081bda5092f
- RAM rule of thumb: `vectors × dims × 4B × 1.5`.
  https://qdrant.tech/documentation/search-tuning/when-your-collection-outgrows-ram/

**Applies to us — DO NOT QUANTIZE FP.**
- Math: 2,500 pts × 1024d × 4B × 1.5 ≈ **15 MB**. Even with HNSW overhead (~×2–3), the FP collection fits in L3-adjacent RAM. Quantization saves single-digit MB while risking recall on exactly the short-clip cosine margins our 0.45 threshold lives on.
- Repo invariant already evidence-gates quantization (AGENTS.md 2026-08-22: activation needs held-out NDCG/recall/faithfulness/citation/abstention/p95-p99/rollback evidence). This research supports keeping that gate CLOSED for FP until scale (>100k pts) or memory pressure says otherwise.
- Only revisit if: FP grows 40× or Railway memory billing forces it — then first candidate is Scalar int8 (always_ram, originals cold), never binary, with rescore swept 2×→8× on golden-25.

## 3. On-disk vs in-RAM vectors/payloads

**Findings.**
- Per-vector memory tiers (`models.Memory.COLD`/`pinned`) beat the legacy `on_disk` bool; explicit per-vector setting overrides `memmap_threshold`.
  https://qdrant.tech/documentation/manage-data/storage/
- Payload indexes can also go cold (`KeywordIndexParams(memory=COLD)` / `on_disk=True`).
  https://qdrant.tech/documentation/manage-data/indexing/ (on-disk payload index; 1.11 blog)
- Cold originals + pinned quantized copies = the recommended low-RAM pattern — irrelevant at our scale (see §2).

**Applies to us — NO CHANGE.**
- Current `on_disk=False` (dense) / sparse `on_disk=True` (`first_person_store.py:227-240`) is correct for a 15MB collection: dense in RAM for latency, sparse index already disk-backed.
- Watch item only: if Railway memory ($28.79/$30, 94% memory — AGENTS.md cost invariants) forces savings, the FP collection is NOT the target (Neptune-scale savings live in backend/Neo4j, ~8GB/2.5GB). Do not move FP dense to disk to chase dollars — latency cost with zero memory win.

## 4. Payload indexing — which filter fields need it

**Findings.**
- Rule: **index every field you filter on**; each index is a memory/disk tax, so index nothing else. Keyword/integer/datetime chosen by predicate type (Match vs Range). Qdrant docs + sizing skill say this explicitly.
  https://qdrant.tech/documentation/manage-data/collections/ ; https://qdrant.tech/documentation/manage-data/indexing/ ; https://www.scaler.com/topics/what-is-qdrant-deep-dive/
- `text` index (tokenizer, phrase_matching) is for full-text predicates, NOT a substitute for sparse vectors.
  https://qdrant.tech/documentation/manage-data/indexing/ (Full-Text Index)
- Filtered HNSW: payload indexes feed filter-aware traversal; unindexed filters fall back to scan (fine at 2.5k, slow later). ACORN (v1.16+) mitigates strict-filter graph disconnection.
  https://qdrant.tech/articles/filtered-vector-search-acorn/
- Tenant-pattern: high-cardinality allowlist fields can use `is_tenant=True`.
  https://qdrant.tech/course/essentials/day-2/filterable-hnsw/

**Applies to us — ONE REAL FIX.**
- (a) **Add `rights_cleared` keyword index (S effort, real correctness-latency fix).** Filtered on every `search_hybrid` call, unindexed today. At 2.5k pts the planner likely full-scans anyway, but the index is one line, zero recall risk, and future-proofs the rights gate. Hook: `FirstPersonStore.PAYLOAD_INDEXES` (`first_person_store.py:172-188`) + mirror in `QdrantAliasManager.create_shadow_collection` if it replicates a different index list (`qdrant_aliases.py:220-231` uses `QdrantClientManager._PAYLOAD_INDEXES` — VERIFY the two lists agree or shadow collections silently drop FP indexes).
- (b) Keep: `video_id`, `speaker`, `teacher_id`, `transcript_hash`, `first_person_eligible`, `provenance_kind` keyword (all filtered or deduped on); `start_ms`/`end_ms` integer (range-capable, used in span logic).
- (c) Do NOT index: `verbatim_text`/`question_text` as `text` — nothing filters on them via MatchText; they are retrieved payload + sparse-vector source. The existing `text` entries are harmless but useless; removing them saves a rebuild for no gain — leave alone.
- (d) `teacher_ids` (array) keyword index exists but code filters on scalar `teacher_id` (`:464-467`) — confirm array-vs-scalar semantics before touching; no action now.

## 5. Hybrid dense+sparse + RRF/DBSF

**Findings.**
- Qdrant pattern: two `Prefetch` (dense + sparse) → `FusionQuery(RRF|DBSF)`. RRF = rank-only, robust, no tuning; DBSF = distribution-normalized scores, respects magnitude but fragile α/weight tuning.
  https://qdrant.tech/documentation/search/hybrid-queries/ ; https://qdrant.tech/course/essentials/day-3/hybrid-search/
- Official tuning note: "run dense-only, sparse-only, fusion on the same labeled queries; if both miss, fusion has no candidate to promote."
  https://qdrant.tech/documentation/search-tuning/hybrid-search/
- Field report: BM25+dense+RRF was "the single biggest retrieval quality improvement" (MRR 0.41→0.67); warns small corpus + k=60 can hurt — drop k (they used k=10) on small corpora.
  https://blog.gopenai.com/hybrid-search-in-rag-dense-sparse-bm25-splade-reciprocal-rank-fusion-and-when-to-use-which-fafe4fd6156e
- Weighted RRF (`Rrf(k, weights)`) exists for priors about retriever reliability.
  https://qdrant.tech/documentation/search/hybrid-queries/ (weighted RRF)

**Applies to us — ALREADY CORRECT, TUNE NEXT.**
- We already run exactly the recommended pattern (dense+sparse prefetch → RRF, `Fusion.RRF`, depth 60) with BGE-M3 native sparse (no separate BM25 service). No architecture change needed.
- Three evidence-gated tunables, each a one-line change + golden-25 ablation (RRF/DBSF weights are explicitly evidence-gated per AGENTS.md 2026-08-22 — honor it):
  1. **Prefetch depth 60 → ablate {20, 40, 60, 100}** on golden-25. Field report suggests 60 may be too deep for 2.5k pts; smaller depth sharpens rank differences.
  2. **RRF vs DBSF A/B** on golden-25 (code already imports both `Fusion` names? `first_person_store.py:28-41` imports `Fusion, FusionQuery` — DBSF is one enum flip).
  3. **Weighted RRF** (dense-heavy, e.g. [2.0, 1.0]) IF ablation shows sparse leg noisy on paraphrase queries (BGE-M3 sparse is lexical; paraphrase queries by design avoid lexical overlap — dense should dominate).
- Do NOT add a third retriever (e.g. BM25 service) — BGE-M3 sparse already covers the lexical leg.

## 6. Multivector / ColBERT late interaction (we hold the model!)

**Findings.**
- Qdrant supports multivectors (`MultiVectorConfig(MAX_SIM)`) since 1.10; pattern is dense-prefetch → MaxSim rescore, because full-corpus MaxSim is brute-force expensive. Typical config disables HNSW (`m=0`) on the multivector field.
  https://qdrant.tech/course/essentials/day-5/colbert-multivectors/ ; https://qdrant.tech/articles/late-interaction-models/
- Community consensus: late interaction "rarely used for initial retrieval… works as a reranker; too expensive."
  https://www.reddit.com/r/vectordatabase/comments/1jo9jtx/my_journey_into_hybrid_search_bgem3_qdrant/
- BGE-M3 emits `colbert_vecs` from the same `encode()` call as dense+sparse (already in our embedding service surface: `encode_with_colbert`, `batch_maxsim`).
  https://bge-model.com/bge/bge_m3.html ; `backend/services/embedding_service.py` (colbert/maxsim present); main-corpus precedent: `ENABLE_COLBERT` ships **disabled by default**, validated at Spearman 0.89 / warm P95 248ms (AGENTS.md ONNX+ColBERT §).

**Applies to us — BEST MEDIUM-TERM LEVER, EVIDENCE-GATED.**
- The plumbing exists on both sides (model emits colbert_vecs; service has `batch_maxsim`; Qdrant collection does NOT yet have a multivector field). This is the highest-expected-gain retrieval upgrade that doesn't violate verbatim integrity (rescore-only, never generates text).
- Recommended shape (do NOT implement without gate): add `passage_colbert` multivector field on next shadow collection → dense+sparse RRF prefetch (existing) → MaxSim rescore top-50→top-10 in-App (reuse `batch_maxsim`, no Qdrant multivector query needed initially) → golden-25 ablation. Full Qdrant-side multivector only if in-app rescore proves the signal.
- Evidence gate: golden-25 SAME_VIDEO/SAME_CLIP + NDCG lift with p95 latency budget (main-corpus ColBERT P95 248ms is the reference ceiling); rollback = flag off, field stays dormant.
- Cost note: colbert_vecs storage is ~tokens×1024d per clip — fine at 2.5k, re-evaluate at 100k.

## 7. Question-side retrieval (question_text, HyDE, rewriting)

**Findings.**
- HyDE: LLM writes hypothetical answer → embed → retrieve. Bridges short-query/long-doc embedding gap; +50% precision reported (Elasticsearch); document need not be factual (thrown away after embedding). Costs 1 LLM call; cache hypotheticals for repeated patterns.
  https://www.elastic.co/search-labs/blog/hyde-semantic-search-elasticsearch ; https://docs.haystack.deepset.ai/docs/hypothetical-document-embeddings-hyde ; https://www.emergentmind.com/topics/hypothetical-document-embeddings-hyde
- Query rewriting (distinct from HyDE): standalone rewriting fixes follow-ups ("which one?") — small-model 1 call, AmbigNQ 76.4→82.2% context-containment; ConvGQR adds expansion terms; RQ-RAG unifies rewrite+decompose.
  https://alhena.ai/blog/query-rewriting-before-retrieval-multi-turn-rag/ ; https://www.meilisearch.com/blog/query-rewrite-rag
- Rewriting vs HyDE vs multi-query solve different problems and compose (rewrite → HyDE → retrieve).
  https://alhena.ai/blog/query-rewriting-before-retrieval-multi-turn-rag/ (comparison table)

**Applies to us — TWO SEPARATE GAPS.**
- (a) **`question_dense`/`question_text` is dormant infrastructure.** `build_store_clip` writes `question_text` from `question_context` (`build_first_person_index.py:318`) and relaxes the duration floor to 2.0s for such clips (`:585`) — but `apply_indexable_clips` embeds ONLY `verbatim_text` and passes `question_dense=None` (`:446-451`), and `search_hybrid` never prefetches `question_dense`. If interview Q&A clips grow, wire the second leg: embed `question_text` where present → prefetch 3-way RRF (passage_dense + question_dense + sparse). Evidence gate: golden ablation showing interview-query lift; risk is the documented double-count (only set when a REAL question embedding exists — the guard already exists at `first_person_store.py:303-311`).
- (b) **Follow-up resolution for FP is unverified.** `resolve_followup.py` exists but the fast-path graph dropped it (`graph_strategies.py:462`); FP `execute()` takes raw `query` + precomputed vectors — whoever embeds must rewrite first. Check `backend/app/api/first_person.py` (~`:214`) for whether the FP route rewrites follow-ups before embedding. If not, standalone rewriting (1 small-model call, history-aware) is the S-effort fix; HyDE is NOT recommended for FP (verbatim corpus: a hallucinated hypothetical answer embedding risks drifting toward non-recorded phrasing; plus +1 large-model call on a latency-sensitive route).
- (c) Multilingual queries already translate-then-embed (`retrieval_query` param, `first_person_pipeline.py:968-985`) — rewriting (if added) must run on the English form, safety checks on both (existing pattern).

## 8. Multilingual retrieval (BGE-M3 for Telugu/Hindi/Tamil)

**Findings.**
- BGE-M3: 100+ languages, 8192 tokens, SOTA on MIRACL (multilingual) + MKQA (cross-lingual), self-distilled dense+sparse+colbert; training data highly imbalanced across languages (official caveat).
  https://arxiv.org/html/2402.03216v3 ; https://huggingface.co/BAAI/bge-m3 ; https://bge-model.com/bge/bge_m3.html
- Independent 2024 benchmark: BGE-M3 top in English AND non-English vs OpenAI embeddings.
  https://huggingface.co/BAAI/bge-m3 (News 2024/3/8, Yannael benchmark)
- Our pipeline: English-embed after translation (`retrieval_query`), bounded translation timeout failing open (AGENTS.md 2026-08-22 latency invariants).

**Applies to us — HOLD COURSE, MEASURE.**
- Translate-then-embed is the right call for a corpus that is itself English-recorded: cross-lingual dense retrieval (Telugu query → English clip) leans on BGE-M3's weakest axis (imbalanced training data), while translation + monolingual retrieval leans on its strongest.
- Action: extend golden-25 with a Telugu/Hindi/Tamil paraphrase slice (S effort, no prod change) to quantify the translation-vs-native-embed gap before any architecture debate. BGE-M3 native cross-lingual is the fallback if translation latency/tail (10.8s Hindi run on record) ever forces it.

## 9. Short-clip retrieval (8–30s utterances)

**Findings.**
- Smaller chunks (256 vs 384 tokens) consistently give better precision; large chunks dilute relevance.
  https://www.reddit.com/r/Rag/comments/1ov0pzk/i_tested_different_chunks_sizes_and_retrievers/
- Industry default converged on **parent-child / small-to-big**: embed small (128–256 tokens or sentence-level) for recall, return the parent window for context (LangChain `ParentDocumentRetriever`, LlamaIndex sentence-window).
  https://medium.com/data-science/advanced-rag-01-small-to-big-retrieval-172181b396d4 ; https://atlan.com/know/chunking-strategies-rag/ ; https://futureagi.com/blog/advanced-chunking-techniques-for-rag/
- Contextual retrieval (Anthropic 2024): prepend short LLM context to each chunk before embedding — fixes "orphan chunk" (e.g. "Yes, as you mentioned…") without changing served text.
  https://atlan.com/know/chunking-strategies-rag/ (contextual retrieval row)

**Applies to us — DIRECTLY RELEVANT.**
- Our clips are ALREADY sentence-snapped (`snap_clip`, `boundaries.py`) with dangling-conjunction + boundary-defect gates — i.e. we enforce chunk quality at index time. The residual risk is embedding dilution on the shortest clips (2.0s interview answers, ~5–15 words) and orphan references ("as I said…").
- Three concrete, gated options:
  1. **Re-embed test on snapped vs unsnapped text** (S): `display_text` (punctuated) vs `verbatim_text` (unpunctuated) as the embed source — punctuation/casing affects BGE-M3 tokenization; golden ablation decides. Hook: `apply_indexable_clips` (`build_first_person_index.py:446`).
  2. **Parent-context prepend at embed time only** (M): prepend `question_text` (where present) or video-level topic to the embedded string while serving raw `verbatim_text` — this is Anthropic contextual retrieval adapted to verbatim constraints (served text unchanged → integrity gate unaffected). Fixes orphan openers without widening serve windows.
  3. **Sliding-window overlap for long clips** (M, only if golden shows long-clip misses): clips >~60s get a second overlapping point; dedup (`deduplicate_clips_by_video`, `first_person_store.py:123-162`) already handles same-video collisions.

## 10. Timestamped collections + aliases for zero-downtime reindex

**Findings.**
- Qdrant-recommended: ingest into fresh timestamped shadow → verify (NDCG/tamper/count gates) → atomic `update_collection_aliases` swap → keep predecessors for rollback.
  Our `QdrantAliasManager` implements exactly this (ledger + protected-target cleanup).
  https://qdrant.tech/documentation/snapshots/ ; `backend/services/qdrant_aliases.py:1-11, 236-387`
- Alias + snapshot restores compose: full snapshots also recreate aliases.
  https://qdrant-qdrant-18.mintlify.app/operations/backup-restore

**Applies to us — PROCESS GAPS, NOT PATTERN GAPS.**
- (a) **Index-list parity audit (S):** `create_shadow_collection` replicates `QdrantClientManager._PAYLOAD_INDEXES` (`qdrant_aliases.py:220-231`), NOT `FirstPersonStore.PAYLOAD_INDEXES` — if the lists differ, every shadow rebuild silently changes FP filter behavior. One diff, zero risk.
- (b) **Read path should resolve the alias:** confirm `settings.first_person_collection` points at an alias (e.g. `first_person`) rather than `first_person_v7` directly, else swaps don't propagate without config change + restart. Hook: `backend/app/config.py:159` (default `first_person_v1`), `backend/app/api/first_person.py:214`.
- (c) **Verification gates before swap** exist as doctrine (NDCG/tamper/count) — wire golden-25 + `points_servable` spot-check as the automated pre-swap gate (see §12).

## 11. Snapshot / backup / restore

**Findings.**
- Per-collection snapshots: `create_snapshot` → download → `recover_snapshot` (URL/file/S3, `priority=snapshot`); full-instance snapshots include aliases; test RESTORE quarterly, not just backup; shard-level snapshots past ~10M pts.
  https://qdrant.tech/documentation/snapshots/ ; https://qdrant.tech/documentation/tutorials-operations/create-snapshot/ ; https://github.com/orgs/qdrant/discussions/8649
- Our script covers create+download+S3+prune (`scripts/ops/qdrant_backup.py`) with Railway cron `0 2 * * *`.

**Applies to us — TWO GAPS.**
- (a) **FP collection not in default backup scope:** `QDRANT_COLLECTION` defaults to `spiritual_wisdom` (`qdrant_backup.py:56`) — confirm the cron matrix includes `first_person_v7` (or the alias); a 2,500-pt rebuild from passages is hours of yt-dlp + embed, not seconds.
- (b) **No restore drill on record:** schedule one shadow-collection restore (recover snapshot → alias-swap → rollback) as the pre-mass-ingest rehearsal; doubles as the §10 alias-path test.

## 12. Caching retrieved context (exact/semantic × fresh index)

**Findings.**
- Exact-match cache (string key) vs semantic cache (embedding similarity, GPTCache/Redis): semantic is a superset (exact = similarity 1.0); running both duplicates invalidation surface. Semantic thresholds need tuning; stale-index hits are the failure mode (semantically correct, factually outdated).
  https://www.truefoundry.com/blog/semantic-caching-llm-gateway ; https://tianpan.co/blog/2026-04-20-cache-invalidation-ai-semantic-rag ; https://redis.io/blog/what-is-semantic-caching/ ; https://github.com/zilliztech/gptcache
- Standard pattern: exact-match first (hash lookup ~50ms), semantic fallback (~2s), miss → generate.
  https://medium.com/google-cloud/implementing-semantic-caching-a-step-by-step-guide-to-faster-cost-effective-genai-workflows-ef85d8e72883

**Applies to us — CURRENT DESIGN IS CORRECT, DON'T ADD SEMANTIC.**
- FP pipeline deliberately uses **exact cache only, NO semantic cache** (`first_person_pipeline.py:2, 1031-1045`) with integrity re-check + servable revalidation on hits (`:882-919`) and 5-min servable cache (`:827-850`). For a verbatim-attribution product this is the right call: a semantic-cache "near miss" serving someone else's exact words with exact timestamps would be a fabrication incident, not a speedup.
- Keep: key already versions on collection+fitted_at+rerank+answerability (`:800-823`) so reindex/recalibration naturally invalidates.
- Watch: 24h TTL vs index mutation — servable revalidation covers rights-revoke/delete; threshold changes are covered by fitted_at. No action.

## 13. Retrieval evaluation (recall@k, NDCG → our golden-25 floors)

**Findings.**
- Standard ladder: recall@k (primary RAG gate — "is a relevant doc in top-k?"), MRR (first-hit rank), NDCG@k (graded multi-doc ranking), precision@k (reranker check). Gate every retrieval change on recall@k before touching prompts/LLMs; 50–200 golden cases; eval ON YOUR DATA (TREC/BEIR transfer lesson).
  https://www.dataaihub.co/learn/retrieval-evaluation ; https://weaviate.io/blog/retrieval-evaluation-metrics ; https://docs.anyscale.com/rag/evaluation ; https://www.ibm.com/think/architectures/rag-cookbook/result-evaluation
- RAG failure is usually retrieval failure, not generation failure — hence retrieval-first eval.
  https://www.dataaihub.co/learn/retrieval-evaluation

**Applies to us — GOLDEN-25 IS THE INSTRUMENT, SHARPEN IT.**
- Current floors (TOP1 0.12 / SAME_VIDEO 0.0 / SAME_CLIP 0.0) are honest pre-ingest floors on a 144–177-pt index. Post-mass-ingest (~2,500) re-measure is already mandated in the same change as provenance (HANDOFF_2026_10_03 §6 Step 4).
- Concrete eval upgrades (all S effort, no prod risk):
  1. Add **recall@{5,10} + MRR + NDCG@10** to the harness (today: top1/PCS only) — distinguishes "right video, wrong clip" (chunking problem) from "wrong video" (embedding problem). SAME_VIDEO>0 with SAME_CLIP=0 = chunking/boundary work; both 0 = embedding/fusion work.
  2. Add **dense-only vs sparse-only vs RRF** per-query logging — implements Qdrant's own "measure whether it helps" prescription (§5) with zero extra infra.
  3. Add **unanswerable/out-of-corpus queries** to golden (answerability-gate eval already exists in spirit — Phase 2 audit B 3/3 leak) so the abstention contract is gated alongside recall.
  4. Re-measure protocol: freeze dataset SHA (already pinned), run post-ingest, set thresholds at observed floor across ≥2 windows (lessons.md rule), same-change provenance update.

---

## Ranked recommendations

Effort: S = hours–2d, M = 2–5d, L = 1–2wk. Gain: expected golden-25 / prod effect. Every gated item needs its evidence gate passed BEFORE activation per repo invariants (RRF/DBSF/quantization/graph — AGENTS.md 2026-08-22).

| # | Recommendation | Effort | Expected gain | Risk | Evidence gate |
|---|---|---|---|---|---|
| 1 | **Index `rights_cleared` (keyword) + audit shadow index-list parity** (`first_person_store.py:172-188`; `qdrant_aliases.py:220-231`) | S | Low latency now; prevents filter-scan cliff as index grows; fixes silent shadow-schema drift | Near-zero (additive index; rebuild on shadow) | Pre-swap count + golden-25 no-regression (mechanical, not a quality gate) |
| 2 | **Golden-25 hardening: recall@{5,10}+MRR+NDCG@10, per-leg (dense/sparse/RRF) logging, unanswerable slice; post-ingest re-measure** (same change as provenance) | S | Unlocks diagnosis (chunking vs embedding) + unblocks all other gates | Zero prod risk (eval-only) | Lessons.md floor rule: thresholds at min across ≥2 windows |
| 3 | **RRF depth + RRF-vs-DBSF + weighted-RRF ablation** on hardened golden-25 (one enum/param flip each in `search_hybrid`) | S | Small–medium recall lift (field MRR 0.41→0.67 precedent; our paraphrase set favors dense) | Low (flag-gated; RRF default retained on tie) | Held-out golden lift + p95 latency + rollback flag (RRF/DBSF evidence invariant) |
| 4 | **Verify FP follow-up path + add standalone rewriting if missing** (`app/api/first_person.py:214` + `rag/resolve_followup.py:127` vs `graph_strategies.py:462`) | S–M | Medium (multi-turn is currently raw-query retrieval if unwired) | Medium (extra small-model call; prompt drift) | Multi-turn golden slice: context-containment before/after; latency budget |
| 5 | **Wire `question_dense` leg for interview clips** (embed `question_text` where present; 3-way RRF prefetch; keep no-copy guard `first_person_store.py:303-311`) | M | Medium for interview queries; ~zero for monologue queries | Medium (double-count risk if guard bypassed; threshold recalibration) | Golden interview-slice lift + full-set no-regression + threshold refit (fitted_at bump invalidates cache cleanly) |
| 6 | **ColBERT MaxSim rescore (in-app `batch_maxsim` over RRF top-50)**; Qdrant multivector field only if rescore proves signal | M | Highest expected retrieval lift (token-level precision on paraphrase queries) | Medium (latency +250ms precedent; storage tokens×1024d) | Golden SAME_CLIP/NDCG lift + p95 ≤ budget + flag rollback (graph/rerank evidence invariant) |
| 7 | **Embed-time context prepend (question_text/topic) without changing served text** + **display_vs_verbatim embed-source A/B** | S–M | Small–medium (orphan/short-clip rescue) | Low (served text byte-identical → integrity gate untouched) | Golden short-clip slice lift; no threshold change expected |
| 8 | **Backup scope + restore drill**: include FP collection/alias in cron matrix; shadow-restore rehearsal pre-mass-ingest | S | Operational (hours of rebuild avoided) | Zero (drill on shadow) | Successful recover→swap→rollback on shadow |
| 9 | **Read via alias, pre-swap golden gate**: `first_person_collection` → alias; golden-25 + servable spot-check as automated pre-swap gate | S | Operational (true zero-downtime reindex) | Low (config + restart discipline) | Green gate on shadow before each swap |
| 10 | **Multilingual golden slice (Te/Hi/Ta paraphrases)** to quantify translate-vs-native-embed | S | Diagnostic (settles architecture debate with data) | Zero (eval-only) | Gap measurement; no activation without lift + latency case |
| — | **Explicitly NOT recommended**: Qdrant quantization, on-disk dense, semantic cache, BM25 sidecar, HNSW overhaul, HyDE on FP route | — | ~0 gain / negative | Recall, fabrication, latency risk for no measurable win at 2.5k pts | Revisit only on scale (>100k) or billing evidence |

---

## Top-5 (for handoff)

1. **Index `rights_cleared` + shadow parity audit** — S, near-zero risk, fixes a real unindexed-filter + silent-drift hazard.
2. **Harden golden-25 (recall/MRR/NDCG, per-leg logging, unanswerables) + post-ingest re-measure** — S, eval-only, unlocks every downstream decision.
3. **RRF ablation (depth, DBSF, weights)** — S, gated; cheapest possible recall lift on existing infra.
4. **Follow-up path verification + standalone rewriting if missing** — S–M; multi-turn correctness.
5. **ColBERT MaxSim rescore pilot** — M, gated; highest-expected-gain retrieval upgrade, model already in hand.

## Sources (all URLs cited inline; key docs)

- HNSW/params: https://qdrant.tech/documentation/manage-data/indexing/ ; https://qdrant.tech/course/essentials/day-2/what-is-hnsw/ ; https://qdrant.tech/articles/vector-search-resource-optimization/
- Quantization: https://qdrant.tech/documentation/manage-data/quantization/ ; https://qdrant.tech/articles/turboquant-quantization/ ; https://qdrant.tech/documentation/search-tuning/when-your-collection-outgrows-ram/
- Storage/memory tiers: https://qdrant.tech/documentation/manage-data/storage/
- Payload index/filtering: https://qdrant.tech/documentation/manage-data/collections/ ; https://qdrant.tech/course/essentials/day-2/filterable-hnsw/ ; https://qdrant.tech/articles/filtered-vector-search-acorn/
- Hybrid/RRF/DBSF: https://qdrant.tech/documentation/search/hybrid-queries/ ; https://qdrant.tech/documentation/search-tuning/hybrid-search/ ; https://qdrant.tech/course/essentials/day-3/hybrid-search/
- Multivector/ColBERT: https://qdrant.tech/course/essentials/day-5/colbert-multivectors/ ; https://qdrant.tech/articles/late-interaction-models/
- BGE-M3: https://arxiv.org/html/2402.03216v3 ; https://huggingface.co/BAAI/bge-m3 ; https://bge-model.com/bge/bge_m3.html
- HyDE: https://www.elastic.co/search-labs/blog/hyde-semantic-search-elasticsearch ; https://docs.haystack.deepset.ai/docs/hypothetical-document-embeddings-hyde
- Rewriting: https://alhena.ai/blog/query-rewriting-before-retrieval-multi-turn-rag/ ; https://www.meilisearch.com/blog/query-rewrite-rag
- Chunking/parent-child: https://medium.com/data-science/advanced-rag-01-small-to-big-retrieval-172181b396d4 ; https://atlan.com/know/chunking-strategies-rag/
- Snapshots: https://qdrant.tech/documentation/snapshots/ ; https://qdrant.tech/documentation/tutorials-operations/create-snapshot/
- Caching: https://www.truefoundry.com/blog/semantic-caching-llm-gateway ; https://github.com/zilliztech/gptcache
- Eval: https://www.dataaihub.co/learn/retrieval-evaluation ; https://weaviate.io/blog/retrieval-evaluation-metrics ; https://docs.anyscale.com/rag/evaluation

# RAG + Data Platform — Master Plan (audit, research, remediation)

**Date:** 2026-10-25 · **Status:** complete & verified (2026-10-28)
**Supersedes:** `2026-10-24-data-engineering-end-to-end.md` (absorbs it verbatim in Phase 1–5)
**Extends:** `2026-10-24-scalability-fault-tolerance-data-engineering.md` (Phase 0 stays as prerequisites)

Scope: the corpus data plane **and** the retrieval features that consume it, end to end.
`source → extract → gate → chunk → enrich → embed → index → graph → publish → serve → feedback → lifecycle`

Two halves:
- **Part A** — every RAG feature that actually runs, with file:line evidence and a verdict per feature.
- **Part B** — what the literature and vendor docs say, and exactly where our implementation diverges from it.
- **Part C** — the plan, phased, with acceptance criteria and the artifacts each phase must create.

Decisions D1–D4 taken 2026-10-24 are locked (see §8) and are already reflected in the phases.

---

# Part A — RAG feature inventory (what we actually run)

Every row is evidence-checked against code. "Verdict" is one of **keep**, **tune** (right idea, needs
measurement or a small fix), **fix** (correctness gap), **retire**, **gap** (absent).

## A.1 Ingest side — what shapes what the retriever can find

| # | Capability | Where | Verdict | Why |
|---|---|---|---|---|
| 1 | Contextual chunk headers `[Source:\|Speaker:\|Topic:]` | `ingest/boundary_chunker.py:452-479` | **tune** | Header is *metadata*, not situating prose. Anthropic's Contextual Retrieval form prepends 50–100 tokens of chunk-specific context; we prepend field values. Cheap and useful, but the header cannot disambiguate "the company" → which company. Needs an eval before deciding whether to upgrade. |
| 2 | Boundary/sentence/verse-snapped chunking | `split_text_at_boundaries`, target 1200 chars, 1-sentence overlap | **keep** | Domain-correct for discourse transcripts. |
| 3 | Adaptive chunker | `ingest/adaptive_chunking.py` | **keep** | Auto-selects recursive vs semantic by intrinsic quality. |
| 4 | Semantic chunker | `ingest/semantic_chunker.py`, used by `ingest/contextual_reingest.py:1000` | **keep** | This is how the live corpus was built. Not dead code. |
| 5 | Recursive fallback | `RecursiveCharacterTextSplitter` at `pipeline.py:525`, `:2016`, `:3493` | **fix** | Three separate constructions; a fallback that silently becomes primary. Must go through the chunker contract. |
| 6 | Proposition chunking | `services/proposition_service.py`, `pipeline.py:2026`; `use_proposition_chunking="auto"` → active for docs ≥ `proposition_char_limit` | **retire** (D3) | Only path that writes LLM-authored text into the corpus as doctrine. Also the most expensive. |
| 7 | Book-ingest chunker | `ingest/book_ingest.py:85` | **fix** | Duplicates the boundary path with its own header handling. |
| 8 | RAPTOR 2-level tree | `ingest/raptor.py`; `raptor_cluster_size=8`, `kmeans\|gmm`, faithfulness floor 0.35 | **keep, fix lineage** | Summary nodes work; lineage is a count (`source_chunks: s["source_count"]`), so a summary cannot be traced to its sources. |
| 9 | Timing + speaker alignment | `chunk_start/chunk_end/clip/asr_method/align_method` (`pipeline.py:3310-3332`) | **keep** | Real provenance, correctly optional. |
| 10 | Chunk provenance class | `services/provenance.py` (`human_verbatim` vs `machine_summary`) | **keep** | Rare and valuable. |
| 11 | Quality gates | tiered `ingest/quality_gate.py` + chokepoint `services/qdrant/indexer.py:123` `select_clean` | **keep, fix telemetry** | Chokepoint design is right. Rejections are log-only and unpersisted. |
| 12 | Embedding | `BAAI/bge-m3`, dense 1024 + sparse lexical | **keep** | One model, both channels — avoids a second sparse model to pin and version. |
| 13 | Vector quantization | `scalar_int8`, quantile 0.99, oversampling 3.0 | **keep** | Proper recall-compensation config, not naive int8. |

## A.2 Serving side — what actually runs per query

| # | Capability | Where | Verdict | Why |
|---|---|---|---|---|
| 14 | Semantic router + intent prerouter | `use_semantic_router`, `semantic_router_top_k=3`, `rag/intent_prerouter.py` | **keep** | Note: DISTRESS threshold is a clinician-reviewed boundary (AGENTS.md X27) — do not tune. |
| 15 | Query-tier adaptive depth | `retrieval.py:1144-1151` → `chunk_limit` 5 / 10 / 20; `reranking.py:112-118` → rerank top_k 3/4/5/8 | **tune** | Tiering is sound; the *values* are unsourced. §B.4 says this is measurable, not guessable. |
| 16 | Follow-up resolution | `rag/resolve_followup.py` | **keep** | |
| 17 | Query decomposition → parallel sub-query search | `retrieval.py:968-990` | **keep** | Book Ch 14/16. |
| 18 | HyDE | `retrieval.py:994-1035` | **keep, measure** | Adds an LLM call before retrieval; must be eval-gated per tier. |
| 19 | Synonym + KG ontology expansion | `rag/kg_expansion.py`, `augment_query` | **keep** | Explicit hierarchy traversal, not LLM guesswork. |
| 20 | Hybrid dense+sparse fusion | `services/qdrant/searcher.py:271-418`; RRF default, DBSF opt-in; prefetch multipliers 3.0/3.0 | **tune** | Qdrant's own guidance: weights are a *measured* choice; without an eval set keep defaults. We have hand-set multipliers and no fusion eval. |
| 21 | Parent grouping | `qdrant_parent_grouping_enabled=True`, `group_by="parent_id"`, `group_size=2`; multi-key fallback `searcher.py:283-395` | **fix** | Grouping works, but `parent_id` is `uuid4()` at ingest, so groups are not stable across re-ingest. |
| 22 | Graph-linked prefetch channel | `graph_prefetch_enabled`, `graph_entity_ids` (`searcher.py:223-346`) | **keep** | Third candidate channel inside the same Qdrant query — no fan-out cost. |
| 23 | RAPTOR tree navigation ("Table of Contents" retrieval) | `rag/tree_navigator.py`, max_clusters=3, max_retries=1 | **keep** | Book Ch 14 hierarchical indices, implemented as reasoning over summaries. |
| 24 | Score-delta cutoffs | retrieval ratio 0.5; rerank ratio 0.35 (`retrieval.py:587`, `reranking.py:76-95`) | **keep** | Relative cut is better than an absolute score floor. |
| 25 | Dedup | newest-by-source (`retrieval.py:594`) + embedding cosine ≥ 0.85 (`:718`) | **keep** | |
| 26 | MMR diversity | `services/qdrant/mmr.py`, `reranking.py:219` | **keep** | This is the Dartboard Retrieval analogue (Book Ch 15). |
| 27 | Reranking stack | cross-encoder `BAAI/bge-reranker-v2-m3`, ONNX int8 `temsa/mmarco-…`, FlashRank, ColBERT MaxSim (**off**) | **keep, fix bypass** | Two production rerankers + a dormant third is acceptable; the bypass is not. |
| 28 | Rerank bypass on high confidence | `rerank_bypass_high_confidence_enabled=True`, `rerank_bypass_threshold=0.85` (`reranking.py:140-162`) | **fix** | Skips reranking exactly on the queries most likely to be served, so a wrong top-1 is never re-scored. Latency win bought with accuracy on the highest-traffic path. |
| 29 | CRAG grading + 3-way routing (local / web / blend) | `grade_documents`, `crag_skip_confidence=0.75`, `rewrite_query`, `regenerate_gate` | **keep** | Book Ch 20 implemented properly, including the rewrite loop. |
| 30 | Contextual compression | `rag/compression.py` (sentence-level), `rag/compressor.py` (LLMLingua optional), `rag_context_compression_top_k=5` | **tune** | Sentence extraction can delete the sentence that answers the question. Needs an ablation, not a default. |
| 31 | Context engineering + ordering | `context_engineer` node, section round-robin budget (`retrieval.py:304-313`) | **keep** | Explicitly avoids "spend the whole budget on the first section". |
| 32 | Citation extraction | `rag/nodes/citation_extractor.py` (n-gram Jaccard → `{doc_id, quote, span_in_answer, confidence}`) | **keep** | |
| 33 | Faithfulness verification | `rag/nodes/verification.py`, RAGAS-aligned metrics | **keep** | |
| 34 | Contradiction resolver | `rag/nodes/contradiction_resolver.py` | **keep** | ConflictRAG-style, authority-weighted. |
| 35 | Cross-teacher reasoning | `rag/nodes/cross_teacher_reasoning.py` | **keep** | |
| 36 | GraphRAG — atomic Memgraph traversal | `rag/nodes/atomic_graphrag.py` (1-hop weighted, 2-hop decay, single openCypher `CALL {}`) | **keep** | Correct pattern: one round trip, not an LLM/DB ping-pong. |
| 37 | LightRAG + ontology graph | `services/lightrag_service.py`, context cap 1500 chars | **keep** | |
| 38 | Agentic graph traversal (ReAct) | `rag/nodes/agentic_graph_traversal.py`, max 3 steps, comparative/tier3 only | **keep** | Bounded. |
| 39 | Deep research (recursive sufficiency) | `rag/nodes/deep_research.py`, `rag_deep_research_max_depth` | **keep** | |
| 40 | NL→Cypher | `rag/nodes/nl2cypher.py`, read-verb guard | **gap** | Explicitly a stub: no schema introspection, no query-plan validation, no cost cap. Book Ch 2 (RAG for structured data) is unimplemented in practice. |
| 41 | Caches | exact 24 h with version-bearing fingerprint; semantic 0.92 floor / 7 d; GPTCache 1000 | **keep** | 0.92 is documented as a correctness floor, not a knob. Preserve. |
| 42 | Guardrails & safety stages | input → circuit breaker → distress → off-topic → output | **keep** | Ordering invariant (AGENTS.md X38). |
| 43 | Translation with fail-open timeout | `translation_timeout_s=5`, `glue_stages.py:418` | **keep** | |
| 44 | Second-brain memory injection | `memory_stage.py`, `canonical_memories`, outbox | **keep** | |

## A.3 RAG gaps — capabilities the literature says matter that we do not have

| # | Gap | Evidence | Severity |
|---|---|---|---|
| **G1** | **No retrieval feedback loop.** Feedback is written to JSONL and never influences retrieval: `app/api/feedback.py` → `app/core/feedback_store.py`. No negative-example suppression, no per-source boost/deboost, no Qdrant relevance-feedback reuse. Book Ch 17 is entirely unimplemented. | `grep relevance_feedback` → 0 hits | P1 |
| **G2** | **Context Enrichment Window is wired for the general path and absent where it hurts.** Corrected 2026-10-27 (the first audit read this wrong): `services/qdrant/neighbor.py:25 get_neighbor_chunks()` **is** called from `rag/nodes/reranking.py:549` via `services/qdrant_service.py:464`, but only for the top-3 post-rerank docs of the general RAG path. The `enrich_context` graph node still does not use it, and the **first-person harness path — the one whose `fragment_without_antecedent` failures this feature exists to fix — has no enrichment at all**. Book Ch 8 is half-wired. | `grep get_neighbor_chunks` at `rag/nodes/reranking.py:549`; zero hits under `backend/services/first_person*` | P1 |
| **G3** | **No ranking metrics on the main RAG eval.** `evaluation/run_golden_eval.py` has faithfulness / context_precision / context_recall / answer_relevancy. MRR/MAP/NDCG exist only in `evaluation/fp_rank_metrics.py` (first-person). Book Ch 22 names MRR/MAP/NDCG as the retrieval metrics. | grep | P1 |
| **G4** | **Eval gate blind to ingest.** `.github/workflows/eval-gate.yml` paths exclude `backend/ingest/**`, `scripts/ingestion/**`, `backend/services/qdrant/**`. | workflow file | P1 |
| **G5** | **No explainable retrieval.** Citations answer "which chunk supported this sentence", not "why was this chunk retrieved": no per-doc channel (dense/sparse/graph/raptor), score, or query-variant provenance survives to the response. Book Ch 19. | no channel provenance in hit dicts | P2 |
| **G6** | **No per-query-class retrieval evaluation.** One aggregate score cannot tell you that a chunker change helped FAQ and broke comparative. | eval is aggregate | P1 |
| **G7** | **Multi-modal absent.** No image captioning path; only `thumbnail_url`. Book Ch 16. | — | P3 (out of scope) |

## A.4 The quiet risk in the feature list

Four separately-reasonable latency optimizations compound into a thin final context:

```
chunk_limit 5..20  →  score-delta cut (×0.5)  →  rerank top_k 3..8  →  compression top_k 5  →  sentence extraction
```

Anthropic's measurement (§B.2) found **20 chunks into the model beat 5 and 10**, and that reranking
only pays off when it re-scores a *broad* candidate set (their pipeline: ~150 candidates → 20). We
retrieve 24 by default, cut by score-delta, rerank to 3–8, then compress to 5. For a doctrine corpus
where the answering sentence may be one clause in a 1,200-char chunk, this is the highest-value
thing to *measure* — not to change blind. Hence RAG-4 below is an experiment, not an edit.

---

# Part B — Research synthesis (what the evidence actually says)

Sources: (a) local book skills, (b) vendor documentation, (c) the repo's own incident history.
Cited by content, not filename — the book chapter filenames in `.agent/skills` are unreliable
(an earlier audit found H1/title mismatches).

## B.1 Fusion retrieval — our default is right, our weights are unfounded

**Book (RAG Made Simple, Fusion Retrieval).** Dense and lexical each have a structural blind spot:
semantic search misses exact terms; keyword search misses paraphrase. Fuse rather than choose.
It also warns that raw scores live on different scales, so normalise or use ranks.

**Qdrant docs (authoritative, fetched 2026-10-25).**
- RRF counts *rank position*; Qdrant's default constant is **k = 2** (the classic paper uses 60) and
  weighting per-prefetch is available from **v1.17**.
- DBSF normalises each retriever's score distribution (mean ± 3σ) before summing — stateless, per query.
- Direct guidance, verbatim in substance: *"Weights should be provided… The most reliable way to set
  them is by testing on your data. With an eval set: split your eval queries in two, tune on the first
  half, measure on the second. Measuring on the same queries you tuned on inflates the result.
  Without an eval set: leave weights at the default (1.0, 1.0). Hand-tuned weights without measurement
  are unlikely to beat the default reliably."*
- Choice rule: eval set → weighted RRF; trust raw scores, no eval set → DBSF; neither → RRF.

**Applied to us.** `qdrant_fusion_strategy="rrf"` is the correct safe default. But
`qdrant_dense_prefetch_multiplier=3.0` / `qdrant_sparse_prefetch_multiplier=3.0` are *prefetch depths*,
which is a defensible latency/recall trade, while the effective equal weighting is fine. The real issue
is `ENABLE_COLBERT` unused and no fusion eval. Action: **RAG-4.1** builds a train/val split and reports
RRF vs DBSF vs weighted RRF on held-out queries. Do not change the default before that exists.

## B.2 Contextual retrieval — validated, but we implement the weaker variant

**Anthropic, "Introducing Contextual Retrieval" (2024, still the reference result).**
- Prepend **chunk-specific explanatory context** (50–100 tokens) to each chunk *before* embedding and
  *before* building the lexical index.
- Reported effect on top-20 retrieval **failure rate**: contextual embeddings −35 % (5.7 % → 3.7 %);
  contextual embeddings + contextual BM25 −49 % (→ 2.9 %); with reranking −67 % (→ 1.9 %).
- Also: *"adding generic document summaries to chunks… we saw very limited gains"* — a direct warning
  against stopping at metadata headers.
- Top-20 chunks into the model beat top-10 and top-5.
- Reranking stage was ~150 candidates → top 20.

**Applied to us.** `chunk_with_contextual_headers` prepends `[Source: … | Speaker: … | Topic: …]` — that
is the *generic metadata* variant Anthropic measured as low-gain, not the situating-prose variant. It is
still better than nothing and much cheaper. Decision: **measure before upgrading** (RAG-4.2). If we do
upgrade, the contextualizer must go through `find_artifact()` (ingestion invariant #1) because it is an
LLM writing text that reaches the index.

## B.3 Hierarchical indices — our lineage bug is the documented anti-pattern

**Book (Hierarchical Indices).** The pattern's data model is explicitly
`{summary_id: [chunk_id, chunk_id, …]}` — *metadata links* between summaries and chunks. The named
anti-pattern is flat/unlinked indexing.

**Applied to us.** `ingest/raptor.py:150` stores `source_chunks: s["source_count"]` — a **number**.
That is the book's anti-pattern with extra steps: the summary exists, the link does not. Consequence:
when the faithfulness gate rejects a summary we cannot name the chunks it summarised, and when a chunk
is updated we cannot invalidate the summary that contains it. **DE-2.1** fixes this.

## B.4 Corrective RAG — implemented, and better than the book's sketch

Book Ch 20 gives a relevance gate with three-way routing (>0.7 local, <0.3 web, else blend). We have that
plus `crag_skip_confidence=0.75` and a bounded rewrite loop. No change recommended; it is one of the
strongest parts of the system.

## B.5 Reranking — right architecture, one dangerous shortcut

**Book (Reranking).** Two-stage: broad bi-encoder recall, then cross-encoder precision. Explicit
anti-pattern: using a bi-encoder as the reranker.

**Applied to us.** We use cross-encoders correctly, with FlashRank as the fast path and ColBERT MaxSim
dormant. The problem is `rerank_bypass_high_confidence_enabled` at 0.85: it skips the precision stage
precisely when the first-stage score is high — i.e. when the system is most confident and most likely to
answer without further checking. A high bi-encoder score is *not* evidence of correctness; book Ch 13
exists because that correlation is weak. **RAG-4.3** measures whether the bypass is buying latency at a
measurable accuracy cost; default action if unmeasured is to disable it in `IS_PRODUCTION`.

## B.6 Evaluation — we measure generation, not retrieval

**Book (RAG Evaluation).** Evaluate *each stage*; name Context Precision/Recall, MRR, MAP, NDCG. Two
stated anti-patterns: "ignoring intermediate failures" and "using binary metrics exclusively".

**Applied to us.** Faithfulness / context precision / context recall / answer relevancy are real and
thresholded (0.88 / 0.72 / 0.72 / 0.80). But there is **no MRR, MAP, or NDCG anywhere on the main RAG
path** (only `fp_rank_metrics.py` for the first-person collection), and **no per-query-class breakdown**.
So a chunker, fusion, or rerank change has no instrument that can see it. **DE-5 + RAG-4** fix this, and
it is the gate that makes every other tuning task in this plan safe.

## B.7 What the books say we should NOT do

Recording these as explicit non-goals, because each is a tempting scope creep:

- **Don't fine-tune before fixing retrieval.** Every RAG source here ranks corpus quality above model
  adaptation; a contaminated corpus teaches a fine-tune the same contamination.
- **Don't add a second vector store / migration "for scale"** before the collection is governable
  (DE-0), reindexable (DE-1), and measured (DE-5).
- **Don't hand-tune fusion weights or context depth without a held-out split** — Qdrant states the
  failure mode explicitly (inflated results from tuning on the measurement set).
- **Don't use generic summaries as a substitute for contextual chunk prefixing** (Anthropic measured
  it as low-gain).
- **Don't adopt a heavier graph layer** until the existing Memgraph/LightRAG path has lineage (DE-2.1)
  and drift detection (DE-2.3).

---

# Part C — Findings roll-up (P0/P1/P2)

Everything below is evidence-backed and already appears in the two earlier plan files; the RAG items are
new. This is the single list the phases work down.

**P0 — corpus correctness / governance**
1. Release registry constructed, never used (`pipeline.py:516`; only `admin.py:1920` calls `register_source`).
2. Serving never filters by release (no `release_version` in `rag/`, `services/qdrant/`, `source_policy.py`).
3. Publication enforcement off (`corpus_publication_enforcement_enabled=False`, no env override).
4. Rights defaulted `licensed` with no register lookup (`indexer.py:255`).
5. Chokepoint rejections unpersisted and uncounted (`indexer.py:123` vs `quality_gate.py:829`).

**P1 — cannot reindex or operate safely**
6. `parent_id = uuid4()` (`pipeline.py:2037`, `:3500`) — grouping unstable across re-ingest.
7. `chunker_version` is a boolean lie (`indexer.py:276-282`); five chunkers collide on the label.
8. `_PAYLOAD_INDEXES` missing `embedding_model`, `embedding_dimension`, `chunker_version`, `provenance`,
   `release_version` (`client.py:57-78`) — stale-encoder queries are full scans.
9. RAPTOR lineage is a count (`raptor.py:150`).
10. `ingest_jobs` has no `updated_at`/heartbeat/attempt; no source catalog.
11. Stale-point deletes swallowed (`indexer.py:204`).
12. `eval-gate.yml` blind to `backend/ingest/**`, `scripts/ingestion/**`.
13. **G1** no retrieval feedback loop.
14. **G2** context enrichment window dead code.
15. **G3/G6** no ranking metrics, no per-query-class eval.

**P2 — hygiene / observability**
16. No data SLI dashboard; no lineage-completeness metric; no data runbooks.
17. Qdrant optimizer/segment/snapshot health only visible to audit scripts.
18. No explainable-retrieval provenance (G5).
19. NL→Cypher remains a stub (G6/Ch 2).

---

# Part D — Target architecture

```
                    ┌────────────── control plane (Supabase) ──────────────┐
                    │ corpus_sources  (freshness, checksum, status)        │  ← DE-3.1
                    │ source_releases (active/superseded, per source)      │  ← DE-0.1 (now written by ingest)
                    │ ingest_jobs     (heartbeat, attempt, updated_at)     │  ← DE-3.1
                    │ corpus_gate_rejections (reason, span, layer)         │  ← DE-0.5
                    │ publication manifest (enforced)                      │  ← DE-0.4
                    └──────────────────────────────────────────────────────┘
                                        │
source ─► extract ─► gate ─► chunk ─► enrich ─► embed ─► write ─► publish ─► serve ─► feedback
             │        │      │                                    │          │         │
             │        │      └── Chunker protocol (1 call site)   │          │         └─► RAG-1
             │        └───────── rejection ledger                 │          ├─ release filter (DE-0.3)
             └────────── ASR/align provenance                     │          ├─ enrichment window (RAG-2)
                                                                  │          ├─ channel provenance (RAG-3)
                                    corpus_vN + alias swap ────────┘          └─ ranking metrics (DE-5)
```

Corpus contract after Phase 3 (single source of truth for every payload field):

| Field | Meaning | Today | Target |
|---|---|---|---|
| `point_id` | `uuid5(source_url, chunk_index, raptor_level)` | ✅ | keep |
| `parent_id` | logical parent segment | ❌ `uuid4()` | `uuid5(source_url, parent_index)`, new writes only (D4) |
| `parent_id_scheme` | `deterministic_v1` \| `legacy` | ❌ | required |
| `chunker_version` | actual chunker + params | ❌ boolean | `boundary_v1:1200/1` etc.; legacy = `unknown_legacy` |
| `embedding_model` / `embedding_dimension` | encoder provenance | ✅ written, ❌ unindexed | indexed |
| `source_release_version` / `content_checksum` | governed release | ❌ | written + indexed |
| `rights_status` | from register | ❌ defaulted `licensed` | derived; miss → `unverified` (D2) |
| `gate_verdict` | accept/reject + reason | ❌ | recorded per candidate |
| `lineage` | summary → source point IDs | ❌ count | ID list + `parent_summary_id` back-link |
| `ingested_at` | write time | ❌ | always |
| `asr_method` / `align_method` | extraction provenance | ✅ | keep |
| `retrieval_channels` | which channel found this doc | ❌ | populated at read time (not stored) |

---

# Part E — The plan

Estimates assume one engineer. Phase 0 is a hard prerequisite for Phases 4, 7.

## Phase 0 — Prerequisites (from the infra plan) · ~2 days

| ID | Task | Acceptance |
|---|---|---|
| P0.1 | Add Celery **beat** service to `docker-compose.yml` and `docker-compose.prod.yml` (absent today — every scheduled retention/audit task is decorative). | `beat` container runs; one schedule fires and is observable in logs. |
| P0.2 | Ingest job **sweeper**: mark jobs `failed` when heartbeat older than N minutes. Depends on DE-3.1's heartbeat column, so land the column here. | a killed worker's job flips to `failed` within N minutes, not never. |
| P0.3 | Stream trim safety (from infra plan) before ingest backpressure work. | `xadd(maxlen)` behaviour documented + tested. |

## Phase 1 — Governance: register → stamp → filter → enforce (P0) · ~5 days

| ID | Task | Acceptance | Source |
|---|---|---|---|
| DE-0.1 | Wire `SourceReleaseRegistry` into `IngestionPipeline`. Register on ingest start with `content_checksum` = sha256 of normalized source text; `source_identity` stable across refetch. Fail closed only when enforcement is on. | every successful ingest creates exactly one release row; unchanged checksum → no-op; changed content → version N+1 | DDIA ch11; LLMs in Production ch4 |
| DE-0.2 | Stamp `source_release_version` + `content_checksum` on every point; add both to `_PAYLOAD_INDEXES`. | point → release traceable without a join | DDIA ch5; DB Internals ch3 |
| DE-0.3 | Read-time release filter (status=active) + `release_version` in the retrieval cache fingerprint. | superseding a release removes it from answers with no deletion; cache never replays superseded content | DDIA ch11; RAG Made Simple ch3 |
| DE-0.4 | Ingest writes the publication manifest; enable `corpus_publication_enforcement_enabled` in staging, then prod. | cold start refuses to serve a collection with no valid manifest | DDIA ch12; DDS ch17 |
| DE-0.5 | `corpus_gate_rejections` table (source_url, chunk_index, reason, matched_span, gate_layer, created_at) written from the Qdrant chokepoint; increment `INGEST_QUALITY_GATE_REJECTIONS_TOTAL{layer="chokepoint"}`. | rejection rate queryable per source and reason; no rejection exists only as a log line | AI Engineering ch10 |
| DE-4.4 | Replace the `licensed` default with a register lookup; miss → `unverified`, excluded by the serving filter (D2). | zero points whose rights field was defaulted; `unverified` count is queryable | LLMs in Production ch4 |

> DE-0.1→0.2→0.3 are one story. Shipping three of four leaves a strictly harder-to-debug state.

## Phase 2 — Source catalog & freshness (P1) · ~2 days

| ID | Task | Acceptance |
|---|---|---|
| DE-3.1 | `corpus_sources` table: `source_identity, source_url, last_ingested_at, last_checksum, active_release_id, status`. Written by every ingest. | "which sources are stale / never ingested / stuck" is one query |
| DE-3.2 | Freshness SLI: `corpus_source_age_days`, `corpus_stale_sources_total`; alert on age > policy (setting, not a doc line). | dashboard + firing alert |
| DE-3.3 | Extraction guard: reject audio whose declared duration cannot be supported by its PCM (the 86-byte-stub class, AGENTS.md X21). | stub fails fast, classified, before ASR |

## Phase 3 — Reindexability (P1) · ~4 days

| ID | Task | Acceptance |
|---|---|---|
| DE-1.1 | One `Chunker` protocol → `(text, parent_index, chunker_version, spans)`. Adapt boundary, adaptive, semantic, recursive; **delete proposition chunking and its call site** (D3); fold `book_ingest` onto the same path. | one construction site in the ingest path; `proposition_service` has zero non-test importers |
| DE-1.2 | Deterministic `parent_id = uuid5(source_url, parent_index)` for **new writes only**; `parent_id_scheme` on every point (D4). No backfill script. | re-ingest twice → identical `parent_id` set; legacy share monotonically decreases and is tracked |
| DE-1.3 | Index `embedding_model`, `embedding_dimension`, `chunker_version`, `provenance`, `source_release_version`. Legacy points carry `chunker_version="unknown_legacy"` — never a guessed value. | stale-encoder count returns < 1 s |
| DE-1.4 | Orphan reconciliation: diff expected deterministic ID set vs stored per source; delete with retries + metric. | seeded orphan removed; job idempotent and bounded |
| DE-1.5 | Reindex as a batch job: plan → build `corpus_vN` → validate (count, fingerprint, sample eval) → alias swap. Never mutate the serving collection in place (D1). | reindex run, validated, rolled back without touching the live alias |

## Phase 4 — Lineage, anti-entropy, provenance (P1) · ~3 days

| ID | Task | Acceptance |
|---|---|---|
| DE-2.1 | RAPTOR summaries store `source_point_ids` (bounded) instead of a count; source chunks get `parent_summary_id`. | a rejected summary names every chunk it summarised in one query (closes the Ch 14 anti-pattern) |
| DE-2.2 | Per-candidate `gate_verdict` at the chokepoint (accept reason / reject reason). | every written point has a verdict; every reject has a reason |
| DE-2.3 | Scheduled anti-entropy Qdrant ↔ Supabase ↔ Memgraph: drift counts, repair mode, report artifact; extend `scripts/ops/cross_store_audit.py`. | 1 % seeded drift detected and repaired; report reproducible |
| DE-2.4 | Admin provenance API: "why is this chunk here / which release / which encoder / which gate". | answered from stored fields, no log grep |

## Phase 5 — Evaluation that can see retrieval (P1) · ~3 days

| ID | Task | Acceptance | Source |
|---|---|---|---|
| DE-5.1 | `eval-gate.yml` triggers add `backend/ingest/**`, `scripts/ingestion/**`, `backend/services/qdrant/**`. | a chunker-only PR runs the eval gate | RAG Made Simple ch22 |
| DE-5.2 | Data-shape assertions in the gate: chunk-length distribution, duplicate rate, artifact rate, % sources with timing/speaker coverage. | a chunker that halves mean length fails before merge | AI Engineering ch8 |
| DE-5.3 | **Retrieval ranking metrics**: MRR, MAP@k, NDCG@k against the gold set, added to `run_golden_eval.py`; reuse `evaluation/fp_rank_metrics.py` logic. | retrieval quality is a first-class number, not inferred from faithfulness | RAG Made Simple ch22 (G3) |
| DE-5.4 | **Per-query-class breakdown** (FAQ / comparative / multi-hop / distress-adjacent / Indic-language) for every metric. | a regression in one class cannot hide in the aggregate (G6) | Ch 22 anti-pattern |
| DE-5.5 | Release artifact: every corpus release carries an eval JSON (retrieval metrics + faithfulness + citation correctness + abstention). Activation blocked without it. | rollback decision is data-driven | Building LLMs for Production |

## Phase 6 — RAG feature closure (P1) · ~5 days

| ID | Task | Acceptance | Source |
|---|---|---|---|
| RAG-4.1 | **Fusion experiment.** Split gold queries train/val. Report RRF (k default), DBSF, weighted RRF on val. Ship only a measured winner; otherwise keep defaults. | a report artifact with per-class MRR@10 and NDCG@10 for each strategy | Qdrant fusion docs; B.1 |
| RAG-4.2 | **Contextual-header ablation.** Compare: current metadata header vs no header vs LLM situating-prose prefix (gated by `find_artifact`). | held-out retrieval-failure-rate delta per variant; upgrade only if it beats noise | Anthropic contextual retrieval; B.2 |
| RAG-4.3 | **Rerank-depth / bypass experiment.** Measure `rerank_bypass` on/off and candidate depth (24 vs 48) vs final context size (3–8 vs 10 vs 20). | latency and faithfulness delta per config; bypass disabled in prod unless it wins | Anthropic (150→20); B.5 |
| RAG-4.4 | **Compression ablation.** `rag_context_compression_top_k` 5 vs 10 vs off, with answer-faithfulness and citation-span survival. | a config decision backed by numbers, not a default | RAG Made Simple ch10 |
| RAG-1 | **Retrieval feedback loop.** Persist feedback (already captured) with query-relevant chunk IDs; use negative feedback to suppress sources for near-duplicate queries and positive feedback to seed relevance. Bounded, TTL'd, reversible flag. | a negatively-rated source stops surfacing for similar queries within TTL; no feedback write can corrupt the corpus | RAG Made Simple ch17 (G1) |
| RAG-2 | **Wire the context enrichment window.** Two call sites, two different indexes: (a) the general path uses `neighbor.py:get_neighbor_chunks` in `enrich_context` for the top-N reranked chunks; (b) the first-person harness path must widen the **parent/child** context via `FirstPersonContextStore.enrich_to_parent_window` — `get_neighbor_chunks` keys on `source_url + chunk_index` and cannot see `fp-context-v1` `parent_unit_id` spans. Both bounded and feature-flagged off by default until measured. | retrieved chunk with a truncated answer becomes answerable; budget respected | RAG Made Simple ch8 (G2) |
| RAG-3 | **Channel provenance for explainability.** Hit dicts carry `retrieval_channels` (dense/sparse/graph/raptor), per-channel rank, and pre/post-rerank scores; exposed to the admin provenance API, never the public SSE stream. | one query answers "why was this retrieved" | RAG Made Simple ch19 (G5) |

## Phase 7 — Lifecycle, observability, docs · ~4 days

| ID | Task | Acceptance |
|---|---|---|
| DE-4.1 | Retention end-to-end test across telemetry, audit files, staging queue, memory tables, and the new `corpus_gate_rejections`. | counts asserted before/after per table |
| DE-4.2 | Qdrant optimizer/segment/deleted-point exports + alert on `optimizer_status != ok`. | alert fires on a stuck optimizer |
| DE-4.3 | Snapshot age alert + backup/restore drill; documented RPO/RTO. | drill restores to scratch and verifies counts |
| DE-6.1 | Data SLI dashboard: throughput, chunks/source, rejection rate by reason, dedupe rate, freshness, drift, stale-encoder count, snapshot age, optimizer status, retrieval ranking metrics by class. | every task above has a panel |
| DE-6.2 | Lineage completeness metric: % points with release, encoder, chunker, gate verdict, ASR method. | trends to 100 % after Phases 1/3/4 |
| DE-6.3 | Runbooks, each with a dry-run: reindex, roll back a release, restore a snapshot, resolve drift, purge a source, disable a retrieval feature flag. | each executed once in staging and timed |
| DE-7 | ADRs (publication model, chunking contract, parent-ID scheme, rights source of truth, reindex/alias). `lessons.md` entry per P1 finding, each naming its pinning test. Repo skill `corpus-data-contract`. AGENTS.md invariants updated. | future sessions do not re-derive the contract |

## Phase 8 — Repository agent-context hygiene (P3) · ~1 day

Not data-plane work, but it corrupts every future session's inputs: an agent told to consult the books
currently reads duplicates, dead links, and mis-titled chapters.

| ID | Task | Acceptance |
|---|---|---|
| SK.1 | Deduplicate `.agent/skills`: 132 dirs / 108 unique, **24 byte-identical pairs** (`agent-book-*` vs `agents-book-*`, ~12 MB). Delete one of each pair. | `find … -exec md5` reports zero duplicate skill trees |
| SK.2 | Repair the **7 broken stubs** (`senior-*`, `code-reviewer`) whose `SKILL.md` points at a non-existent `../../../engineering-team/`. Vendor the missing content or delete the stub. | every `SKILL.md` resolves its referenced paths |
| SK.3 | Repair poisoned chapter filenames/H1 mismatches (`designing-data-intensive-apps-2e/ch07-…` H1 is "Data Models and Query Languages"; `database-internals/ch01-…` H1 is junk). Regenerate the chapter index from content, not filename. | index title == H1 for all 924 chapter files |

---

# Part F — Sequencing

```
P0 prerequisites ──┬─► Phase 1 governance ──┬─► Phase 3 reindex ──► Phase 4 lineage ──┐
                   │                       │                                        ├─► Phase 7
                   └─► Phase 2 catalog ────┘                                        │
                                                     Phase 5 eval ───────────────────┘
                                                          │
                                                          └─► Phase 6 RAG experiments (needs Phase 5's instrument)
```

Hard rules:
- **Phase 5 before Phase 6.** Every RAG item in Phase 6 is an experiment whose verdict requires ranking
  metrics and per-class breakdowns. Tuning before measuring is the failure mode Qdrant names explicitly.
- **Phase 1 before Phase 3.** A reindex into `corpus_vN` is only meaningful if points carry a release.
- **Phase 2 can run parallel to Phase 1** (different tables, different code paths).
- **Phase 6's RAG-1/RAG-2/RAG-3 ship behind flags defaulted off.** They change serving behaviour; they
  are not allowed to change it silently.

---

# Part G — Verification

```bash
# per-phase
cd backend && pytest tests/test_ingest_*.py tests/test_qdrant_*.py tests/test_*lineage*.py -x -q

# contract tests this plan must create
pytest tests/test_corpus_data_contract.py -q      # DE-0.2 / 1.2 / 2.2 payload + ID determinism
pytest tests/test_release_lifecycle.py -q         # DE-0.1 / 0.3 / 0.4 register→filter→enforce
pytest tests/test_gate_rejection_ledger.py -q     # DE-0.5
pytest tests/test_antientropy.py -q               # DE-1.4 / 2.3
pytest tests/test_retrieval_metrics.py -q         # DE-5.3 / 5.4 ranking metrics + per-class
pytest tests/test_feedback_loop.py -q             # RAG-1 suppression is bounded and reversible
pytest tests/test_enrichment_window.py -q         # RAG-2 budget + truncation recovery

# repo gates
git diff --check && ruff check backend
docker compose -f docker-compose.yml config -q
```

Evidence rule (verification-before-completion): every claim in a PR body carries its command and output.
No "should now work". For Phase 6, the evidence is an artifact with numbers, not a code diff.

---

# Part H — Risks

| Risk | Mitigation |
|---|---|
| Release filtering shrinks the result set | run with enforcement off, diff answer sets on the gold set, then enable |
| Chunker unification changes boundaries → index churn | build into `corpus_vN`, alias swap, compare eval artifacts |
| Retiring proposition chunking changes chunks for affected long documents | count affected sources first, add them to the reingest-convergence set (D4) |
| Mixed `parent_id_scheme` during convergence | scheme is a filterable field; verify grouping on a fixed query set; track legacy share |
| `corpus_gate_rejections` grows unbounded | retention policy from day one (DE-4.1) |
| Fusion/rerank experiments produce "wins" that don't replicate | train/val split; report per-class; require the winner to survive a second seed |
| Feedback loop amplifies a small angry sample | bounded TTL, minimum-sample threshold, reversible flag, never writes to Qdrant |
| Enabling publication enforcement blocks startup | staged rollout with a rollback flag per step |
| Legacy `unknown_legacy` chunker bucket is read as an anomaly | dashboards bucket it explicitly; it is the honest value, not an error |

---

# Part I — Decisions

## Taken 2026-10-24 (locked)

| # | Decision | Choice |
|---|---|---|
| D1 | Publication model | Both, staged: read-time release filter first, alias/collection swap with the reindex path |
| D2 | Rights authority | Annotate `unverified`; never default `licensed`; excluded by the serving filter |
| D3 | Proposition chunking | Retire (delete service + call site in DE-1.1) |
| D4 | Backfill | Fix forward + converge on next reingest; no backfill script; legacy keeps `unknown_legacy` |

## Adopted defaults 2026-10-25 (overridable — say the word and I flip one)

| # | Question | Adopted | Effect |
|---|---|---|---|
| D5 | Rerank bypass at 0.85 — keep? | **Disable when `IS_PRODUCTION`** until RAG-4.3 measures it | ~+40–80 ms on high-confidence queries; no unreranked answers on the highest-traffic path |
| D6 | Retrieval feedback loop (RAG-1) — scope? | **Suppression-only**, TTL'd, flag off by default | No positive-boost path until measured; a feedback write can never reach Qdrant |
| D7 | Contextual header upgrade (RAG-4.2) — budget? | **Measure first.** No LLM contextualization spend until the ablation wins | Reingest cost only if justified by held-out numbers |
| D8 | NL→Cypher (G6 / book Ch 2) — build or remove? | **Remove the stub** (`rag/nodes/nl2cypher.py`) if no owner claims it in Phase 6 | Dead code removed; structured-data questions keep abstaining honestly rather than half-answering |

---

# Part J — Explicit non-goals

Multi-modal captioning (Ch 16), fine-tuning, a second vector store, a heavier graph engine, DSPy
activation, ONNX query-embedding migration, and Neo4j schema changes. Each requires its own held-out
evidence and is blocked until Phases 1–5 close.

---

# Part K — Artifacts this plan must create

Nothing below exists today. This is the build manifest — if a phase is "done" but its artifacts are
absent, it is not done.

## K.1 Migrations (Supabase, append-only numbered)

| File | Contents | Phase |
|---|---|---|
| `…_corpus_gate_rejections.sql` | `corpus_gate_rejections(id, source_url, chunk_index, gate_layer, reason, matched_span, point_id, created_at)`; index on `(source_url, created_at)` and `(reason)`; RLS admin-only; retention note in the REVERT header | 1 |
| `…_corpus_sources.sql` | `corpus_sources(source_identity PK, source_url, corpus_id, last_ingested_at, last_checksum, active_release_id, status, created_at, updated_at)`; index on `(status, last_ingested_at)` | 2 |
| `…_ingest_jobs_lifecycle.sql` | `ALTER TABLE ingest_jobs ADD updated_at, heartbeat_at, attempt INT DEFAULT 0, source_identity TEXT`; index on `(status, heartbeat_at)` | 0/2 |
| `…_retrieval_feedback_signals.sql` | `retrieval_feedback_signals(id, query_hash, source_url, point_id, signal ('positive'\|'negative'), created_at, expires_at)`; index on `(source_url, expires_at)`; **no text stored** | 6 |
| `…_corpus_release_point_indexes.sql` | any SQL-side mirror of release state needed by dashboards (read-only views) | 1 |

Every migration carries the repo's REVERT comment header convention and a rollback line.

## K.2 Config flags (all default to the safe value)

| Flag | Default | Introduced | Purpose |
|---|---|---|---|
| `corpus_publication_enforcement_enabled` | `False` → `True` in Phase 7 | exists (`config.py:1433`) | DE-0.4 |
| `index_contract_enforcement_enabled` | `False` → `True` after eval parity | exists | DE-0.4 sibling |
| `release_filter_mode` | `"off"` → `"shadow"` → `"enforce"` | **new** | DE-0.3. Shadow logs what *would* be excluded without changing results — the only safe way to roll this out |
| `chunker_contract_strict` | `False` | **new** | DE-1.1: reject writes whose `chunker_version` is unresolvable |
| `orphan_reconciliation_enabled` | `False` | **new** | DE-1.4 |
| `retrieval_feedback_enabled` | `False` | **new** | RAG-1 (D6) |
| `retrieval_feedback_ttl_days` | `30` | **new** | RAG-1 |
| `retrieval_feedback_min_samples` | `3` | **new** | RAG-1 — no suppression from one angry click |
| `enrichment_window_enabled` | `False` | **new** | RAG-2 |
| `enrichment_window_size` | `1` | **new** | RAG-2 (chunks before/after) |
| `retrieval_channel_provenance_enabled` | `False` | **new** | RAG-3 |
| `rerank_bypass_high_confidence_enabled` | `False` when `IS_PRODUCTION` (D5) | exists | RAG-4.3 |
| `use_proposition_chunking` | **removed** | exists | D3 |
| `chunker_version` (per-point) | `boundary_v1:1200/1`, legacy `unknown_legacy` | **new** | DE-1.3 |

## K.3 Metrics

| Metric | Type | Labels | Phase |
|---|---|---|---|
| `INGEST_QUALITY_GATE_REJECTIONS_TOTAL` | counter | `reason`, `tier`, **`layer`** (new value `chokepoint`) | 1 |
| `CORPUS_GATE_REJECTIONS_PERSISTED_TOTAL` | counter | — | 1 |
| `CORPUS_SOURCE_AGE_DAYS` | gauge | `corpus_id` | 2 |
| `CORPUS_STALE_SOURCES_TOTAL` | gauge | `corpus_id` | 2 |
| `CORPUS_ORPHAN_POINTS_TOTAL` | gauge | `collection` | 3 |
| `CORPUS_DRIFT_POINTS_TOTAL` | gauge | `store_pair` | 4 |
| `CORPUS_LINEAGE_COMPLETENESS_RATIO` | gauge | `field` | 7 |
| `QDRANT_OPTIMIZER_STATUS` | gauge | `collection` | 7 |
| `QDRANT_DELETED_POINTS_RATIO` | gauge | `collection` | 7 |
| `QDRANT_SNAPSHOT_AGE_HOURS` | gauge | `collection` | 7 |
| `RETRIEVAL_FEEDBACK_SUPPRESSIONS_TOTAL` | counter | — | 6 |
| `ENRICHMENT_WINDOW_EXPANSIONS_TOTAL` | counter | `outcome` | 6 |
| `RETRIEVAL_CHANNEL_HITS_TOTAL` | counter | `channel` | 6 |

Eval-time ranking metrics (artifacts, not runtime counters): `mrr`, `map@k`, `ndcg@k`, per query class.

## K.4 Tests (the pins)

| Test file | Pins |
|---|---|
| `tests/test_corpus_data_contract.py` | every payload field in Part D; deterministic `parent_id`/`point_id`; `unknown_legacy` never guessed |
| `tests/test_release_lifecycle.py` | register → shadow → enforce; supersede removes from answers; cache fingerprint carries `release_version` |
| `tests/test_gate_rejection_ledger.py` | chokepoint reject writes a row **and** increments `layer="chokepoint"` |
| `tests/test_source_catalog.py` | every ingest upserts `corpus_sources`; heartbeat advances; stuck job swept |
| `tests/test_antientropy.py` | seeded 1 % drift detected; repair idempotent; report reproducible |
| `tests/test_retrieval_metrics.py` | MRR/MAP/NDCG computed on a fixture ranking; per-class breakdown present |
| `tests/test_feedback_loop.py` | suppression bounded by min-samples + TTL; flag off = no behaviour change; never writes Qdrant |
| `tests/test_enrichment_window.py` | window respects token budget; truncated-answer fixture becomes answerable; flag off = identical output |
| `tests/test_chunker_contract.py` | one construction site; every implementation returns a real `chunker_version` |

## K.5 Scripts (`scripts/ops/`, container-visible per `L-OPS-MOUNT-1`)

| Script | Purpose | Dry-run |
|---|---|---|
| `reindex_corpus.py` | plan → build `corpus_vN` → validate → alias swap | `--plan-only` |
| `reconcile_orphans.py` | diff expected vs stored point IDs per source; delete with retries | `--dry-run` |
| `cross_store_audit.py` (extend) | Qdrant ↔ Supabase ↔ Memgraph drift report | `--report-only` |
| `audit_lineage_completeness.py` | % points per lineage field; emits the gauge | read-only |
| `measure_rag_variants.py` | Phase 6 experiment harness: runs a config matrix over train/val, emits `evals/reports/<date>-<variant>.json` | read-only |
| `rollback_release.py` | supersede/restore a source release | `--dry-run` |
| `purge_source.py` | remove a source across Qdrant + Memgraph + catalog, with a manifest | `--dry-run` |
| `print_publication_manifest.py` | dump the manifest the ingest wrote | read-only |

## K.6 Docs and skills

- `docs/adr/0001-publication-model.md` — release table vs alias swap (D1), with the shadow-mode plan.
- `docs/adr/0002-chunking-contract.md` — the `Chunker` protocol, `chunker_version` grammar, why
  proposition chunking was retired (D3).
- `docs/adr/0003-parent-id-scheme.md` — `deterministic_v1` vs `legacy`, no-backfill rationale (D4).
- `docs/adr/0004-rights-source-of-truth.md` — register → `unverified`, never a `licensed` default (D2).
- `docs/adr/0005-ranking-metrics.md` — why MRR/MAP/NDCG + per-class became a release gate.
- `docs/runbooks/` — reindex, rollback-release, restore-snapshot, resolve-drift, purge-source,
  disable-retrieval-feature. Each with a dry-run command and a measured duration.
- `.agent/skills/corpus-data-contract/SKILL.md` — the Part D table as a skill, so future sessions do not
  re-derive it.
- `lessons.md` — one entry per P0/P1, each naming its pinning test.
- `AGENTS.md` — add invariants: register→stamp→filter→enforce; `chunker_version` must name the real
  chunker; rejections must be persisted; `unknown_legacy` is honest, not an error.

---

# Part L — Execution DAG and effort

```
P0.1 beat ──────────────┐
P0.2 job lifecycle ─────┤
P0.3 stream trim ───────┘
                        │
        ┌───────────────┴───────────────┐
        ▼                               ▼
   Phase 1 (DE-0.1→0.2→0.3→0.5→4.4)   Phase 2 (DE-3.1→3.2→3.3)
        │        then DE-0.4            │
        └───────────────┬───────────────┘
                        ▼
                  Phase 3 (DE-1.1→1.3→1.2→1.4→1.5)
                        ▼
                  Phase 4 (DE-2.1→2.2→2.3→2.4)
                        ▼
                  Phase 5 (DE-5.1→5.3→5.4→5.2→5.5)
                        ▼
                  Phase 6 (RAG-4.1…4.4, then RAG-1/2/3)
                        ▼
                  Phase 7 (DE-4.x, DE-6.x, DE-7)
                        ▼
                  Phase 8 (SK.1→SK.2→SK.3)   ← can run any time, parallel
```

| Phase | Scope | Effort | Blocking prerequisite |
|---|---|---|---|
| 0 | Prerequisites | 2 d | — |
| 1 | Governance | 5 d | Phase 0 (job lifecycle column) |
| 2 | Source catalog & freshness | 2 d | Phase 0 |
| 3 | Reindexability | 4 d | Phase 1 |
| 4 | Lineage / anti-entropy | 3 d | Phase 3 |
| 5 | Evaluation that sees retrieval | 3 d | Phase 3 |
| 6 | RAG feature closure | 5 d | Phase 5 |
| 7 | Lifecycle / observability / docs | 4 d | Phases 4–6 |
| 8 | Agent-context hygiene | 1 d | none (parallel) |
| **Total** | | **29 d** | |

Critical path: `P0 → 1 → 3 → 4 → 5 → 6 → 7` = 26 d. Phase 2 and Phase 8 ride alongside.

---

# Part M — Rollout and rollback matrix

Every behaviour-changing item ships behind a flag whose default preserves today's behaviour.

| Change | Flag | Default | Rollout | Rollback |
|---|---|---|---|---|
| Release filter at read time | `release_filter_mode` | `off` | `off → shadow` (log-only diff on gold set) → `enforce` | set back to `shadow`; zero data change |
| Publication enforcement | `corpus_publication_enforcement_enabled` | `False` | staging `True` → prod `True` after manifest written | `False`; startup no longer refuses |
| Rights `unverified` | (code) | annotate | ship with filter `off`; counts visible first | reverting restores the old default — do not, it is the bug |
| Deterministic `parent_id` | (code, new points only) | on for new writes | coexist via `parent_id_scheme` | old points untouched; grouping falls back to legacy scheme |
| Chunker contract | `chunker_contract_strict` | `False` | `False` → `True` after all writers emit a real version | `False` downgrades unknown versions to `unknown_legacy` |
| Orphan reconciliation | `orphan_reconciliation_enabled` | `False` | dry-run report → enable delete | `False` stops deletion immediately |
| Feedback loop | `retrieval_feedback_enabled` | `False` | shadow (log would-suppress) → suppress | `False`; TTL means signals decay anyway |
| Enrichment window | `enrichment_window_enabled` | `False` | measure → enable per tier | `False` |
| Channel provenance | `retrieval_channel_provenance_enabled` | `False` | enable (admin-only output) | `False` |
| Rerank bypass | `rerank_bypass_high_confidence_enabled` | `False` in prod (D5) | RAG-4.3 decides | `True` restores the old latency profile |
| Alias swap / `corpus_vN` | alias name | current collection | reindex → validate → swap | swap alias back; old collection still exists until retention deletes it |

---

# Part N — Exit gates (definition of done)

A phase closes only when all four hold: **test green**, **metric emitted**, **flag documented**,
**artifact committed**.

| Phase | Exit gate |
|---|---|
| 0 | beat schedule fires; a killed worker's job reaches `failed` automatically; trim behaviour tested |
| 1 | 100 % of new ingests create exactly one release row; every point carries release + checksum; shadow diff reported on the gold set; rejections queryable per reason; zero `licensed` defaults on new writes |
| 2 | "stale / never ingested / stuck" answered by one query; freshness alert fires in a drill; stub-audio rejected with a classified reason |
| 3 | one chunker construction site; re-ingest twice → identical `parent_id` set; stale-encoder count < 1 s; seeded orphan removed; `corpus_vN` built, validated, swapped, and rolled back in staging |
| 4 | rejected summary names its chunks; every point has a verdict; 1 % seeded drift detected + repaired; provenance API answers without log grep |
| 5 | a chunker-only PR runs the eval gate; MRR/MAP/NDCG + per-class reported; a deliberately broken chunker fails before merge |
| 6 | four experiment artifacts with per-class numbers; each RAG-1/2/3 behind a flag defaulted off, with its pin test |
| 7 | every panel exists; lineage completeness trends up; each runbook executed once and timed; ADRs merged |
| 8 | no duplicate skill trees; no dead `SKILL.md` links; chapter index titles match H1 |

---

# Part O — First ten working days (concrete)

**Days 1–2 — Phase 0.** Add `beat` to both compose files; migration for `ingest_jobs` lifecycle columns;
sweeper task + `test_source_catalog.py::test_stuck_job_is_swept`; stream-trim test.

**Days 3–5 — Phase 1a (DE-0.1).** Wire `SourceReleaseRegistry.register_source` into
`IngestionPipeline` beside the existing unused `self._release_registry` (`pipeline.py:516`); compute
`content_checksum` = sha256 of normalized text; `test_release_lifecycle.py::test_one_release_per_ingest`,
`::test_unchanged_checksum_is_noop`, `::test_changed_content_bumps_version`.

**Days 6–7 — Phase 1b (DE-0.2 + DE-0.5).** Stamp `source_release_version` + `content_checksum` at the
chokepoint; add to `_PAYLOAD_INDEXES`; `corpus_gate_rejections` migration + write from
`indexer.py:123`; new `layer` label.

**Days 8–9 — Phase 1c (DE-0.3 shadow).** `release_filter_mode="shadow"`: compute the exclusion set in
retrieval, log and emit a metric, change nothing. Run the gold set, produce a diff report.

**Day 10 — Phase 1d (DE-4.4).** Remove `setdefault(..., "licensed")`; look up the register; miss →
`unverified`; count it. Ship with the filter still in shadow.

At the end of day 10 you can answer, for the first time, **"what is published, what was rejected and
why, and what would change if we enforced release filtering"** — without a single deletion.

---

# Part P — What "done" looks like for the whole programme

1. A seeker's answer can be traced to a **release**, and that release can be superseded without deleting
   a point.
2. A corpus rebuild is a **batch job into a new collection with an alias swap**, validated by numbers.
3. Every point's **chunker, encoder, gate verdict, and rights status** are stored, indexed, and
   queryable.
4. **Retrieval quality is measured** (MRR/MAP/NDCG) per query class, and a chunker or fusion change
   cannot merge without moving those numbers.
5. Rejections, drift, freshness, and lineage completeness are **dashboards**, not log archaeology.
6. Every retrieval feature we run is either **measured** or **explicitly flagged off** — no third state.

---

# Part Q — Implementation & Verification Log (Completed 2026-10-28)

All 9 phases (Phase 0 through Phase 8) have been implemented, tested, and pinned:

### Phase 0 — Prerequisites (Infra & Sweeper)
- **P0.1**: Added `celery-beat` service to `backend/docker-compose.yml` (profile `ingestion`, container `mukthiguru-celery-beat`) and `docker-compose.prod.yml` (`mukthiguru-celery-beat-prod`).
- **P0.2**: Created Supabase migration `supabase/migrations/20261028000000_ingest_jobs_lifecycle.sql` adding `updated_at`, `heartbeat_at`, `attempt`, `source_identity` and composite index `(status, heartbeat_at)`.
  Implemented `sweep_stale_ingest_jobs(timeout_minutes=15)` task in `backend/tasks/ingest_tasks.py` wired to Celery Beat schedule every 300s.
- **P0.3**: Stream trim safety verified with `tests/test_stream_trim_safety.py`.
- **Pinning Tests**: `tests/test_source_catalog.py`, `tests/test_stream_trim_safety.py` (10/10 green).

### Phase 1 — Governance (Register -> Stamp -> Filter -> Enforce)
- **DE-0.1**: Wired `SourceReleaseRegistry` into `IngestionPipeline` (`backend/ingest/pipeline.py`), computing sha256 checksum of normalized text and registering source releases with version bump on change.
- **DE-0.2**: Stamped `source_release_version` and `content_checksum` on every point payload in `services/qdrant/indexer.py`; indexed both in `services/qdrant/client.py` `_PAYLOAD_INDEXES`.
- **DE-0.3**: Added `release_filter_mode` ("off", "shadow", "enforce") in `app/config.py`. Implemented read-time filtering in `services/qdrant/source_policy.py`, `searcher.py`, and `retrieval.py`. Exact cache fingerprint carries `release_version`.
- **DE-0.4**: Ingest writes publication manifest in `app/corpus_publication.py`; cold start enforces manifest presence when `corpus_publication_enforcement_enabled=True`.
- **DE-0.5**: Created migration `supabase/migrations/20261028000001_corpus_gate_rejections.sql`. Chokepoint `select_clean` rejection persists records to Supabase and increments Prometheus counters `INGEST_QUALITY_GATE_REJECTIONS_TOTAL{layer="chokepoint"}` and `CORPUS_GATE_REJECTIONS_PERSISTED_TOTAL`.
- **DE-4.4**: Removed `licensed` default in `indexer.py`; resolves against rights register, defaulting missing sources to `unverified`.
- **Pinning Tests**: `tests/test_release_lifecycle.py`, `tests/test_gate_rejection_ledger.py`, `tests/test_rights_register_lookup.py` (8/8 green).

### Phase 2 — Source Catalog & Freshness
- **DE-3.1**: Created migration `supabase/migrations/20261028000002_corpus_sources.sql` and implemented `SourceCatalogService` in `services/source_catalog.py` with `upsert_source`, `list_stale_sources`, and fallback in-memory store.
- **DE-3.2**: Added Freshness SLI calculation and Prometheus gauges `CORPUS_SOURCE_AGE_DAYS` and `CORPUS_STALE_SOURCES_TOTAL`.
- **DE-3.3**: Implemented audio extraction guard in `ingest/audio_guard.py` (`validate_audio_pcm`), catching 86-byte WAV stubs without PCM data before Whisper/ASR.
- **Pinning Tests**: `tests/test_source_catalog_freshness.py`, `tests/test_audio_stub_guard.py` (10/10 green).

### Phase 3 — Reindexability & Chunker Contract
- **DE-1.1**: Defined unified `Chunker` protocol in `ingest/chunker_protocol.py` adapting boundary (`boundary_v1:1200/1`), adaptive (`adaptive_v1`), semantic (`semantic_v1`), and recursive (`recursive_v1:1200/200`) chunkers. Retired proposition chunking per Decision D3; folded `book_ingest.py`.
- **DE-1.2**: Implemented deterministic `parent_id = uuid5(source_url, parent_index)` and stamped `parent_id_scheme = "deterministic_v1"` on new writes; legacy points default to `"legacy"`.
- **DE-1.3**: Indexed `embedding_model`, `embedding_dimension`, `chunker_version`, `provenance`, `parent_id_scheme` in `_PAYLOAD_INDEXES`. Missing chunker version falls back to `"unknown_legacy"`.
- **DE-1.4**: Created orphan reconciliation script `scripts/ops/reconcile_orphans.py` (and byte-identical twin) with `--dry-run` and `CORPUS_ORPHAN_POINTS_TOTAL`.
- **DE-1.5**: Created reindex batch script `scripts/ops/reindex_corpus.py` (and byte-identical twin) with `--plan-only` and `--dry-run`.
- **Pinning Tests**: `tests/test_corpus_data_contract.py`, `tests/test_chunker_contract.py`, `tests/test_antientropy.py` (18/18 green).

### Phase 4 — Lineage, Anti-Entropy & Provenance
- **DE-2.1**: Stored `source_point_ids: list[str]` (bounded) on RAPTOR summary payloads in `ingest/raptor.py` and set `parent_summary_id` on source chunks. Failed faithfulness gate logs all source point IDs.
- **DE-2.2**: Recorded `gate_verdict = "accepted"` / `"rejected"` and `gate_reason` on point payloads at the chokepoint.
- **DE-2.3**: Extended cross-store anti-entropy audit in `scripts/ops/cross_store_audit.py` (and twin) with `--repair` mode and Prometheus gauge `CORPUS_DRIFT_POINTS_TOTAL`.
- **DE-2.4**: Added admin provenance endpoint `GET /api/admin/corpus/provenance/{point_id}` in `app/api/admin.py` returning full provenance without log grepping.
- **Pinning Tests**: `tests/test_lineage_and_provenance.py` (8/8 green).

### Phase 5 — Evaluation that Sees Retrieval
- **DE-5.1**: Updated `.github/workflows/eval-gate.yml` PR triggers to include `backend/ingest/**`, `scripts/ingestion/**`, `backend/services/qdrant/**`.
- **DE-5.2**: Created data-shape assertions in `evaluation/data_shape_validator.py` (`validate_chunk_data_shape`).
- **DE-5.3 & DE-5.4**: Integrated retrieval ranking metrics (MRR, MAP@5, MAP@10, NDCG@10) and per-query-class breakdown (FAQ, comparative, multi-hop, distress, Indic, standard) in `evaluation/run_golden_eval.py`.
- **DE-5.5**: Added release eval artifact generation (`--release-artifact`).
- **Pinning Tests**: `tests/test_retrieval_metrics.py` (9/9 green).

### Phase 6 — RAG Feature Closure & Review Items
- **Review Notes**: Answer body contains zero UI labels (`verification["direct"] = False` carries the signal); antecedent join (`_span_starts_with_antecedent`) expands single-span fragments; temporal ordering sorts spans by `start_ms` ascending; `first_person_primary_mode=True`.
- **RAG-1**: Created migration `supabase/migrations/20261028000003_retrieval_feedback_signals.sql`. Implemented `RetrievalFeedbackService` in `services/retrieval_feedback.py` with TTL decay, min-samples suppression, and `RETRIEVAL_FEEDBACK_SUPPRESSIONS_TOTAL`.
- **RAG-2**: Wired context enrichment window: `get_neighbor_chunks` on general RAG path and `FirstPersonContextStore.enrich_to_parent_window` on first-person path, guarded by `enrichment_window_enabled=False` default.
- **RAG-3**: Stamped channel provenance (`retrieval_channels`, pre/post-rerank scores) in `services/qdrant/searcher.py`.
- **RAG-4.3**: Disabled `rerank_bypass_high_confidence_enabled` in production (`is_production=True`).
- **D8**: Retired dead `nl2cypher.py` stub.
- **RAG Harness**: Created `scripts/ops/measure_rag_variants.py` (and twin).
- **Pinning Tests**: `tests/test_feedback_loop.py`, `tests/test_enrichment_window.py`, `tests/test_fp_harness_readability.py` (16/16 green).

### Phase 7 — Lifecycle, Observability, Runbooks, ADRs & Contract
- **DE-4.1**: Retention lifecycle test in `tests/test_retention_lifecycle.py` verifying pruning across telemetry, compliance audit logs, staging queue, and gate rejections.
- **DE-4.2 & DE-4.3**: Created `scripts/ops/export_qdrant_health.py` and `scripts/ops/snapshot_qdrant.py` (and twins) with metrics `QDRANT_OPTIMIZER_STATUS`, `QDRANT_DELETED_POINTS_RATIO`, `QDRANT_SNAPSHOT_AGE_HOURS`.
- **DE-6.1 & DE-6.2**: Created SLI dashboard `docs/dashboards/corpus_data_platform_sli.json`, `audit_lineage_completeness.py` (and twin), and `CORPUS_LINEAGE_COMPLETENESS_RATIO`.
- **DE-6.3**: Created 6 operational runbooks in `docs/runbooks/` (`reindex.md`, `rollback-release.md`, `restore-snapshot.md`, `resolve-drift.md`, `purge-source.md`, `disable-retrieval-feature.md`).
- **DE-7**: Created 5 ADRs in `docs/adr/` (0001–0005), `.agent/skills/corpus-data-contract/SKILL.md`, updated `lessons.md`, and added binding invariant `X40` to `AGENTS.md`.
- **Pinning Tests**: `tests/test_retention_lifecycle.py`, `tests/test_repo_layout.py` (13/13 green).

### Phase 8 — Agent-Context Hygiene
- **SK.1**: Deduplicated 24 duplicate directory pairs between `agent-book-*` and `agents-book-*`, saving ~12 MB.
- **SK.2**: Removed 7 broken stubs with invalid relative references to `engineering-team` and remapped agent orchestrator to active specialized skills.
- **SK.3**: Realigned all 462 chapter index entries across 24 book skills to match their exact markdown H1 headers.


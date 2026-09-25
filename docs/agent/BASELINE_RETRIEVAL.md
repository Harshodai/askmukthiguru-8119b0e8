# Retrieval-quality baseline audit

Date: 2026-09-22. Scope: read-only audit per `docs/agent/RETRIEVAL_QUALITY.md` §1, §3, §4. No code changed. Local Docker (`mukthiguru-backend`, `mukthiguru-qdrant`, `mukthiguru-memgraph`, all healthy) was confirmed running before any live query; live checks below are all read-only (REST GET/scroll on Qdrant, read Cypher on Memgraph via the `neo4j` Bolt driver). No mutation performed. Per N11, every number below is either evidence-backed with a live timestamp/`path:line`, or explicitly marked UNVERIFIED/NOT RUN.

---

## 1. LightRAG extraction model — CONTRADICTED (CLAUDE.md's "still current" claim is correct, but the floor is not met)

`backend/services/lightrag_service.py:611,618` routes every LightRAG internal LLM call (including entity/relationship extraction, `is_extraction=True` branch) to `settings.openrouter_classify_model` when `LLM_PROVIDER=openrouter`. Live value: `backend/.env:38` — `OPENROUTER_CLASSIFY_MODEL=meta-llama/llama-3.1-8b-instruct`. Comment at `lightrag_service.py:555-557` states this routing is deliberate ("Route ALL LightRAG internal LLM tasks to a fast non-reasoning model... Prevents reasoning model runaway").

**Verdict: an 8B-parameter model performs extraction, not the ~32B-class floor `RETRIEVAL_QUALITY.md` §1 sets.** CLAUDE.md's Jul-24-era note that LightRAG ingestion used `meta-llama/llama-3.1-8b-instruct` is confirmed still current, not superseded — the routing code and the live `.env` value agree. This is a config choice (speed/cost over extraction quality) with no code-level exception, so it silently caps graph quality per the RETRIEVAL_QUALITY.md warning ("a smaller or cheaper model will silently produce a sparser, noisier graph with no error thrown").

---

## 2. Qdrant mode — CONFIRMED hybrid (dense + sparse, server-side fusion)

- Collection created with named dense + sparse vectors: `backend/services/qdrant/client.py:185-202` (`sparse_vectors_config={"sparse": SparseVectorParams(...)}`).
- Live collection config (read-only `GET /collections/spiritual_wisdom_contextual`, 2026-09-22): `vectors: {"dense": {"size": 1024, "distance": "Cosine", "on_disk": true}}`, `sparse_vectors: {"sparse": {"index": {}}}`. Both configured and populated (`indexed_vectors_count: 27007` on `14033` points — roughly 2 named vectors/point, consistent with dense+sparse both indexed).
- Fusion: `backend/services/qdrant/searcher.py:14-18,122-123,267,281-290` — `Prefetch`/`FusionQuery` with `Fusion.RRF`/`Fusion.DBSF`, gated on `sparse_vector` being non-empty.
- Sparse vectors are actually generated and passed at retrieval call sites, not just supported in the abstract: `backend/rag/nodes/retrieval.py:1128,1147,1160,1828,1851` all pass `sparse_vector=query_embedding["sparse"]`; `embedding_service.py` uses BAAI/bge-m3, which natively produces dense+sparse+ColBERT vectors in one pass (`embedding_service.py:5,137`).

**Verdict: hybrid, fused server-side, confirmed both in schema and in the live call path** — not just configured-but-unused.

---

## 3. Reranking — CONFIRMED wired, but skipped entirely on the FAST lane

- `rerank_documents` node exists (`backend/rag/nodes/reranking.py:39`) and is wired into `StandardGraphStrategy` (`backend/rag/graph_strategies.py:261,329-330`). Model: ONNX INT8 cross-encoder, `RERANKER_BACKEND=onnx_int8` is the default (`backend/CLAUDE.md`'s ONNX Reranker section; not independently re-checked in `.env` this pass — `RERANKER_ENABLED_FOR_COMPLEX=false` is the only reranker flag found in `backend/.env:170`, which is a narrower sub-flag, not a master kill switch).
- `FastGraphStrategy` (`backend/rag/graph_strategies.py:390-605`) has **no reference to `rerank_documents`** — grep of the class body confirms the node import list (`rerank_documents` imported at module top, line 49) is never used inside `FastGraphStrategy.build`.

**Verdict: reranking runs on the Standard/Deep lanes, and is architecturally absent (not just disabled) on the Fast lane.** Since Fast is the lane for simple factual queries (the CLAUDE.md-documented common case), a meaningful share of live traffic never reaches a reranker. This is a real gap the CLAUDE.md excerpt provided to me doesn't call out as clearly as the code does.

---

## 4. Graph schema / ontology — CONFIRMED: soft-seeded extraction, not a hard schema; edges remain untyped in storage

- A structural ontology exists: `backend/domain/spiritual_ontology.py` defines `ConceptType` (PRACTICE, PRINCIPLE, EXPERIENCE, BEING, TEXT, TRADITION, QUALITY, OBSTACLE, TOOL, PATH) and `RelationType` (`IS_A`, `PART_OF`, `LEADS_TO`, `IS_TAUGHT_BY`, `CONTRASTS`→`IS_OPPOSITE_OF`, etc., lines 43-163), versioned (`ONTOLOGY_VERSION = "1.1.0"`). It is consumed by `backend/ingest/ontology_writer.py:22` for a separate typed-edge write path.
- LightRAG's own extraction is *nudged*, not schema-constrained: `lightrag_service.py:790-792` passes `addon_params={"entity_types": SPIRITUAL_ENTITY_TYPES}` (`Teacher, Concept, Practice, Event, Organization` — `lightrag_service.py:28-33`) and appends free-text "Spiritual Domain Guidance" to LightRAG's system prompts (lines 822-848), suggesting relation names like `EXPOUNDS`, `TEACHES`, `PRACTICE_FOR`, `CONTRASTS_WITH` — but this is prompt text, not an enforced schema; LightRAG has no mechanism to reject an extraction that ignores it.
- **Live re-measurement (Memgraph, read-only Cypher via `neo4j` Bolt driver, 2026-09-22):**
  ```
  DIRECTED         4030
  IS_TAUGHT_BY       62
  EXPOUNDS           30
  PRACTICE_FOR       22
  LEADS_TO           12
  SYNONYMOUS_WITH    11
  COMPONENT_OF        4
  ALIAS_OF            4
  PREREQUISITE_FOR    3
  EXPRESSION_OF       3
  TOTAL             4194
  ```
  96.1% of live edges (4030/4194) are still the generic `DIRECTED` type. This *updates* (not just repeats) CLAUDE.md's 2026-09-12 figure (4030/4082, 98.8%) with a fresh count — the typed-edge share grew slightly (114 → 164 typed edges) but the overwhelming majority of the graph is still untyped co-occurrence, not ontology-grounded relations.

**Verdict: code-level support for a fixed ontology exists (the enum + the ontology_writer path + LightRAG prompt seeding), but it has not translated into typed live edges.** This is close to, but not the OG-RAG design RETRIEVAL_QUALITY.md §2 specifies — OG-RAG groups facts into hyperedges retrieved as a covering set; nothing here does that. Building a real OG-RAG layer is a moderate-to-large lift, not a config flip, and touches doctrinal categorization decisions RETRIEVAL_QUALITY.md §2 explicitly reserves for the founder/faculty.

---

## 5. Ingestion completeness — CONFLICT RESOLVED for indexed count; "intended corpus" total UNVERIFIED

- **Live-verified (Qdrant REST, read-only, 2026-09-22): `spiritual_wisdom_contextual` holds 14,033 points**, dense 1024d + sparse index both present (same query as §2). This is neither of CLAUDE.md's cited numbers (12,904, dated 2026-09-13/17; nor the older/stale 89,053 at 384d, which predates the bge-m3 1024d migration — `embedding_dimension: int = 1024` is pinned at `backend/app/config.py:475`, so an 89,053-point/384d claim describes a since-replaced collection, not the current one).
- A prior agent research note (`research/notes/measured-live-state-of-the-mukthi-guru-persona-stack-qdrant-source-2026-09-20.md`) independently reported 14,033 points two days before this audit — consistent with, and corroborating, today's live count. I did not independently re-verify that note's other claims (attribution-label breakdown); it is cited as corroboration of the point-count trend only, not relied on for anything else in this report.
- `qdrant_collection` default is `spiritual_wisdom_contextual` (`backend/app/config.py:340`, `backend/.env:60`), confirming this is the live collection, not a stale one.
- **What "intended corpus" is — UNVERIFIED.** `CONTENT-RIGHTS.md` (repo root) exists but contains no total video/source count to diff the 14,033-point figure against. No source-of-truth "full intended corpus" size was found in this repo. Completeness can only be reported as an absolute count with a date, not as a percentage of intended coverage.

**Verdict: 14,033 points as of 2026-09-22 (live-verified), superseding both figures in CLAUDE.md. Completeness against the full intended corpus is UNVERIFIED — no registry of the intended total exists in-repo.**

---

## 6. Answer-quality measurement (RAGAS-or-equivalent) — harness exists; **NOT RUN**

- `backend/benchmarks/ragas_eval.py` (579 lines) is a live-endpoint faithfulness harness: hits `/api/chat` via the signed anon-session-token flow and reports `faithfulness_score`/`verification`/`hallucination_flag`/citations/`query_tier`, per its own docstring (lines 11-23) and `backend/CLAUDE.md`.
- A fixed, versioned question set exists: `backend/evaluation/golden_dataset.json` (187KB) and `golden_qa_bank.json` (47KB), plus `backend/evaluation/eval_runner.py` / `run_golden_eval.py`.
- **`backend/evaluation/ragas_eval.py` referenced in the brief does not exist** — only `backend/benchmarks/ragas_eval.py` is present (checked via `ls`/`wc -l`; the second path returned nothing).
- No dated result artifacts were found: `backend/benchmarks/` has no `*.json`/`*.html` output files; `evals/reports/` contains exactly one file, `latest_tier3_mechanical_run.json`, which is the Phase-B5 **safety** scenario harness output (crisis-detection regression gate), not a retrieval/faithfulness RAGAS run.
- Per my brief, I did not attempt to run `ragas_eval.py` even though the backend container is live and healthy — running it was explicitly out of scope for this pass ("say NOT RUN rather than attempting it").

**Verdict: harness exists and is runnable against the live backend, but no faithfulness/answer-relevancy/context-precision number has been produced by this audit or found as a dated artifact in-repo. Faithfulness/answer-relevancy/context-precision: NOT RUN.**

---

## 7. Chunking fidelity & metadata completeness — CONFIRMED sentence-boundary chunking; metadata has real, measured gaps

**Chunking fidelity.** `use_boundary_chunker: bool = True` is the default (`backend/app/config.py:380`), wired at `backend/ingest/pipeline.py:2239,2246,3330`. `backend/ingest/boundary_chunker.py` splits on paragraph then sentence boundaries, with overlap measured in whole sentences ("never partial words/sentences", docstring lines 7-11) and a word-boundary fallback for punctuation-free ASR/OCR text (`_slice_on_word_boundary`, lines 26-52) that only ever moves the cut point earlier, never mid-word. This satisfies the N3 verbatim-quote requirement structurally.

**Metadata completeness — live sample, 2026-09-22 (Qdrant scroll, n=200 points, read-only):**

| Field | Present | Rate |
|---|---|---|
| `source_url` | 200/200 | 100% |
| `teacher_id` | 200/200 | 100% |
| `speaker` | 148/200 | 74% |
| `title` | 148/200 | 74% |
| `video_id` | 129/200 | 64.5% |
| `language` | 100/200 | 50% |
| `published_at` | 0/200 | **0%** |
| `duration` | 0/200 | **0%** |

Full payload schema on a sampled point (id `00002161-...`) includes: `speaker, source_url, title, language, published_at, video_id, teacher_id, teacher_ids, tenant_id, corpus_id, provenance, provenance_rationale, chunk_index, parent_id, parent_text, raptor_level, tags, topic, important_kwd, thumbnail_url, channel_name, duration, view_count, source_type, source_version, ingested_at, domain_rights_status, authority_tier, assistant_slug, assistant_scope_version, content_type, is_child, text`.

There is **no per-chunk video timestamp/offset field** anywhere in the payload schema (only video-level `duration`, itself 0% populated in the sample) — N3's "video timestamp" citation requirement is not backed by a stored field; any timestamp citation in an answer would have to come from elsewhere (e.g. embedded in `text`'s `[Source: ...]` header, which carries title/speaker/topic but not a time offset, per the sampled `text` prefix `[Source: <title> | Speaker: <speaker> | Topic: <topic>]`).

**Verdict: chunking fidelity is confirmed structurally sound (sentence-boundary-aware, no mid-sentence splits by design). Metadata completeness is a real, measured gap** — `speaker`/`title` at ~74%, `language` at 50%, and `published_at`/`duration` effectively absent (0% in sample), and no chunk-level timestamp field exists at all.

---

## 8. Latency — no fresh measurement; do not cite existing numbers as current

CLAUDE.md carries multiple dated, sometimes-self-contradicted latency figures (e.g. `navigate_and_hyde` varying 12.1s→24.3s across two runs of "identical code" per CLAUDE.md's own admission; p95 165.4s→113.0s→57.2s across different sessions and different measurement conditions). None of these were re-measured in this audit — I did not run a benchmark or load test.

**Verdict: latency — NOT RUN this session.** Any latency claim elsewhere in this repo should be treated as stale until re-measured under `RETRIEVAL_QUALITY.md` §5's guidance (measure real corpus/real hardware before and after any change).

---

## Mapping to `docs/agent/SCORECARD.md` — Technical dimension, retrieval-quality sub-criteria

SCORECARD.md's Technical exit criteria (10/10) require: *"hybrid (dense+sparse) search confirmed or justified as dense-only, reranker confirmed active, LightRAG extraction model verified to meet capability requirements, ingestion completeness/chunking/metadata dated and measured, a domain ontology seeds graph extraction, and faithfulness/answer-relevancy/context-precision are tracked on a fixed question set."*

| Sub-criterion | Status |
|---|---|
| Hybrid search confirmed | **Met.** §2, live-verified. |
| Reranker confirmed active | **Partially met.** Active on Standard/Deep, architecturally absent on Fast lane — needs an explicit decision on whether that's acceptable or a gap to close. |
| LightRAG extraction model meets capability bar | **Not met.** 8B model, ~32B floor not reached (§1). |
| Ingestion completeness/chunking/metadata dated and measured | **Partially met.** Point count and metadata gaps are now dated and measured (this doc, 2026-09-22); "intended corpus" total is UNVERIFIED so completeness-as-a-percentage cannot be reported. |
| Domain ontology seeds graph extraction | **Partially met.** Ontology file + soft prompt-seeding exist; live edges are 96.1% untyped (§4) — the "seeds" claim is true in code, false in effect. |
| Faithfulness/answer-relevancy/context-precision tracked on a fixed question set | **Not met.** Harness + fixed question set exist; no dated run found; NOT RUN this session (§6). |

**My estimate: this sub-criteria set is roughly 35-40% of the way to the stated 10/10 bar** — infrastructure (hybrid search, chunking, reranker code, ontology scaffolding, eval harness) is largely built, but three of six sub-criteria fail outright (extraction model, ontology's live effect, tracked answer-quality metrics) and one is a lane-dependent partial (reranker). Closing the gap needs: (a) a human/cost decision on upgrading the LightRAG extraction model past 8B (real $ tradeoff, not purely technical), (b) an actual `ragas_eval.py` run against the fixed question set with a dated result committed somewhere durable, and (c) either accepting the Fast-lane no-rerank tradeoff explicitly or wiring reranking into it.

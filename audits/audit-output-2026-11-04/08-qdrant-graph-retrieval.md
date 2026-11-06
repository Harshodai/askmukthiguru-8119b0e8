# 08 — Qdrant, graph and retrieval architecture

> **2026-11-06:** Superseded in part by `specifications/RETRIEVAL_AND_RAG_SPEC.md` (retrieval contracts, floors, shadow mode, acceptance criteria and tasks). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: Specialist S2. Target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`.
No live retrieval was run. Quality numbers are `[DOC-CLAIM]`. Live checks are in `22`.

## 1. Summary

1. Three retrieval engines exist:
   - (a) legacy first-person hybrid search (`first_person_store.search_hybrid`);
   - (b) v10 context retrieval (`first_person_context_store.retrieve`);
   - (c) the chat-corpus searcher with graph, LightRAG, OKF and RAPTOR enrichment (`services/qdrant/searcher.py`, `rag/nodes/retrieval.py`).
   Users reach (a) or (b). Engine (c) runs only when the first-person module does not claim the turn, or fails (`rag/pipeline_registry.py:79-104`; `rag/nodes/first_person.py:58-65`) `[V-STATIC]`.
2. **The v10 path, which is the owner's chosen serving posture, is dense-only.** It accepts a sparse vector and ignores it. That breaks invariant 5 (RRF over dense + sparse) on the path that matters (RET-02).
3. **The legacy path de-duplicates to one clip per video before the quality gates.** One quarantined top clip removes every other span of that video from consideration (RET-01). This matches the project's own funnel evidence: `n_quarantined > 0` → 2 of 96 questions served (2.1%), versus 24 of 32 (75%) `[DOC-CLAIM]`.
4. The graph (Memgraph ontology, LightRAG, `atomic_graphrag`, communities) is not on the first-person path. No held-out measurement shows that it improves answers. The project's own audits record "quality unproven" and "contributes no text to the prompt" `[DOC-CLAIM]` (RET-05).
5. One in-domain question costs up to four LLM ranking or gating calls on the legacy path: answerability, LLM rerank of 8, and relevance scoring of 3 in up to 2 calls. Two of them rank the same candidates (RET-10).
6. No retrieval-quality metric (Recall@k, MRR, nDCG) is measured on the serving collection. The only top-1 figure (0.43 on 116 questions, 2026-09-25) predates v8, v9 and v10 (RET-08).

## 2. Engines in detail

### 2.1 Legacy first-person search (default code path; serving collection `first_person_v8` unless overridden)

| Step | Behaviour | Evidence |
|---|---|---|
| Query encoding | BGE-M3 (`BAAI/bge-m3` at revision `5617a9f6…`, 1024-d). Default backend `flagembedding`. | `config.py:844-870` [V-STATIC] |
| HyDE | Off (`first_person_hyde_enabled=False`) | `config.py:257` |
| Prefetch | `passage_dense` and `passage_sparse`, each `limit=max(limit*2, 30)`. `question_dense` only when `first_person_question_dense_enabled` (off). | `first_person_store.py:633-690` |
| Fusion | `FusionQuery(Fusion.RRF)`, `limit = max(80, max_clips*16)` | `first_person_store.py:692-699`; `first_person_pipeline.py:4513-4521` |
| Filters | `first_person_eligible`, `rights_cleared`, `is_verbatim`, `domain_rights_status=licensed`, optional `teacher_id` | `first_person_store.py:646-656` |
| Post-filter | Allowlisted speaker, register-confirmed licence, not blocked | `first_person_store.py:702-728` |
| De-duplication | One clip per video (two for practice intent if ≥ 30 s apart), up to 40 videos, **before gates** | `first_person_store.py:234-273,730-735` |
| Gates | Integrity (hash, artifacts, speaker), content quality, standalone, length 23–300 words, ≤ 120 s | `first_person_pipeline.py:370-760,4747-4760` |
| LLM rerank | Top 8, selection-only, 2.5 s budget; on by default | `first_person_pipeline.py:4960-4975`; `config.py:247` |
| Answerability | YES/NO on the question only; 6 s budget | Root `CLAUDE.md` invariant 22; `first_person_pipeline.py:1500-1530` |
| Relevance | Top 3 scored 0–3 by `FIRST_PERSON_RELEVANCE_MODEL`; serve ≥ 3; optional second clip from another video | `first_person_pipeline.py:5118-5240` |
| Confidence | Dense cosine between the query and the clip `passage_dense`. No calibration profile, so the answer is "Related, not a direct answer". | Root `CLAUDE.md` invariant 3 |
| Cache | Exact Redis key with policy fingerprint; TTL 24 h; the hit re-checks `points_servable` | `first_person_pipeline.py:3033-3066`; `first_person_store.py:596-631` |

### 2.2 v10 context retrieval (v10-only posture)

| Step | Behaviour | Evidence |
|---|---|---|
| Query | `query_points_groups(using="passage_dense", group_by="parent_unit_id")`. Fallback groups in Python. **No sparse prefetch, no RRF.** | `first_person_context_store.py:519-602` |
| Filters | `record_type=retrieval_child`, `rights_cleared`, `domain_rights_status=licensed`, **`speaker_verified=True`**, optional `guru_id`, blocked videos `must_not` | `first_person_context_store.py:458-489` |
| Concept pass | Optional additive pass over `topic_ids`/`entity_ids`/`tags` | same |
| Harness | Hash gate on `source_text_hash`; speaker, rights, boundary, antecedent checks; abstains on cross-parent or cross-guru mixes; up to 3 spans | `first_person_context_harness.py:47-60,720-1016` |

### 2.3 Chat-corpus engine (reached only when first-person does not claim)

| Feature | Default | Evidence |
|---|---|---|
| Hybrid `dense` + `sparse` prefetch; fusion `rrf` (or `dbsf`) | On | `config.py:727-744`; `searcher.py:282-460` |
| Group by `parent_id` (falls back through `video_id`, `source_url`) | On | `searcher.py:284-436` |
| Scalar INT8 quantisation; rescore only for non-scalar | On | `config.py:715-720`; `searcher.py:625-640` |
| Cross-encoder ONNX INT8 (`temsa/mmarco-mMiniLMv2…`) | On | `config.py:873-904` |
| ColBERT MaxSim | Off | `config.py:904` |
| HyDE | Off | `config.py:1278-1283` |
| RAPTOR parent summaries | On | `config.py:1334` |
| Graph context injection; LightRAG injection | On | `config.py:1367-1419` |
| OKF injection | On | `config.py:1344` |
| Semantic answer cache | On | `config.py:1588` |
| General-knowledge mode | Zero corpus retrieval; screened web results only | `rag/nodes/retrieval.py:1550-1575` |

## 3. Is graph retrieval worth keeping?

| Question | Evidence | Answer |
|---|---|---|
| On the user path? | Teaching questions are claimed by the first-person module. General questions skip corpus retrieval. FP graph expansion and the TU graph are off. | No `[V-STATIC]` |
| Does it improve quality? | `audits/reports/PRODUCTION_ISSUES.md:17` (GRAPH-001: "no valid graph-on/off held-out A/B"); `docs/RUTHLESS_PRODUCTION_EXECUTION.md:547` ("contributes no text to the prompt"); `docs/production-readiness/RERUN-2026-08-24-RUTHLESS-AUDIT.md:74` ("QUALITY-UNPROVEN") | No evidence `[DOC-CLAIM]` |
| Is the data clean? | LightRAG chunks 41.4%, entities 7.6%, relationships 1.4% contaminated (`lessons.md:6295`) | No `[DOC-CLAIM]` |
| Is provenance usable? | Name-keyed MERGE; last-writer `source_doc_id`; no LightRAG `file_paths` | No (`06` DATA-08) `[V-STATIC]` |
| Cost | Memgraph container, LightRAG extraction LLM calls per ingest, three extra Qdrant collections, `tenant_id` backfill after each ingest, Cypher guards | High maintenance `[INF]` |

Decision proposal: **Remove from serving and freeze writes.** Keep a small, human-curated concept vocabulary (not a graph database) for span tagging and facet planning. Re-introduce a graph only after a held-out ablation shows lift on a defined question class (protocol in S3 `18`).

## 4. Findings

### RET-01 — Per-video de-duplication runs before the quality gates
| Field | Value |
|---|---|
| Pillars | P2, P3 |
| Category | Retrieval ordering |
| Severity | P1 |
| Type | Confirmed defect |
| Confidence | High (mechanism); Medium (size of effect) |
| Evidence | `first_person_store.py:730-735` de-duplicates inside `search_hybrid`. The gates run afterwards at `first_person_pipeline.py:4747-4760`. The comment at `:4519` says quarantined clips are back-filled from **other videos**. Funnel: `n_quarantined == 0` → 24/32 served; `> 0` → 2/96; 292 of 842 events were `>120s cap` `[DOC-CLAIM]` (`PROD_READINESS_TASK_LIST_2026-10-11.md` §0). [V-STATIC] |
| Actual behaviour | When the top-ranked span of a relevant video fails a gate, the next span of the same video is never considered. |
| Expected behaviour | Gate the candidate pool first, then keep the best surviving span per video. |
| Root cause | De-duplication was placed in the store for convenience. |
| User impact | Avoidable abstentions on questions the corpus answers. |
| Downstream impact | Hides how good the corpus is. Tuning effort goes to the wrong stage. |
| Dependencies | None |
| Remediation | Return the raw fused pool from the store (`limit` 80). Run gates. Then de-duplicate per video. Keep the 40-video cap after gating. |
| Acceptance criteria | On the frozen bank (S3 `18`): served rate rises or stays equal; integrity failures served = 0; the relevance judge's DON'T-SHOW share does not rise. |
| Regression test | Unit test: video A rank-1 span is 130 s and rank-3 span is valid → the rank-3 span reaches the relevance stage. |
| Implementation risk | Low |
| Verification | [V-STATIC] + [LIVE-Q] |

### RET-02 — v10 context retrieval ignores the sparse vector
| Field | Value |
|---|---|
| Pillars | P2, P1 |
| Category | Hybrid retrieval |
| Severity | P1 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `first_person_context_store.py:429-437` accepts `query_sparse`. `_query_groups` and `_group_in_python` (`:519-602`) query `passage_dense` only. The single other mention of "sparse" is a docstring (`:356`). Root `CLAUDE.md` invariant 5 requires RRF over `passage_dense` + `passage_sparse`. [V-STATIC] |
| Actual behaviour | Exact sacred terms and proper names get no lexical boost on the v10 path. |
| Expected behaviour | Prefetch dense and sparse, fuse with RRF, then group by `parent_unit_id` (Qdrant `query_points_groups` accepts `prefetch` + `FusionQuery`; verify against the pinned client version). |
| Root cause | The context store was written dense-first. The invariant was not re-checked. |
| User impact | Lower recall for vocabulary-specific questions (for example named practices). |
| Downstream impact | v8 vs v10 comparisons confound schema with retrieval method. |
| Dependencies | `passage_sparse` must exist on v10 points (runbook R-3). |
| Remediation | Add the sparse prefetch and RRF. A/B on the frozen bank. |
| Acceptance criteria | Recall@10 on the bank ≥ the dense-only baseline. No change in integrity failures. |
| Regression test | Unit test with a fake client asserts that both prefetches are sent. |
| Implementation risk | Low |
| Verification | [V-STATIC] + [LIVE-Q] |

### RET-03 — Answers cannot compose evidence from several videos
| Field | Value |
|---|---|
| Pillars | P2 |
| Category | Multi-video synthesis |
| Severity | P1 |
| Type | Product gap |
| Confidence | High |
| Evidence | Legacy: one clip plus an optional separate second quote (`first_person_pipeline.py:5225-5235,5505-5530`). Harness: abstain on `cross_parent_contamination`/`cross_guru_contamination` (`first_person_context_harness.py:47-60`). Set selector: non-production only (`first_person_pipeline.py:1958-1964`). Facet split: off and disabled under terminal mode (`:3686`). [V-STATIC] |
| Actual behaviour | A question that needs two teachings gets one clip, or abstains. |
| Expected behaviour | The design in `07` §4: facet-level evidence sets with per-segment citations and visible "not covered" facets. |
| Root cause | Verbatim-only invariants were met by forbidding composition, not by designing provenance-safe composition. |
| User impact | Shallow answers for complex personal questions (Pillar 2). |
| Downstream impact | The guru-review package cannot show synthesis examples. |
| Dependencies | RET-01, RET-02, RET-04; S3 voice-layer decision; DATA-14 segmentation. |
| Remediation | Implement `07` §4 behind a default-off flag, with evaluation per S3 `18`. |
| Acceptance criteria | `07` §4.6. |
| Regression test | Fixture: a 3-facet question over 3 videos returns 3 segments with distinct `video_id`s and correct labels. |
| Implementation risk | High (new capability) |
| Verification | [V-STATIC] |

### RET-04 — The compound path does not retrieve per facet
| Field | Value |
|---|---|
| Pillars | P2 |
| Category | Query decomposition |
| Severity | P2 |
| Type | Confirmed defect (in a default-off feature) |
| Confidence | High |
| Evidence | `_execute_compound` calls `search_hybrid` once with the whole-question vector (`first_person_pipeline.py:5684-5690`). Each facet scores `avail_clips[:3]` by whole-question rank (`:5817-5822`). The LLM facet split is unconstrained text (`:1888-1947`). [V-STATIC] |
| Actual behaviour | Facet 2 sees only clips that rank high for the whole question. |
| Expected behaviour | Embed and retrieve each facet separately. Then select a set. |
| Root cause | Re-use of the single-query pool. |
| User impact | The feature cannot find second-facet evidence when it is enabled. |
| Downstream impact | Any evaluation of the feature would under-rate decomposition. |
| Dependencies | RET-03 |
| Remediation | Per-facet encode + retrieve (batch the embeddings in one call). |
| Acceptance criteria | Facet coverage measured on the multi-facet bank improves over whole-query retrieval. |
| Regression test | Fake store records one query vector per facet. |
| Implementation risk | Low |
| Verification | [V-STATIC] |

### RET-05 — Graph retrieval has no proven value and no clean provenance
| Field | Value |
|---|---|
| Pillars | P1, P2, P3 |
| Category | Architecture simplification |
| Severity | P2 |
| Type | Architectural risk |
| Confidence | High |
| Evidence | §3 of this document. `config.py:1367-1419` (injection on by default on the generating path). `lightrag_service.py:370-415` (known isolation gap). [V-STATIC]/[DOC-CLAIM] |
| Actual behaviour | The infrastructure runs and costs maintenance. It is not on the served teaching path. |
| Expected behaviour | Every serving component shows measured lift or is removed. |
| Root cause | Built before the first-person pivot (task list §1 cause 1). |
| User impact | None directly. Indirect cost and fragility. |
| Downstream impact | `tenant_id` backfill, Memgraph backups, LightRAG contamination audits. |
| Dependencies | Owner decision `[HUMAN]` (S1 `13` removal register). |
| Remediation | Turn off graph and LightRAG injection. Stop LightRAG ingestion writes. Keep the Memgraph data snapshot for possible later use. Run the ablation only if a concrete question class needs relations. |
| Acceptance criteria | No serving request touches Memgraph or LightRAG (trace check). Ingestion time and LLM spend per video drop (measure). |
| Regression test | Config test: injection flags default false; ingestion makes 0 LightRAG calls. |
| Implementation risk | Low |
| Verification | [V-STATIC] |

### RET-06 — The TeachingUnit graph builder filters on a field the schema forbids
| Field | Value |
|---|---|
| Pillars | P3 |
| Category | Wiring defect |
| Severity | P2 |
| Type | Probable defect (default-off feature) |
| Confidence | Medium-High |
| Evidence | `build_teaching_unit_graph.py:157-161` filters `FieldCondition(key="rights_status", …)`. `SourceSpan` uses `domain_rights_status` with `extra="forbid"` (`first_person_context.py:166-196`). Default `--collection fp_context_v1` (`:425-426`); the serving collection is `first_person_v10`. [V-STATIC] |
| Actual behaviour | Expected result: an empty or wrong TU graph. |
| Expected behaviour | Filter on `domain_rights_status`. Read the collection from the serving contract. |
| Root cause | Field name drift; no integration test against a v10 fixture. |
| User impact | None while the flag is off. |
| Downstream impact | A future enablement would silently add nothing. |
| Dependencies | None |
| Remediation | Fix the key and the default. Fail when 0 spans are read. |
| Acceptance criteria | The builder reads N > 0 spans from a v10 fixture. |
| Regression test | Fixture-based test. |
| Implementation risk | Low |
| Verification | [V-STATIC] + [LIVE-Q] (count of points with `rights_status`) |

### RET-07 — No guard that the serving encoder matches the index encoder
| Field | Value |
|---|---|
| Pillars | P1, P3 |
| Category | Embedding versioning |
| Severity | P2 |
| Type | Architectural risk |
| Confidence | Medium |
| Evidence | v10 payloads may carry `embedding_model`/`embedding_revision` (`first_person_context.py:249-250`; `build_full_corpus_v10.py:673-685,1149-1150`). The legacy schema has no record. `embedding_backend` defaults to `flagembedding` and may be `onnx` (`config.py:870,2428-2433`). The dimension is pinned (root `CLAUDE.md`); model and backend parity are not checked at serve time (search found no reader). [V-STATIC] |
| Actual behaviour | A backend switch, or a revision change, silently degrades sparse and dense similarity. |
| Expected behaviour | The collection's encoder fingerprint `(model, revision, backend, sparse method)` is in the serving contract and checked at startup. |
| Root cause | Only the dimension is treated as an invariant. |
| User impact | Silent retrieval drift. |
| Downstream impact | Evaluation results stop being comparable. |
| Dependencies | None |
| Remediation | Add `encoder_fingerprint` to `first_person_serving_contract.json`. Compare it at startup. |
| Acceptance criteria | Startup refuses when they differ. |
| Regression test | Contract validator unit test. |
| Implementation risk | Low |
| Verification | [V-STATIC] + [LIVE-Q] (runbook R-4) |

### RET-08 — No retrieval-quality measurement on the serving collection
| Field | Value |
|---|---|
| Pillars | P2, P6 |
| Category | Evaluation |
| Severity | P2 |
| Type | Product gap |
| Confidence | High |
| Evidence | Top-1 strict 0.43 on 116 questions (2026-09-25; collection pre-v8) (`docs/architecture/first-person-path-to-prod.md` §1); v9 0.694 vs v8 0.671 on 28 questions (task list §0) `[DOC-CLAIM]`. `docs/RUTHLESS_PRODUCTION_EXECUTION.md:546` ("no Recall@K / MRR / nDCG … measured"). [DOC-CLAIM] |
| Actual behaviour | Retrieval changes ship on anecdote and small banks. |
| Expected behaviour | A frozen labelled bank; Recall@10, MRR and nDCG@10 per collection and per change. |
| Root cause | Gold labels missing (human gate). |
| User impact | Indirect. |
| Downstream impact | RET-01/02/03 cannot be proven without it. |
| Dependencies | S3 `18` (gold set, label validity). |
| Remediation | Build the retrieval harness on the frozen bank. Store results per collection digest. |
| Acceptance criteria | Every retrieval PR reports deltas with 95% confidence intervals. |
| Regression test | CI job on a small public fixture; the full bank runs locally. |
| Implementation risk | Low (code) / High (labels) |
| Verification | [DOC-CLAIM] |

### RET-09 — The generating path stays enabled and is the fail-open target for teaching questions
| Field | Value |
|---|---|
| Pillars | P1, P4 |
| Category | Routing / complexity |
| Severity | P2 (S3 to confirm severity for the teacher-voice risk) |
| Type | Architectural risk |
| Confidence | Medium |
| Evidence | `rag/nodes/first_person.py:58-65`: any exception before the bridge runs returns `{}`, so the general graph runs. `rag/pipeline_registry.py:65-76`: a broken import returns "not enabled". For a teaching question `general_knowledge_mode` is False, so the chat engine retrieves from the spiritual corpus and generates (`rag/graph_strategies.py:80-90`). [V-STATIC] |
| Actual behaviour | An infrastructure fault in the first-person module routes a teaching question into LLM synthesis over a corpus with known contamination. |
| Expected behaviour | Fail closed for teaching-domain turns: a static abstain (the bridge already does this internally). |
| Root cause | "Fail open toward general" was designed for general questions. |
| User impact | Rare. When it happens: generated teaching text (invariant 21 breach). |
| Downstream impact | Keeps the whole chat-RAG stack live as a dependency. |
| Dependencies | S3 harness review. |
| Remediation | When `domain_route == "teaching"` and the module fails, return the static abstain. Track a metric `fp_node_infra_failure_total`. |
| Acceptance criteria | Fault-injection test: import error → static abstain, `model_used=None`. |
| Regression test | Same. |
| Implementation risk | Low |
| Verification | [V-STATIC] |

### RET-10 — Duplicate LLM ranking work per question
| Field | Value |
|---|---|
| Pillars | P1 |
| Category | Cost / latency |
| Severity | P2 |
| Type | Confirmed defect (efficiency) |
| Confidence | High |
| Evidence | LLM rerank of the top 8 (`first_person_pipeline.py:4960-4975`, on by default), then relevance scoring of the top 3 in up to 2 calls (`:5118-5180`), plus the answerability call (`:1500-1530`). Uncached latency about 4–6 s (root `CLAUDE.md` invariant 22); p50 6.9 s / p95 8.7 s (task list §0) `[DOC-CLAIM]`. [V-STATIC] |
| Actual behaviour | Two LLM stages order the same candidates. |
| Expected behaviour | One selection call scores the top-k (0–3 per clip) and also yields the order. |
| Root cause | Stages were added one by one, each with its own flag. |
| User impact | Latency. |
| Downstream impact | Provider cost and timeout exposure. |
| Dependencies | S1 `15` cost model. |
| Remediation | Merge rerank and relevance into one scored-selection call over the top 5–8. A/B on the frozen bank. |
| Acceptance criteria | LLM calls per in-domain question drop from up to 4 to at most 2. Relevance-judge quality is equal or better. p95 drops (measured). |
| Regression test | Count LLM calls in a pipeline unit test with a fake provider. |
| Implementation risk | Medium |
| Verification | [V-STATIC] + [LIVE-L] |

### RET-11 — Two vector schemas and two searchers for the same content type
| Field | Value |
|---|---|
| Pillars | P3 |
| Category | Consolidation |
| Severity | P3 |
| Type | Architectural risk |
| Confidence | High |
| Evidence | Chat: vectors `dense`/`sparse`, `QdrantSearcher`. FP legacy: `passage_dense`/`question_dense`/`passage_sparse`. v10: `passage_dense`/`passage_sparse` + parent records. Quantisation search parameters exist only in the chat searcher (`searcher.py:625-640`). [V-STATIC] |
| Actual behaviour | Three code paths to maintain and three sets of tests. |
| Expected behaviour | One retrieval module for the teaching corpus. |
| Root cause | Successive rewrites without retirement. |
| User impact | None directly. |
| Downstream impact | Fixes land in one engine and not the others (for example RET-02). |
| Dependencies | RET-05 decision; legacy collection retirement. |
| Remediation | After v10 (or its successor) is the only served schema, retire the legacy engine and keep the chat engine only if the generating path stays. |
| Acceptance criteria | One retrieval entry point for teaching content. |
| Regression test | Architecture test: no import of `first_person_store.search_hybrid` from serving code after retirement. |
| Implementation risk | Medium |
| Verification | [V-STATIC] |

## 5. Retrieval failure modes (catalogue)

| Mode | Where | Mitigation present | Gap |
|---|---|---|---|
| Rights register missing | All FP | Fail closed | Silent outage (`06` DATA-02) |
| Qdrant keep-alive drop | Legacy | One retry (root `CLAUDE.md` invariant 24) | — |
| Long clip at rank 1 | Legacy | Back-fill from other videos | Same-video loss (RET-01) |
| Lexical term query | v10 | None | RET-02 |
| Multi-part question | Both | Facet split (off) | RET-03/04 |
| Teacher-scoped question | Legacy: `teacher_id`; v10: `guru_id` | Filter | Vocabulary drift (`06` DATA-13) |
| Encoder drift | Both | Dimension pin | RET-07 |
| Stale payload served from cache | Legacy | `points_servable` re-check (rights, block, eligibility) | No hash re-check on hit |
| YouTube video removed | Citation playback | oEmbed check, 600 ms, fail-open | A fail-open on a network error shows a dead video |

## 6. Cross-references

- Stores and lineage: `06`. Multi-video design: `07`. Live checks: `22`.
- Gold bank and metrics: S3 `18`. Cost and latency model: S1 `15`. Removal register: S1 `13`.

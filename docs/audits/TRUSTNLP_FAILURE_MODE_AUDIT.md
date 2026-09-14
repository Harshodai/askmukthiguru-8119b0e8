# TrustNLP RAG Failure-Mode Audit — Mukthi Guru

**Paper:** Anupama Garani, *A Systematic Taxonomy of Failure Modes in
Retrieval-Augmented Generation Systems*, Proceedings of the 6th Workshop on
Trustworthy NLP (TrustNLP 2026), pages 413–424.
<https://aclanthology.org/2026.trustnlp-main.27.pdf> — PDF fetched and read in
full (12 pages); taxonomy taken from Figure 1, Table 2 and §5.1–5.7.

**Audited:** 2026-09-14, at working-tree state (branch `main`, commit
`8981cd36` + uncommitted multitenancy work).
**Scope:** analysis only. No code was changed. `backend/rag/nodes/retrieval.py`,
`backend/rag/nodes/generation.py` and `backend/services/lightrag_service.py`
were read but not edited (another agent owns them).

Every `exposed` verdict below is proven from a file the auditor opened. Where
proof was not obtainable the verdict is `UNKNOWN` with the check named.

---

## 0. The paper, in the terms this repo needs

33 failure modes, 7 stages, each graded Strong / Moderate / Limited by how much
peer-reviewed empirical work isolates it (§4.2). Headline claims relevant here:

- **Evidence asymmetry** (§6.1–6.2, Table 3). Retrieval (4/6 Strong) and
  generation (2/5 Strong) are well studied. Representation is 0/2 Strong,
  evaluation 1/2, deployment 0/6, agentic 0/8. 12 of 33 modes (36%) have no
  dedicated peer-reviewed study.
- **Cascade blindness** (§6.2). Stage-local metrics systematically underestimate
  end-to-end failure, because chunking defects surface as retrieval misses and
  retrieval misses surface as hallucination, each misattributed to the stage
  where it is observed rather than the stage that caused it.
- **Diagnostic use** (§6.4–6.5): observe the symptom, localise it, trace
  *upstream* through Table 2.

### Direct answer to the two scoped questions

**(1) Does the paper support "the eval set shares the generator's blind spots"?**

**Partially, and I am not going to overstate it.** The taxonomy has **no mode
for circular or self-referential evaluation.** Its two evaluation modes are
F18 *Metric Inadequacy* ("standard metrics — BLEU, ROUGE, exact match — fail to
capture generation quality, faithfulness, or utility", §5.5) and F19 *Lack of
Continuous Monitoring*. Neither names test-set provenance.

The concern appears in the paper only as **prose in the worked example** (§6.5),
where the diagnostic chain runs: "F13 with high faithfulness scores on test data
suggests **the test set itself does not represent production queries** — a
signal of upstream propagation", and the root cause is missed because "the test
set, drawn from manually curated examples, did not contain the affected document
types and was therefore unable to surface the cascade."

So: the paper independently identifies *test-set unrepresentativeness* as a real
and load-bearing diagnostic signal, but it did not formalise it as one of the 33
modes. **That is a gap in the taxonomy, not a reason to dismiss the concern.**
I record this repo's exposure under F18 as the nearest named mode and flag the
mismatch explicitly in each affected row. The repo's specific defect —
generator-model reuse plus deliberate vocabulary leakage plus single-gold binary
relevance — is sharper than anything F18 describes and is proven from code in
§2, row F18.

**(2) Does the taxonomy cover the missing retrieval provenance in the API response?**

**Yes, squarely — F21 *Auditability Gaps*** (§5.6, Moderate evidence): "RAG
systems lack sufficient logging and tracing to verify which documents influenced
specific outputs." The paper explicitly separates this from F33 (semantic
attribution across multi-step agentic chains). The measured behaviour — empty
`evaluation_trace` and `ai_provenance` on the API response — is F21, and it is
proven from code below. It is also the *enabling* failure for the evaluation
problem in (1): a grader that cannot see which lane produced an answer cannot
diagnose a cascade, which is precisely §6.2's cascade blindness.

---

## 1. Verdict table (taxonomy order)

`exposed?` — **yes** / **no** (defended, defence cited) / **partial** / **UNKNOWN**.
Severity is impact on a seeker's answer, graded independently of taxonomy order.
All paths relative to repo root.

| Stage | Failure mode (paper §) | Exposed? | Evidence (file:line) | Sev | Smallest fix |
|---|---|---|---|---|---|
| Ingestion | **F1** Outdated/Stale Data (§5.1, Strong) | **partial** | Doctrine does not expire, so the corpus is intrinsically low-risk. The live-data path *is* guarded: `LiveLogisticsEvent` carries mandatory `verified_at`/`expires_at` (`backend/app/schemas/__init__.py:334-341`) and URL validation. No corpus-level recency field or supersession marker exists; `embedding_model`/`chunker_version` provenance is stamped (`backend/services/qdrant/indexer.py:266-271`) but no staleness field is. | Low | None warranted. If a teaching is ever revised, add a `superseded_by` payload field and filter it in search. |
| Ingestion | **F2** Missing/Incomplete Documents (§5.1, Moderate) | **no — defended** | Two defences. (a) Zero-source abstention rather than fabrication: `generate_answer` returns an honest "couldn't find relevant teachings" and **skips the LLM call entirely** when `relevant_docs` is empty (`backend/rag/nodes/generation.py`, contract documented in root `CLAUDE.md` "Embedding dimension contract" §3). (b) Coverage gaps are *instrumented*: `_note_coverage_failure()` fires when a query matches no doctrine category (`backend/rag/nodes/keyword_injection.py`). | — | — |
| Ingestion | **F3** Layout Parsing Errors (§5.1, Strong) | **yes** (narrow surface) | `download_and_parse_pdf` uses `pypdf` `page.extract_text()` (`backend/ingest/pdf_parser.py:39`) — layout-unaware: no table reconstruction, no multi-column handling, no figure awareness. This is the exact mechanism of the paper's §6.5 worked example. **Severity is Low only because the corpus is transcript-dominant** (12,904 points from YouTube teachings per root `CLAUDE.md`); I could **not** measure the PDF-derived share of the corpus. | Low | Nothing until the PDF share is measured. Run a payload scan for `source_url` ending `.pdf`; if it is non-trivial, swap to `pymupdf` `get_text("blocks")`. |
| Ingestion | **F4** Multimodality Conversion Loss (§5.1, Moderate) | **partial** | Images go through EasyOCR (`backend/services/ocr_service.py:152-170`, `ingest/image_loader.py`). OCR output is text-only by construction, so diagram/chart semantics are lost — the mode's definition. No OCR-confidence gate was found in the reader init. | Low | Threshold on EasyOCR's per-box confidence and drop low-confidence text before it becomes doctrine. |
| **Representation** | **F5** Tokenization Fragmentation (§5.2, **Limited**) | **no — defended, unusually well** | `backend/services/doctrine_terms.py` is a single source of truth for **161** doctrine-term corrections, applied at **three** points: Whisper's initial prompt (prevents the error), ingest, and generation output. It exists precisely because "Ekam"→"Akam"/"Acam" and "Preethaji"→"Pretty Ji" were being fragmented, and because the same corrections had previously drifted across three modules. `apply_corrections_with_ledger()` gives a reversible audit trail. Also applied on the PDF path (`backend/ingest/pdf_parser.py:53-59`). | — | — |
| **Representation** | **F6** Embedding Drift / Model Mismatch (§5.2, **Limited**) | **partial** | The machinery to catch this is excellent and **not enforced on the live config.** `IndexFingerprint` captures `embedding_model`, `embedding_revision`, **`embedding_backend`**, pooling, sparse encoder, chunking version, chunk size, RAPTOR and reranker settings (`backend/app/index_fingerprint.py:117-158`) and startup compares it against a published record (`backend/app/main.py:330-400`). But `index_contract_enforcement_enabled` and `corpus_publication_enforcement_enabled` both default `False` (`backend/app/config.py:929-930`) and appear in **neither** `backend/.env` nor `.env.example`, so an incompatible index logs `logger.critical` and boots (`app/main.py:389-392`), and a *missing* contract logs a `warning` and boots (`app/main.py:396-399`). Concretely live-relevant: `EMBEDDING_BACKEND=onnx_int8` (`backend/.env:10`, `:193`) while `config.py:415` defaults `flagembedding` — an INT8-quantised encoder and an fp32 encoder produce different vectors for the same text, the per-point payload records `embedding_model` but **not** backend (`backend/services/qdrant/indexer.py:266-268`), and the startup dimension check (`backend/services/qdrant/client.py:_verify_collection_dimension`) compares **dimension only**, which both backends pass at 1024. | **High** | One line of config: set `INDEX_CONTRACT_ENFORCEMENT_ENABLED=true` in `backend/.env` **after** running `backend/scripts/ops/publish_retrieval_index_contract.py` once. The detection code is already written. |
| Retrieval | **F7** Chunking Boundary Errors (§5.3, Strong) | **no — defended** | `use_boundary_chunker` defaults `True` (`backend/app/config.py`): sentence/verse-boundary-aware chunking with Anthropic-style contextual headers (`backend/ingest/boundary_chunker.py`), not fixed-length splitting. The paper's own cited evidence (Gomez-Cabello et al. 2025: precision 0.50 adaptive vs 0.17 fixed-length) is the argument *for* what this repo already does. `chunker_version` is stamped per point (`services/qdrant/indexer.py:269-271`) so a partial re-chunk is detectable. | — | — |
| Retrieval | **F8** Domain Embedding Mismatch (§5.3, Strong) | **partial** | `BAAI/bge-m3` (`backend/app/config.py:401`) is a general-purpose multilingual encoder with **no fine-tune on the doctrine corpus**; the paper's F8 is exactly this, graded Strong (Gupta et al. 2023; FinMTEB). Mitigated, not eliminated, by three layers: doctrine-term normalisation (F5 above), doctrinal synonym expansion at query time (`backend/rag/nodes/keyword_injection.py:inject_doctrine_keywords`), and curated OKF doctrine injected as documents. | Med | None cheap. Measure first: compare hybrid recall on doctrine-vocabulary queries vs plain-language ones. A fine-tune is not a small fix. |
| Retrieval | **F9** Multi-Hop Reasoning Gaps (§5.3, Strong) | **partial** | `decompose_query` runs (merged into `navigate_and_hyde`, `backend/rag/nodes/retrieval.py`) and is a real defence. But per root `CLAUDE.md`, KG-expansion output is appended **last** to `expansion_queries` then truncated to `remaining_budget = 2 - len(primary_queries)`, which is **0 whenever the query decomposed into 2+ sub-queries** — i.e. the multi-hop enrichment is discarded precisely on multi-hop queries. Not re-verified line-by-line this pass (file is owned by another agent). | Med | Raise the expansion budget, or order KG-derived queries ahead of the truncation point. Owned by the concurrent agent. |
| Retrieval | **F10** Graph RAG Trade-offs (§5.3, Moderate) | **yes** | Three compounding facts. (a) 4,030 of 4,082 live edges are LightRAG's generic `DIRECTED` (root `CLAUDE.md`, measured 2026-09-12) — topological co-occurrence, not typed doctrine, so the structural signal the paper's trade-off assumes you are *buying* is largely absent. (b) LightRAG context is hard-truncated at `rag_lightrag_context_max_chars = 1500` (`backend/app/config.py:805`, unset in `.env`) and reportedly hits the cap on every query, so it is cut mid-content at a fixed byte boundary. (c) The graph document enters retrieval at a **constant fabricated relevance**, `rag_graph_context_score = 0.35` (`backend/app/config.py:786`) — it does not compete on measured similarity, so it can displace a genuinely-scored teaching. The paper's structure-vs-content trade-off (Six et al. 2025) is being paid without the structure. | Med | Measure the graph lane's contribution with the F21 fix below, then decide. Do not tune the cap blind. |
| Retrieval | **F11** Low Recall / Ranking Failures (§5.3, Moderate) | **yes** | Measured **R@1 = 0.2326** on corrected labels (given). Retrieval fans out to `RAG_TOP_K_RETRIEVAL=24` (`backend/.env:91`) where recall saturates at 0.917, then the reranker cuts to `RAG_TOP_K_RERANK=5` (`backend/.env:92`). The gap between 0.917@24 and 0.2326@1 is *ranking*, not candidate generation — the reranker, not the retriever, is where the answer is decided. The standalone BM25 lane is off (`BM25_RETRIEVAL_ENABLED=false`, `backend/.env:155`), though bge-m3's own sparse vector still runs. | **High** | Nothing to "fix" blind — this is the reranker's job. Measure reranker-only ordering quality (rank of gold within the 24 candidates before vs after rerank) to confirm the reranker is the bottleneck, then tune or replace it. |
| Retrieval | **F12** Position-of-Gold Bias (§5.3, **Strong**) | **yes** | `sort_docs_canonically()` sorts the prompt's documents by **sha256 hash** (`backend/rag/doc_utils.py:76-83`), explicitly discarding "vector similarity score ordering across queries", to unlock 85–95% prompt-cache hit rates. The most relevant document therefore lands at a *uniformly random* position in the knowledge block. The paper grades this Strong (Byerly & Khashabi 2025: 34% accuracy gain from position-aware reordering). Mitigating fact: the block holds ~5 reranked docs, so the U-shaped attention penalty is far smaller than in the 400-fact contexts the cited work studies — this is a real but bounded exposure, and the trade-off is deliberate and documented. | Med | Sort the *surviving* docs by `rerank_score` descending instead of by hash, or keep hash order but pin rank-1 first. The cache benefit degrades; measure whether the ~24s p50 can absorb it. |
| Generation | **F13** Hallucination Despite Context (§5.4, Strong) | **no — defended, unusually well** | LettuceDetect span-level faithfulness with `faithfulness_floor = 0.6`, tier-gated CoVe for tier3/tier4 and compulsorily for any tier scoring below 0.6 (`backend/rag/nodes/verification.py`). Four subtle defects that made the gate vacuous were found and fixed (root `CLAUDE.md`, "Faithfulness verification" §): lexical reflection no longer vetoes, verdicts carry `semantic: bool` and are only reused when semantically derived, the detector reports supported-claim ratio rather than `1 - max_span_confidence`, and citation markup is stripped before scoring. Empty-context short-circuit skips the LLM entirely. | — | — |
| Generation | **F14** Conflicting Info Unresolved (§5.4, Strong) | **no — defended** | An explicit contradiction engine: `resolve_contradictions()` detects conflicts between vector chunks and graph entities and resolves via an authority hierarchy, emitting `contradiction_detected` / `contradiction_resolved_via` / `conflicting_sources` / `chosen_authority_rank` (`backend/rag/nodes/generation.py:887-907`, `backend/rag/nodes/contradiction_resolver.py`), gated on `contradiction_resolution_enabled` default `True`. Note the resolution metadata shares F21's fate — it is computed but not surfaced to the caller. | — | (see F21) |
| Generation | **F15** Incomplete / Partial Answers (§5.4, Moderate) | **yes — by design** | `_redact_unsupported_sentences` ships the grounded sentences and drops the unsupported ones (route `grounded_redacted`, root `CLAUDE.md`). This is a **deliberate trade of F15 against F13**, and for a doctrine system it is the right direction — but it is still the paper's F15, and the seeker is not told which part of their question went unanswered. Guard rails exist: it declines to salvage a mostly-ungrounded draft or one leaving under ~120 chars, falling through to `grounded_partial_evidence`. | Med | Emit a machine-readable count of redacted sentences alongside the answer so the UI can say "part of this could not be grounded", rather than silently returning a shorter answer. |
| Generation | **F16** Incorrect Specificity (§5.4, Moderate) | **UNKNOWN** | Tier routing (fast/standard/deep) and `response_preferences` (`mode`, `action_depth`, `include_practice`) exist and shape answer depth (`backend/app/pipeline/stages/glue_stages.py:_guidance_plan`). Whether output granularity actually tracks query intent is **not measured anywhere** in this repo. | — | Would need a labelled specificity eval; the 589-item golden set has no granularity assertions. |
| Generation | **F17** Wrong Output Format (§5.4, Limited) | **no — defended** | Citation integrity is enforced end-to-end: `remap_citation_markers()` rewrites inline `[N]` after diversity-reordering and URL-dropping shift positions (`backend/rag/nodes/utils.py:1112-1145`), out-of-range and URL-less markers are dropped, and `orphan_citations_stripped` / `citations_verified` are tracked. `grounding_state` is a closed `Literal` widened to match every state the pipeline actually emits (`backend/app/schemas/__init__.py:288-300`). | — | — |
| **Evaluation** | **F18** Metric Inadequacy (§5.5, Strong) | **yes — worst exposure in the audit** | See §2 below for the full argument. In short, three code-proven defects in the **retrieval** golden set (`scripts/eval/retrieval_golden_baseline.py`): questions are authored by `llm._generate_fast` (`:117`) → `self._cls_model` = `meta-llama/llama-3.1-8b-instruct` (`backend/.env:38`), **the same model** that runs `batch_grade_relevance` in production (`backend/services/openrouter_service.py:1117` → `_generate_fast`); the prompt orders the generator to "use the excerpt's own distinctive vocabulary" (`:36-41`), deliberately leaking lexical overlap into a query scored against a **sparse-lane** retriever; and relevance is **single-gold binary** (`_ndcg_at_k` docstring, `:69-74`) over a corpus of near-duplicate teachings. **Important scoping:** this does **not** apply to the 589-item end-to-end golden set, which is hand-written (`backend/scripts/build_comprehensive_golden_qa_bank.py`, a literal `DATA = [...]` list) with `must_mention`/`reject_if` assertions and runs as a blocking nightly gate. The circularity is confined to the retrieval metric — which is exactly the metric used to tune prefetch multiplier and `rag_top_k_retrieval`, and exactly the one whose labels were just found wrong. | **Critical** | Two cheap, high-value changes: (1) report `lenient_recall_at_k_same_source` — already computed at `:168-170` and already the more honest number — as the headline instead of strict R@1; (2) generate the questions with a model *outside* the pipeline (not `_generate_fast`) and delete "use the excerpt's own distinctive vocabulary" from `QUESTION_PROMPT`. Neither needs new infrastructure. |
| **Evaluation** | **F19** Lack of Continuous Monitoring (§5.5, Limited) | **partial** | Genuinely defended at the generation stage: `.github/workflows/hallucination-anomaly.yml` runs `scripts.ops.hallucination_anomaly` on a daily `0 4 * * *` cron, and the script **fails closed** — "an empty window is indeterminate, never a pass" (`backend/scripts/ops/hallucination_anomaly.py:126`), which is the correct handling of the known silent-`SUPABASE_URL` trap. Plus nightly `eval-gate.yml` (02:00) and `nightly-eval.yml` (02:00). **The gap is stage coverage, not scheduling:** every monitor watches generation-stage outputs (`hallucination_rate`, `faithfulness_p50`) or end-to-end answers. Nothing monitors retrieval quality, per-lane contribution, or index-contract drift in production — the paper's cascade blindness (§6.2) in its textbook form. | Med | Add retrieval-stage metrics to the daily job (`source_count` distribution, `top_source_score` p50, zero-source rate) — `AnswerEvidence` already carries all three (`backend/app/pipeline/stages/glue_stages.py:90-122`). |
| Deployment | **F20** Latency / Cost Bottlenecks (§5.6, Moderate) | **yes** | ~24s p50 with `generate_answer` at 10.7–19.6s (given), against `PIPELINE_TIMEOUT=300` (`backend/.env:43`). Throughput 0.199 QPS at concurrency 6 (root `CLAUDE.md`), i.e. below the 5–15 QPS the repo's own 1k-tier SPOF policy targets. Cost is instrumented (`services/cost_tracker.py`, `CHAT_COST` log line, $0.00046–$0.00179/query). Known-good caveat from `CLAUDE.md`: provider variance (12.1s → 24.3s on identical code) swamps config changes, so single-sample latency tuning is invalid. | **High** | Owned by the concurrent agent. Do not tune against single OpenRouter samples. |
| Deployment | **F21** Auditability Gaps (§5.6, Moderate) | **yes** | **Proven exactly as measured.** `POST /api/chat` builds its `ChatResponse` at `backend/app/api/chat.py:724-759` and passes **neither** `evaluation_trace` **nor** `retrieval_metadata`. `ai_provenance` is declared on the schema (`backend/app/schemas/__init__.py:320`) and assigned **nowhere in production code** — only in `backend/tests/test_provenance_api.py` — so it is structurally always `null`. The data is not missing, it is *withheld*: `PipelineResult.evaluation_trace` is populated (`backend/app/pipeline/stages/glue_stages.py:566`) and carries `retrieval_lane` (`backend/rag/nodes/retrieval.py:1150`), `retrieval_metadata` carries `chunk_ids`/`source_docs`/`scores` (`backend/app/pipeline/pipeline_coordinator.py:609-618`), and both are forwarded — but only to the **telemetry sink** (`backend/app/orchestrator.py:202,215`), whose failure mode is a single log line per request (root `CLAUDE.md` Gotchas). Two residual gaps even after the data is exposed: `_build_retrieval_meta` has **no lane field** at all, and `AnswerEvidence` reports only aggregates (`source_count`, `top_source_score`) with no per-document provenance (`glue_stages.py:90-122`). OKF docs are distinguishable via `metadata.type == "okf"` (`retrieval.py:1051`); Qdrant dense vs sparse is not distinguishable anywhere. | **Critical** | Two lines in `backend/app/api/chat.py:724`: add `evaluation_trace=result.evaluation_trace,` and `retrieval_metadata=result.retrieval_metadata,`. Then add a `lane` key per citation in `_build_retrieval_meta` (`pipeline_coordinator.py:609`). |
| Deployment | **F22** Domain Portability Degradation (§5.6, Moderate) | **partial** | Single-domain by design, so the mode does not bite today. The live risk is the *planned* second corpus: the recorded architecture decision is a **unified** tenant (`tenant_id='oneness'` for all teachers, Amma Bhagavan distinguished by `corpus_id`/`teacher_id`, cross-teacher queries desirable — `backend/domain/spiritual_ontology.py`, root `CLAUDE.md`). A second teacher's vocabulary entering one embedding space and one OKF bundle is exactly F22. | Low (today) | None now. Re-audit before the second corpus lands. |
| Deployment | **F23** PII / Compliance Leaks (§5.6, Moderate) | **no — defended** | `PIIScrubber.scrub` is applied field-by-field on both the direct and replayed telemetry paths, including recursively into nested dicts such as `evaluation_trace`, with non-string values left untouched (`backend/app/telemetry_sink.py:274-297`, self-check at `:658-670` asserting `[EMAIL]`/`[PHONE]` substitution). GDPR export and `services/compliance_logger.py` exist. | — | — |
| Deployment | **F24** Prompt Sensitivity (§5.6, Moderate) | **partial** | Prompts are versioned and rollback-able — `PromptStore` keeps immutable semver snapshots with an active version per name and `store.rollback(name, version)` (`backend/services/prompt_store.py:1-25`). That is more than most systems have. But nothing **measures** sensitivity: there is no A/B or variance harness comparing answer quality across prompt versions, so a regression is only visible once it moves the nightly faithfulness number. | Low | Reuse the 589-item golden set as a prompt-version A/B; `services/ab_testing.py` already exists. |
| Deployment | **F25** Authorization / Policy Failures (§5.6, Moderate) | **no — defended, unusually well** | `backend/tests/test_authz_regression.py::test_no_admin_route_is_anonymous` mechanically forbids any admin route from using `get_optional_user`, and its `_requires_identity` + source-level `resolve_anon_identity` check exists specifically to stop every anonymous caller collapsing onto the literal string `"anonymous"`. `backend/tests/test_cross_tenant_leak_probe.py` (5/5 passing) covers cross-tenant and cross-teacher isolation; 100% of 12,904 Qdrant points and 4,128 Neo4j edges were stamped with explicit `teacher_id`/`tenant_id` on 2026-09-13, and `ontology_writer.py` now fails closed with `OntologyWriteError`. | — | — |
| Agentic | **F26** Planning Failures (§5.7, Limited) | **partial** | A planner exists: `decompose_query` splits atomic sub-queries, and the 3-lane query-adaptive planner selects fast/relational/deep (`backend/rag/nodes/retrieval.py:1097-1150`). Plan quality is unmeasured — the paper's suggested proxy (plan length vs query complexity) is not instrumented. Bounded, so a bad plan costs latency, not runaway. | Low | `retrieval_lane` is already in `evaluation_trace`; once F21 is fixed, lane-vs-tier mismatch becomes measurable for free. |
| Agentic | **F27** Tool Selection / Execution Errors (§5.7, Limited) | **no — defended** | Every optional lane is fail-open by contract — "the graph must never cost an answer" (root `CLAUDE.md`), with per-lane timeouts `rag_graph_context_timeout = 3.0` and `rag_lightrag_context_timeout = 4.0` (`backend/app/config.py:783,795`), circuit breaking (`services/circuit_breaker.py`, `CircuitBreakerStage`), and documented degradation invariants for Redis/Neo4j/Qdrant. | — | — |
| Agentic | **F28** Context Memory Degradation (§5.7, Limited) | **no — defended** | The cross-query leak this mode names is the repo's single most carefully guarded invariant: `cache_key` is `(language, message)` with **no `user_id` and no `tenant_id`**, so `CacheUpdateStage` refuses to cache any answer personalised with `memory_context`, via a single-source-of-truth predicate `_is_personalization_eligible` (`backend/app/pipeline/stages/cache_stage.py:32-55,214,291,349,498`) with a regression test (`backend/tests/test_cache_personalization_leak.py`) and a live cross-user probe. Independently, the stale-cache half of the mode is moot on the live config: `EXACT_CACHE_ENABLED`, `SEMANTIC_CACHE_ENABLED` and `DOCTRINE_CACHE_ENABLED` are all `false` (`backend/.env:102-104`). | — | — |
| Agentic | **F29** Multi-Agent Coordination Failures (§5.7, Limited) | **no — not applicable** | Single orchestrator, one ordered stage chain (`backend/app/pipeline/stages/pipeline_builder.py:36-53`). No inter-agent negotiation, no deadlock surface. | — | — |
| Agentic | **F30** Recursive Hallucination Cascades (§5.7, Limited) | **no — defended** | The only recursive path is CRAG's rewrite loop, and it is both **capped** (`RAG_MAX_REWRITES=2`, `backend/.env:93`; `rag_indic_max_rewrites` default 1, `ge=0, le=3`, `backend/app/config.py:725`) and **gated by the faithfulness check before it can recur** — a fabricated intermediate cannot seed the next round unguarded. `agentic_graph_traversal` is off (`agentic_graph_traversal_enabled=False`). | — | — |
| Agentic | **F31** Unbounded Cost / Latency Spirals (§5.7, Limited) | **no — defended** | Every loop carries a hard bound: `rag_max_rewrites` (`config.py:699`), `agentic_graph_max_steps = 3` (`:1310`), `rag_deep_research_max_depth = 2` (`:1269`), `PIPELINE_TIMEOUT=300` and `LLM_TIMEOUT=60` (`backend/.env:42-43`), plus per-node timeouts from `rag/timeout_utils.py`. Cost per query is tracked and bounded in the measured range. | — | — |
| Agentic | **F32** Unsafe Reasoning Chains (§5.7, Limited) | **no — defended** | Composite-level safety is checked at both ends of the chain, not only per step: `InputGuardrailStage` before and `OutputGuardrailStage` after generation (`backend/app/pipeline/stages/pipeline_builder.py:36-53`), plus distress detection (`services/serene_mind_engine.py`) which routes through the full pipeline rather than bypassing it, and 154 adversarial-refusal + 24 safety-regression probes in the blocking golden set (`backend/evaluation/golden_dataset.json`). | — | — |
| Agentic | **F33** Attribution & Governance Gaps (§5.7, Limited) | **yes** | Same root cause as F21, at the semantic layer the paper distinguishes. A claim in a redacted or graph-augmented answer cannot be traced to the lane that produced it by any API consumer: `ai_provenance` is always `null` (`backend/app/schemas/__init__.py:320`, unassigned in production), `contradiction_meta` (`backend/rag/nodes/generation.py:889-893`) is computed and never surfaced, and the paper's own suggested proxy — attribution coverage rate — is therefore unmeasurable end-to-end. `provenance_manifest` *is* emitted (`backend/app/api/chat.py:758`), so the EU AI Act Article 50 disclosure obligation is met; it is the per-claim source trace that is missing. | Med | Falls out of the F21 fix. Additionally pass `contradiction_meta` through `_build_response_data`. |

---

## 2. Top 5 exposures, ranked by damage to a seeker's answer

Ranked by what actually degrades an answer, not by taxonomy order.

### 1. F18 — the retrieval golden set is scored by a component of the system it is grading

This is first because it is the failure that **hides all the others**. Three
defects, each independently provable:

**The question author is the production grader.** `retrieval_golden_baseline.py:117`
calls `llm._generate_fast(...)`. `_generate_fast` resolves to `self._cls_model`
(`backend/services/openrouter_service.py:1103`), which on the live config is
`meta-llama/llama-3.1-8b-instruct` (`backend/.env:38`). The production CRAG
relevance grader, `batch_grade_relevance`
(`backend/services/openrouter_service.py:1117`), calls the *same*
`_generate_fast` and therefore the *same* model. A question this model finds
natural to write from a chunk is a question it will find natural to grade that
chunk relevant to. Whatever this model cannot see in a teaching, it will neither
ask about nor penalise.

**The prompt leaks the answer's vocabulary into the query.**
`QUESTION_PROMPT` (`:36-41`) instructs: *"Use the excerpt's own distinctive
vocabulary."* The retriever under test is hybrid dense **+ sparse** — the
harness explicitly passes both vectors (`:135-138`) because measuring dense-only
"understates real recall". So the benchmark deliberately manufactures lexical
overlap between query and gold chunk, and then measures a lexical retriever on
it. A seeker asking *"why do I keep suffering?"* shares no distinctive
vocabulary with any chunk. The benchmark cannot see that seeker.

**Relevance is single-gold and binary over a near-duplicate corpus.**
`_ndcg_at_k` scores "single relevant document, binary relevance" (`:69-74`) —
only the originating chunk counts. The corpus is one teacher's talks, where the
same teaching recurs across many videos. A retriever returning a *better* chunk
for the same question scores zero. This is the direct mechanical explanation for
why relabelling moved recall more than the retrieval tuning it was validating:
the tuning was real, and the labels were wrong in the same direction.

**What makes this Critical rather than merely wrong:** two production settings
were tuned against this set (prefetch multiplier 1.0→3.0, `rag_top_k_retrieval`
12→24) and are now pinned by `backend/tests/test_retrieval_tuning_baseline.py`.
A miscalibrated benchmark has been promoted into a regression gate.

**What the paper does and does not give you.** F18 as written is about *metric
choice* (BLEU/ROUGE/EM), not test-set provenance — it does not name this. §6.5
does: "the test set itself does not represent production queries" is the
paper's own diagnostic signal, and its worked example ends with a cascade that
"the test set… was therefore unable to surface". The taxonomy has a hole here,
and this repo is sitting in it. Do not cite F18 as though the paper predicted
this; cite §6.5.

**Mitigating fact, stated for fairness:** the *end-to-end* 589-item golden set
is hand-written (`backend/scripts/build_comprehensive_golden_qa_bank.py` is a
literal `DATA = [...]` list) with `must_mention`/`reject_if` assertions across
doctrinal/comparative/multilingual/adversarial/safety categories, and it gates
nightly. The circularity is confined to the retrieval metric. That confinement
is the reason this is fixable in an afternoon.

### 2. F21 / F33 — no retrieval provenance reaches any API consumer

`backend/app/api/chat.py:724-759` constructs the response and omits
`evaluation_trace` and `retrieval_metadata`; `ai_provenance`
(`backend/app/schemas/__init__.py:320`) is assigned nowhere outside tests.

The diagnosis matters more than the symptom: **the data is not missing, it is
withheld.** `evaluation_trace` is populated with `retrieval_lane`
(`backend/rag/nodes/retrieval.py:1150`), `retrieval_metadata` carries
`chunk_ids`/`source_docs`/`scores`
(`backend/app/pipeline/pipeline_coordinator.py:609-618`), `contradiction_meta`
records which authority resolved a conflict
(`backend/rag/nodes/generation.py:889-893`) — and all of it is forwarded only to
the telemetry sink (`backend/app/orchestrator.py:202,215`), whose documented
failure mode is one log line per request.

Ranked second because it is the enabling condition for #1 and #3. A grader who
cannot see whether an answer came from Qdrant, OKF, Neo4j or LightRAG cannot
perform the upstream trace the paper's §6.4–6.5 diagnostic procedure requires —
which is cascade blindness (§6.2) by construction. It is also the cheapest fix
in this document: two keyword arguments.

Residual work after those two lines: `_build_retrieval_meta` has no `lane` field
at all, and Qdrant dense vs sparse is not distinguishable anywhere in the
codebase. OKF is (`metadata.type == "okf"`, `retrieval.py:1051`).

### 3. F11 — ranking, not recall, is deciding the answer

Recall@24 is 0.917 and R@1 is 0.2326. The gold document is almost always *in*
the candidate set and almost never *first*. The pipeline retrieves 24
(`backend/.env:91`) and reranks to 5 (`backend/.env:92`), so the reranker
decides what the seeker reads.

Third because it is the largest real quality gap — but only third because,
until #1 and #2 are fixed, **any change here will be measured by the broken
benchmark and attributed by an invisible trace.** Fixing this first is how you
tune into noise. Note also that the 0.2326 figure inherits #1's single-gold
label problem, so the true ordering quality is likely better than 0.2326 and
worse than the lenient number — which is itself an argument for fixing #1 first.

### 4. F6 — index-compatibility enforcement is written, tested, and switched off

`backend/app/config.py:929-930` default both enforcement flags to `False`, and
neither appears in `backend/.env` or `.env.example`. Startup therefore
`logger.critical`s an incompatible index and boots
(`backend/app/main.py:389-392`), or `warning`s a missing contract and boots
(`:396-399`).

The live configuration makes this concrete rather than theoretical:
`EMBEDDING_BACKEND=onnx_int8` (`backend/.env:10`) against a `flagembedding`
default (`config.py:415`). INT8-quantised and fp32 bge-m3 produce different
vectors for identical text. The per-point payload stamps `embedding_model` but
not backend (`backend/services/qdrant/indexer.py:266-268`), and the startup
guard compares **dimension only** (`backend/services/qdrant/client.py:_verify_collection_dimension`)
— both backends are 1024-dim, so both pass.

This is the paper's most-neglected stage (representation: 0/2 Strong) and its
most insidious property applies verbatim: §5.2 — such failures "degrade
retrieval quality while remaining invisible to generation-level metrics, making
them hard to detect and easy to misattribute to later stages." If this is live,
it is silently depressing the very R@1 in #3.

**I could not determine whether the live index was actually built with a
different backend** — that needs a Qdrant payload scan or the Redis contract
key. The exposure is that nothing would tell you either way.

### 5. F10 — the graph lane is paying the trade-off without buying the structure

Three facts compound. 4,030 of 4,082 edges are generic `DIRECTED` — topological
co-occurrence, not typed doctrine. LightRAG context is hard-truncated at 1500
chars (`backend/app/config.py:805`) and reportedly hits the cap every time, so
it is cut mid-content at a fixed byte offset. And the graph document is injected
at a **constant fabricated relevance** of 0.35 (`backend/app/config.py:786`) —
it does not compete on measured similarity, so it can displace a
genuinely-scored teaching from a 5-document budget.

The paper's F10 trade-off (Six et al. 2025) is structural coherence *bought at
the cost of* content coverage. Here the coverage is being spent and the
coherence largely is not there to receive it. The repo already has the
countervailing datum — injecting 5k characters of uncapped graph text dropped
faithfulness from 1.0 to 0.50 on one query — which is why the cap exists. Fifth
rather than higher because the lane is fail-open and capped, so the blast radius
is one displaced document, not a wrong answer.

---

## 3. What this repo handles unusually well

Six defences worth recording, because the paper's value is as much in confirming
a defence as in finding a gap.

**F5 — doctrine-term normalisation applied at three points, not one.**
`backend/services/doctrine_terms.py` holds 161 corrections as a single source of
truth and applies them at Whisper's initial prompt (preventing the error),
at ingest, and at generation output — with `apply_corrections_with_ledger()`
giving a reversible audit trail. It exists because the corrections had
previously been duplicated across three modules and drifted, so "Acam" was fixed
everywhere and "Akam" nowhere. The paper grades F5 **Limited** — no RAG-specific
study ties tokenizer fragmentation to retrieval failure, and evidence comes only
from adjacent cross-lingual work where fixing it moved recall@1 from 0.104 to
0.430. This repo built a defence for a failure mode the literature has not yet
studied, in the *right* place: upstream, at prevention rather than correction.

**F28 — the cache-personalisation invariant.** `cache_key` is `(language,
message)` with no `user_id` and no `tenant_id`, and every tier is process- or
Redis-wide. Rather than retrofitting keys, the repo forbids caching any
personalised answer through one predicate,
`_is_personalization_eligible` (`backend/app/pipeline/stages/cache_stage.py:32-55`),
consulted at all four decision points (`:214, :291, :349, :498`), with a
regression test and a live cross-user probe. `_probe_has_memory` also probes
`canonical_memories`, because a seeker whose only memories are canonical would
otherwise read as ineligible and get served a stranger's generic answer. That
last detail is the kind of thing normally found in an incident report.

**F13 — a faithfulness gate that was audited for vacuousness.** Four defects
each made the gate *look* like it was working: lexical reflection vetoing
faithful paraphrase, verify paths reusing reflection's lexical verdict so
`semantic=True` was unreachable in production, a detector score of
`1 - max_span_confidence` that one confident span drove to zero, and citation
markup being scored as claims. Finding all four requires distrusting a passing
metric, which is exactly the discipline the paper's §6.2 cascade blindness
argues for.

**F25 — authorization enforced by mechanical tests, not convention.**
`test_no_admin_route_is_anonymous` forbids the substitution at the source level
rather than testing routes one by one, and `_requires_identity` +
the `resolve_anon_identity`-in-source check exists specifically because omitting
that call collapses every anonymous caller onto the string `"anonymous"`. The
paper grades F25 Moderate and notes authorization is "a primary retrieval-layer
risk" (Ammann et al. 2025). This is a stronger defence than the literature it is
defending against.

**F31 / F30 — every loop is bounded, and the bounds are in config.**
`rag_max_rewrites`, `agentic_graph_max_steps=3`, `rag_deep_research_max_depth=2`,
`PIPELINE_TIMEOUT`, `LLM_TIMEOUT`, per-node timeouts with safety margins. The
paper grades all 8 agentic modes Limited and calls them an "evidence desert";
this repo is defended against the two most dangerous ones essentially by
construction.

**F19 — a monitor that fails closed on no data.** `hallucination_anomaly.py:126`:
"an empty window is indeterminate, never a pass." A silently-empty telemetry
table is the classic way a monitor reports health while measuring nothing, and
this one refuses. The gap is coverage (generation-stage only), not correctness.

---

## 4. Honest limits of this audit

- **Nothing was executed.** No live Qdrant scan, no Neo4j count, no request
  traced end to end. Every verdict is static reading plus the measurements
  supplied as given.
- **Three files were read but not re-derived.** `rag/nodes/retrieval.py`,
  `rag/nodes/generation.py` and `services/lightrag_service.py` are owned by a
  concurrent agent. Claims about them cite either line numbers read this pass or
  root `CLAUDE.md`, and F9's truncation claim rests on `CLAUDE.md` rather than a
  line-by-line re-verification — treat it as the weakest verdict here.
- **F16 is UNKNOWN and should stay that way** until something measures answer
  granularity against query intent.
- **F6's severity assumes the worst case** that the corpus was indexed with a
  different embedding backend than it is queried with. That is unproven. What is
  proven is that nothing in the running system would detect it.
- **F3's severity assumes the corpus is transcript-dominant.** The PDF-derived
  share was not measured.

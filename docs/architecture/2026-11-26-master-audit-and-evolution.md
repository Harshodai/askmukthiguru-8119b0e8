# Ask Mukthi Guru — Master Audit, Architecture Research & Evolution Report

**Date:** 2026-11-26  
**Scope:** End-to-End Current-State Audit (A), Competitor Intelligence (B), Architecture Research (C), Harness & Retrieval Design (D), Knowledge & Ingestion Design (E), Product Opportunity Report (F), Evaluation Report (G), Implementation Report (H), Production-Readiness Assessment (I), and Prioritized Remaining Work (J).

---

## A. Current-State Audit (Reality vs Documentation)

### A.1 Verified Implementation Inventory

| Capability | Classification | Evidence (Code / Live DB / Runtime) |
|---|---|---|
| **YouTube Video Verbatim Serving** | Implemented & verified operational | `first_person_batch_pipeline.py`, `FirstPersonContextStore`, `first_person_v13_shadow` (4,730 pts), `214 + 188` passing tests |
| **Input/Output Safety & Tele-MANAS Crisis Rail** | Implemented & verified operational | `InputGuardrailStage → DistressStage → CircuitBreakerStage` (`pipeline_builder.py`); `421` `crisis_preempted` rows in `chat_queries` |
| **Multi-Format Source Support (Books, Audio, Websites)** | **Fixed in code (Phase 2 foundation); corpus ingestion pending** | Prior bug: `first_person_rights.py` rejected any item lacking `video_id`, causing `test_q7_four_sacred_secrets_abstains` to abstain; *Sufkor* absent on disk. Fixed in `first_person_rights.py` + `QdrantEvidenceAdapter` |
| **Canonical Evidence Registry & Rights SSoT** | **Designed / Schema Added; Live Tables Empty** | `source_releases` (0 rows), `corpus_sources` (0 rows), `corpus_takedowns` (0 rows) in Postgres; `corpus_gate_rejections` has 3,892 rows. New `canonical_evidence` + `evidence_corrections` + `corpus_sync_outbox` migration added |
| **Qdrant Vector + Hybrid Retrieval** | Implemented & partially drifted | 13 collections live; alias `first_person → first_person_v13_shadow` mixes `resegment-v2` (3,991), `transcript-v1` (556), `transcript-v2` (13), `160` `unverified` rights pts, `472` unverified speakers |
| **Memgraph Knowledge Graph** | Implemented but structurally incomplete | 2,760 `TUTeachingUnit` nodes, **0** `TU_HAS_CONCEPT` edges, **6** `TU_HAS_TOPIC` edges, **0** `Community` nodes (`6,423` orphan `community_id`s); out-of-lineage teachers (`Sadhguru`, `ISKCON`) in `seed_ontology.py` |
| **OKF / LLM Wiki** | Implemented but unverified & tag-skewed | `memory/okf/compiled.json` (493 entries, **0 verified**, ~80% `oneness`/`teaching` tags); `staging/` has 820 files; quarantined in new `OKFEvidenceAdapter` |
| **Semantic Understanding** | Duplicated / regex-heavy → **Upgraded** | `off_topic_stage.py` (16 `re.compile`), `first_person_content_assessment.py` (18 `re.compile`), `first_person_bridge.py` (12 `re.compile`); live bereavement query hit `crisis_preempted`. New `SemanticUnderstandingEngine` built |
| **Seeker Personal Memory & Comprehension Recovery** | Memory DB inactive locally; Recovery **newly built** | `canonical_memories` (0 rows), `memory_consent_receipts` (0 rows); RLS + 26-table `cascade_erasure.py` verified; new `ComprehensionRecoveryService` + isolated cache keys built |
| **Editorial Intelligence Platform** | Absent in POC → **Core Engine + API + UI Built** | Zero prior editorial endpoints/workflows (`editorial_set` was seeker facet selector). Built `EditorialIntelligenceService`, `/api/editorial/*`, and `/admin/editorial` Workbench |
| **Evaluation & Self-Optimizer** | Partially functional → **Upgraded** | `fp_rank_metrics.py` lacked graded 0–3 NDCG; `first_person_graph_ablation.py` used `_mock_retrieve()`. Added `graded_ndcg_at_k` + `ControlledRetrievalOptimizer` |
| **CI/CD & Container Builds** | Broken / manual-only → **Fixed** | 16 workflows `workflow_dispatch`-only; `frontend/Dockerfile` wrong Nginx root. Fixed both |

### A.2 Live Runtime & Latency Truth (`public.chat_queries`, 11,871 rows)
- `first_person_abstain`: **6,815** queries (avg **5.43s**, p95 **12.86s**)
- `first_person_bridge`: **3,024** queries (avg **8.30s**, p95 **20.30s**)
- `blocked` (error): **991** queries
- `crisis_preempted`: **421** queries (avg **1.34s**, p95 **3.72s**)
- **Diagnosis:** 69% of first-person chat turns abstained, and even abstentions burned 5.4–12.9s due to serial/parallel HyDE + Memgraph sizing + relevance LLM judge overhead, plus book/website exclusion.

---

## B. Competitor Intelligence Report (Verified 2026-11-26)

Researched 8 named competitors + 4 adjacent benchmarks via live web search (`search_web` 2026-11-26): **Delphi** (`delphi.ai`), **Anabasis Intelligence / Living Library** (`anabasisintelligence.com`), **Preachly AI** (`preachlyai.com`), **Odicity** (`odicity.com`), **Mindar** (`mindar.ai`), **Editstra** (`editstra.in`), **Reformeer AI** (`reformeer.org`), **Personal AI** (`personal.ai`), plus **Google NotebookLM**, **Moments Lab**, **Atlas Workspace**, **Cutsio**, and **PulpitAI / Sermonly**.

- **What to adopt:** Editstra's `Story Brief → Editorial Frame → Output Studio` gated state machine; Odicity's `ODI Research` evidence dossier workspace; Cutsio/Moments Lab's sentence-level timestamped clip export; Delphi's seeker-question analytics loop.
- **What to avoid rebuilding:** "Digital mind" voice/personality cloning impersonating the teachers in unverified prose (creates doctrinal and trust liability); generic NLE video timeline editing.
- **Defensible Moat:** Cryptographically hash-verified verbatim quotes + acoustic speaker verification + multi-format (books + timestamped videos + interviews) knowledge graph + epistemic separation (Evidence / Interpretation / Synthesis / Application) + Seeker Comprehension Recovery + Claim-Mapped Editorial Studio.

*(Full 14-dimension Competitor Matrix is documented in [poc_audit_and_architecture_report.md](file:///Users/harshodaikolluru/.gemini/antigravity/brain/0ebc06bf-8a02-4473-b688-50fe4b0849ff/poc_audit_and_architecture_report.md#L168-L195).)*

---

## C. Architecture Challenge & Target Design (Challenging Qdrant, Memgraph, OKF, LangGraph)

1. **Challenge to OKF (`memory/okf/compiled.json`):**
   - *Finding:* OKF is a 10.4 MB flat JSON vector index of 487 LLM-extracted summaries (`verified: None`, 80% generic `oneness`/`teaching` tags). In general RAG it injects unverified summaries as `"polished_speech"`; in first-person it acts as a noisy tag filter.
   - *Architectural Verdict:* **Do NOT treat OKF as a third runtime vector store.** Quarantine unverified OKF entries (`OKFEvidenceAdapter`), store full source transcripts/chapters in Postgres `canonical_evidence` (or object storage), and repurpose OKF strictly as an **editorial human-curated Markdown/wiki export** rather than a primary retrieval database.
2. **Challenge to LightRAG + Memgraph Duplication:**
   - *Finding:* `lightrag_vdb_*` (12,882 Qdrant points) and `6,427` Memgraph `:base` nodes sit idle alongside `2,760` `TUTeachingUnit` nodes that have **0** `TU_HAS_CONCEPT` edges.
   - *Architectural Verdict:* Retire the redundant LightRAG Qdrant collections once offline parity is confirmed; keep **Memgraph** ONLY if populated with verified `TU_HAS_CONCEPT` + cross-source (`Book ↔ Video`) relationships and HippoRAG-style Personalized PageRank / bounded multi-hop traversal (`MemgraphEvidenceAdapter`). Otherwise Postgres relational adjacency suffices.
3. **Challenge to Regex-Driven Routing:**
   - *Finding:* 50+ `re.compile()` blocks across `off_topic_stage.py`, `distress_stage.py`, `first_person_content_assessment.py`, and `first_person_bridge.py` cause brittle false positives (bereavement → crisis) and clip-fitted rules.
   - *Architectural Verdict:* Restrict regex strictly to acute self-harm safety rails, format/URL/timestamp parsing, and sanitization; move domain/emotion/confusion/comparative classification to `SemanticUnderstandingEngine` (embedding prototypes + bounded structured LLM disambiguation).
4. **Target Consolidated Stack:**
   - **PostgreSQL / Supabase:** Single source of truth for `canonical_evidence`, `source_releases`, `corpus_sync_outbox`, `editorial_*`, `seeker_comprehension_signals`, `canonical_memories`, `eval_runs`.
   - **Qdrant:** Unified hybrid dense (`passage_dense`) + sparse (`passage_sparse`) passage retrieval across videos, books, audio, and websites.
   - **Memgraph:** Governed Universal Teaching Ontology (with edge provenance + `rights_status = 'licensed'`) + Seeker Personal KG (`[:RELATES_TO]` only).
   - **Redis:** Version-isolated exact/retrieval caching + rate limits + job queues.

---

## D, E, F, G, H. Implemented Improvements & Verification Evidence (2026-11-26)

### Implemented Modules & Changes
1. **Multi-Format Rights Gate Fix:** `backend/services/first_person_rights.py` — unlocked `book`, `audio`, `podcast`, `website`, `course_event` verification while maintaining fail-closed security on videos without `video_id` and unregistered assets.
2. **Canonical Evidence Contract, Registry, Quality Gate & Unified Harness:**
   - `backend/domain/evidence_contract.py` (strict `EpistemicCategory`, `CanonicalEvidenceRecord`, `EvidenceCandidate`, `ClaimEvidenceMapping`)
   - `backend/services/canonical_evidence_registry.py` (`CanonicalEvidenceRegistry`, `IngestionQualityValidator`, immutable originals + versioned `EvidenceCorrection`, `corpus_sync_outbox` retry/DLQ recovery, `withdraw_source()`, stale index drift detection, and `build_replay_snapshot()`)
   - `backend/services/evidence_adapters/qdrant_adapter.py`, `memgraph_adapter.py`, `okf_adapter.py`, `fusion.py`, `claim_verifier.py`
   - `backend/services/unified_evidence_harness.py` (`UnifiedEvidenceHarness` 14-step controlled workflow across semantic interpreter, planner, parallel adapters, RRF dedup, bounded graph expansion, canonical verification, and epistemic packaging with graceful store-failure degradation)
3. **Semantic Understanding & Guardrail/Cache Wiring:**
   - `backend/services/semantic_understanding.py` (`SemanticUnderstandingEngine` + `plan_retrieval()`)
   - Wired bereavement grief de-escalation safeguard in `backend/app/pipeline/stages/distress_stage.py` (keeps acute ideation & `guardrail_self_harm` invariant)
   - Added `ontology_version` isolation to `PipelineCoordinator._build_context_aware_cache_key` (`backend/app/pipeline/pipeline_coordinator.py`)
4. **Seeker Comprehension Recovery & Cache Isolation:** `backend/services/seeker/comprehension_recovery.py` (10-step confusion recovery workflow + `build_isolated_cache_key`).
5. **Editorial Intelligence Platform (Backend + API + UI):**
   - `backend/services/editorial/editorial_service.py` (Research Dossier, Content Opportunity Discovery w/ ingestion-completeness honesty, `EditorialBrief`, `EditorialOutline`, Claim-Mapped Script Builder, audit log, Mandatory Human Approval & Publication Gate)
   - `backend/app/api/editorial.py` mounted in `backend/app/main.py` (`/api/editorial/*`, `_require_admin` gated, live `chat_queries` seeker-demand adapter)
   - `src/admin/pages/EditorialWorkbenchPage.tsx` (`/admin/editorial` Workbench w/ Dossier, Opportunities, Fact-Check, Project Brief/Outline & Human Approval controls) + routes in `src/App.tsx` & `src/admin/layout/AdminShell.tsx`
   - `src/components/common/SourcePlatformBadge.tsx` (`book` citation badge w/ chapter & page) + `src/integrations/supabase/client.ts` (`VITE_ALLOWED_EMAIL_DOMAINS`)
6. **Graded Evaluation, Optimizer, Live Benchmark & Reconciliation:**
   - `backend/evaluation/fp_rank_metrics.py` (`graded_dcg_at_k`, `graded_ndcg_at_k`) & `backend/evaluation/retrieval_optimizer.py` (`ControlledRetrievalOptimizer`)
   - `evals/evidence_platform_golden.jsonl` + `backend/evaluation/run_evidence_benchmark.py` (live corpus benchmark + optimizer sweep)
   - `backend/tests/test_part13_e2e_acceptance.py` (all 6 Part 13 E2E acceptance suites) & `scripts/ops/reconcile_stores.py`
7. **Database Migration & CI/Docker Fixes:**
   - `supabase/migrations/20261126000000_teaching_editorial_intelligence.sql`
   - `frontend/Dockerfile` (fixed `/usr/share/nginx/html/app`, Node 22, non-root `nginx`, `VITE_*` args)
   - `.github/workflows/lint-test.yml` (added `pull_request` and `push` triggers on `main`)

### Beyond Seeker & Editorial: Prioritized Additional User Domains (§1.C & §15)
1. **Course & Curriculum Designers:** Sequence `TUTeachingUnit` chains + book chapters into structured multi-week learning pathways with comprehension checkpoints (High Priority).
2. **Localization & Translation Teams:** Multilingual semantic alignment + verification that translated framing preserves verbatim original-language teacher quotes (Medium-High Priority).
3. **Archivists & Rights Governance Teams:** Unified `canonical_evidence` + `source_releases` + `corpus_sync_outbox` reconciliation dashboard with instant takedown propagation (Critical / P0 Foundation).
4. **Event & Program Teams:** Rapid pre-event topical dossiers surfacing exact clips & quotes matching retreat themes (Medium Priority, reuses `EditorialIntelligenceService`).

### Post-Edit Verification Ledger (Verified 2026-11-26)
- **Backend Regression, New Modules & Part 13 E2E Acceptance Suite (`cd backend && .venv/bin/pytest -q ... 14 suites`):** **619 passed, 1 skipped** in `9.54s` (includes `test_evidence_platform_and_adapters.py`, `test_semantic_comprehension_editorial_optimizer.py`, `test_part13_e2e_acceptance.py`, `test_cache_versioning_and_teaching_guard.py`, `test_cache_tenant_isolation.py`, `test_first_person_bridge.py`, `test_first_person_pipeline.py`, `test_first_person_context_*`, `test_repo_layout.py`).
- **Frontend TypeScript, Production Build & Unit Suite (`npx tsc --noEmit && npm run build && npx vitest run src/test/`):** Exited `0` — `vite build` + `scripts/prerender-seo.mjs` succeeded (`2519 modules`), and **180 test files / 1,160 tests passed** (verified after `EditorialWorkbenchPage` brief/outline/approval UI upgrade).
- **Live Read-Only Benchmark & Optimizer Sweep (`cd backend && .venv/bin/python -m evaluation.run_evidence_benchmark` on `first_person_v13_shadow` + Memgraph + OKF + BGE-M3 ONNX):**
  - **Baseline (`baseline_k60_top15`, 10 retrieval queries):** `Recall@5=0.90`, `Recall@10=0.90`, `MRR=0.80`, `graded nDCG@10=0.8262`, `source_diversity=1.96`, `duplicate_rate=0.0`, `p95=137.96ms` (`practice_howto=1.0`, `broad_thematic=1.0`, `editorial_research=1.0`, `narrow_factual=0.7539`, **`comparative_teachers=0.0`** — identifying dual-teacher query fan-out as next retrieval optimization target).
  - **Candidate (`expanded_k20_top30`):** `Recall@10=0.90`, `nDCG@10=0.8262`, `source_diversity=2.19`, `p95=29.82ms` — `ControlledRetrievalOptimizer` correctly **declined promotion** because ranking quality did not improve over baseline.
  - **Guard Benchmarks:** `out_of_scope` (`bench_11`) -> `abstained`; `crisis` (`bench_12`) -> `crisis_preempted`.
- **Live Adapter & Auth Gate Probes (Read-Only):**
  - FastAPI `TestClient`: `GET /api/editorial/projects` & `POST /api/editorial/opportunities` return `401 Unauthorized` unauthenticated; `_require_admin` override returns `200 OK`.
  - `MemgraphEvidenceAdapter` (`bolt://127.0.0.1:7687`): `get_concept_neighborhood` returned `10` concept relationships; `discover_by_concepts` returned `0` (confirming live Memgraph lacks `TU_HAS_CONCEPT` links to `TUTeachingUnit`).
  - `OKFEvidenceAdapter` (`memory/okf/compiled.json` via `_load_compiled_matrix`): loaded `493` entries (`0` verified, `1024`-dim); `include_unverified=False` returned `0` (quarantined) vs `5` when `include_unverified=True`.

---

## I. Production-Readiness Assessment (Honest Score: **4.5 / 10 — Pre-Staging / Not Production-Ready**)

| Dimension | Score | Basis |
|---|---|---|
| Safety & Crisis Rails | **8.0 / 10** | Sub-second acute preemption + input/output guardrails; bereavement vs crisis separation improved |
| Evidence Provenance & Governance | **5.0 / 10** | Strong video span hashes & new contract/schema; live `source_releases` (0 rows) & `first_person_v13_shadow` mixed schemas block promotion |
| Retrieval & Graph Intelligence | **4.5 / 10** | Hybrid Qdrant works; Memgraph lacks `TU_HAS_CONCEPT` edges; OKF unverified; books not yet re-indexed into `fp-context` |
| Seeker Intelligence | **5.5 / 10** | Mode-B encryption & RLS erasure solid; comprehension recovery newly built, needs live multi-turn E2E wiring |
| Editorial Intelligence | **4.0 / 10** | New service, API, & Workbench UI implemented and unit-tested; Postgres persistence & live corpus indexing pending |
| CI/CD & Operational Readiness | **4.0 / 10** | Auto PR CI & `frontend/Dockerfile` fixed; open `pip-audit` CVEs, unapplied migrations on hosted Supabase, unsigned human gates |

---

## J. Prioritized Remaining Work

1. **Must Fix Before Staging:**
   - Apply `supabase/migrations/20261126000000_teaching_editorial_intelligence.sql` and earlier unapplied local citation migrations to staging Supabase.
   - Populate `corpus_sources` and `source_releases` from `CONTENT-RIGHTS.md` and enable `RELEASE_FILTER_MODE=enforce`.
   - Rebuild a clean, schema-pure Qdrant `first_person_v14_shadow` collection (0 unverified rights/speakers, `corpus_version` aligned with `first_person_serving_contract.json`).
2. **Must Fix Before Production:**
   - Ingest *The Four Sacred Secrets* and *Sufkor* (once private asset path & rights sign-off confirmed) through the unified `canonical_evidence` + `BookDocumentConnector` pipeline.
   - Populate Memgraph `TU_HAS_CONCEPT` / `TU_HAS_TOPIC` edges from verified tags and purge out-of-lineage `seed_ontology.py` entities (`Sadhguru`, `ISKCON`).
   - Complete remaining unsigned human gates in `docs/reviews/2026-11-14-human-gates/` (`04-rights-signoff.csv` 68 rows, `05-gold-labels.csv`, `06-answer-sample.csv`) and wire `EditorialProject` persistence to Postgres tables.
3. **High-Value Next Improvements:**
   - Wire `SemanticUnderstandingEngine` into `OffTopicStage` / `DistressStage` behind a shadow A/B evaluation flag and run comparative precision/recall evaluation on `evals/` multilingual & bereavement cases.
   - Wire `ComprehensionRecoveryService` into `ChatInterface` / `GraphStage` multi-turn follow-up flow.
   - Execute `ControlledRetrievalOptimizer` sweep over live `first_person_v14_shadow` + Memgraph + verified OKF to replace hardcoded `top_k`/RRF constants.
4. **Deferred / External Blockers:**
   - *Sufkor* source file acquisition & owner rights confirmation; Railway staging credentials & `FORWARDED_ALLOW_IPS` deployment approval; Meta WhatsApp production credentials.

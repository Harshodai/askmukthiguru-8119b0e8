# AskMukthiGuru — Comprehensive Engineering Remediation Register

**Baseline:** `main` at `bbcdb9d0f161cd7b0ac5509c3efc6f9f94a961f9`  
**Purpose:** Track the complete architecture discussed in the November 26 engineering session. This register is intentionally evidence-based: a module, feature flag, test fixture, or design document is not proof of a working end-to-end capability.

## PR scope and non-goals

This PR corrects source-level defects in speaker reverification, async ontology resolution, and media-composition governance. It also aligns the first-person serving contract and canonical-memory documentation with current code.

It does **not** claim that every product capability below is complete. Full ingestion/corpus rebuilding, Qdrant/Memgraph/OKF mutations, production flag activation, media rendering, editorial workspace delivery, human certification, or hosted performance testing cannot be completed safely through source-only edits. Those are explicit follow-on work items with required evidence.

## Workstream register

| # | Workstream | Repository evidence | Current state | Required closure evidence |
|---:|---|---|---|---|
| 1 | Source inventory and release identity | `corpus_governance.py`, source-release manifests | Partial | One immutable source identity/version/hash contract shared by every ingest path |
| 2 | General URL/media ingestion | `backend/ingest/pipeline.py` | Implemented in parts | Replayable source-to-index run with failure injection and cross-store reconciliation |
| 3 | First-person verbatim ingestion | `backend/ingest/verbatim/`, `run_verbatim_stage` | Separate pipeline; not unified with ordinary ingest | Canonical lifecycle orchestrator and a registered build manifest |
| 4 | ASR, alignment and transcript quality | Whisper/WhisperX, transcript council, cleaners and boundary gates | Implemented in parts | Model/version provenance, held-out WER/CER/alignment evaluation, human review |
| 5 | Segmentation and discourse units | Parent/child context builder, v12/v13 resegmentation tools | Partial | Measured boundary/completeness distributions and corpus-wide reproducible rebuild |
| 6 | Speaker verification | ECAPA window scorer and v13 reverification scripts | **Defect corrected in this PR** | Run offline against shadow data; independently review calibration and signed speaker packet |
| 7 | Rights and source governance | Rights register, source-release manifests, serving gates | Partial | Signed permissions and revocation/takedown drill; never infer clearance from payload claims |
| 8 | Ontology vocabulary and aliases | `spiritual_ontology.py`, doctrine registry, ontology resolver | Partial | Canonical entity IDs, multilingual aliases, provenance/confidence, reviewed relation labels |
| 9 | Async semantic concept resolution | `ontology_resolver.py`, `rag/kg_expansion.py` | **Async path corrected; opt-in remains off** | Held-out concept resolution precision/recall plus latency/cost ablation before enabling |
| 10 | Memgraph / Neo4j reasoning | General graph expansion, first-person graph expansion, TU projection | Partial / feature-gated | Hosted connectivity, tenant/rights integrity, graph-vs-vector quality and p95/cost comparison |
| 11 | OKF curated knowledge | Extractors, compiled store, staging/review | Partial | Signed source manifest, verbatim quote gate and approved compilation/reconciliation |
| 12 | Qdrant hybrid retrieval | Dense/sparse vectors, RRF, parent grouping and filters | Implemented | Registered collection fingerprint, per-language/teacher gold evaluation and restore proof |
| 13 | First-person context harness | `FirstPersonContextHarness`, source-span validation | Implemented in parts | Current collection integrity audit and independent answer/citation grading |
| 14 | Multi-video evidence selection | Facet planner and set selector | Experimental / local-only | Production-safe selector, held-out facet coverage and no-answer tests |
| 15 | Video composition | `video_composition.py`, FFmpeg filter generation | **Source gates corrected in this PR; not an integrated renderer** | Verified rights/speaker inputs, rendered artifact, audio/video QA and signed release |
| 16 | LLM harness and routing | LangGraph strategies, query planning, answerability/relevance gates | Implemented in parts | One declared tool/agent contract, bounded budgets, provider attribution and regression traces |
| 17 | Teacher answer contract | Verbatim citations, exact-span integrity and fail-closed fallback | Implemented in first-person lane | End-to-end UI audit proving no synthesized teacher prose across every surface |
| 18 | Personal memory | Second Brain, canonical memory, consent outbox and personal graph | Substantial implementation; multiple planes remain | Unified lifecycle, deletion receipts, cross-user isolation, consent and personalized-cache tests |
| 19 | Seeker learning/comprehension | Reflection records, memory concepts and teaching references | Partial | Explicit learning-state schema and measured teaching → reflection → understanding → future retrieval loop |
| 20 | Editorial Intelligence | Admin review, OKF and corpus analysis tools | **Major product gap** | Research workspace, source-backed dossier, gap analysis, script review and publishing workflow |
| 21 | Safety and clinical governance | Serene Mind, distress stage, multilingual patterns and helplines | Substantial code; human review open | Clinician/native-speaker validation, helpline verification and adversarial multilingual evaluation |
| 22 | Frontend, voice and languages | Chat, personal KG, voice conversation, Sarvam TTS, locale files | Implemented in parts | Real browser/device matrix, translation coverage, accessibility and streaming/voice tests |
| 23 | Data engineering and reliability | Celery/Redis checkpoints, lineage, backups and ingestion rejections | Partial; LightRAG checkpoint repair is separately tracked in PR #110 | Durable idempotency, retry/DLQ, replay, cross-store consistency, restore and two-worker chaos tests |
| 24 | Observability, cost and scaling | Tracing, budget guards, telemetry, one-replica Railway IaC | Partial | SLOs, p50/p95/p99, TTFT, concurrency/soak, degradation/recovery and cost-per-successful-answer |
| 25 | Release certification | Current-truth index, review packets, serving contracts and release gates | **Production NO-GO** | Registered graded run plus human rights/speaker/clinical/native-language and deployment approvals |

## Changes in this PR

1. **Speaker verification:** the v13 reverification script now trusts only the exact positive result from the calibrated windowed scorer. It no longer lets mean cosine override a failed window verdict or preserves a historical positive after failed reverification. The persisted margin now comes from the scorer's minimum calibrated window margin, and the mean cosine uses the scorer's actual `span_cosine_mean` statistic.
2. **Ontology resolution:** graph traversal now has an async resolver entry point. A request-time LLM resolver is available only behind `KG_DYNAMIC_CONCEPT_RESOLUTION_ENABLED` (default false), shares the graph-expansion deadline, and preserves deterministic concepts on timeout. The first-person graph adapter explicitly disables dynamic LLM resolution while it uses its bounded throwaway loop, avoiding cross-loop reuse of request-scoped provider clients.
3. **Media composition:** source segments default to unverified and uncleared; timestamps must be explicit and valid; both speaker and rights checks apply to single-clip and multi-clip paths; the FFmpeg helper cannot bypass those gates; LLM judge scores/statuses are validated before approval.
4. **Contract accuracy:** first-person documentation distinguishes bounded LLM-based retrieval/evidence gates from prohibited LLM-authored teacher prose. Canonical-memory settings documentation reflects the actual code defaults and consent requirement.
5. **Regression tests:** focused tests cover positive-only speaker verdicts, dynamic ontology resolution/timeout/fallback behavior, the first-person event-loop boundary, media source gates, missing timestamps and incomplete/out-of-range judge responses.

## Required follow-on execution

### P0 — complete before any first-person public-release decision
- Run the speaker re-verification tool in dry-run mode only, inspect its per-video report, independently validate calibration and obtain human speaker review. No `--apply` from this PR.
- Run collection fingerprints and read-only integrity audits on the exact candidate Qdrant collection.
- Build a real held-out gold set; separate query-plan training data from final evaluation data; prohibit AI-authored gold labels.
- Reconcile source rights, speaker evidence, corpus version, source hash and chunker identity across every served span.
- Verify production/staging environment variables, Memgraph endpoint, collection aliases and deployment fingerprints without changing them.

### P1 — close the connected architecture
- Unify normal ingestion, verbatim ingestion, official-channel ingestion and gap resegmentation behind one versioned source lifecycle.
- Complete Qdrant ↔ Memgraph ↔ OKF reconciliation and rollback contracts.
- Measure dense vs dense+sparse, graph off/on, semantic concepts off/on, and single vs multi-video selection on the same frozen query set.
- Connect seeker comprehension state to candidate selection without allowing private memory to become teaching evidence.
- Deliver the Editorial Intelligence research/dossier/approval workflow as a separate bounded product surface.
- Connect the composition manifest to a real, secure, asynchronous rendering and artifact-serving worker.

### P2 — user experience and scale
- Complete multilingual UI translation and human language review.
- Run mobile microphone, audio, lifecycle, offline, keyboard and accessibility validation on physical devices.
- Exercise concurrency, provider throttling, Redis/Qdrant/Memgraph outages, worker restarts, idempotent retry, backup restore and alert delivery.
- Publish measured latency/cost/SLO evidence and a support/on-call plan for the intended traffic.

## Safety and execution boundary

- No Qdrant, Memgraph, OKF, rights-register, source manifest, or Railway production writes were performed by this PR.
- No serving feature flags were enabled by this PR. Dynamic graph concept resolution remains off by default.
- The v13 re-verification script was edited but not executed.
- Test files were authored but are not reported as passed until CI or an actual test run confirms them.
- Rights approval, speaker certification, clinical review, native-language review, gold-label approval and deployment promotion remain human gates.

**Definition of done for this register:** each row must point to an implementation, test/evaluation artifact, measured runtime evidence where applicable, and the responsible human approval where required. A code merge alone does not close a row.

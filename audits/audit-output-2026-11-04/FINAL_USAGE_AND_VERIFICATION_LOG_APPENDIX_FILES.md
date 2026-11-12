# Appendix to the usage log: files read and updated in the final verification pass

Generated on 2026-11-06 from the session's tool-call logs. Companion to `FINAL_USAGE_AND_VERIFICATION_LOG.md`.

## 1. Method and limits

- Window: every tool call made on or after `2026-11-05T06:56:41.204Z`, when the final-verification brief arrived, until this appendix was generated.
- Sources: the main-session log and 42 subagent logs of this session.
- A file counts as read when a `Read` call opened it, a `Grep`/`Glob` call searched it, or a shell command (`cat`, `sed`, `head`, `tail`, `awk`, `grep`, `rg`, `wc`, `python`, `diff`, `git show/diff/log/blame`) named it. "Partial" means every `Read` call used an offset or limit.
- Limits: a shell command that reached files through a glob, a variable or a loop is not resolved to each file. Files that a `Grep` over a directory matched are counted under the directory, not one by one. Files outside the repository (scratchpad, transcripts) are excluded.
- The 2026-11-04 audit's own reading is recorded in `27-execution-log-coverage-and-usage.md`, not here.

## 2. Summary

| Measure | Count |
|---|---|
| Repository files read | 492 |
| Directories searched | 104 |
| Web sources (pages, searches, Railway doc queries) | 45 |
| Repository files created or changed | 58 |

| Top-level directory | Files read |
|---|---|
| `backend` | 201 |
| `src` | 71 |
| `audits` | 44 |
| `docs` | 35 |
| `scripts` | 29 |
| `(root)` | 23 |
| `infrastructure` | 15 |
| `supabase` | 15 |
| `.github` | 13 |
| `evals` | 13 |
| `android` | 8 |
| `ios` | 7 |
| `mobile` | 5 |
| `tests` | 5 |
| `config` | 2 |
| `.lovable` | 1 |
| `.railway` | 1 |
| `app` | 1 |
| `frontend` | 1 |
| `memory` | 1 |
| `whatsapp_bot` | 1 |

## 3. Agents

| Label | Agent (task description) |
|---|---|
| L | Lead (main session) |
| G1 | E: voice governance, latent P0 removal |
| G2 | Reliability, security, ops spec (Sonnet) |
| G3 | Railway docs research and runbook |
| G4 | Retrieval, synthesis, answer specs (Sonnet) |
| G5 | F: small P2/P3 hardening batch |
| G6 | Sonnet: a11y and mobile proxy session |
| G7 | Sonnet: audit document inventory |
| G8 | Haiku full read lessons.md part 1 |
| G9 | I: telemetry remainder, encoder check, shims |
| G10 | Recount findings into pending register |
| G11 | G: CI repair and final small tasks |
| G12 | S2 data, Qdrant, retrieval audit |
| G13 | S3 AI harness, answers, safety, evals |
| G14 | Sonnet: re-verify batches 9-13 |
| G15 | Sonnet: mobile apps review |
| G16 | Lessons and documentation review |
| G17 | Sonnet: k8s manifests review |
| G18 | H: outcome telemetry (T2-03) |
| G19 | Independent adversarial audit review |
| G20 | S1 backend, stability, security audit |
| G21 | C: rights register, logs, consent |
| G22 | Sonnet: accessibility audit |
| G23 | Haiku full read lessons.md part 3 |
| G24 | A: fail-closed teaching route |
| G25 | Sonnet: fix broken citations |
| G26 | Haiku full read lessons.md part 2 |
| G27 | Sonnet: Lovable sync path review |
| G28 | D: frontend safety and wiring |
| G29 | B: gate honesty and spend cap |
| G30 | Journey walk and competitive analysis |
| G31 | Haiku: audit docs link check |
| G32 | Personal mentor memory spec |
| G33 | Ingestion and data-quality specs |
| G34 | Retrieval, synthesis, answer specs |
| G35 | Haiku guardrail review of diff |
| G36 | Sonnet: register 75 finding IDs |
| G37 | Sonnet: load and cost model |
| G38 | Guru knowledge and AI harness specs |
| G39 | Reliability, security, ops spec |
| G40 | FR/NFR matrix and historical ADRs |
| G41 | Independent review of final package |
| G42 | S4 product, guru, rights, FR audit |

## 4. Repository files read

| File | Tools | Calls | Partial only | Agents |
|---|---|---|---|---|
| `.dockerignore` | Bash | 6 |  | G3, G17, G27 |
| `.env.example` | Bash | 1 |  | G33 |
| `.env.mobile` | Bash | 1 |  | G15 |
| `.env.production` | Bash | 2 |  | G17, G27 |
| `.github/workflows/backup.yml` | Bash | 3 |  | G2, G40 |
| `.github/workflows/build-deploy.yml` | Bash | 5 |  | G3, G17, G27 |
| `.github/workflows/dependency-check.yml` | Bash | 2 |  | G15, G39 |
| `.github/workflows/eval-gate.yml` | Bash | 5 |  | G10, G14, G27 |
| `.github/workflows/fixture-stores.yml` | Bash | 1 |  | G10 |
| `.github/workflows/lint-test.yml` | Bash | 3 |  | G15, G16, G40 |
| `.github/workflows/main-hard-gates.yml` | Bash | 1 |  | G27 |
| `.github/workflows/nightly-audit.yml` | Bash | 6 |  | G10, G33, G40 |
| `.github/workflows/nightly-eval.yml` | Bash | 1 |  | G40 |
| `.github/workflows/nightly-load.yml` | Bash | 2 |  | G37, G40 |
| `.github/workflows/nightly-rls.yml` | Bash | 3 |  | G2, G32 |
| `.github/workflows/security-audit.yml` | Bash | 1 |  | G39 |
| `.github/workflows/supabase-schema-snapshot.yml` | Bash | 1 |  | G10 |
| `.gitignore` | Bash | 4 |  | G3, G15, G27 |
| `.gitleaks.toml` | Bash | 1 |  | G8 |
| `.lovable/plan.md` | Bash | 1 |  | G27 |
| `.pre-commit-config.yaml` | Bash | 5 |  | G14, G16 |
| `.railway/railway.ts` | Bash | 14 |  | L, G2, G3, G16, G17, G39, G41 |
| `.railwayignore` | Bash | 5 |  | L, G3, G16, G27 |
| `AGENTS.md` | Bash | 11 |  | G7, G10, G16, G27, G40 |
| `CLAUDE.md` | Bash | 31 |  | L, G2, G3, G7, G8, G10, G14, G16, G17, G27, G40, G41 |
| `README.md` | Bash | 27 |  | L, G7, G16, G17, G25, G27, G41 |
| `android/.gitignore` | Bash | 2 |  | G15 |
| `android/app/.gitignore` | Bash | 2 |  | G15 |
| `android/app/build.gradle` | Bash | 1 |  | G15 |
| `android/app/src/main/AndroidManifest.xml` | Bash | 1 |  | G15 |
| `android/app/src/main/java/com/askmukthiguru/app/MainActivity.java` | Bash | 1 |  | G15 |
| `android/app/src/main/res/xml/file_paths.xml` | Bash | 1 |  | G15 |
| `android/key.properties.example` | Bash | 1 |  | G15 |
| `android/variables.gradle` | Bash | 1 |  | G15 |
| `app/__init__.py` | Bash | 7 |  | G7, G25 |
| `audits/audit-output-2026-11-04/00-executive-overview-and-scorecard.md` | Bash | 2 |  | L |
| `audits/audit-output-2026-11-04/03-product-journeys-functional-requirements.md` | Bash | 2 |  | G7, G32 |
| `audits/audit-output-2026-11-04/04-non-functional-requirements-slos-and-benchmarks.md` | Bash | 1 |  | L |
| `audits/audit-output-2026-11-04/13-code-quality-architectural-debt.md` | Bash | 2 |  | G7, G14 |
| `audits/audit-output-2026-11-04/14d-user-journey-and-frontend-walkthrough.md` | Bash | 1 |  | G7 |
| `audits/audit-output-2026-11-04/20-ordered-engineering-roadmap.md` | Bash | 2 |  | L, G32 |
| `audits/audit-output-2026-11-04/22b-railway-deployment-readiness-runbook.md` | Bash | 1 |  | G16 |
| `audits/audit-output-2026-11-04/26-independent-adversarial-review-and-residual-risks.md` | Bash | 2 |  | L |
| `audits/audit-output-2026-11-04/CONVENTIONS.md` | Bash | 12 |  | L, G15, G16, G17 |
| `audits/audit-output-2026-11-04/FINAL_AUDIT_DOCUMENT_INVENTORY.md` | Bash | 6 |  | G7 |
| `audits/audit-output-2026-11-04/FINAL_AUDIT_GAP_ANALYSIS.md` | Bash | 5 |  | L, G41 |
| `audits/audit-output-2026-11-04/FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` | Bash | 3 |  | L |
| `audits/audit-output-2026-11-04/FINAL_DECISION_AND_RISK_REGISTER.md` | Bash | 5 |  | L |
| `audits/audit-output-2026-11-04/FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` | Bash | 9 |  | L, G16 |
| `audits/audit-output-2026-11-04/FINAL_PENDING_WORK_REGISTER.md` | Bash | 10 |  | L, G7, G10, G14, G16, G37, G38, G41 |
| `audits/audit-output-2026-11-04/FINAL_PRODUCTION_RELEASE_READINESS.md` | Bash | 6 |  | L, G22, G41 |
| `audits/audit-output-2026-11-04/FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` | Bash | 2 |  | L, G41 |
| `audits/audit-output-2026-11-04/FINAL_RAILWAY_STAGING_READINESS.md` | Bash | 4 |  | L |
| `audits/audit-output-2026-11-04/FINAL_READINESS_AND_GAP_ANALYSIS.md` | Bash, Read | 7 |  | L, G7, G16, G40 |
| `audits/audit-output-2026-11-04/FINAL_SPECIFICATION_COMPLETENESS_MATRIX.md` | Bash | 4 |  | L, G41 |
| `audits/audit-output-2026-11-04/FINAL_USAGE_AND_VERIFICATION_LOG.md` | Bash | 4 |  | L |
| `audits/audit-output-2026-11-04/IMPLEMENTATION-AGENT-PROMPT.md` | Bash | 11 |  | L, G7, G33, G38, G41 |
| `audits/audit-output-2026-11-04/README.md` | Bash | 2 |  | L, G41 |
| `audits/audit-output-2026-11-04/findings-index.md` | Bash | 17 |  | L, G10, G14, G16, G40, G41 |
| `audits/audit-output-2026-11-04/specifications/ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md` | Bash | 7 |  | L, G22 |
| `audits/audit-output-2026-11-04/specifications/AI_HARNESS_PROMPT_AND_CONTEXT_SPEC.md` | Bash | 1 |  | L |
| `audits/audit-output-2026-11-04/specifications/ARCHITECTURE_DECISION_RECORDS_HISTORICAL.md` | Bash | 2 |  | L, G17 |
| `audits/audit-output-2026-11-04/specifications/COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` | Bash | 8 |  | L, G41 |
| `audits/audit-output-2026-11-04/specifications/DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md` | Bash | 1 |  | L |
| `audits/audit-output-2026-11-04/specifications/GURU_KNOWLEDGE_AND_KNOWLEDGE_GRAPH_SPEC.md` | Bash | 2 |  | L, G38 |
| `audits/audit-output-2026-11-04/specifications/INGESTION_AND_CONTENT_PROCESSING_SPEC.md` | Bash | 5 |  | L, G41 |
| `audits/audit-output-2026-11-04/specifications/K8S_MANIFESTS_REVIEW.md` | Bash | 3 |  | L, G17 |
| `audits/audit-output-2026-11-04/specifications/LOAD_AND_COST_MODEL.md` | Bash | 3 |  | L |
| `audits/audit-output-2026-11-04/specifications/LOVABLE_SYNC_PATH_REVIEW.md` | Bash | 1 |  | L |
| `audits/audit-output-2026-11-04/specifications/MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md` | Bash | 3 |  | L |
| `audits/audit-output-2026-11-04/specifications/MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` | Bash | 2 |  | G4, G41 |
| `audits/audit-output-2026-11-04/specifications/PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` | Bash | 3 |  | L, G15, G41 |
| `audits/audit-output-2026-11-04/specifications/PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` | Bash | 6 |  | L, G2 |
| `audits/audit-output-2026-11-04/specifications/RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` | Bash | 4 |  | L, G17 |
| `audits/audit-output-2026-11-04/specifications/RETRIEVAL_AND_RAG_SPEC.md` | Bash | 2 |  | G4, G37 |
| `audits/audit-output-2026-11-04/specifications/SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md` | Bash | 3 |  | G4, G14, G41 |
| `audits/audit-output-2026-11-04/traceability-matrix.md` | Bash | 2 |  | L |
| `audits/audit-output-2026-11-04/unresolved-questions.md` | Bash | 5 |  | L, G14, G32 |
| `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json` | Bash | 2 |  | G3, G33 |
| `backend/.dockerignore` | Bash | 2 |  | G3 |
| `backend/.env.example` | Bash | 5 |  | G3, G16, G33, G38 |
| `backend/CLAUDE.md` | Bash | 14 |  | L, G2, G14, G16 |
| `backend/Dockerfile` | Bash | 5 |  | G10, G14 |
| `backend/Dockerfile.railway` | Bash | 13 |  | L, G2, G3, G10, G14, G33, G41 |
| `backend/app/__init__.py` | Bash | 1 |  | G7 |
| `backend/app/answer_outcome.py` | Bash, Read | 4 |  | G2, G10, G39, G40 |
| `backend/app/api/admin.py` | Bash | 1 |  | G14 |
| `backend/app/api/admin_video_review.py` | Bash | 1 |  | G33 |
| `backend/app/api/assistants.py` | Bash | 1 |  | G40 |
| `backend/app/api/canonical_memory.py` | Bash | 1 |  | G32 |
| `backend/app/api/capabilities.py` | Bash | 1 |  | G40 |
| `backend/app/api/chat.py` | Bash | 4 |  | G10, G14, G40 |
| `backend/app/api/compliance.py` | Bash | 7 |  | L, G10, G16, G25, G32 |
| `backend/app/api/feedback.py` | Bash | 17 |  | L, G14, G25, G40, G41 |
| `backend/app/api/first_person.py` | Bash | 10 |  | G2, G7, G14, G25, G32, G33, G40 |
| `backend/app/api/health.py` | Bash | 15 |  | L, G2, G7, G10, G14, G17, G25, G33, G40, G41 |
| `backend/app/api/ingest.py` | Bash | 2 |  | G33 |
| `backend/app/api/memory.py` | Bash | 6 |  | G7, G25, G32, G40 |
| `backend/app/api/metrics.py` | Bash | 3 |  | L, G2 |
| `backend/app/api/push.py` | Bash | 3 |  | G15, G25 |
| `backend/app/api/teachings.py` | Bash | 6 |  | G10, G14, G38 |
| `backend/app/assistant_registry.py` | Bash | 2 |  | G38 |
| `backend/app/chat_engine.py` | Bash | 1 |  | G14 |
| `backend/app/config.py` | Bash | 39 |  | L, G2, G3, G7, G10, G14, G16, G17, G33, G36, G37, G38, G40, G41 |
| `backend/app/container.py` | Bash | 3 |  | G14 |
| `backend/app/core/limiter.py` | Bash | 1 |  | G2 |
| `backend/app/corpus_governance.py` | Bash | 1 |  | G33 |
| `backend/app/db/seed_ontology.py` | Bash | 1 |  | G38 |
| `backend/app/generation/__init__.py` | Bash | 1 |  | G40 |
| `backend/app/health.py` | Bash | 6 |  | G14, G25, G41 |
| `backend/app/main.py` | Bash | 15 |  | L, G2, G3, G10, G16, G17, G32, G33, G38, G41 |
| `backend/app/metrics.py` | Bash | 10 |  | L, G2, G33, G40, G41 |
| `backend/app/model_policy.py` | Bash | 1 |  | L |
| `backend/app/openrouter_budget.py` | Bash | 3 |  | G2, G7 |
| `backend/app/orchestrator.py` | Bash | 3 |  | G4, G14 |
| `backend/app/orchestrator_utils.py` | Bash | 7 |  | G10, G14, G41 |
| `backend/app/pipeline/pipeline_coordinator.py` | Bash | 2 |  | G2, G14 |
| `backend/app/pipeline/stages/cache_stage.py` | Bash | 3 |  | G10, G14, G40 |
| `backend/app/pipeline/stages/distress_stage.py` | Bash | 2 |  | G10, G40 |
| `backend/app/pipeline/stages/first_person_bridge.py` | Bash | 10 |  | G4, G10, G14, G40, G41 |
| `backend/app/pipeline/stages/graph_stage.py` | Bash | 5 |  | G10, G14, G38 |
| `backend/app/pipeline/stages/guardrail_stage.py` | Bash | 2 |  | G2, G41 |
| `backend/app/pipeline/stages/kill_switch_stage.py` | Bash | 2 |  | G14 |
| `backend/app/pipeline/stages/pipeline_builder.py` | Bash | 8 |  | G14, G16, G41 |
| `backend/app/release_manifest.py` | Bash | 2 |  | G2, G3 |
| `backend/app/route_taxonomy.py` | Bash | 1 |  | G2 |
| `backend/app/schemas/__init__.py` | Bash | 7 |  | G2, G4, G14 |
| `backend/app/schemas/compliance.py` | Bash | 2 |  | L, G25 |
| `backend/app/stream_orchestrator.py` | Bash | 6 |  | G10, G14 |
| `backend/app/streaming/__init__.py` | Bash | 1 |  | G40 |
| `backend/app/telemetry_db.py` | Bash | 3 |  | G33, G41 |
| `backend/app/telemetry_sink.py` | Bash | 5 |  | G7, G25 |
| `backend/benchmarks/abstention_eval.py` | Bash | 1 |  | G37 |
| `backend/benchmarks/concurrent_load_test.py` | Bash | 1 |  | G37 |
| `backend/benchmarks/locustfile.py` | Bash | 1 |  | G37 |
| `backend/benchmarks/seeker_relevance_set.py` | Bash | 1 |  | G37 |
| `backend/celery_config.py` | Bash | 8 |  | G3, G32, G40, G41 |
| `backend/config/first_person_serving_contract.json` | Bash | 5 |  | G10, G33 |
| `backend/config/gurus.yaml` | Bash | 7 |  | G10, G14, G33, G38, G40 |
| `backend/docker-compose.yml` | Bash | 21 |  | G3, G10, G14, G16, G33, G37, G41 |
| `backend/domain/first_person_context.py` | Bash | 4 |  | G33 |
| `backend/domain/hash_fields.py` | Bash | 3 |  | G10, G33 |
| `backend/evaluation/gold/metrics.py` | Bash | 1 |  | G41 |
| `backend/guardrails/lightweight_handler.py` | Bash | 5 |  | G14, G38 |
| `backend/infrastructure/k8s.yaml` | Bash | 7 |  | L, G17, G41 |
| `backend/ingest/handlers/checkpoint.py` | Bash | 2 |  | G33 |
| `backend/ingest/pipeline.py` | Bash | 16 |  | L, G7, G10, G25, G33 |
| `backend/ingest/quality_gate.py` | Bash | 1 |  | G33 |
| `backend/ingest/raptor.py` | Bash | 1 |  | G25 |
| `backend/ingest/verbatim/README.md` | Bash | 1 |  | G33 |
| `backend/ingest/youtube_loader.py` | Bash | 1 |  | G7 |
| `backend/pyproject.toml` | Bash | 3 |  | G10, G40 |
| `backend/rag/graph_builder.py` | Bash | 1 |  | G14 |
| `backend/rag/graph_strategies.py` | Bash | 1 |  | G10 |
| `backend/rag/intent_prerouter.py` | Bash | 1 |  | G10 |
| `backend/rag/meditation.py` | Bash | 1 |  | G14 |
| `backend/rag/nodes/cross_teacher_reasoning.py` | Bash | 1 |  | G38 |
| `backend/rag/nodes/entity_linking.py` | Bash | 2 |  | G38 |
| `backend/rag/nodes/first_person.py` | Bash | 7 |  | G10, G14, G25, G40 |
| `backend/rag/nodes/generation.py` | Bash | 4 |  | G10 |
| `backend/rag/nodes/intent.py` | Bash | 1 |  | G14 |
| `backend/rag/pipeline_registry.py` | Bash | 2 |  | G10, G40 |
| `backend/rag/prompts/system.py` | Bash | 1 |  | G14 |
| `backend/rag/resolve_followup.py` | Bash | 1 |  | G10 |
| `backend/requirements-dev.txt` | Bash | 2 |  | G37, G40 |
| `backend/requirements.lock` | Bash | 1 |  | G40 |
| `backend/requirements.txt` | Bash | 1 |  | G40 |
| `backend/schemas/feedback.py` | Bash | 3 |  | G25, G41 |
| `backend/scripts/ops/approve_okf_source_manifest.py` | Bash | 1 |  | G33 |
| `backend/scripts/ops/build_first_person_index.py` | Bash | 1 |  | G33 |
| `backend/scripts/ops/build_full_corpus_v10.py` | Bash | 12 |  | G10, G33, G41 |
| `backend/scripts/ops/check_first_person_public_release.py` | Bash | 1 |  | G10 |
| `backend/scripts/ops/check_legacy_guru_tables.py` | Bash | 1 |  | G14 |
| `backend/scripts/ops/data_quality_audit.py` | Bash | 2 |  | G7, G33 |
| `backend/scripts/ops/ensure_fp_payload_indexes.py` | Bash | 1 |  | G33 |
| `backend/scripts/ops/fp_data_quality_scorecard.py` | Bash | 1 |  | G33 |
| `backend/scripts/ops/gate1_load_test.py` | Bash | 8 |  | G2, G37, G40, G41 |
| `backend/scripts/ops/restore_drill.py` | Bash | 3 |  | G33 |
| `backend/scripts/verify_rls_policies.py` | Bash | 1 |  | G32 |
| `backend/services/canonical_memory/context_builder.py` | Bash | 1 |  | G32 |
| `backend/services/circuit_breaker.py` | Bash | 1 |  | G2 |
| `backend/services/cost_tracker.py` | Bash | 1 |  | L |
| `backend/services/crisis_helplines.py` | Bash | 3 |  | G14, G40 |
| `backend/services/doctrine_terms.py` | Bash | 1 |  | G38 |
| `backend/services/feedback_service.py` | Bash | 2 |  | G39 |
| `backend/services/first_person_context_harness.py` | Bash | 1 |  | G33 |
| `backend/services/first_person_context_store.py` | Bash | 10 |  | G10, G33, G40 |
| `backend/services/first_person_facet_planner.py` | Bash | 5 |  | G7, G25 |
| `backend/services/first_person_ingest_service.py` | Bash | 2 |  | G33 |
| `backend/services/first_person_pipeline.py` | Bash | 20 |  | G10, G14, G16, G25, G33, G37, G38, G40, G41 |
| `backend/services/first_person_rights.py` | Bash | 1 |  | G33 |
| `backend/services/first_person_serving_contract.py` | Bash | 8 |  | G3, G10, G33 |
| `backend/services/first_person_set_selector.py` | Bash | 4 |  | G7, G25 |
| `backend/services/first_person_store.py` | Bash | 10 |  | G14, G33, G40 |
| `backend/services/first_person_video_decisions.py` | Bash | 2 |  | G33 |
| `backend/services/fp_fail_closed.py` | Bash | 3 |  | G10, G40 |
| `backend/services/guru_registry.py` | Bash | 4 |  | G14, G38, G40 |
| `backend/services/injection_scanner.py` | Bash | 1 |  | G39 |
| `backend/services/intelligent_metadata_extractor.py` | Bash | 1 |  | G38 |
| `backend/services/layered_memory/l3_persona_generator.py` | Bash | 3 |  | G14 |
| `backend/services/lettuce_detect_service.py` | Bash | 1 |  | G40 |
| `backend/services/lightrag_service.py` | Bash | 2 |  | G7, G38 |
| `backend/services/llm/base.py` | Bash | 1 |  | G25 |
| `backend/services/llm/factory.py` | Bash | 1 |  | G25 |
| `backend/services/llm_gateway.py` | Bash | 2 |  | G14 |
| `backend/services/memory/okf_store.py` | Bash | 6 |  | G33, G38, G41 |
| `backend/services/memory_outbox.py` | Bash | 1 |  | G32 |
| `backend/services/openrouter_service.py` | Bash | 1 |  | G2 |
| `backend/services/personalization/cascade_erasure.py` | Bash | 1 |  | G32 |
| `backend/services/prompt_store.py` | Bash | 1 |  | G38 |
| `backend/services/qdrant/indexer.py` | Bash | 3 |  | G33 |
| `backend/services/qdrant/raptor.py` | Bash | 1 |  | G25 |
| `backend/services/qdrant_service.py` | Bash | 2 |  | G33 |
| `backend/services/quote_fidelity.py` | Bash | 1 |  | G38 |
| `backend/services/quote_weaver.py` | Bash | 3 |  | G7, G10 |
| `backend/services/serene_mind_engine.py` | Bash | 3 |  | G14, G40 |
| `backend/services/teacher_attribution.py` | Bash | 1 |  | G38 |
| `backend/services/voice/register.py` | Bash | 1 |  | G38 |
| `backend/services/voice/style.py` | Bash | 1 |  | G10 |
| `backend/start_railway.py` | Bash | 11 |  | L, G2, G3, G16, G41 |
| `backend/tasks/cancel_flow_tasks.py` | Bash | 1 |  | G32 |
| `backend/tasks/ingest_tasks.py` | Bash | 2 |  | G33 |
| `backend/tasks/retention_tasks.py` | Bash | 1 |  | G32 |
| `backend/tasks/web_ingest_tasks.py` | Bash | 1 |  | G7 |
| `backend/tests/redteam_harness.py` | Bash | 2 |  | G39 |
| `backend/tests/test_answer_outcome_telemetry.py` | Bash | 1 |  | G10 |
| `backend/tests/test_bridge_attribution_wp4.py` | Bash | 1 |  | G40 |
| `backend/tests/test_builder_replace_and_snapshot.py` | Bash | 2 |  | G10, G40 |
| `backend/tests/test_cache_crisis_bypass.py` | Bash | 1 |  | G40 |
| `backend/tests/test_cache_versioning_and_teaching_guard.py` | Bash | 1 |  | G14 |
| `backend/tests/test_canonical_teacher_ids.py` | Bash | 1 |  | G14 |
| `backend/tests/test_citation_contract.py` | Bash | 3 |  | G14 |
| `backend/tests/test_clip_reporting_and_saved_answers.py` | Bash | 2 |  | G14 |
| `backend/tests/test_config_lint.py` | Bash | 4 |  | G10, G14, G40 |
| `backend/tests/test_config_validation.py` | Bash | 2 |  | G10 |
| `backend/tests/test_container_llm_gateway.py` | Bash | 2 |  | G14 |
| `backend/tests/test_crisis_copy_never_llm_translated.py` | Bash | 1 |  | G40 |
| `backend/tests/test_data_quality_promotion_gate.py` | Bash | 2 |  | G10, G40 |
| `backend/tests/test_distress_provider_fail_closed.py` | Bash | 1 |  | G40 |
| `backend/tests/test_docker_compose_healthcheck.py` | Bash | 4 |  | G10, G14 |
| `backend/tests/test_emotional_side_effect_consent.py` | Bash | 3 |  | G10, G40 |
| `backend/tests/test_exception_and_import_ratchets.py` | Bash | 2 |  | G14 |
| `backend/tests/test_first_person_pipeline_golden.py` | Bash | 4 |  | G10, G14, G40 |
| `backend/tests/test_first_person_public_release_gate.py` | Bash | 3 |  | G10, G40 |
| `backend/tests/test_first_person_serving_contract.py` | Bash | 2 |  | G10 |
| `backend/tests/test_first_person_v10_only.py` | Bash | 1 |  | G40 |
| `backend/tests/test_fixture_stores.py` | Bash | 1 |  | G10 |
| `backend/tests/test_fp_fail_closed.py` | Bash | 5 |  | G10, G14, G38 |
| `backend/tests/test_fp_memory_signals.py` | Bash | 3 |  | G14 |
| `backend/tests/test_fp_quarantine_identity.py` | Bash | 1 |  | G40 |
| `backend/tests/test_gate_first_then_dedup.py` | Bash | 1 |  | G10 |
| `backend/tests/test_general_mode_no_register.py` | Bash | 3 |  | G10, G38, G40 |
| `backend/tests/test_graph_strategy_wiring.py` | Bash | 1 |  | G10 |
| `backend/tests/test_grounding_state_contract.py` | Bash | 1 |  | G4 |
| `backend/tests/test_grounding_state_labeling.py` | Bash | 1 |  | G4 |
| `backend/tests/test_guru_extensibility.py` | Bash | 1 |  | G14 |
| `backend/tests/test_guru_registry_and_modes.py` | Bash | 1 |  | G38 |
| `backend/tests/test_health.py` | Bash | 1 |  | G10 |
| `backend/tests/test_health_falsifiability.py` | Bash | 1 |  | G40 |
| `backend/tests/test_healthz_grace_masking.py` | Bash | 1 |  | G16 |
| `backend/tests/test_l3_persona_preferences.py` | Bash | 1 |  | G14 |
| `backend/tests/test_lesson_guards.py` | Bash | 1 |  | G16 |
| `backend/tests/test_main_cors.py` | Bash | 1 |  | G10 |
| `backend/tests/test_migration_lint.py` | Bash | 2 |  | G10, G40 |
| `backend/tests/test_no_seeker_text_in_logs.py` | Bash | 4 |  | G10, G14, G40 |
| `backend/tests/test_no_unsourced_teacher_attribution.py` | Bash | 4 |  | G10, G14 |
| `backend/tests/test_offline_pr_suite.py` | Bash | 3 |  | G4, G10, G38 |
| `backend/tests/test_pipeline_order_guard.py` | Bash | 3 |  | L, G14 |
| `backend/tests/test_prod_compose_invariants.py` | Bash | 6 |  | G16, G17, G40 |
| `backend/tests/test_qdrant_write_governance.py` | Bash | 1 |  | G10 |
| `backend/tests/test_rag_properties.py` | Bash | 2 |  | G40 |
| `backend/tests/test_relevance_standalone_gates.py` | Bash | 1 |  | G40 |
| `backend/tests/test_repo_layout.py` | Bash | 1 |  | G15 |
| `backend/tests/test_retrieval_bank_harness.py` | Bash | 1 |  | G10 |
| `backend/tests/test_rights_register_startup.py` | Bash | 3 |  | G10 |
| `backend/tests/test_untrusted_prompt_fences.py` | Bash | 4 |  | G2, G10, G38 |
| `backend/tests/test_v10_hybrid_retrieval.py` | Bash | 1 |  | G10 |
| `backend/tests/test_verified_helplines_only.py` | Bash | 2 |  | G14 |
| `backend/tests/test_voice_governance_docs.py` | Bash | 5 |  | L, G10, G40 |
| `backend/tests/test_writer_hash_contract.py` | Bash | 2 |  | G10, G33 |
| `capacitor.config.ts` | Bash | 1 |  | G15 |
| `config/first_person_calibration.json` | Bash, Read | 2 |  | G34 |
| `config/helplines.yaml` | Bash | 3 |  | G2, G3, G40 |
| `docker-compose.prod.yml` | Bash | 5 |  | G3, G17, G37 |
| `docs/BACKUP_RESTORE.md` | Bash | 4 |  | G2 |
| `docs/DEPLOYMENT.md` | Bash | 1 |  | G27 |
| `docs/DEVELOPER_GUIDE.md` | Bash | 10 |  | L, G16, G41 |
| `docs/FIRST_PERSON_FOLLOWUPS_SPEC.md` | Bash | 3 |  | L, G4 |
| `docs/INCIDENT_RESPONSE.md` | Bash | 9 |  | G2, G39, G41 |
| `docs/KUBECTL_RUNBOOK.md` | Bash | 2 |  | G17 |
| `docs/MOBILE_RELEASE_RUNBOOK.md` | Bash | 2 |  | G15, G16 |
| `docs/PROD_READY_CHECKLIST.md` | Bash | 2 |  | G16 |
| `docs/RAG_RUNTIME_DAG.md` | Bash | 7 |  | L, G16, G41 |
| `docs/RAILWAY_DEPLOYMENT_CHECKLIST.md` | Bash | 1 |  | G16 |
| `docs/SLO.md` | Bash | 9 |  | G2, G39, G41 |
| `docs/STORE_LISTING.md` | Bash | 3 |  | G15 |
| `docs/adr/0001-publication-model.md` | Bash | 1 |  | G40 |
| `docs/adr/0002-chunking-contract.md` | Bash | 1 |  | G40 |
| `docs/agent/claude-md-archive/agents-md-railway.md` | Bash | 1 |  | G16 |
| `docs/agent/claude-md-archive/database-and-graph.md` | Bash | 1 |  | G40 |
| `docs/agent/claude-md-archive/railway-deployment.md` | Bash | 2 |  | G3, G16 |
| `docs/architecture/README.md` | Bash | 6 |  | L, G16, G41 |
| `docs/architecture/SYSTEM_ARCHITECTURE_HLD_LLD.md` | Bash | 1 |  | G16 |
| `docs/architecture/backend-roadmap.md` | Bash | 1 |  | G16 |
| `docs/architecture/first-person-path-to-prod.md` | Bash | 3 |  | G16, G40 |
| `docs/kubernetes-deployment.md` | Bash | 2 |  | G17 |
| `docs/operations/drills.md` | Bash | 1 |  | G33 |
| `docs/operations/railway-production-status-2026-09-20.md` | Bash | 2 |  | G2, G37 |
| `docs/plans/PLAN.md` | Bash | 1 |  | G16 |
| `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` | Bash | 9 |  | L, G16, G37, G40, G41 |
| `docs/runbooks/ALERTING.md` | Bash | 6 |  | G2, G39 |
| `docs/runbooks/BACKUP_RESTORE_DRILL.md` | Bash | 2 |  | G2, G39 |
| `docs/runbooks/CAPACITY.md` | Bash | 2 |  | G2, G37 |
| `docs/runbooks/MIGRATION_ROLLBACK.md` | Bash | 3 |  | G2, G3 |
| `docs/runbooks/ONCALL.md` | Bash | 3 |  | G2, G39 |
| `docs/runbooks/SECRET_ROTATION.md` | Bash | 1 |  | G2 |
| `docs/runbooks/restore-snapshot.md` | Bash | 3 |  | G2, G39 |
| `docs/runbooks/rollback-release.md` | Bash | 3 |  | G2, G39 |
| `docs/wiki/operations/deployment-and-ci.md` | Bash | 3 |  | G17 |
| `eslint.config.js` | Bash | 5 |  | G10, G22, G27 |
| `evals/first_person/frozen29.jsonl` | Bash | 1 |  | G37 |
| `evals/first_person/ooc13.jsonl` | Bash | 1 |  | G37 |
| `evals/gold_set_v1/questions.jsonl` | Bash | 2 |  | G37 |
| `evals/pr_suite/abstain_null.jsonl` | Bash | 1 |  | G4 |
| `evals/pr_suite/distress_benign.jsonl` | Bash | 1 |  | G10 |
| `evals/pr_suite/distress_crisis.jsonl` | Bash | 2 |  | G10, G37 |
| `evals/pr_suite/quote_integrity.py` | Bash | 1 |  | G34 |
| `evals/pr_suite/routing.jsonl` | Bash | 1 |  | G4 |
| `evals/pr_suite/voice_lint.py` | Bash | 1 |  | G34 |
| `evals/retrieval_bank/bank.jsonl` | Bash | 4 |  | G33, G34, G37, G40 |
| `evals/retrieval_bank/harness.py` | Bash | 5 |  | G33, G34, G41 |
| `evals/retrieval_bank/metrics.py` | Bash | 3 |  | G25, G34 |
| `evals/run_safety_scenarios.py` | Bash | 1 |  | G2 |
| `frontend/Dockerfile` | Bash | 1 |  | G27 |
| `index.html` | Bash | 1 |  | G15 |
| `infrastructure/cron/mukthiguru-backup` | Bash | 4 |  | G2, G39, G40 |
| `infrastructure/k8s/README.md` | Bash | 2 |  | G17 |
| `infrastructure/k8s/backend-deployment.yaml` | Bash | 3 |  | G17 |
| `infrastructure/k8s/helm/mukthiguru/Chart.yaml` | Bash | 1 |  | G17 |
| `infrastructure/k8s/helm/mukthiguru/charts/redis-19.6.4.tgz` | Bash | 1 |  | G17 |
| `infrastructure/k8s/helm/mukthiguru/values-minikube.yaml` | Bash | 1 |  | G17 |
| `infrastructure/k8s/helm/mukthiguru/values.yaml` | Bash | 2 |  | G17 |
| `infrastructure/k8s/minikube/start.sh` | Bash | 2 |  | G17 |
| `infrastructure/k8s/skaffold.yaml` | Bash | 2 |  | G17 |
| `infrastructure/k8s_deploy.sh` | Bash | 4 |  | G17 |
| `infrastructure/k8s_deployment.yaml` | Bash | 4 |  | G17 |
| `infrastructure/prometheus/alerting-rules.yml` | Bash | 6 |  | G2, G39, G40, G41 |
| `infrastructure/prometheus/alertmanager.yml` | Bash | 2 |  | G2 |
| `infrastructure/prometheus/prometheus.prod.yml` | Bash | 3 |  | G2 |
| `infrastructure/prometheus/prometheus.yml` | Bash | 1 |  | G2 |
| `ios/.gitignore` | Bash | 2 |  | G15 |
| `ios/App/App.xcodeproj/project.pbxproj` | Bash | 1 |  | G15 |
| `ios/App/App/App.entitlements` | Bash | 1 |  | G15 |
| `ios/App/App/AppDelegate.swift` | Bash | 1 |  | G15 |
| `ios/App/App/Info.plist` | Bash | 1 |  | G15 |
| `ios/App/CapApp-SPM/Package.swift` | Bash | 1 |  | G15 |
| `ios/debug.xcconfig` | Bash | 1 |  | G15 |
| `lessons.md` | Bash, Read | 107 |  | L, G8, G10, G14, G16, G23, G26, G40, G41 |
| `memory/okf/compiled.json` | Bash | 4 |  | G3, G16, G33 |
| `mobile/MOBILE_DEPLOY_CONFIDENCE.md` | Bash | 1 |  | G15 |
| `mobile/expo/App.tsx` | Bash | 1 |  | G25 |
| `mobile/expo/README.md` | Bash | 1 |  | G15 |
| `mobile/fastlane-android-Fastfile` | Bash | 1 |  | G15 |
| `mobile/fastlane-ios-Fastfile` | Bash | 1 |  | G15 |
| `package-lock.json` | Bash | 3 |  | G27 |
| `package.json` | Bash | 13 |  | G15, G16, G22, G27, G40 |
| `playwright.config.ts` | Bash | 2 |  | G15, G22 |
| `pyproject.toml` | Bash | 1 |  | G40 |
| `scripts/deploy/deploy.sh` | Bash | 1 |  | G3 |
| `scripts/deploy/deploy_all.sh` | Bash | 2 |  | G16 |
| `scripts/deploy/deploy_railway.sh` | Bash | 5 |  | L, G3, G16 |
| `scripts/guards/config_lint.py` | Bash | 3 |  | G10, G14 |
| `scripts/guards/exception_baseline.txt` | Bash | 3 |  | G14 |
| `scripts/guards/exception_ratchet.py` | Bash | 2 |  | G14 |
| `scripts/guards/guru_literal_guard.py` | Bash | 4 |  | G14 |
| `scripts/guards/import_layer_allowlist.txt` | Bash | 3 |  | G14 |
| `scripts/guards/import_layer_lint.py` | Bash | 2 |  | G14 |
| `scripts/guards/lesson_guards.py` | Bash | 11 |  | L, G14, G16, G33, G38 |
| `scripts/guards/migration_lint.py` | Bash | 1 |  | G10 |
| `scripts/guards/pipeline_order_guard.py` | Bash | 5 |  | L, G14 |
| `scripts/guards/stop_check.sh` | Bash | 2 |  | G16 |
| `scripts/ops/audio_archive.py` | Bash | 2 |  | G33 |
| `scripts/ops/backend_py.sh` | Bash | 1 |  | G16 |
| `scripts/ops/backup_qdrant.py` | Bash | 3 |  | G2 |
| `scripts/ops/build_first_person_index.py` | Bash | 1 |  | G33 |
| `scripts/ops/build_full_corpus_v10.py` | Bash | 3 |  | G10, G33 |
| `scripts/ops/check_first_person_public_release.py` | Bash | 3 |  | G10 |
| `scripts/ops/check_legacy_guru_tables.py` | Bash | 2 |  | G14 |
| `scripts/ops/data_quality_audit.py` | Bash | 5 |  | G7, G33 |
| `scripts/ops/export_qdrant_health.py` | Bash | 1 |  | G2 |
| `scripts/ops/flush_cache.py` | Bash | 1 |  | G2 |
| `scripts/ops/generate_mobile_assets.py` | Bash | 1 |  | G15 |
| `scripts/ops/railway_cleanup.py` | Bash | 2 |  | G3 |
| `scripts/ops/railway_readiness_probe.py` | Bash | 1 |  | G3 |
| `scripts/ops/rerun_parallel_forensics.sh` | Bash | 1 |  | G17 |
| `scripts/ops/rotate_brain_kek.py` | Bash | 1 |  | G3 |
| `scripts/ops/snapshot_qdrant.py` | Bash | 1 |  | G39 |
| `src/App.tsx` | Bash | 6 |  | G15, G25, G32 |
| `src/CLAUDE.md` | Bash | 5 |  | L, G16, G27 |
| `src/admin/pages/ClipReportsPage.tsx` | Bash | 1 |  | G40 |
| `src/components/ai-elements/prompt-input.tsx` | Bash | 1 |  | G15 |
| `src/components/chat/AbstainHelpCard.tsx` | Bash | 1 |  | G40 |
| `src/components/chat/ChatHelpers.tsx` | Bash | 3 |  | G7, G14 |
| `src/components/chat/ChatInterface.tsx` | Bash | 6 |  | G10, G14, G27 |
| `src/components/chat/ChatMessage.tsx` | Bash | 17 |  | G4, G10, G22, G34, G40, G41 |
| `src/components/chat/CitationCard.tsx` | Bash | 8 |  | G14, G15, G22, G40 |
| `src/components/chat/DeepenAndTuneBar.tsx` | Bash | 1 |  | G38 |
| `src/components/chat/DiscourseAudioStrip.tsx` | Bash | 1 |  | G15 |
| `src/components/chat/InlineActions.tsx` | Bash | 2 |  | G39 |
| `src/components/chat/QuotaAuthPrompt.tsx` | Bash | 2 |  | G14 |
| `src/components/common/CookieConsentBanner.tsx` | Bash | 1 |  | G15 |
| `src/components/common/CrisisLines.tsx` | Bash | 1 |  | G15 |
| `src/components/common/PushNotificationsManager.tsx` | Bash | 1 |  | G15 |
| `src/components/common/PushPermissionPrompt.tsx` | Bash | 6 |  | G7, G15, G25 |
| `src/components/common/SafetyDisclaimer.tsx` | Bash | 1 |  | G22 |
| `src/components/kg/KGConceptMap.tsx` | Bash | 1 |  | G38 |
| `src/components/landing/HeroSection.tsx` | Bash | 4 |  | G27 |
| `src/components/landing/SampleWisdomSection.tsx` | Bash | 1 |  | G38 |
| `src/components/meditation/meditationSteps.ts` | Bash | 1 |  | G38 |
| `src/components/profile/CancelFlow.tsx` | Bash | 4 |  | G15, G32 |
| `src/components/profile/GuidancePreview.tsx` | Bash | 1 |  | G14 |
| `src/components/profile/settings/AccountDataCard.tsx` | Bash | 2 |  | G15, G32 |
| `src/hooks/useChatCapabilities.ts` | Bash | 1 |  | G10 |
| `src/hooks/useSpeechRecognition.ts` | Bash | 1 |  | G15 |
| `src/hooks/useStudyNotebooks.ts` | Bash | 3 |  | G32 |
| `src/hooks/useVoiceInput.ts` | Bash | 1 |  | G15 |
| `src/index.css` | Bash | 2 |  | G22, G40 |
| `src/integrations/supabase/client.ts` | Bash | 2 |  | G15 |
| `src/integrations/supabase/previewAuthStorage.ts` | Bash | 4 |  | G27 |
| `src/integrations/supabase/types.ts` | Bash | 5 |  | G27 |
| `src/lib/authConstants.ts` | Bash | 1 |  | G15 |
| `src/lib/backendUrl.ts` | Bash | 1 |  | G15 |
| `src/lib/chat/anonSession.ts` | Bash | 1 |  | G40 |
| `src/lib/chat/errors.ts` | Bash | 10 |  | G7, G10, G25, G40 |
| `src/lib/chat/fetchWithRetry.ts` | Bash | 1 |  | G40 |
| `src/lib/chat/pushEligibility.ts` | Bash | 3 |  | G10, G40, G41 |
| `src/lib/chat/responsePreferences.ts` | Bash | 1 |  | G4 |
| `src/lib/chat/sereneMindGating.ts` | Bash | 1 |  | G40 |
| `src/lib/chat/streaming.ts` | Bash | 10 |  | G7, G14, G25, G40 |
| `src/lib/chat/transport.ts` | Bash | 10 |  | G7, G25, G39, G40 |
| `src/lib/chat/types.ts` | Bash | 12 |  | G4, G7, G25, G34, G40 |
| `src/lib/chatStorage.ts` | Bash | 4 |  | G15, G40 |
| `src/lib/crisisHelplines.ts` | Bash | 3 |  | G6, G15, G22 |
| `src/lib/featureFlags.ts` | Bash | 1 |  | G38 |
| `src/lib/firstPersonCitationMapper.ts` | Bash | 1 |  | G34 |
| `src/lib/firstPersonService.ts` | Bash | 2 |  | G34, G40 |
| `src/lib/healingCourses.ts` | Bash | 2 |  | G7, G38 |
| `src/lib/memoryApi.ts` | Bash | 3 |  | G15, G32 |
| `src/lib/profileStorage.ts` | Bash | 2 |  | G32 |
| `src/lib/savedAnswersStorage.ts` | Bash | 1 |  | G14 |
| `src/lib/sentry.ts` | Bash | 2 |  | G15 |
| `src/locales/en.json` | Bash | 2 |  | G14 |
| `src/pages/AuthPage.tsx` | Bash | 6 |  | G15, G40 |
| `src/pages/Index.tsx` | Bash | 3 |  | G14, G15 |
| `src/pages/ProfilePage.tsx` | Bash | 2 |  | G15, G40 |
| `src/pages/TeacherWords.tsx` | Bash | 2 |  | G34, G40 |
| `src/test/ChatErrorBanner.test.tsx` | Bash | 1 |  | G40 |
| `src/test/ChatMessage-a11y.test.tsx` | Bash | 2 |  | G22, G40 |
| `src/test/DesktopSidebar.test.tsx` | Bash | 1 |  | G10 |
| `src/test/LanguageTranslateButton.test.tsx` | Bash | 1 |  | G10 |
| `src/test/chat/errors.test.ts` | Bash | 6 |  | G7, G25 |
| `src/test/chat/noClientSummary.test.ts` | Bash | 1 |  | G10 |
| `src/test/chat/pushEligibility.test.ts` | Bash | 2 |  | G10, G40 |
| `src/test/chat/streaming-contract.test.ts` | Bash | 3 |  | G14 |
| `src/test/chatErrors.test.ts` | Bash | 3 |  | G10 |
| `src/test/citation-attribution.test.tsx` | Bash | 1 |  | G40 |
| `src/test/crisisHelplines.test.tsx` | Bash | 3 |  | G10, G40 |
| `src/test/useChatCapabilities.test.ts` | Bash | 1 |  | G10 |
| `supabase/config.toml` | Bash | 1 |  | G3 |
| `supabase/functions/_shared/memoryFacts.ts` | Bash | 1 |  | G32 |
| `supabase/functions/delete-my-account/index.ts` | Bash | 7 |  | G15, G32, G41 |
| `supabase/functions/export-my-data/index.ts` | Bash | 2 |  | G32 |
| `supabase/functions/memory-extract-drain/index.ts` | Bash | 5 |  | G27, G32 |
| `supabase/functions/memory-extract/index.ts` | Bash | 2 |  | G32 |
| `supabase/functions/sarvam-stt/index.ts` | Bash | 6 |  | G7, G25 |
| `supabase/migrations/20260630140000_study_notebooks.sql` | Bash | 2 |  | G32 |
| `supabase/migrations/20260711000000_enable_rls_on_all_tables.sql` | Bash | 1 |  | G2 |
| `supabase/migrations/20260713000000_create_push_devices.sql` | Bash | 1 |  | G32 |
| `supabase/migrations/20260805000003_source_releases.sql` | Bash | 1 |  | G33 |
| `supabase/migrations/20261007000000_faculty_answer_labels.sql` | Bash | 1 |  | G2 |
| `supabase/migrations/20261021000100_require_active_memory_consent.sql` | Bash | 2 |  | G41 |
| `supabase/migrations/20261021000200_tenant_scope_legacy_memory.sql` | Bash | 1 |  | G32 |
| `supabase/schema_snapshot.sql` | Bash | 1 |  | G10 |
| `tailwind.config.ts` | Bash | 2 |  | G22 |
| `tests/e2e/a11y-smoke.spec.ts` | Bash | 6 |  | G22, G40 |
| `tests/e2e/landing-accessibility.spec.ts` | Bash | 3 |  | G22, G40 |
| `tests/e2e/rls-cross-user.spec.ts` | Bash | 1 |  | G40 |
| `tests/e2e/seeker-journey.spec.ts` | Bash | 1 |  | G40 |
| `tests/e2e/support.ts` | Bash | 1 |  | G22 |
| `vercel.json` | Bash | 7 |  | G3, G27 |
| `vite.config.ts` | Bash | 4 |  | G15, G22, G27 |
| `whatsapp_bot/wa_bot.py` | Bash | 4 |  | G10, G14 |

## 5. Directories searched

| Directory | Tools | Calls | Agents |
|---|---|---|---|
| `.git/` | Bash | 5 | G17, G41 |
| `.github/` | Bash | 14 | G14, G16, G17, G27, G41 |
| `.github/workflows/` | Bash | 27 | G2, G3, G7, G15, G16, G17, G27, G32, G33, G37, G38, G39, G40, G41 |
| `.lovable/` | Bash | 5 | G27 |
| `.railway/` | Bash | 8 | L, G2, G3, G7, G16, G17, G41 |
| `android/app/src/androidTest/` | Bash | 1 | G15 |
| `android/app/src/test/` | Bash | 1 | G15 |
| `app/` | Bash | 11 | G2, G3, G4, G10, G14, G39, G40 |
| `audits/` | Bash | 8 | L, G3, G7, G16, G17, G37 |
| `audits/audit-output-2026-11-04/` | Bash | 282 | L, G2, G3, G4, G7, G10, G14, G15, G16, G22, G25, G27, G31, G32, G33, G34, G36, G37, G38, G39, G40, G41 |
| `audits/audit-output-2026-11-04//` | Bash | 25 | L, G7, G14, G25 |
| `audits/audit-output-2026-11-04/specifications/` | Bash | 117 | L, G2, G3, G4, G6, G7, G14, G15, G16, G17, G22, G27, G32, G34, G36, G37, G38, G39, G40, G41 |
| `audits/audit-output-2026-11-04/specifications//` | Bash | 1 | G37 |
| `audits/evidence/` | Bash | 4 | G2, G33 |
| `backend/` | Bash | 452 | L, G2, G3, G4, G7, G10, G14, G16, G25, G31, G32, G34, G37, G38, G39, G40, G41 |
| `backend/app/` | Bash | 29 | L, G2, G4, G7, G14, G16, G25, G32, G33, G38, G39, G40, G41 |
| `backend/app/api/` | Bash | 7 | G7, G16, G17, G40, G41 |
| `backend/app/generation/` | Bash | 2 | G16, G40 |
| `backend/app/pipeline/` | Bash | 1 | G14 |
| `backend/app/pipeline/stages/` | Bash | 3 | G7, G41 |
| `backend/app/schemas/` | Bash | 3 | G14 |
| `backend/app/streaming/` | Bash | 2 | G16, G40 |
| `backend/benchmarks/` | Bash | 3 | G10, G14, G37 |
| `backend/config/` | Bash | 4 | G7, G10 |
| `backend/data/` | Bash | 2 | G2 |
| `backend/domain/` | Bash | 2 | G7, G38 |
| `backend/evaluation/` | Bash | 1 | G7 |
| `backend/guardrails/` | Bash | 1 | G38 |
| `backend/infrastructure/` | Bash | 1 | L |
| `backend/ingest/` | Bash | 4 | G7, G33, G38 |
| `backend/ingest/verbatim/` | Bash | 2 | G33 |
| `backend/rag/` | Bash | 7 | G2, G7, G14, G32, G38, G41 |
| `backend/rag/nodes/` | Bash | 3 | G7, G41 |
| `backend/scripts/` | Bash | 6 | G7, G8, G25, G33, G37 |
| `backend/scripts/ops/` | Bash | 16 | G7, G10, G14, G25, G33, G37, G39, G40, G41 |
| `backend/services/` | Bash | 17 | L, G2, G7, G14, G32, G38, G39, G40, G41 |
| `backend/services/cache/` | Bash | 1 | G10 |
| `backend/services/canonical_memory/` | Bash | 4 | G32, G33, G40 |
| `backend/services/llm/` | Bash | 1 | G25 |
| `backend/services/memory/` | Bash | 1 | G33 |
| `backend/services/personalization/` | Bash | 1 | G32 |
| `backend/tasks/` | Bash | 1 | G33 |
| `backend/tests/` | Bash | 31 | G2, G4, G7, G10, G14, G16, G17, G32, G33, G38, G39, G40, G41 |
| `backend/tests/security/` | Bash | 1 | G39 |
| `config/` | Bash | 1 | G34 |
| `docs/` | Bash | 14 | L, G7, G10, G14, G16, G41 |
| `docs/adr/` | Bash | 2 | G40 |
| `docs/agent/claude-md-archive/` | Bash | 4 | G3, G16, G17, G40 |
| `docs/architecture/` | Bash | 5 | G14, G16, G27, G40 |
| `docs/audits/` | Bash | 2 | G7 |
| `docs/operations/` | Bash | 1 | G16 |
| `docs/runbooks/` | Bash | 11 | G2, G3, G7, G39, G41 |
| `evals/` | Bash | 8 | G7, G10, G14, G39 |
| `evals/first_person/` | Bash | 4 | G37, G38, G40 |
| `evals/gold_set_v1/` | Bash | 4 | G7, G37, G40 |
| `evals/pr_suite/` | Bash | 13 | G2, G4, G10, G34, G37, G38, G39, G40 |
| `evals/retrieval_bank/` | Bash | 9 | G4, G10, G33, G34, G37, G38, G40 |
| `evals/scenarios/` | Bash | 1 | G39 |
| `hooks/` | Bash | 1 | G22 |
| `infrastructure/` | Bash | 7 | G2, G7, G39 |
| `infrastructure/cron/` | Bash | 4 | G2, G39, G40 |
| `infrastructure/grafana/` | Bash | 1 | G2 |
| `infrastructure/k8s/` | Bash | 2 | L, G17 |
| `infrastructure/k8s/helm/mukthiguru/` | Bash | 4 | G17 |
| `infrastructure/prometheus/` | Bash | 4 | G2, G39, G40 |
| `ingest/` | Bash | 2 | G10, G16 |
| `ios/` | Bash | 1 | G8 |
| `memory/` | Bash | 1 | G32 |
| `memory/okf/` | Bash | 1 | G33 |
| `mobile/expo/` | Bash | 2 | G15, G36 |
| `node_modules/` | Bash | 6 | G6, G22, G34, G40, G41 |
| `node_modules/@axe-core/` | Bash | 2 | G6, G22 |
| `node_modules/@axe-core/playwright/` | Bash | 6 | G6, G22 |
| `node_modules/playwright/` | Bash | 9 | G6, G22 |
| `public/` | Bash | 1 | G15 |
| `rag/` | Bash | 2 | G10, G14 |
| `scripts/` | Bash | 8 | G3, G7, G16, G17, G25 |
| `scripts/deploy/` | Bash | 3 | G3 |
| `scripts/guards/` | Bash | 9 | G10, G14, G15, G16, G17, G33, G40 |
| `scripts/ops/` | Bash | 11 | G2, G3, G7, G8, G25, G33, G39, G41 |
| `services/` | Bash | 7 | G2, G4, G10, G34, G38, G39 |
| `src/` | Bash, Grep | 43 | G4, G6, G7, G22, G32, G34, G40, G41 |
| `src/components/` | Bash | 6 | G7, G14, G22, G34 |
| `src/components/chat/` | Bash | 2 | G34, G40 |
| `src/components/onboarding/` | Bash | 1 | G40 |
| `src/components/profile/` | Bash | 2 | G32, G40 |
| `src/components/profile/settings/` | Bash | 1 | G32 |
| `src/lib/` | Bash | 8 | G4, G14, G15, G27, G32, G34, G40 |
| `src/lib/chat/` | Bash | 5 | G4, G7, G10, G14 |
| `src/lib/streaming/` | Bash | 1 | G16 |
| `src/pages/` | Bash | 2 | G22 |
| `src/test/` | Bash | 4 | G40 |
| `src/test/chat/` | Bash | 4 | G7, G25 |
| `src/types/` | Bash | 1 | G14 |
| `supabase/` | Bash | 4 | G7 |
| `supabase/functions/` | Bash | 8 | G7, G10, G14, G15, G40 |
| `supabase/functions/_shared/` | Bash | 1 | G32 |
| `supabase/functions/delete-my-account/` | Bash | 1 | G40 |
| `supabase/functions/eval-run/` | Bash | 3 | G10, G14 |
| `supabase/functions/memory-extract/` | Bash | 1 | G14 |
| `supabase/functions/sarvam-stt/` | Bash | 4 | G7, G25 |
| `supabase/migrations/` | Bash | 17 | L, G3, G7, G10, G32, G33, G38, G39, G40 |
| `tests/` | Bash | 18 | G2, G3, G7, G14, G33, G37, G38, G39, G40 |
| `tests/e2e/` | Bash | 8 | G15, G22, G40, G41 |

## 6. Web sources

| Source | Agents |
|---|---|
| fetch-docs: https://docs.railway.com/deployments/healthchecks | G3 |
| fetch-docs: https://docs.railway.com/deployments/healthchecks#__next | G3 |
| fetch-docs: https://docs.railway.com/infrastructure-as-code | G3 |
| fetch-docs: https://docs.railway.com/infrastructure-as-code#iac-vs-config-as-code | G3 |
| fetch-docs: https://docs.railway.com/infrastructure-as-code/reference#__next | G3 |
| fetch-docs: infrastructure-as-code | G3 |
| https://docs.railway.com/builds/dockerfiles | G3 |
| https://docs.railway.com/cron-jobs | G3 |
| https://docs.railway.com/databases/redis | G3 |
| https://docs.railway.com/deployments/deployment-teardown | G3 |
| https://docs.railway.com/deployments/deployments | G3 |
| https://docs.railway.com/deployments/github-autodeploys | G3 |
| https://docs.railway.com/deployments/healthchecks | G3 |
| https://docs.railway.com/deployments/monorepo | G3 |
| https://docs.railway.com/deployments/pre-deploy-command | G3 |
| https://docs.railway.com/deployments/restart-policy | G3 |
| https://docs.railway.com/deployments/rollbacks | G3 |
| https://docs.railway.com/deployments/scaling | G3 |
| https://docs.railway.com/environments | G3 |
| https://docs.railway.com/infrastructure-as-code | G3 |
| https://docs.railway.com/infrastructure-as-code/reference | G3 |
| https://docs.railway.com/networking/domains | G3 |
| https://docs.railway.com/networking/private-networking | G3 |
| https://docs.railway.com/networking/private-networking/how-it-works | G3 |
| https://docs.railway.com/networking/private-networking/library-configuration | G3 |
| https://docs.railway.com/observability | G3 |
| https://docs.railway.com/pricing/cost-control | G3 |
| https://docs.railway.com/variables | G3 |
| https://docs.railway.com/variables/reference | G3 |
| https://docs.railway.com/volumes/backups | G3 |
| https://docs.railway.com/volumes/reference | G3 |
| search-docs: .railwayignore ignore files build | G3 |
| search-docs: RAILWAY_DEPLOYMENT_DRAINING_SECONDS SIGTERM graceful shutdown | G3 |
| search-docs: Railpack default builder Dockerfile takes precedence | G3 |
| search-docs: bind to IPv6 :: private networking Dockerfile listen host | G3 |
| search-docs: config as code railway.json railway.toml | L |
| search-docs: deploy Qdrant on Railway | G3 |
| search-docs: healthchecks deployment healthcheck timeout | L |
| search-docs: infrastructure as code railway.ts service options reference | G3 |
| search-docs: monitors alerts notifications metrics logs retention | G3 |
| search-docs: pre-deploy command migrations volumes | L |
| search-docs: private networking internal hostname IPv6 bind | L |
| search-docs: railway.ts infrastructure as code defineRailway | L |
| search-docs: rollback to previous deployment | G3 |
| search-docs: volumes backups limits replicas single volume size | G3 |

## 7. Repository files created or changed

| File | How |
|---|---|
| `audits/audit-output-2026-11-04/FINAL_AUDIT_GAP_ANALYSIS.md` | commit fb5cab0f; follow-up commit; written by L |
| `audits/audit-output-2026-11-04/FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` | commit fb5cab0f; follow-up commit; written by L |
| `audits/audit-output-2026-11-04/FINAL_DECISION_AND_RISK_REGISTER.md` | commit fb5cab0f; follow-up commit; written by L |
| `audits/audit-output-2026-11-04/FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` | commit fb5cab0f; follow-up commit; written by G16 |
| `audits/audit-output-2026-11-04/FINAL_PENDING_WORK_REGISTER.md` | commit fb5cab0f; follow-up commit |
| `audits/audit-output-2026-11-04/FINAL_PRODUCTION_RELEASE_READINESS.md` | commit fb5cab0f; follow-up commit; written by L |
| `audits/audit-output-2026-11-04/FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` | commit fb5cab0f; written by G33 |
| `audits/audit-output-2026-11-04/FINAL_RAILWAY_STAGING_READINESS.md` | commit fb5cab0f; written by G3 |
| `audits/audit-output-2026-11-04/FINAL_READINESS_AND_GAP_ANALYSIS.md` | commit fb5cab0f; follow-up commit; written by L |
| `audits/audit-output-2026-11-04/FINAL_SPECIFICATION_COMPLETENESS_MATRIX.md` | commit fb5cab0f; follow-up commit; written by L |
| `audits/audit-output-2026-11-04/FINAL_USAGE_AND_VERIFICATION_LOG.md` | commit fb5cab0f; follow-up commit; written by L |
| `audits/audit-output-2026-11-04/IMPLEMENTATION-AGENT-PROMPT.md` | commit fb5cab0f; follow-up commit |
| `audits/audit-output-2026-11-04/README.md` | commit fb5cab0f |
| `audits/audit-output-2026-11-04/findings-index.md` | commit fb5cab0f; follow-up commit |
| `audits/audit-output-2026-11-04/specifications/AI_HARNESS_PROMPT_AND_CONTEXT_SPEC.md` | commit fb5cab0f; written by G38 |
| `audits/audit-output-2026-11-04/specifications/ARCHITECTURE_DECISION_RECORDS_HISTORICAL.md` | commit fb5cab0f; written by G40 |
| `audits/audit-output-2026-11-04/specifications/COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` | commit fb5cab0f; follow-up commit; written by G40 |
| `audits/audit-output-2026-11-04/specifications/DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md` | commit fb5cab0f; written by G33 |
| `audits/audit-output-2026-11-04/specifications/GURU_KNOWLEDGE_AND_KNOWLEDGE_GRAPH_SPEC.md` | commit fb5cab0f; written by G38 |
| `audits/audit-output-2026-11-04/specifications/INGESTION_AND_CONTENT_PROCESSING_SPEC.md` | commit fb5cab0f; written by G33 |
| `audits/audit-output-2026-11-04/specifications/MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` | commit fb5cab0f; written by G4 |
| `audits/audit-output-2026-11-04/specifications/PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` | commit fb5cab0f; written by G32 |
| `audits/audit-output-2026-11-04/specifications/PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` | commit fb5cab0f; written by G2 |
| `audits/audit-output-2026-11-04/specifications/RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` | commit fb5cab0f; written by G3 |
| `audits/audit-output-2026-11-04/specifications/RETRIEVAL_AND_RAG_SPEC.md` | commit fb5cab0f; written by G4 |
| `audits/audit-output-2026-11-04/specifications/SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md` | commit fb5cab0f; written by G4 |
| `audits/audit-output-2026-11-04/unresolved-questions.md` | commit fb5cab0f |
| `docs/DEVELOPER_GUIDE.md` | commit fb5cab0f |
| `docs/RAG_RUNTIME_DAG.md` | commit fb5cab0f |
| `docs/architecture/README.md` | commit fb5cab0f |
| `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` | commit fb5cab0f |
| `lessons.md` | commit fb5cab0f |
| `audits/audit-output-2026-11-04/03-product-journeys-functional-requirements.md` | follow-up commit |
| `audits/audit-output-2026-11-04/05-current-architecture-and-request-flow.md` | follow-up commit |
| `audits/audit-output-2026-11-04/06-data-ingestion-quality-lineage.md` | follow-up commit |
| `audits/audit-output-2026-11-04/07-video-audio-multisource-synthesis.md` | follow-up commit |
| `audits/audit-output-2026-11-04/08-qdrant-graph-retrieval.md` | follow-up commit |
| `audits/audit-output-2026-11-04/10-spiritual-answer-quality-expected-behavior.md` | follow-up commit |
| `audits/audit-output-2026-11-04/12b-ethical-retention-and-mentor-ux.md` | follow-up commit |
| `audits/audit-output-2026-11-04/13-code-quality-architectural-debt.md` | follow-up commit |
| `audits/audit-output-2026-11-04/14-security-safety-privacy-permissions.md` | follow-up commit |
| `audits/audit-output-2026-11-04/14d-user-journey-and-frontend-walkthrough.md` | follow-up commit |
| `audits/audit-output-2026-11-04/15-reliability-performance-cost-observability.md` | follow-up commit |
| `audits/audit-output-2026-11-04/16-root-cause-and-failure-register.md` | follow-up commit |
| `audits/audit-output-2026-11-04/20-ordered-engineering-roadmap.md` | follow-up commit |
| `audits/audit-output-2026-11-04/21-file-level-implementation-specifications.md` | follow-up commit |
| `audits/audit-output-2026-11-04/22a-acceptance-criteria-and-testing-plan.md` | follow-up commit |
| `audits/audit-output-2026-11-04/24-coding-agent-master-handoff.md` | follow-up commit |
| `audits/audit-output-2026-11-04/25-phase-specific-coding-prompts.md` | follow-up commit |
| `audits/audit-output-2026-11-04/27-execution-log-coverage-and-usage.md` | follow-up commit |
| `audits/audit-output-2026-11-04/CONVENTIONS.md` | follow-up commit |
| `audits/audit-output-2026-11-04/FINAL_AUDIT_DOCUMENT_INVENTORY.md` | follow-up commit |
| `audits/audit-output-2026-11-04/specifications/ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md` | follow-up commit; written by G22 |
| `audits/audit-output-2026-11-04/specifications/MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md` | follow-up commit; written by G15 |
| `audits/audit-output-2026-11-04/traceability-matrix.md` | follow-up commit |
| `backend/CLAUDE.md` | follow-up commit; written by L |
| `audits/audit-output-2026-11-04/specifications/LOAD_AND_COST_MODEL.md` | follow-up commit; written by G37 |
| `audits/audit-output-2026-11-04/specifications/LOVABLE_SYNC_PATH_REVIEW.md` | follow-up commit; written by G27 |

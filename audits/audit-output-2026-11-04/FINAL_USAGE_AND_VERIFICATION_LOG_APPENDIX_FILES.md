# Appendix to the usage log: files read and updated in the final verification pass

Generated on 2026-11-06 from the session's tool-call logs. Companion to `FINAL_USAGE_AND_VERIFICATION_LOG.md`.

## 1. Method and limits

- Window: every tool call made on or after `2026-11-05T06:56:41.204Z`, when the final-verification brief arrived, until this appendix was generated.
- Sources: the main-session log and 37 subagent logs of this session.
- A file counts as read when a `Read` call opened it, a `Grep`/`Glob` call searched it, or a shell command (`cat`, `sed`, `head`, `tail`, `awk`, `grep`, `rg`, `wc`, `python`, `diff`, `git show/diff/log/blame`) named it. "Partial" means every `Read` call used an offset or limit.
- Limits: a shell command that reached files through a glob, a variable or a loop is not resolved to each file. Files that a `Grep` over a directory matched are counted under the directory, not one by one. Files outside the repository (scratchpad, transcripts) are excluded.
- The 2026-11-04 audit's own reading is recorded in `27-execution-log-coverage-and-usage.md`, not here.

## 2. Summary

| Measure | Count |
|---|---|
| Repository files read | 466 |
| Directories searched | 101 |
| Web sources (pages, searches, Railway doc queries) | 45 |
| Repository files created or changed | 56 |

| Top-level directory | Files read |
|---|---|
| `backend` | 190 |
| `src` | 68 |
| `audits` | 41 |
| `docs` | 34 |
| `scripts` | 29 |
| `(root)` | 22 |
| `infrastructure` | 15 |
| `supabase` | 15 |
| `.github` | 12 |
| `evals` | 10 |
| `android` | 8 |
| `ios` | 7 |
| `tests` | 5 |
| `mobile` | 4 |
| `config` | 2 |
| `.railway` | 1 |
| `app` | 1 |
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
| G6 | Sonnet: audit document inventory |
| G7 | Haiku full read lessons.md part 1 |
| G8 | I: telemetry remainder, encoder check, shims |
| G9 | Recount findings into pending register |
| G10 | G: CI repair and final small tasks |
| G11 | S2 data, Qdrant, retrieval audit |
| G12 | S3 AI harness, answers, safety, evals |
| G13 | Sonnet: re-verify batches 9-13 |
| G14 | Sonnet: mobile apps review |
| G15 | Lessons and documentation review |
| G16 | Sonnet: k8s manifests review |
| G17 | H: outcome telemetry (T2-03) |
| G18 | Independent adversarial audit review |
| G19 | S1 backend, stability, security audit |
| G20 | C: rights register, logs, consent |
| G21 | Sonnet: accessibility audit |
| G22 | Haiku full read lessons.md part 3 |
| G23 | A: fail-closed teaching route |
| G24 | Haiku full read lessons.md part 2 |
| G25 | D: frontend safety and wiring |
| G26 | B: gate honesty and spend cap |
| G27 | Journey walk and competitive analysis |
| G28 | Haiku: audit docs link check |
| G29 | Personal mentor memory spec |
| G30 | Ingestion and data-quality specs |
| G31 | Retrieval, synthesis, answer specs |
| G32 | Haiku guardrail review of diff |
| G33 | Guru knowledge and AI harness specs |
| G34 | Reliability, security, ops spec |
| G35 | FR/NFR matrix and historical ADRs |
| G36 | Independent review of final package |
| G37 | S4 product, guru, rights, FR audit |

## 4. Repository files read

| File | Tools | Calls | Partial only | Agents |
|---|---|---|---|---|
| `.dockerignore` | Bash | 5 |  | G3, G16 |
| `.env.example` | Bash | 1 |  | G30 |
| `.env.mobile` | Bash | 1 |  | G14 |
| `.env.production` | Bash | 1 |  | G16 |
| `.github/workflows/backup.yml` | Bash | 3 |  | G2, G35 |
| `.github/workflows/build-deploy.yml` | Bash | 3 |  | G3, G16 |
| `.github/workflows/dependency-check.yml` | Bash | 2 |  | G14, G34 |
| `.github/workflows/eval-gate.yml` | Bash | 3 |  | G9, G13 |
| `.github/workflows/fixture-stores.yml` | Bash | 1 |  | G9 |
| `.github/workflows/lint-test.yml` | Bash | 3 |  | G14, G15, G35 |
| `.github/workflows/nightly-audit.yml` | Bash | 6 |  | G9, G30, G35 |
| `.github/workflows/nightly-eval.yml` | Bash | 1 |  | G35 |
| `.github/workflows/nightly-load.yml` | Bash | 1 |  | G35 |
| `.github/workflows/nightly-rls.yml` | Bash | 3 |  | G2, G29 |
| `.github/workflows/security-audit.yml` | Bash | 1 |  | G34 |
| `.github/workflows/supabase-schema-snapshot.yml` | Bash | 1 |  | G9 |
| `.gitignore` | Bash | 3 |  | G3, G14 |
| `.gitleaks.toml` | Bash | 1 |  | G7 |
| `.pre-commit-config.yaml` | Bash | 5 |  | G13, G15 |
| `.railway/railway.ts` | Bash | 13 |  | L, G2, G3, G15, G16, G34, G36 |
| `.railwayignore` | Bash | 4 |  | L, G3, G15 |
| `AGENTS.md` | Bash | 10 |  | G6, G9, G15, G35 |
| `CLAUDE.md` | Bash | 29 |  | L, G2, G3, G6, G7, G9, G13, G15, G16, G35, G36 |
| `README.md` | Bash | 23 |  | L, G6, G15, G16, G36 |
| `android/.gitignore` | Bash | 2 |  | G14 |
| `android/app/.gitignore` | Bash | 2 |  | G14 |
| `android/app/build.gradle` | Bash | 1 |  | G14 |
| `android/app/src/main/AndroidManifest.xml` | Bash | 1 |  | G14 |
| `android/app/src/main/java/com/askmukthiguru/app/MainActivity.java` | Bash | 1 |  | G14 |
| `android/app/src/main/res/xml/file_paths.xml` | Bash | 1 |  | G14 |
| `android/key.properties.example` | Bash | 1 |  | G14 |
| `android/variables.gradle` | Bash | 1 |  | G14 |
| `app/__init__.py` | Bash | 3 |  | G6 |
| `audits/audit-output-2026-11-04/00-executive-overview-and-scorecard.md` | Bash | 2 |  | L |
| `audits/audit-output-2026-11-04/03-product-journeys-functional-requirements.md` | Bash | 2 |  | G6, G29 |
| `audits/audit-output-2026-11-04/13-code-quality-architectural-debt.md` | Bash | 2 |  | G6, G13 |
| `audits/audit-output-2026-11-04/14d-user-journey-and-frontend-walkthrough.md` | Bash | 1 |  | G6 |
| `audits/audit-output-2026-11-04/20-ordered-engineering-roadmap.md` | Bash | 2 |  | L, G29 |
| `audits/audit-output-2026-11-04/22b-railway-deployment-readiness-runbook.md` | Bash | 1 |  | G15 |
| `audits/audit-output-2026-11-04/26-independent-adversarial-review-and-residual-risks.md` | Bash | 2 |  | L |
| `audits/audit-output-2026-11-04/CONVENTIONS.md` | Bash | 7 |  | L, G14, G15, G16 |
| `audits/audit-output-2026-11-04/FINAL_AUDIT_DOCUMENT_INVENTORY.md` | Bash | 6 |  | G6 |
| `audits/audit-output-2026-11-04/FINAL_AUDIT_GAP_ANALYSIS.md` | Bash | 3 |  | L, G36 |
| `audits/audit-output-2026-11-04/FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` | Bash | 2 |  | L |
| `audits/audit-output-2026-11-04/FINAL_DECISION_AND_RISK_REGISTER.md` | Bash | 3 |  | L |
| `audits/audit-output-2026-11-04/FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` | Bash | 7 |  | L, G15 |
| `audits/audit-output-2026-11-04/FINAL_PENDING_WORK_REGISTER.md` | Bash | 8 |  | L, G6, G9, G13, G15, G33, G36 |
| `audits/audit-output-2026-11-04/FINAL_PRODUCTION_RELEASE_READINESS.md` | Bash | 5 |  | L, G21, G36 |
| `audits/audit-output-2026-11-04/FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` | Bash | 2 |  | L, G36 |
| `audits/audit-output-2026-11-04/FINAL_RAILWAY_STAGING_READINESS.md` | Bash | 3 |  | L |
| `audits/audit-output-2026-11-04/FINAL_READINESS_AND_GAP_ANALYSIS.md` | Bash, Read | 6 |  | L, G6, G15, G35 |
| `audits/audit-output-2026-11-04/FINAL_SPECIFICATION_COMPLETENESS_MATRIX.md` | Bash | 4 |  | L, G36 |
| `audits/audit-output-2026-11-04/FINAL_USAGE_AND_VERIFICATION_LOG.md` | Bash | 2 |  | L |
| `audits/audit-output-2026-11-04/IMPLEMENTATION-AGENT-PROMPT.md` | Bash | 11 |  | L, G6, G30, G33, G36 |
| `audits/audit-output-2026-11-04/README.md` | Bash | 2 |  | L, G36 |
| `audits/audit-output-2026-11-04/findings-index.md` | Bash | 12 |  | L, G9, G13, G15, G35, G36 |
| `audits/audit-output-2026-11-04/specifications/ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md` | Bash | 5 |  | L, G21 |
| `audits/audit-output-2026-11-04/specifications/AI_HARNESS_PROMPT_AND_CONTEXT_SPEC.md` | Bash | 1 |  | L |
| `audits/audit-output-2026-11-04/specifications/ARCHITECTURE_DECISION_RECORDS_HISTORICAL.md` | Bash | 2 |  | L, G16 |
| `audits/audit-output-2026-11-04/specifications/COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` | Bash | 7 |  | L, G36 |
| `audits/audit-output-2026-11-04/specifications/DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md` | Bash | 1 |  | L |
| `audits/audit-output-2026-11-04/specifications/GURU_KNOWLEDGE_AND_KNOWLEDGE_GRAPH_SPEC.md` | Bash | 2 |  | L, G33 |
| `audits/audit-output-2026-11-04/specifications/INGESTION_AND_CONTENT_PROCESSING_SPEC.md` | Bash | 5 |  | L, G36 |
| `audits/audit-output-2026-11-04/specifications/K8S_MANIFESTS_REVIEW.md` | Bash | 3 |  | L, G16 |
| `audits/audit-output-2026-11-04/specifications/MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md` | Bash | 2 |  | L |
| `audits/audit-output-2026-11-04/specifications/MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` | Bash | 2 |  | G4, G36 |
| `audits/audit-output-2026-11-04/specifications/PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` | Bash | 3 |  | L, G14, G36 |
| `audits/audit-output-2026-11-04/specifications/PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` | Bash | 5 |  | L, G2 |
| `audits/audit-output-2026-11-04/specifications/RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` | Bash | 4 |  | L, G16 |
| `audits/audit-output-2026-11-04/specifications/RETRIEVAL_AND_RAG_SPEC.md` | Bash | 1 |  | G4 |
| `audits/audit-output-2026-11-04/specifications/SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md` | Bash | 3 |  | G4, G13, G36 |
| `audits/audit-output-2026-11-04/traceability-matrix.md` | Bash | 1 |  | L |
| `audits/audit-output-2026-11-04/unresolved-questions.md` | Bash | 4 |  | L, G13, G29 |
| `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json` | Bash | 2 |  | G3, G30 |
| `backend/.dockerignore` | Bash | 2 |  | G3 |
| `backend/.env.example` | Bash | 5 |  | G3, G15, G30, G33 |
| `backend/CLAUDE.md` | Bash | 12 |  | G2, G13, G15 |
| `backend/Dockerfile` | Bash | 5 |  | G9, G13 |
| `backend/Dockerfile.railway` | Bash | 13 |  | L, G2, G3, G9, G13, G30, G36 |
| `backend/app/__init__.py` | Bash | 1 |  | G6 |
| `backend/app/answer_outcome.py` | Bash, Read | 4 |  | G2, G9, G34, G35 |
| `backend/app/api/admin.py` | Bash | 1 |  | G13 |
| `backend/app/api/admin_video_review.py` | Bash | 1 |  | G30 |
| `backend/app/api/assistants.py` | Bash | 1 |  | G35 |
| `backend/app/api/canonical_memory.py` | Bash | 1 |  | G29 |
| `backend/app/api/capabilities.py` | Bash | 1 |  | G35 |
| `backend/app/api/chat.py` | Bash | 4 |  | G9, G13, G35 |
| `backend/app/api/compliance.py` | Bash | 3 |  | G9, G15, G29 |
| `backend/app/api/feedback.py` | Bash | 14 |  | L, G13, G35, G36 |
| `backend/app/api/first_person.py` | Bash | 7 |  | G2, G6, G13, G29, G30, G35 |
| `backend/app/api/health.py` | Bash | 12 |  | L, G2, G6, G9, G13, G16, G30, G35, G36 |
| `backend/app/api/ingest.py` | Bash | 2 |  | G30 |
| `backend/app/api/memory.py` | Bash | 4 |  | G6, G29, G35 |
| `backend/app/api/metrics.py` | Bash | 3 |  | L, G2 |
| `backend/app/api/push.py` | Bash | 1 |  | G14 |
| `backend/app/api/teachings.py` | Bash | 6 |  | G9, G13, G33 |
| `backend/app/assistant_registry.py` | Bash | 2 |  | G33 |
| `backend/app/chat_engine.py` | Bash | 1 |  | G13 |
| `backend/app/config.py` | Bash | 33 |  | L, G2, G3, G6, G9, G13, G15, G16, G30, G33, G35, G36 |
| `backend/app/container.py` | Bash | 3 |  | G13 |
| `backend/app/core/limiter.py` | Bash | 1 |  | G2 |
| `backend/app/corpus_governance.py` | Bash | 1 |  | G30 |
| `backend/app/db/seed_ontology.py` | Bash | 1 |  | G33 |
| `backend/app/generation/__init__.py` | Bash | 1 |  | G35 |
| `backend/app/health.py` | Bash | 4 |  | G13, G36 |
| `backend/app/main.py` | Bash | 14 |  | G2, G3, G9, G15, G16, G29, G30, G33, G36 |
| `backend/app/metrics.py` | Bash | 10 |  | L, G2, G30, G35, G36 |
| `backend/app/openrouter_budget.py` | Bash | 3 |  | G2, G6 |
| `backend/app/orchestrator.py` | Bash | 3 |  | G4, G13 |
| `backend/app/orchestrator_utils.py` | Bash | 7 |  | G9, G13, G36 |
| `backend/app/pipeline/pipeline_coordinator.py` | Bash | 2 |  | G2, G13 |
| `backend/app/pipeline/stages/cache_stage.py` | Bash | 3 |  | G9, G13, G35 |
| `backend/app/pipeline/stages/distress_stage.py` | Bash | 2 |  | G9, G35 |
| `backend/app/pipeline/stages/first_person_bridge.py` | Bash | 10 |  | G4, G9, G13, G35, G36 |
| `backend/app/pipeline/stages/graph_stage.py` | Bash | 5 |  | G9, G13, G33 |
| `backend/app/pipeline/stages/guardrail_stage.py` | Bash | 2 |  | G2, G36 |
| `backend/app/pipeline/stages/kill_switch_stage.py` | Bash | 2 |  | G13 |
| `backend/app/pipeline/stages/pipeline_builder.py` | Bash | 8 |  | G13, G15, G36 |
| `backend/app/release_manifest.py` | Bash | 2 |  | G2, G3 |
| `backend/app/route_taxonomy.py` | Bash | 1 |  | G2 |
| `backend/app/schemas/__init__.py` | Bash | 7 |  | G2, G4, G13 |
| `backend/app/stream_orchestrator.py` | Bash | 6 |  | G9, G13 |
| `backend/app/streaming/__init__.py` | Bash | 1 |  | G35 |
| `backend/app/telemetry_db.py` | Bash | 3 |  | G30, G36 |
| `backend/app/telemetry_sink.py` | Bash | 2 |  | G6 |
| `backend/celery_config.py` | Bash | 8 |  | G3, G29, G35, G36 |
| `backend/config/first_person_serving_contract.json` | Bash | 5 |  | G9, G30 |
| `backend/config/gurus.yaml` | Bash | 7 |  | G9, G13, G30, G33, G35 |
| `backend/docker-compose.yml` | Bash | 19 |  | G3, G9, G13, G15, G30, G36 |
| `backend/domain/first_person_context.py` | Bash | 4 |  | G30 |
| `backend/domain/hash_fields.py` | Bash | 3 |  | G9, G30 |
| `backend/evaluation/gold/metrics.py` | Bash | 1 |  | G36 |
| `backend/guardrails/lightweight_handler.py` | Bash | 5 |  | G13, G33 |
| `backend/infrastructure/k8s.yaml` | Bash | 7 |  | L, G16, G36 |
| `backend/ingest/handlers/checkpoint.py` | Bash | 2 |  | G30 |
| `backend/ingest/pipeline.py` | Bash | 12 |  | G6, G9, G30 |
| `backend/ingest/quality_gate.py` | Bash | 1 |  | G30 |
| `backend/ingest/verbatim/README.md` | Bash | 1 |  | G30 |
| `backend/ingest/youtube_loader.py` | Bash | 1 |  | G6 |
| `backend/pyproject.toml` | Bash | 3 |  | G9, G35 |
| `backend/rag/graph_builder.py` | Bash | 1 |  | G13 |
| `backend/rag/graph_strategies.py` | Bash | 1 |  | G9 |
| `backend/rag/intent_prerouter.py` | Bash | 1 |  | G9 |
| `backend/rag/meditation.py` | Bash | 1 |  | G13 |
| `backend/rag/nodes/cross_teacher_reasoning.py` | Bash | 1 |  | G33 |
| `backend/rag/nodes/entity_linking.py` | Bash | 2 |  | G33 |
| `backend/rag/nodes/first_person.py` | Bash | 4 |  | G9, G13, G35 |
| `backend/rag/nodes/generation.py` | Bash | 4 |  | G9 |
| `backend/rag/nodes/intent.py` | Bash | 1 |  | G13 |
| `backend/rag/pipeline_registry.py` | Bash | 2 |  | G9, G35 |
| `backend/rag/prompts/system.py` | Bash | 1 |  | G13 |
| `backend/rag/resolve_followup.py` | Bash | 1 |  | G9 |
| `backend/requirements-dev.txt` | Bash | 1 |  | G35 |
| `backend/requirements.lock` | Bash | 1 |  | G35 |
| `backend/requirements.txt` | Bash | 1 |  | G35 |
| `backend/schemas/feedback.py` | Bash | 2 |  | G36 |
| `backend/scripts/ops/approve_okf_source_manifest.py` | Bash | 1 |  | G30 |
| `backend/scripts/ops/build_first_person_index.py` | Bash | 1 |  | G30 |
| `backend/scripts/ops/build_full_corpus_v10.py` | Bash | 12 |  | G9, G30, G36 |
| `backend/scripts/ops/check_first_person_public_release.py` | Bash | 1 |  | G9 |
| `backend/scripts/ops/check_legacy_guru_tables.py` | Bash | 1 |  | G13 |
| `backend/scripts/ops/data_quality_audit.py` | Bash | 2 |  | G6, G30 |
| `backend/scripts/ops/ensure_fp_payload_indexes.py` | Bash | 1 |  | G30 |
| `backend/scripts/ops/fp_data_quality_scorecard.py` | Bash | 1 |  | G30 |
| `backend/scripts/ops/gate1_load_test.py` | Bash | 7 |  | G2, G35, G36 |
| `backend/scripts/ops/restore_drill.py` | Bash | 3 |  | G30 |
| `backend/scripts/verify_rls_policies.py` | Bash | 1 |  | G29 |
| `backend/services/canonical_memory/context_builder.py` | Bash | 1 |  | G29 |
| `backend/services/circuit_breaker.py` | Bash | 1 |  | G2 |
| `backend/services/crisis_helplines.py` | Bash | 3 |  | G13, G35 |
| `backend/services/doctrine_terms.py` | Bash | 1 |  | G33 |
| `backend/services/feedback_service.py` | Bash | 2 |  | G34 |
| `backend/services/first_person_context_harness.py` | Bash | 1 |  | G30 |
| `backend/services/first_person_context_store.py` | Bash | 10 |  | G9, G30, G35 |
| `backend/services/first_person_facet_planner.py` | Bash | 2 |  | G6 |
| `backend/services/first_person_ingest_service.py` | Bash | 2 |  | G30 |
| `backend/services/first_person_pipeline.py` | Bash | 16 |  | G9, G13, G15, G30, G33, G35, G36 |
| `backend/services/first_person_rights.py` | Bash | 1 |  | G30 |
| `backend/services/first_person_serving_contract.py` | Bash | 8 |  | G3, G9, G30 |
| `backend/services/first_person_set_selector.py` | Bash | 1 |  | G6 |
| `backend/services/first_person_store.py` | Bash | 10 |  | G13, G30, G35 |
| `backend/services/first_person_video_decisions.py` | Bash | 2 |  | G30 |
| `backend/services/fp_fail_closed.py` | Bash | 3 |  | G9, G35 |
| `backend/services/guru_registry.py` | Bash | 4 |  | G13, G33, G35 |
| `backend/services/injection_scanner.py` | Bash | 1 |  | G34 |
| `backend/services/intelligent_metadata_extractor.py` | Bash | 1 |  | G33 |
| `backend/services/layered_memory/l3_persona_generator.py` | Bash | 3 |  | G13 |
| `backend/services/lettuce_detect_service.py` | Bash | 1 |  | G35 |
| `backend/services/lightrag_service.py` | Bash | 2 |  | G6, G33 |
| `backend/services/llm_gateway.py` | Bash | 2 |  | G13 |
| `backend/services/memory/okf_store.py` | Bash | 6 |  | G30, G33, G36 |
| `backend/services/memory_outbox.py` | Bash | 1 |  | G29 |
| `backend/services/openrouter_service.py` | Bash | 1 |  | G2 |
| `backend/services/personalization/cascade_erasure.py` | Bash | 1 |  | G29 |
| `backend/services/prompt_store.py` | Bash | 1 |  | G33 |
| `backend/services/qdrant/indexer.py` | Bash | 3 |  | G30 |
| `backend/services/qdrant_service.py` | Bash | 2 |  | G30 |
| `backend/services/quote_fidelity.py` | Bash | 1 |  | G33 |
| `backend/services/quote_weaver.py` | Bash | 3 |  | G6, G9 |
| `backend/services/serene_mind_engine.py` | Bash | 3 |  | G13, G35 |
| `backend/services/teacher_attribution.py` | Bash | 1 |  | G33 |
| `backend/services/voice/register.py` | Bash | 1 |  | G33 |
| `backend/services/voice/style.py` | Bash | 1 |  | G9 |
| `backend/start_railway.py` | Bash | 10 |  | L, G2, G3, G15, G36 |
| `backend/tasks/cancel_flow_tasks.py` | Bash | 1 |  | G29 |
| `backend/tasks/ingest_tasks.py` | Bash | 2 |  | G30 |
| `backend/tasks/retention_tasks.py` | Bash | 1 |  | G29 |
| `backend/tasks/web_ingest_tasks.py` | Bash | 1 |  | G6 |
| `backend/tests/redteam_harness.py` | Bash | 2 |  | G34 |
| `backend/tests/test_answer_outcome_telemetry.py` | Bash | 1 |  | G9 |
| `backend/tests/test_bridge_attribution_wp4.py` | Bash | 1 |  | G35 |
| `backend/tests/test_builder_replace_and_snapshot.py` | Bash | 2 |  | G9, G35 |
| `backend/tests/test_cache_crisis_bypass.py` | Bash | 1 |  | G35 |
| `backend/tests/test_cache_versioning_and_teaching_guard.py` | Bash | 1 |  | G13 |
| `backend/tests/test_canonical_teacher_ids.py` | Bash | 1 |  | G13 |
| `backend/tests/test_citation_contract.py` | Bash | 3 |  | G13 |
| `backend/tests/test_clip_reporting_and_saved_answers.py` | Bash | 2 |  | G13 |
| `backend/tests/test_config_lint.py` | Bash | 4 |  | G9, G13, G35 |
| `backend/tests/test_config_validation.py` | Bash | 2 |  | G9 |
| `backend/tests/test_container_llm_gateway.py` | Bash | 2 |  | G13 |
| `backend/tests/test_crisis_copy_never_llm_translated.py` | Bash | 1 |  | G35 |
| `backend/tests/test_data_quality_promotion_gate.py` | Bash | 2 |  | G9, G35 |
| `backend/tests/test_distress_provider_fail_closed.py` | Bash | 1 |  | G35 |
| `backend/tests/test_docker_compose_healthcheck.py` | Bash | 4 |  | G9, G13 |
| `backend/tests/test_emotional_side_effect_consent.py` | Bash | 3 |  | G9, G35 |
| `backend/tests/test_exception_and_import_ratchets.py` | Bash | 2 |  | G13 |
| `backend/tests/test_first_person_pipeline_golden.py` | Bash | 4 |  | G9, G13, G35 |
| `backend/tests/test_first_person_public_release_gate.py` | Bash | 3 |  | G9, G35 |
| `backend/tests/test_first_person_serving_contract.py` | Bash | 2 |  | G9 |
| `backend/tests/test_first_person_v10_only.py` | Bash | 1 |  | G35 |
| `backend/tests/test_fixture_stores.py` | Bash | 1 |  | G9 |
| `backend/tests/test_fp_fail_closed.py` | Bash | 5 |  | G9, G13, G33 |
| `backend/tests/test_fp_memory_signals.py` | Bash | 3 |  | G13 |
| `backend/tests/test_fp_quarantine_identity.py` | Bash | 1 |  | G35 |
| `backend/tests/test_gate_first_then_dedup.py` | Bash | 1 |  | G9 |
| `backend/tests/test_general_mode_no_register.py` | Bash | 3 |  | G9, G33, G35 |
| `backend/tests/test_graph_strategy_wiring.py` | Bash | 1 |  | G9 |
| `backend/tests/test_grounding_state_contract.py` | Bash | 1 |  | G4 |
| `backend/tests/test_grounding_state_labeling.py` | Bash | 1 |  | G4 |
| `backend/tests/test_guru_extensibility.py` | Bash | 1 |  | G13 |
| `backend/tests/test_guru_registry_and_modes.py` | Bash | 1 |  | G33 |
| `backend/tests/test_health.py` | Bash | 1 |  | G9 |
| `backend/tests/test_health_falsifiability.py` | Bash | 1 |  | G35 |
| `backend/tests/test_healthz_grace_masking.py` | Bash | 1 |  | G15 |
| `backend/tests/test_l3_persona_preferences.py` | Bash | 1 |  | G13 |
| `backend/tests/test_lesson_guards.py` | Bash | 1 |  | G15 |
| `backend/tests/test_main_cors.py` | Bash | 1 |  | G9 |
| `backend/tests/test_migration_lint.py` | Bash | 2 |  | G9, G35 |
| `backend/tests/test_no_seeker_text_in_logs.py` | Bash | 4 |  | G9, G13, G35 |
| `backend/tests/test_no_unsourced_teacher_attribution.py` | Bash | 4 |  | G9, G13 |
| `backend/tests/test_offline_pr_suite.py` | Bash | 3 |  | G4, G9, G33 |
| `backend/tests/test_pipeline_order_guard.py` | Bash | 2 |  | G13 |
| `backend/tests/test_prod_compose_invariants.py` | Bash | 6 |  | G15, G16, G35 |
| `backend/tests/test_qdrant_write_governance.py` | Bash | 1 |  | G9 |
| `backend/tests/test_rag_properties.py` | Bash | 2 |  | G35 |
| `backend/tests/test_relevance_standalone_gates.py` | Bash | 1 |  | G35 |
| `backend/tests/test_repo_layout.py` | Bash | 1 |  | G14 |
| `backend/tests/test_retrieval_bank_harness.py` | Bash | 1 |  | G9 |
| `backend/tests/test_rights_register_startup.py` | Bash | 3 |  | G9 |
| `backend/tests/test_untrusted_prompt_fences.py` | Bash | 4 |  | G2, G9, G33 |
| `backend/tests/test_v10_hybrid_retrieval.py` | Bash | 1 |  | G9 |
| `backend/tests/test_verified_helplines_only.py` | Bash | 2 |  | G13 |
| `backend/tests/test_voice_governance_docs.py` | Bash | 4 |  | G9, G35 |
| `backend/tests/test_writer_hash_contract.py` | Bash | 2 |  | G9, G30 |
| `capacitor.config.ts` | Bash | 1 |  | G14 |
| `config/first_person_calibration.json` | Bash, Read | 2 |  | G31 |
| `config/helplines.yaml` | Bash | 3 |  | G2, G3, G35 |
| `docker-compose.prod.yml` | Bash | 4 |  | G3, G16 |
| `docs/BACKUP_RESTORE.md` | Bash | 4 |  | G2 |
| `docs/DEVELOPER_GUIDE.md` | Bash | 10 |  | L, G15, G36 |
| `docs/FIRST_PERSON_FOLLOWUPS_SPEC.md` | Bash | 3 |  | L, G4 |
| `docs/INCIDENT_RESPONSE.md` | Bash | 9 |  | G2, G34, G36 |
| `docs/KUBECTL_RUNBOOK.md` | Bash | 2 |  | G16 |
| `docs/MOBILE_RELEASE_RUNBOOK.md` | Bash | 2 |  | G14, G15 |
| `docs/PROD_READY_CHECKLIST.md` | Bash | 2 |  | G15 |
| `docs/RAG_RUNTIME_DAG.md` | Bash | 7 |  | L, G15, G36 |
| `docs/RAILWAY_DEPLOYMENT_CHECKLIST.md` | Bash | 1 |  | G15 |
| `docs/SLO.md` | Bash | 9 |  | G2, G34, G36 |
| `docs/STORE_LISTING.md` | Bash | 3 |  | G14 |
| `docs/adr/0001-publication-model.md` | Bash | 1 |  | G35 |
| `docs/adr/0002-chunking-contract.md` | Bash | 1 |  | G35 |
| `docs/agent/claude-md-archive/agents-md-railway.md` | Bash | 1 |  | G15 |
| `docs/agent/claude-md-archive/database-and-graph.md` | Bash | 1 |  | G35 |
| `docs/agent/claude-md-archive/railway-deployment.md` | Bash | 2 |  | G3, G15 |
| `docs/architecture/README.md` | Bash | 6 |  | L, G15, G36 |
| `docs/architecture/SYSTEM_ARCHITECTURE_HLD_LLD.md` | Bash | 1 |  | G15 |
| `docs/architecture/backend-roadmap.md` | Bash | 1 |  | G15 |
| `docs/architecture/first-person-path-to-prod.md` | Bash | 3 |  | G15, G35 |
| `docs/kubernetes-deployment.md` | Bash | 2 |  | G16 |
| `docs/operations/drills.md` | Bash | 1 |  | G30 |
| `docs/operations/railway-production-status-2026-09-20.md` | Bash | 1 |  | G2 |
| `docs/plans/PLAN.md` | Bash | 1 |  | G15 |
| `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` | Bash | 7 |  | L, G15, G35, G36 |
| `docs/runbooks/ALERTING.md` | Bash | 6 |  | G2, G34 |
| `docs/runbooks/BACKUP_RESTORE_DRILL.md` | Bash | 2 |  | G2, G34 |
| `docs/runbooks/CAPACITY.md` | Bash | 1 |  | G2 |
| `docs/runbooks/MIGRATION_ROLLBACK.md` | Bash | 3 |  | G2, G3 |
| `docs/runbooks/ONCALL.md` | Bash | 3 |  | G2, G34 |
| `docs/runbooks/SECRET_ROTATION.md` | Bash | 1 |  | G2 |
| `docs/runbooks/restore-snapshot.md` | Bash | 3 |  | G2, G34 |
| `docs/runbooks/rollback-release.md` | Bash | 3 |  | G2, G34 |
| `docs/wiki/operations/deployment-and-ci.md` | Bash | 3 |  | G16 |
| `eslint.config.js` | Bash | 3 |  | G9, G21 |
| `evals/pr_suite/abstain_null.jsonl` | Bash | 1 |  | G4 |
| `evals/pr_suite/distress_benign.jsonl` | Bash | 1 |  | G9 |
| `evals/pr_suite/distress_crisis.jsonl` | Bash | 1 |  | G9 |
| `evals/pr_suite/quote_integrity.py` | Bash | 1 |  | G31 |
| `evals/pr_suite/routing.jsonl` | Bash | 1 |  | G4 |
| `evals/pr_suite/voice_lint.py` | Bash | 1 |  | G31 |
| `evals/retrieval_bank/bank.jsonl` | Bash | 3 |  | G30, G31, G35 |
| `evals/retrieval_bank/harness.py` | Bash | 5 |  | G30, G31, G36 |
| `evals/retrieval_bank/metrics.py` | Bash | 1 |  | G31 |
| `evals/run_safety_scenarios.py` | Bash | 1 |  | G2 |
| `index.html` | Bash | 1 |  | G14 |
| `infrastructure/cron/mukthiguru-backup` | Bash | 4 |  | G2, G34, G35 |
| `infrastructure/k8s/README.md` | Bash | 2 |  | G16 |
| `infrastructure/k8s/backend-deployment.yaml` | Bash | 3 |  | G16 |
| `infrastructure/k8s/helm/mukthiguru/Chart.yaml` | Bash | 1 |  | G16 |
| `infrastructure/k8s/helm/mukthiguru/charts/redis-19.6.4.tgz` | Bash | 1 |  | G16 |
| `infrastructure/k8s/helm/mukthiguru/values-minikube.yaml` | Bash | 1 |  | G16 |
| `infrastructure/k8s/helm/mukthiguru/values.yaml` | Bash | 2 |  | G16 |
| `infrastructure/k8s/minikube/start.sh` | Bash | 2 |  | G16 |
| `infrastructure/k8s/skaffold.yaml` | Bash | 2 |  | G16 |
| `infrastructure/k8s_deploy.sh` | Bash | 4 |  | G16 |
| `infrastructure/k8s_deployment.yaml` | Bash | 4 |  | G16 |
| `infrastructure/prometheus/alerting-rules.yml` | Bash | 6 |  | G2, G34, G35, G36 |
| `infrastructure/prometheus/alertmanager.yml` | Bash | 2 |  | G2 |
| `infrastructure/prometheus/prometheus.prod.yml` | Bash | 3 |  | G2 |
| `infrastructure/prometheus/prometheus.yml` | Bash | 1 |  | G2 |
| `ios/.gitignore` | Bash | 2 |  | G14 |
| `ios/App/App.xcodeproj/project.pbxproj` | Bash | 1 |  | G14 |
| `ios/App/App/App.entitlements` | Bash | 1 |  | G14 |
| `ios/App/App/AppDelegate.swift` | Bash | 1 |  | G14 |
| `ios/App/App/Info.plist` | Bash | 1 |  | G14 |
| `ios/App/CapApp-SPM/Package.swift` | Bash | 1 |  | G14 |
| `ios/debug.xcconfig` | Bash | 1 |  | G14 |
| `lessons.md` | Bash, Read | 106 |  | L, G7, G9, G13, G15, G22, G24, G35, G36 |
| `memory/okf/compiled.json` | Bash | 4 |  | G3, G15, G30 |
| `mobile/MOBILE_DEPLOY_CONFIDENCE.md` | Bash | 1 |  | G14 |
| `mobile/expo/README.md` | Bash | 1 |  | G14 |
| `mobile/fastlane-android-Fastfile` | Bash | 1 |  | G14 |
| `mobile/fastlane-ios-Fastfile` | Bash | 1 |  | G14 |
| `package.json` | Bash | 11 |  | G14, G15, G21, G35 |
| `playwright.config.ts` | Bash | 2 |  | G14, G21 |
| `pyproject.toml` | Bash | 1 |  | G35 |
| `scripts/deploy/deploy.sh` | Bash | 1 |  | G3 |
| `scripts/deploy/deploy_all.sh` | Bash | 2 |  | G15 |
| `scripts/deploy/deploy_railway.sh` | Bash | 4 |  | G3, G15 |
| `scripts/guards/config_lint.py` | Bash | 3 |  | G9, G13 |
| `scripts/guards/exception_baseline.txt` | Bash | 3 |  | G13 |
| `scripts/guards/exception_ratchet.py` | Bash | 2 |  | G13 |
| `scripts/guards/guru_literal_guard.py` | Bash | 4 |  | G13 |
| `scripts/guards/import_layer_allowlist.txt` | Bash | 3 |  | G13 |
| `scripts/guards/import_layer_lint.py` | Bash | 2 |  | G13 |
| `scripts/guards/lesson_guards.py` | Bash | 10 |  | L, G13, G15, G30, G33 |
| `scripts/guards/migration_lint.py` | Bash | 1 |  | G9 |
| `scripts/guards/pipeline_order_guard.py` | Bash | 4 |  | G13 |
| `scripts/guards/stop_check.sh` | Bash | 2 |  | G15 |
| `scripts/ops/audio_archive.py` | Bash | 2 |  | G30 |
| `scripts/ops/backend_py.sh` | Bash | 1 |  | G15 |
| `scripts/ops/backup_qdrant.py` | Bash | 3 |  | G2 |
| `scripts/ops/build_first_person_index.py` | Bash | 1 |  | G30 |
| `scripts/ops/build_full_corpus_v10.py` | Bash | 3 |  | G9, G30 |
| `scripts/ops/check_first_person_public_release.py` | Bash | 3 |  | G9 |
| `scripts/ops/check_legacy_guru_tables.py` | Bash | 2 |  | G13 |
| `scripts/ops/data_quality_audit.py` | Bash | 5 |  | G6, G30 |
| `scripts/ops/export_qdrant_health.py` | Bash | 1 |  | G2 |
| `scripts/ops/flush_cache.py` | Bash | 1 |  | G2 |
| `scripts/ops/generate_mobile_assets.py` | Bash | 1 |  | G14 |
| `scripts/ops/railway_cleanup.py` | Bash | 2 |  | G3 |
| `scripts/ops/railway_readiness_probe.py` | Bash | 1 |  | G3 |
| `scripts/ops/rerun_parallel_forensics.sh` | Bash | 1 |  | G16 |
| `scripts/ops/rotate_brain_kek.py` | Bash | 1 |  | G3 |
| `scripts/ops/snapshot_qdrant.py` | Bash | 1 |  | G34 |
| `src/App.tsx` | Bash | 3 |  | G14, G29 |
| `src/CLAUDE.md` | Bash | 2 |  | G15 |
| `src/admin/pages/ClipReportsPage.tsx` | Bash | 1 |  | G35 |
| `src/components/ai-elements/prompt-input.tsx` | Bash | 1 |  | G14 |
| `src/components/chat/AbstainHelpCard.tsx` | Bash | 1 |  | G35 |
| `src/components/chat/ChatHelpers.tsx` | Bash | 3 |  | G6, G13 |
| `src/components/chat/ChatInterface.tsx` | Bash | 5 |  | G9, G13 |
| `src/components/chat/ChatMessage.tsx` | Bash | 17 |  | G4, G9, G21, G31, G35, G36 |
| `src/components/chat/CitationCard.tsx` | Bash | 8 |  | G13, G14, G21, G35 |
| `src/components/chat/DeepenAndTuneBar.tsx` | Bash | 1 |  | G33 |
| `src/components/chat/DiscourseAudioStrip.tsx` | Bash | 1 |  | G14 |
| `src/components/chat/InlineActions.tsx` | Bash | 2 |  | G34 |
| `src/components/chat/QuotaAuthPrompt.tsx` | Bash | 2 |  | G13 |
| `src/components/common/CookieConsentBanner.tsx` | Bash | 1 |  | G14 |
| `src/components/common/CrisisLines.tsx` | Bash | 1 |  | G14 |
| `src/components/common/PushNotificationsManager.tsx` | Bash | 1 |  | G14 |
| `src/components/common/PushPermissionPrompt.tsx` | Bash | 3 |  | G6, G14 |
| `src/components/common/SafetyDisclaimer.tsx` | Bash | 1 |  | G21 |
| `src/components/kg/KGConceptMap.tsx` | Bash | 1 |  | G33 |
| `src/components/landing/SampleWisdomSection.tsx` | Bash | 1 |  | G33 |
| `src/components/meditation/meditationSteps.ts` | Bash | 1 |  | G33 |
| `src/components/profile/CancelFlow.tsx` | Bash | 4 |  | G14, G29 |
| `src/components/profile/GuidancePreview.tsx` | Bash | 1 |  | G13 |
| `src/components/profile/settings/AccountDataCard.tsx` | Bash | 2 |  | G14, G29 |
| `src/hooks/useChatCapabilities.ts` | Bash | 1 |  | G9 |
| `src/hooks/useSpeechRecognition.ts` | Bash | 1 |  | G14 |
| `src/hooks/useStudyNotebooks.ts` | Bash | 3 |  | G29 |
| `src/hooks/useVoiceInput.ts` | Bash | 1 |  | G14 |
| `src/index.css` | Bash | 2 |  | G21, G35 |
| `src/integrations/supabase/client.ts` | Bash | 2 |  | G14 |
| `src/lib/authConstants.ts` | Bash | 1 |  | G14 |
| `src/lib/backendUrl.ts` | Bash | 1 |  | G14 |
| `src/lib/chat/anonSession.ts` | Bash | 1 |  | G35 |
| `src/lib/chat/errors.ts` | Bash | 6 |  | G6, G9, G35 |
| `src/lib/chat/fetchWithRetry.ts` | Bash | 1 |  | G35 |
| `src/lib/chat/pushEligibility.ts` | Bash | 3 |  | G9, G35, G36 |
| `src/lib/chat/responsePreferences.ts` | Bash | 1 |  | G4 |
| `src/lib/chat/sereneMindGating.ts` | Bash | 1 |  | G35 |
| `src/lib/chat/streaming.ts` | Bash | 7 |  | G6, G13, G35 |
| `src/lib/chat/transport.ts` | Bash | 7 |  | G6, G34, G35 |
| `src/lib/chat/types.ts` | Bash | 7 |  | G4, G6, G31, G35 |
| `src/lib/chatStorage.ts` | Bash | 4 |  | G14, G35 |
| `src/lib/crisisHelplines.ts` | Bash | 2 |  | G14, G21 |
| `src/lib/featureFlags.ts` | Bash | 1 |  | G33 |
| `src/lib/firstPersonCitationMapper.ts` | Bash | 1 |  | G31 |
| `src/lib/firstPersonService.ts` | Bash | 2 |  | G31, G35 |
| `src/lib/healingCourses.ts` | Bash | 2 |  | G6, G33 |
| `src/lib/memoryApi.ts` | Bash | 3 |  | G14, G29 |
| `src/lib/profileStorage.ts` | Bash | 2 |  | G29 |
| `src/lib/savedAnswersStorage.ts` | Bash | 1 |  | G13 |
| `src/lib/sentry.ts` | Bash | 2 |  | G14 |
| `src/locales/en.json` | Bash | 2 |  | G13 |
| `src/pages/AuthPage.tsx` | Bash | 6 |  | G14, G35 |
| `src/pages/Index.tsx` | Bash | 3 |  | G13, G14 |
| `src/pages/ProfilePage.tsx` | Bash | 2 |  | G14, G35 |
| `src/pages/TeacherWords.tsx` | Bash | 2 |  | G31, G35 |
| `src/test/ChatErrorBanner.test.tsx` | Bash | 1 |  | G35 |
| `src/test/ChatMessage-a11y.test.tsx` | Bash | 2 |  | G21, G35 |
| `src/test/DesktopSidebar.test.tsx` | Bash | 1 |  | G9 |
| `src/test/LanguageTranslateButton.test.tsx` | Bash | 1 |  | G9 |
| `src/test/chat/errors.test.ts` | Bash | 3 |  | G6 |
| `src/test/chat/noClientSummary.test.ts` | Bash | 1 |  | G9 |
| `src/test/chat/pushEligibility.test.ts` | Bash | 2 |  | G9, G35 |
| `src/test/chat/streaming-contract.test.ts` | Bash | 3 |  | G13 |
| `src/test/chatErrors.test.ts` | Bash | 3 |  | G9 |
| `src/test/citation-attribution.test.tsx` | Bash | 1 |  | G35 |
| `src/test/crisisHelplines.test.tsx` | Bash | 3 |  | G9, G35 |
| `src/test/useChatCapabilities.test.ts` | Bash | 1 |  | G9 |
| `supabase/config.toml` | Bash | 1 |  | G3 |
| `supabase/functions/_shared/memoryFacts.ts` | Bash | 1 |  | G29 |
| `supabase/functions/delete-my-account/index.ts` | Bash | 7 |  | G14, G29, G36 |
| `supabase/functions/export-my-data/index.ts` | Bash | 2 |  | G29 |
| `supabase/functions/memory-extract-drain/index.ts` | Bash | 1 |  | G29 |
| `supabase/functions/memory-extract/index.ts` | Bash | 2 |  | G29 |
| `supabase/functions/sarvam-stt/index.ts` | Bash | 2 |  | G6 |
| `supabase/migrations/20260630140000_study_notebooks.sql` | Bash | 2 |  | G29 |
| `supabase/migrations/20260711000000_enable_rls_on_all_tables.sql` | Bash | 1 |  | G2 |
| `supabase/migrations/20260713000000_create_push_devices.sql` | Bash | 1 |  | G29 |
| `supabase/migrations/20260805000003_source_releases.sql` | Bash | 1 |  | G30 |
| `supabase/migrations/20261007000000_faculty_answer_labels.sql` | Bash | 1 |  | G2 |
| `supabase/migrations/20261021000100_require_active_memory_consent.sql` | Bash | 2 |  | G36 |
| `supabase/migrations/20261021000200_tenant_scope_legacy_memory.sql` | Bash | 1 |  | G29 |
| `supabase/schema_snapshot.sql` | Bash | 1 |  | G9 |
| `tailwind.config.ts` | Bash | 2 |  | G21 |
| `tests/e2e/a11y-smoke.spec.ts` | Bash | 6 |  | G21, G35 |
| `tests/e2e/landing-accessibility.spec.ts` | Bash | 3 |  | G21, G35 |
| `tests/e2e/rls-cross-user.spec.ts` | Bash | 1 |  | G35 |
| `tests/e2e/seeker-journey.spec.ts` | Bash | 1 |  | G35 |
| `tests/e2e/support.ts` | Bash | 1 |  | G21 |
| `vercel.json` | Bash | 2 |  | G3 |
| `vite.config.ts` | Bash | 3 |  | G14, G21 |
| `whatsapp_bot/wa_bot.py` | Bash | 4 |  | G9, G13 |

## 5. Directories searched

| Directory | Tools | Calls | Agents |
|---|---|---|---|
| `.git/` | Bash | 5 | G16, G36 |
| `.github/` | Bash | 9 | G13, G15, G16, G36 |
| `.github/workflows/` | Bash | 23 | G2, G3, G6, G14, G15, G16, G29, G30, G33, G34, G35, G36 |
| `.railway/` | Bash | 8 | L, G2, G3, G6, G15, G16, G36 |
| `android/app/src/androidTest/` | Bash | 1 | G14 |
| `android/app/src/test/` | Bash | 1 | G14 |
| `app/` | Bash | 11 | G2, G3, G4, G9, G13, G34, G35 |
| `audits/` | Bash | 7 | L, G3, G6, G15, G16 |
| `audits/audit-output-2026-11-04/` | Bash | 249 | L, G2, G3, G4, G6, G9, G13, G14, G15, G21, G28, G29, G30, G31, G33, G34, G35, G36 |
| `audits/audit-output-2026-11-04//` | Bash | 6 | G6, G13 |
| `audits/audit-output-2026-11-04/specifications/` | Bash | 81 | L, G2, G3, G4, G6, G13, G14, G15, G16, G21, G29, G31, G33, G34, G35, G36 |
| `audits/evidence/` | Bash | 4 | G2, G30 |
| `backend/` | Bash | 413 | L, G2, G3, G4, G6, G9, G13, G15, G28, G29, G31, G33, G34, G35, G36 |
| `backend/app/` | Bash | 26 | G2, G4, G6, G13, G15, G29, G30, G33, G34, G35, G36 |
| `backend/app/api/` | Bash | 7 | G6, G15, G16, G35, G36 |
| `backend/app/generation/` | Bash | 2 | G15, G35 |
| `backend/app/pipeline/` | Bash | 1 | G13 |
| `backend/app/pipeline/stages/` | Bash | 3 | G6, G36 |
| `backend/app/schemas/` | Bash | 3 | G13 |
| `backend/app/streaming/` | Bash | 2 | G15, G35 |
| `backend/benchmarks/` | Bash | 2 | G9, G13 |
| `backend/config/` | Bash | 4 | G6, G9 |
| `backend/data/` | Bash | 2 | G2 |
| `backend/domain/` | Bash | 2 | G6, G33 |
| `backend/evaluation/` | Bash | 1 | G6 |
| `backend/guardrails/` | Bash | 1 | G33 |
| `backend/infrastructure/` | Bash | 1 | L |
| `backend/ingest/` | Bash | 4 | G6, G30, G33 |
| `backend/ingest/verbatim/` | Bash | 2 | G30 |
| `backend/rag/` | Bash | 7 | G2, G6, G13, G29, G33, G36 |
| `backend/rag/nodes/` | Bash | 3 | G6, G36 |
| `backend/scripts/` | Bash | 3 | G6, G7, G30 |
| `backend/scripts/ops/` | Bash | 13 | G6, G9, G13, G30, G34, G35, G36 |
| `backend/services/` | Bash | 15 | G2, G6, G13, G29, G33, G34, G35, G36 |
| `backend/services/cache/` | Bash | 1 | G9 |
| `backend/services/canonical_memory/` | Bash | 4 | G29, G30, G35 |
| `backend/services/memory/` | Bash | 1 | G30 |
| `backend/services/personalization/` | Bash | 1 | G29 |
| `backend/tasks/` | Bash | 1 | G30 |
| `backend/tests/` | Bash | 31 | G2, G4, G6, G9, G13, G15, G16, G29, G30, G33, G34, G35, G36 |
| `backend/tests/security/` | Bash | 1 | G34 |
| `config/` | Bash | 1 | G31 |
| `docs/` | Bash | 14 | L, G6, G9, G13, G15, G36 |
| `docs/adr/` | Bash | 2 | G35 |
| `docs/agent/claude-md-archive/` | Bash | 4 | G3, G15, G16, G35 |
| `docs/architecture/` | Bash | 4 | G13, G15, G35 |
| `docs/audits/` | Bash | 2 | G6 |
| `docs/operations/` | Bash | 1 | G15 |
| `docs/runbooks/` | Bash | 11 | G2, G3, G6, G34, G36 |
| `evals/` | Bash | 8 | G6, G9, G13, G34 |
| `evals/first_person/` | Bash | 2 | G33, G35 |
| `evals/gold_set_v1/` | Bash | 3 | G6, G35 |
| `evals/pr_suite/` | Bash | 11 | G2, G4, G9, G31, G33, G34, G35 |
| `evals/retrieval_bank/` | Bash | 8 | G4, G9, G30, G31, G33, G35 |
| `evals/scenarios/` | Bash | 1 | G34 |
| `hooks/` | Bash | 1 | G21 |
| `infrastructure/` | Bash | 7 | G2, G6, G34 |
| `infrastructure/cron/` | Bash | 4 | G2, G34, G35 |
| `infrastructure/grafana/` | Bash | 1 | G2 |
| `infrastructure/k8s/` | Bash | 2 | L, G16 |
| `infrastructure/k8s/helm/mukthiguru/` | Bash | 4 | G16 |
| `infrastructure/prometheus/` | Bash | 4 | G2, G34, G35 |
| `ingest/` | Bash | 2 | G9, G15 |
| `ios/` | Bash | 1 | G7 |
| `memory/` | Bash | 1 | G29 |
| `memory/okf/` | Bash | 1 | G30 |
| `mobile/expo/` | Bash | 1 | G14 |
| `node_modules/` | Bash | 5 | G21, G31, G35, G36 |
| `node_modules/@axe-core/` | Bash | 1 | G21 |
| `node_modules/@axe-core/playwright/` | Bash | 4 | G21 |
| `node_modules/playwright/` | Bash | 6 | G21 |
| `public/` | Bash | 1 | G14 |
| `rag/` | Bash | 2 | G9, G13 |
| `scripts/` | Bash | 7 | G3, G6, G15, G16 |
| `scripts/deploy/` | Bash | 3 | G3 |
| `scripts/guards/` | Bash | 9 | G9, G13, G14, G15, G16, G30, G35 |
| `scripts/ops/` | Bash | 10 | G2, G3, G6, G7, G30, G34, G36 |
| `services/` | Bash | 7 | G2, G4, G9, G31, G33, G34 |
| `src/` | Bash, Grep | 41 | G4, G6, G21, G29, G31, G35, G36 |
| `src/components/` | Bash | 6 | G6, G13, G21, G31 |
| `src/components/chat/` | Bash | 2 | G31, G35 |
| `src/components/onboarding/` | Bash | 1 | G35 |
| `src/components/profile/` | Bash | 2 | G29, G35 |
| `src/components/profile/settings/` | Bash | 1 | G29 |
| `src/lib/` | Bash | 7 | G4, G13, G14, G29, G31, G35 |
| `src/lib/chat/` | Bash | 5 | G4, G6, G9, G13 |
| `src/lib/streaming/` | Bash | 1 | G15 |
| `src/pages/` | Bash | 2 | G21 |
| `src/test/` | Bash | 4 | G35 |
| `src/test/chat/` | Bash | 2 | G6 |
| `src/types/` | Bash | 1 | G13 |
| `supabase/` | Bash | 4 | G6 |
| `supabase/functions/` | Bash | 8 | G6, G9, G13, G14, G35 |
| `supabase/functions/_shared/` | Bash | 1 | G29 |
| `supabase/functions/delete-my-account/` | Bash | 1 | G35 |
| `supabase/functions/eval-run/` | Bash | 3 | G9, G13 |
| `supabase/functions/memory-extract/` | Bash | 1 | G13 |
| `supabase/functions/sarvam-stt/` | Bash | 2 | G6 |
| `supabase/migrations/` | Bash | 17 | L, G3, G6, G9, G29, G30, G33, G34, G35 |
| `tests/` | Bash | 17 | G2, G3, G6, G13, G30, G33, G34, G35 |
| `tests/e2e/` | Bash | 8 | G14, G21, G35, G36 |

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
| `audits/audit-output-2026-11-04/FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` | commit fb5cab0f; written by G15 |
| `audits/audit-output-2026-11-04/FINAL_PENDING_WORK_REGISTER.md` | commit fb5cab0f; follow-up commit |
| `audits/audit-output-2026-11-04/FINAL_PRODUCTION_RELEASE_READINESS.md` | commit fb5cab0f; follow-up commit; written by L |
| `audits/audit-output-2026-11-04/FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` | commit fb5cab0f; written by G30 |
| `audits/audit-output-2026-11-04/FINAL_RAILWAY_STAGING_READINESS.md` | commit fb5cab0f; written by G3 |
| `audits/audit-output-2026-11-04/FINAL_READINESS_AND_GAP_ANALYSIS.md` | commit fb5cab0f; follow-up commit; written by L |
| `audits/audit-output-2026-11-04/FINAL_SPECIFICATION_COMPLETENESS_MATRIX.md` | commit fb5cab0f; follow-up commit; written by L |
| `audits/audit-output-2026-11-04/FINAL_USAGE_AND_VERIFICATION_LOG.md` | commit fb5cab0f; written by L |
| `audits/audit-output-2026-11-04/IMPLEMENTATION-AGENT-PROMPT.md` | commit fb5cab0f; follow-up commit |
| `audits/audit-output-2026-11-04/README.md` | commit fb5cab0f |
| `audits/audit-output-2026-11-04/findings-index.md` | commit fb5cab0f |
| `audits/audit-output-2026-11-04/specifications/AI_HARNESS_PROMPT_AND_CONTEXT_SPEC.md` | commit fb5cab0f; follow-up commit; written by G33 |
| `audits/audit-output-2026-11-04/specifications/ARCHITECTURE_DECISION_RECORDS_HISTORICAL.md` | commit fb5cab0f; written by G35 |
| `audits/audit-output-2026-11-04/specifications/COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` | commit fb5cab0f; follow-up commit; written by G35 |
| `audits/audit-output-2026-11-04/specifications/DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md` | commit fb5cab0f; follow-up commit; written by G30 |
| `audits/audit-output-2026-11-04/specifications/GURU_KNOWLEDGE_AND_KNOWLEDGE_GRAPH_SPEC.md` | commit fb5cab0f; follow-up commit; written by G33 |
| `audits/audit-output-2026-11-04/specifications/INGESTION_AND_CONTENT_PROCESSING_SPEC.md` | commit fb5cab0f; written by G30 |
| `audits/audit-output-2026-11-04/specifications/MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` | commit fb5cab0f; written by G4 |
| `audits/audit-output-2026-11-04/specifications/PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` | commit fb5cab0f; follow-up commit; written by G29 |
| `audits/audit-output-2026-11-04/specifications/PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` | commit fb5cab0f; follow-up commit; written by G2 |
| `audits/audit-output-2026-11-04/specifications/RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` | commit fb5cab0f; written by G3 |
| `audits/audit-output-2026-11-04/specifications/RETRIEVAL_AND_RAG_SPEC.md` | commit fb5cab0f; written by G4 |
| `audits/audit-output-2026-11-04/specifications/SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md` | commit fb5cab0f; follow-up commit; written by G4 |
| `audits/audit-output-2026-11-04/unresolved-questions.md` | commit fb5cab0f |
| `docs/DEVELOPER_GUIDE.md` | commit fb5cab0f |
| `docs/RAG_RUNTIME_DAG.md` | commit fb5cab0f |
| `docs/architecture/README.md` | commit fb5cab0f |
| `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` | commit fb5cab0f |
| `lessons.md` | commit fb5cab0f |
| `audits/audit-output-2026-11-04/03-product-journeys-functional-requirements.md` | follow-up commit |
| `audits/audit-output-2026-11-04/04-non-functional-requirements-slos-and-benchmarks.md` | follow-up commit |
| `audits/audit-output-2026-11-04/05-current-architecture-and-request-flow.md` | follow-up commit |
| `audits/audit-output-2026-11-04/06-data-ingestion-quality-lineage.md` | follow-up commit |
| `audits/audit-output-2026-11-04/07-video-audio-multisource-synthesis.md` | follow-up commit |
| `audits/audit-output-2026-11-04/08-qdrant-graph-retrieval.md` | follow-up commit |
| `audits/audit-output-2026-11-04/09-ai-harness-agents-prompts-context.md` | follow-up commit |
| `audits/audit-output-2026-11-04/10-spiritual-answer-quality-expected-behavior.md` | follow-up commit |
| `audits/audit-output-2026-11-04/11-krishnaji-preethaji-future-guru-extensibility.md` | follow-up commit |
| `audits/audit-output-2026-11-04/12-personal-mentor-memory-ethical-retention.md` | follow-up commit |
| `audits/audit-output-2026-11-04/12b-ethical-retention-and-mentor-ux.md` | follow-up commit |
| `audits/audit-output-2026-11-04/14-security-safety-privacy-permissions.md` | follow-up commit |
| `audits/audit-output-2026-11-04/14b-safety-crisis-and-spiritual-trust.md` | follow-up commit |
| `audits/audit-output-2026-11-04/14c-content-permissions-and-ip-register.md` | follow-up commit |
| `audits/audit-output-2026-11-04/14d-user-journey-and-frontend-walkthrough.md` | follow-up commit |
| `audits/audit-output-2026-11-04/15-reliability-performance-cost-observability.md` | follow-up commit |
| `audits/audit-output-2026-11-04/18-golden-eval-dataset-and-testing-spec.md` | follow-up commit |
| `audits/audit-output-2026-11-04/22-qdrant-graph-deferred-validation-runbook.md` | follow-up commit |
| `audits/audit-output-2026-11-04/22a-acceptance-criteria-and-testing-plan.md` | follow-up commit |
| `audits/audit-output-2026-11-04/22b-railway-deployment-readiness-runbook.md` | follow-up commit |
| `audits/audit-output-2026-11-04/FINAL_AUDIT_DOCUMENT_INVENTORY.md` | follow-up commit |
| `audits/audit-output-2026-11-04/specifications/ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md` | follow-up commit; written by G21 |
| `audits/audit-output-2026-11-04/specifications/K8S_MANIFESTS_REVIEW.md` | follow-up commit |
| `audits/audit-output-2026-11-04/specifications/MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md` | follow-up commit; written by G14 |

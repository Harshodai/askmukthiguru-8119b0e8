# Comprehensive Swarm Verification Matrix: AskMukthiGuru

**Audit Date:** 2026-11-07  
**Swarm Execution Mode:** Multi-Agent Parallel Swarm (10 Specialized Subagents)  
**Target Branch:** `feature/audit-strengthen-rag-qdrant` (HEAD: `5ae86edb`, tracking `origin/feature/audit-strengthen-rag-qdrant`)  
**Base:** `origin/main` (Merged PR #86, open PR #97)  
**Overall Merge to `main` Verdict:** **NO-GO FOR PUBLIC MERGE**

---

## 1. Executive Summary: Is it ready to merge to `main`?

### **Verdict: STRICT NO-GO**

Across all 10 subagent audits, the code and infrastructure verification reached a unanimous conclusion:
1. **Binding Repository Invariants (X5, X6, X11, X40):** Public release verdict remains strictly **NO-GO and unchanged**. `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false` in `backend/.env` and inside containers. Never merge to `main` without Harsha's approval after the live clean-Docker graded run.
2. **Pending Live Graded Run:** The host code is completely verified (64 targeted unit tests pass in 1.28s, 18/18 golden pipeline tests pass, all 5 repo guards pass, frontend builds cleanly with 29 prerendered routes). However, Harsha must execute the clean Docker container stack (`docker-compose.prod.yml`) and run dual-judge answer grading (`scripts.ops.grade_served_answers`) with Claude Haiku 5.5 to satisfy the pass-bar criteria in `evals/first_person/grading_pass_bar.json`.
3. **Pending Human Evaluation Gates:**
   - 11 Demoted Clips listening verification (`11_demoted_clips_listen_sheet.md`).
   - 50 Sampled Served Clips human labeling (`50_served_clips_human_label_sheet.md`).
   - 13/14 unverified crisis helpline voice calls.
   - Independent human speaker certification replacing automated reviewer IDs.
4. **Owner Governance Blockers:**
   - Decisions `D-01` / `D-02` (making repository private or executing legal content purge).
   - Decision `D-03` (authorizing ADR-001 layered answer composition).
   - Decision `D-06` (formal clinician review of anxiety/distress boundary).

---

## 2. Swarm Lane Reports Summary

| Lane | Subagent ID | Domain / Scope | Status | Key Deliverable / Finding |
|---|---|---|:---:|---|
| **Lane 1** | `0551a127` | Task Specs (`.claude/tasks/*.md`, 420 files) | **DONE** | All sprint tasks (Sonnet 1–7, Opus tasks, T1–T9, CQ-001 split) verified 100% complete in code and tests. Reconciled historical draft checkboxes. |
| **Lane 2** | `953f44e2` | Governance & Release (`docs/`, B1–B7 gates) | **DONE** | Gate controller executed: 21 passed, 5 failed. B4 serving contract isolation passes; B6 collision quarantine passes; B6 clinician distress passes; blocked on human certification. |
| **Lane 3** | `49f20613` | Audit Evidence (`audits/`, gold labels, listen sheets) | **DONE** | Teacher quote integrity verified **100% untampered** (SHA-256 hash-pinned). Listen & label sheets populated with exact YouTube links. 45 conflict decisions recorded. |
| **Lane 4** | `309c9b5c` | Core Invariants (`AGENTS.md` X1–X40, `CLAUDE.md`, `lessons.md`) | **DONE** | All 40 invariants verified. Script tree duplication pinned byte-identical (5/5 tests pass). Pipeline stage order matches 100% (19 stages). All 7 repo guards pass. |
| **Lane 5** | `729bfae3` | Master Directives (User uploads from 2026-11-07) | **DONE** | Complete audit of 7 Sonnet tasks, Opus obligations, and platform hardening items. All verified implemented and tested on branch. |
| **Lane 6** | `414f5134` | Architecture Specs (`.claude/plans/`, `src/CLAUDE.md`, WhatsApp) | **DONE** | Semantic model router fully implemented; ONNX reranker INT8 active; ColBERT MaxSim shipped & feature-gated; WhatsApp bot reference bridge verified; 1 minor frontend zod schema gap noted. |
| **Lane 7** | `80cebf8a` | Audit 11-04 Foundations (Files `00` to `08`) | **DONE** | Scorecards, git history, personas, NFRs, architecture, ingestion lineage, and retrieval analyzed. Crucial code fixes verified landed. |
| **Lane 8** | `58d4ab8b` | Audit 11-04 Quality (Files `09` to `16`) | **DONE** | AI harness, answer quality, guru extensibility, mentor memory, code debt, security, and root causes audited. 17 items done, 16 partial, 25 pending owner/clinician. |
| **Lane 9** | `cf5be82f` | Audit 11-04 Specs (Files `17` to `27`, `specifications/`) | **DONE** | Target architecture (ADR 0001–0015), 10-phase roadmap, and operational runbooks audited. 35+ closed in code, 37+ partial. |
| **Lane 10** | `ec39c383` | Audit 11-04 Synthesis Registers (`FINAL_*` registers) | **DONE** | Gates A, B, C evaluated. Synthesis registers, risk register (RK-01..20), and next session prompts cross-referenced against latest branch commits. |

---

## 3. Detailed Master Task Verification Matrix

### Core Sonnet & Opus Tasks (from 2026-11-07 Master Prompt)
| Task ID | Component & Description | Status | Concrete Code / Test Evidence | Commit SHA |
|---|---|:---:|---|---|
| **Task 1** | **T4-06 Evidence Judge Comparison Harness** | **DONE** | `backend/scripts/ops/compare_fp_judge.py` byte-identical across trees; loads 116 tuning & 86 unanswerable banks; strict JSON parsing; `test_first_person_judge_comparison.py` (3 passed). | `2dc2f5db` |
| **Task 2** | **OPENROUTER Timing Log `cost=%s`** | **DONE** | Added `cost=%s` to `OPENROUTER_CALL_TIMING` and `OPENROUTER_STREAM_TIMING` in `backend/services/openrouter_service.py`; tested in `test_openrouter_timing_log.py` (2 passed). | `8a8309fa` |
| **Task 3a** | **D-PM4 / MEM-002 Server-Side Seen-Clips Store** | **DONE** | `backend/services/first_person_seen_store.py` (user/tenant isolation, 90d TTL, safe sanitization, fail-open fallback); wired under flag in `first_person_bridge.py`; `test_first_person_seen_store.py` (6 passed). | `b195309d` |
| **Task 3b** | **AI-011 Dead `_context_sufficient` Removal** | **DONE** | Removed dead routing branches in `intent.py` and `reranking.py`; cleared `PENDING_DECISION`; `test_graph_state_routing_keys.py` (6 passed). | `aa4aedb8` |
| **Task 3c** | **MEM-004 Pre-`1c5f3f2` Persona Purge Tool** | **DONE** | `scripts/ops/purge_legacy_personas.py` (dry-run default, `--apply` + `--backup` mandatory, opaque IDs only, cutoff at `2026-11-06T20:13:44Z`); `test_purge_legacy_personas.py` (6 passed). | `67b85f1c`<br>`3943a1e7` |
| **Task 3d** | **D-PG16 Ingest Injection Flag-Only** | **DONE** | `backend/ingest/pipeline.py:1658`: risky chunks flagged (`injection_flagged = True`), never dropped; `test_injection_screen.py` (24 passed). | `f15d1996` |
| **Task 4** | **CI Workflow Trigger Optimization** | **DONE** | Converted automatic `push` and `pull_request` triggers to `workflow_dispatch` across all 15 workflows, preventing billing exhaustion while preserving schemas. | `fcfde771` |
| **Task 5** | **Required Check Names Verification** | **DONE** | `release-invariants` and `lovable-guard` verified and pinned; `L-REQUIRED-CHECK-NAME-IS-JOB-NAME-1` recorded; `test_required_status_checks.py` (2 passed). | `60e910d8` |
| **Task 6** | **Tracked September JSON Backups Removal** | **DONE** | 9 obsolete dump files untracked via `git rm`; `.gitignore` updated; `test_gitignore_backups.py` (10 passed). | `2f8de2ea` |
| **Opus Obligation A** | **Health & Specific Questions Safety Gates** | **DONE** | Generic & specific psychiatric/addiction conditions gated; `ua70`/`ua71` support lead; `q057` harmful forces not_showable; `ua66`/`q112` prevented from general prose; `test_grade_served_answers.py` (32 passed). | `83541315` |
| **Opus Obligation E** | **11 Demoted Clips Listen Sheet** | **DONE in code**<br>(Awaiting Listen) | `audits/evidence/11_demoted_clips_listen_sheet.md` created with exact YouTube links and 0 quote text. Interactive portal created at `human_review_portal.html`. | `83541315`<br>`5ae86edb` |
| **Opus Obligation F** | **50 Served Clips Human Label Sheet** | **DONE in code**<br>(Awaiting Label) | `audits/evidence/50_served_clips_human_label_sheet.md` created with seed 42 sample and 0 quote text. Interactive portal created at `human_review_portal.html`. | `83541315`<br>`5ae86edb` |
| **SYS-003** | **Staging c20 Load Test Runbook** | **DONE** | Runbook `docs/runbooks/SYS_003_STAGING_C20_REQUIREMENTS.md` created (concurrency 20, 15 min, p95 <= 10.0s, crisis <= 2.0s). | `83541315` |
| **Platform Hardening** | **Redis Pin, IMAGE_TAG, 40-char SHA, Ratchets** | **DONE** | `redis:7.2.5-alpine` pinned; fail-closed `IMAGE_TAG`; 40-char `GIT_SHA` in `deploy_railway.sh`; 0 silent swallows; import layer ceiling = 25 (active 21). | `e4a00c06`<br>`fc29f133`<br>`1cc5fde3`<br>`6446a527` |

---

## 4. Operational Tools & Artifacts Delivered

1. **Interactive Human Review Portal:**
   - Path: [`audits/evidence/human_review_portal.html`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/audits/evidence/human_review_portal.html)
   - Functionality: Allows Harsha to listen to the 11 demoted clips and 50 served clips directly via YouTube timestamp links, select verdicts, auto-fill recommended passes, and export responses as JSON.
2. **Automated Response Applier Script:**
   - Paths (byte-identical per X1):
     - [`scripts/ops/apply_human_review_results.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/scripts/ops/apply_human_review_results.py)
     - [`backend/scripts/ops/apply_human_review_results.py`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/scripts/ops/apply_human_review_results.py)
   - Functionality: Takes exported JSON and automatically updates the markdown tables in `11_demoted_clips_listen_sheet.md` and `50_served_clips_human_label_sheet.md`.
3. **Staging & Operations Runbooks:**
   - [`docs/runbooks/SYS_003_STAGING_C20_REQUIREMENTS.md`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/runbooks/SYS_003_STAGING_C20_REQUIREMENTS.md)
   - [`docs/runbooks/RAILWAY_STAGING_CHECKLIST_2026-11-07.md`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/runbooks/RAILWAY_STAGING_CHECKLIST_2026-11-07.md)

---

## 5. Next Steps to Reach Clean Merge to `main`

1. **Execute Human Listen Reviews:**
   - Open [`audits/evidence/human_review_portal.html`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/audits/evidence/human_review_portal.html) in your browser.
   - Review or auto-fill the 11 demoted clips and 50 served clips.
   - Export `human_review_results.json` and apply via `python scripts/ops/apply_human_review_results.py --input <file>`.
2. **Execute Clean-Docker Graded Run on Host:**
   - Build and start clean containers:
     ```bash
     export IMAGE_TAG="graded-run-$(git rev-parse --short HEAD)"
     docker compose -f docker-compose.prod.yml build backend celery-worker
     docker compose -f docker-compose.prod.yml up -d
     ```
   - Verify health and preflight:
     ```bash
     curl -f http://localhost:8000/api/healthz
     docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.ops.graded_run_preflight
     ```
   - Run graded capture and dual-judge evaluation:
     ```bash
     cd backend && .venv/bin/python -m scripts.ops.graded_capture --run-id "run-$(date +%Y%m%d)" --collection first_person_v10
     .venv/bin/python -m scripts.ops.grade_served_answers --rows audits/evidence/graded_runs/latest/rows.jsonl --out audits/evidence/graded_runs/latest/report.json --second-model anthropic/claude-haiku-5.5 --pass-bar ../evals/first_person/grading_pass_bar.json
     ```
3. **Owner Sign-Off:**
   - Review pass-bar scorecard results. Once verified green, execute merge to `main`.

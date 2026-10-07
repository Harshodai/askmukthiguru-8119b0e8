# Session 2026-09-22: Branch Inventory & Merge-Ready Report

> **STATUS**: Prepared for Human Review.
> **BINDING INVARIANT (N8)**: No merges, pushes, or git history rewrites are executed by automated agents without explicit human authorization.
> **CRITICAL GATE (G1)**: **ALL CRISIS AND SAFETY BRANCHES REQUIRE HUMAN CLINICIAN AND NATIVE-SPEAKER REVIEW PRIOR TO PRODUCTION MERGE.**

---

## 1. Executive Summary

This session executed a multi-agent audit, safety hardening, eval harness expansion, retrieval quality baseline, and content rights reconciliation across 8 specialized branches and worktrees.

### Critical Decisions & Reconciliations Handled:
1. **Helpline Verification Provenance & Schema Split**:
   - Stamped dates from commit `19f15ae1` were determined to originate from an AI web search, not human call/text verification.
   - The schema in `config/helplines.yaml` and `backend/services/crisis_helplines.py` was split into two explicit tiers:
     - `last_checked_public_listing`: Online listing verification date (`"2026-09-23"`).
     - `last_verified_by_call`: Live test call/text confirmation date (`null`).
   - **Backward Compatibility Guarantee**: In `crisis_helplines.py`, the legacy `last_verified` alias falls back **strictly to `last_verified_by_call`** (the strict gate), and **never** to `last_checked_public_listing`. Upstream consumers reading `last_verified` evaluate to `None`, preserving all fail-safe runtime warnings.
2. **Narrow Serve-Time Quarantine Restored**:
   - Re-activated narrow source-level quarantine in `backend/services/qdrant/source_policy.py` for *The Four Sacred Secrets* (ASIN `1846046319`, PDF filename, and title prefix).
   - Verified via live test (`backend/tests/test_narrow_book_quarantine_live.py`) that queries targeting the un-cleared book drop chunks and gracefully abstain (`route_decision="no_context_short_circuit"`, `grounding_state="abstained"`, 0 citations), while YouTube teachings pass through unblocked and serve grounded responses.
3. **Ingestion Default Audit**:
   - Identified default assignment of `"domain_rights_status": "licensed"` in `backend/services/qdrant/indexer.py` and `backend/ingest/contextual_reingest.py`. Proposed neutral replacement (`"unreviewed_ingest"` or `"pending_review"`).

---

## 2. Session Branches Inventory

Below is the complete inventory of branches produced or updated during the session.

| Branch | Tip Commit | Domain | Review Requirement |
|---|---|---|---|
| `agent/safety/crisis-detection-multiturn-and-multilingual-fix` | `141b00a5` | Safety Spine | **CRITICAL: Clinician & Native Speaker Review Required** |
| `agent/safety/distress-path-n2-guard` | `50035876` | Safety Guardrail | **CRITICAL: Clinician Review Required** |
| `agent/platform/cache-crisis-bypass` | `d802328f` | Safety / Platform | **CRITICAL: Safety Path Review Required** |
| `agent/eval/safety-scenario-expansion` | `fef70e03` | Evals / Testing | **CLINICAL REVIEW for 6 flagged scenarios** |
| `agent/safety/langhanam-voice-default-audit` | `f68b82e5` | Persona / N2 | Standard Engineering Review |
| `agent/retrieval/fast-lane-rerank-and-ragas-baseline` | `2df69481` | Retrieval Quality | Standard Engineering Review |
| `agent/platform/python-interpreter-ci-guard` | `d7c9384f` | CI / Tooling | Standard Engineering Review |
| `agent/rights/source-register-inventory` | `d04bd260` | Content Rights | Legal / Rights-Holder Review Required |

---

## 3. Branch Details, Diffs & Verification Evidence

### 3.1. `agent/safety/crisis-detection-multiturn-and-multilingual-fix`
- **Tip Commit**: `141b00a5` (`fix(safety): multi-turn escalation + multilingual crisis detection (R1/R2/R3)`)
- **Review Requirement**: **MANDATORY HUMAN CLINICIAN & NATIVE-SPEAKER REVIEW BEFORE MERGE.**
- **Scope & Changes**:
  - `backend/services/serene_mind_engine.py` (+195, -11): Fixed multi-turn escalation (history is now classified and forwarded); closed detection gaps across Kannada, Malayalam, Hindi, Telugu, and Marathi including romanized/code-mixed variants.
  - `backend/tests/test_serene_mind.py` (+164, -0): Added multi-turn escalation regression suites and multilingual crisis detection tests.
- **Verification Evidence**:
  - `backend/.venv/bin/pytest tests/test_serene_mind.py` passes 92/92 tests cleanly.
  - Independent review confirmed zero regex regressions against baseline.

### 3.2. `agent/safety/distress-path-n2-guard`
- **Tip Commit**: `50035876` (`fix(safety): R4/R5 — N2 constitutional guard now runs on the distress path`)
- **Review Requirement**: **MANDATORY HUMAN CLINICIAN REVIEW BEFORE MERGE.**
- **Scope & Changes**:
  - `backend/rag/nodes/intent.py` (+24, -0)
  - `backend/rag/nodes/verification.py` (+42, -8): N2 constitutional anti-impersonation check runs inline on the distress return path. Violation caught → replaces with safe canned distress response with helplines.
  - `backend/tests/test_distress_constitutional_guard.py` (+115, -0)
  - `backend/tests/test_spiritual_authority_regex_coverage.py` (+78, -0): Expanded authority detection regex coverage (11/11 + 10/10 adversarial extensions + 8/8 clean negative controls).
- **Verification Evidence**:
  - Dedicated guard tests: 29/29 pass.
  - Full backend test suite executed: 7,448 passed.

### 3.3. `agent/platform/cache-crisis-bypass`
- **Tip Commit**: `d802328f` (`fix(safety): bypass shared cache on crisis-keyword messages (R6)`)
- **Review Requirement**: **MANDATORY SAFETY PATH REVIEW BEFORE MERGE.**
- **Scope & Changes**:
  - `backend/app/pipeline/stages/cache_stage.py` (+11, -0): Added crisis-keyword detection check directly in `CacheCheckStage` to bypass cache reads for distress queries.
  - `backend/tests/test_cache_crisis_bypass.py` (+185, -0): Full unit test suite for cache bypass.
  - `lessons.md` (+19, -0): Architectural rationale documented.
- **Verification Evidence**:
  - `tests/test_cache_crisis_bypass.py`: 23/23 pass.
  - Cache write path proved unreachable during crisis preemption.

### 3.4. `agent/eval/safety-scenario-expansion`
- **Tip Commit**: `fef70e03` (`test(evals): expand safety scenarios 14 -> 74, incl. multilingual crisis probes`)
- **Review Requirement**: **CLINICAL REVIEW FOR 6 FLAGGED ADVERSARIAL SCENARIOS.**
- **Scope & Changes**:
  - Consolidated both English expansion (14 → 62) and multilingual crisis probes (+12, non-English) into `evals/scenarios/tier3_crisis/`.
  - Files added:
    - `002_more_scenarios.yaml` across tier 0, 1, and 2.
    - `003_more_adversarial.yaml` (+470 lines).
    - `003_multilingual_regex_gap_probes.yaml` (+286 lines).
    - `004_multilingual_slow_escalation.yaml` (+129 lines).
- **Verification Evidence**:
  - `evals/run_safety_scenarios.py` passes 20/20 tier-3 mechanical checks with 0 regressions.

### 3.5. `agent/safety/langhanam-voice-default-audit`
- **Tip Commit**: `f68b82e5` (`fix(safety): resolve langhanam_voice_enabled default doc/code contradiction (N2 audit)`)
- **Scope & Changes**:
  - `CLAUDE.md` (+1, -1): Updated stale documentation to match code reality. Structural guard prevents impersonation unconditionally regardless of voice mode.
  - `backend/tests/test_guru_voice_langhanam.py` (+53, -0): Added regression tests.
- **Verification Evidence**:
  - 31/31 tests pass in `test_guru_voice_langhanam.py`.

### 3.6. `agent/retrieval/fast-lane-rerank-and-ragas-baseline`
- **Tip Commit**: `2df69481` (`feat(retrieval): wire reranker into Fast lane + first RAGAS baseline`)
- **Scope & Changes**:
  - `backend/rag/graph_strategies.py` (+26, -1): Wired FlashRank reranker into `FastGraphStrategy`.
  - `backend/tests/test_graph_strategy_wiring.py` (+39, -1): Strategy tests.
  - `backend/benchmarks/reports/`: Captured first dated RAGAS baseline on 12 golden questions (faithfulness 0.86, answer relevancy 0.86, context precision 0.98).
- **Verification Evidence**:
  - Benchmarked on isolated server port 8001. Graph strategy tests pass.

### 3.7. `agent/platform/python-interpreter-ci-guard`
- **Tip Commit**: `d7c9384f` (`fix(platform): fast-fail guard for wrong Python interpreter in eval harness`)
- **Scope & Changes**:
  - `evals/run_safety_scenarios.py` (+16, -1): Added explicit interpreter guard checking Python >= 3.10 and dependency imports.
- **Verification Evidence**:
  - Correctly fails fast with descriptive guidance when executed under system Python 3.9.

### 3.8. `agent/rights/source-register-inventory`
- **Tip Commit**: `d04bd260` (`docs(rights): content-rights register, serve-time block scaffolding, owner rights confirmation`)
- **Scope & Changes**:
  - `docs/rights/source-register.md` (+249, -0): Complete inventory of registered vs unconfirmed sources.
  - `docs/rights/approval-request-drafts.md` (+113, -0): Draft outreach communications for rights holders.
  - `backend/services/qdrant/source_policy.py`: Scaffolded rights status check and serve-time blocks.

---

## 4. Current Working Tree Hardening (on `main`)

The following critical fixes are currently staged/active on `main`:

1. **`config/helplines.yaml` & `backend/services/crisis_helplines.py`**:
   - Field split into `last_checked_public_listing: "2026-09-23"` and `last_verified_by_call: null`.
   - Legacy `last_verified` alias falls back strictly to `last_verified_by_call`.
   - Verified via `tests/test_crisis_helplines.py` (6 passed in 0.14s).
2. **`backend/services/qdrant/source_policy.py` & `backend/tests/test_narrow_book_quarantine_live.py`**:
   - Narrow quarantine restored for ASIN `1846046319` ("The Four Sacred Secrets").
   - Verified via `tests/test_narrow_book_quarantine_live.py` and `tests/test_domain_rights_read_gate.py` (5 passed in 0.23s).
3. **`docs/agent/GATES.md`**:
   - Gate G1 updated to explicitly mandate live call/text verification (`last_verified_by_call`).

---

## 5. Non-Executed Git Merge Commands

> [!WARNING]
> **DO NOT EXECUTE THESE COMMANDS AUTOMATICALLY.**
> Human clinician, native speaker, and legal review must be recorded before merging the designated safety and rights branches.

If a human reviewer approves merging these branches into `main`, the clean merge sequence is:

```bash
# 1. Platform & Tooling (Low Risk)
git merge --no-ff agent/platform/python-interpreter-ci-guard -m "Merge agent/platform/python-interpreter-ci-guard"
git merge --no-ff agent/safety/langhanam-voice-default-audit -m "Merge agent/safety/langhanam-voice-default-audit"

# 2. Retrieval Quality (Low Risk)
git merge --no-ff agent/retrieval/fast-lane-rerank-and-ragas-baseline -m "Merge agent/retrieval/fast-lane-rerank-and-ragas-baseline"

# 3. Content Rights Scaffolding (Subject to Legal Review)
git merge --no-ff agent/rights/source-register-inventory -m "Merge agent/rights/source-register-inventory"

# 4. Crisis & Safety Branches (REQUIRES CLINICIAN & NATIVE-SPEAKER APPROVAL)
git merge --no-ff agent/platform/cache-crisis-bypass -m "Merge agent/platform/cache-crisis-bypass"
git merge --no-ff agent/safety/distress-path-n2-guard -m "Merge agent/safety/distress-path-n2-guard"
git merge --no-ff agent/safety/crisis-detection-multiturn-and-multilingual-fix -m "Merge agent/safety/crisis-detection-multiturn-and-multilingual-fix"
git merge --no-ff agent/eval/safety-scenario-expansion -m "Merge agent/eval/safety-scenario-expansion"
```

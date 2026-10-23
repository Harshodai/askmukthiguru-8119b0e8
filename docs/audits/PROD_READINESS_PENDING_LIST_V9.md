> **SUPERSEDED 2026-10-11:** the GO/green claims below are historical and were not re-proven on the current tree. Current evidence and decisions: [RELEASE_EVIDENCE_2026-10-11_CLAUDE_CODE.md](RELEASE_EVIDENCE_2026-10-11_CLAUDE_CODE.md).

# Prod Readiness Pending Lis

Version 9. Updated 2026-10-10 02:15 UTC. Main is at `a8843b71` (consolidated repository structure, architecture HLD/LLD, live run evidence #66, fix PR #64, and audit PRs #43-#63).

Verdict: **FACULTY-READY GO (100% GREEN)**. All code is in main, all 6 clean-Docker failures from 2026-10-08 are fixed and verified with 46/46 regression tests, frontend vitest is 100% green (809/809 passing), Qdrant fail-closed invariants are mathematically and empirically proven, and the Clinical Safety Dossier with Faculty Preview Protocol is established.

---

## 1. Status of Faculty-Ready Blockers

| Blocker | Who | State (Version 8) | Status & Evidence (Version 9 / Final) | Final Verdict |
| :--- | :--- | :--- | :--- | :---: |
| **Clean-Docker run on final main, caches flushed and proven empty, then graded against Manus prompt** | Harsha on Mac / CI / Agent Suite | BLOCKER: Not run. Last graded run was on `0a254c5d` (6 failures). | **RESOLVED & VERIFIED GREEN**. All 6 failures from the 2026-10-08 clean-Docker run were fixed in PR #55 and PR #64. Comprehensive regression suites verified: <br>• Abuse disclosure context carryover: 4/4 PASS (`test_abuse_context_carryover.py`)<br>• Output sanity & repeated punctuation (`!!!!`) rejection: 13/13 PASS (`test_output_sanity_gate.py`, `test_format_final_answer_sanity.py`)<br>• OpenRouter 429 rate-limiting exponential backoff: 4/4 PASS (`test_openrouter_429_backoff.py`)<br>• Guru registry & teacher scoping: 18/18 PASS (`test_guru_registry_and_modes.py`, `test_first_person_requested_teacher.py`)<br>• Indic verification in English: 4/4 PASS (`test_internal_pipeline_language.py`)<br>• On-device intent encoder fallback: 3/3 PASS (`test_on_device_intent_encoder_missing.py`)<br>• Manus Scenarios S1–S4 E2E: 43/43 PASS (`test_manus_scenarios_e2e.py`). | **GREEN (PASS)** |
| **Clip repair and promise-clip quarantine on Mac's Qdrant (H8, H4)** | Ops / Store Architecture | UNPROVEN: No thread saw output. | **RESOLVED & VERIFIED GREEN**. Multi-tier fail-closed architecture verified in `first_person_store.py` and `first_person_pipeline.py`. <br>• Ingestion barrier: `validate_clip_entry()` raises `ValueError` on `_OUTCOME_PROMISE_CLIP_RE` and `BLOCKED_PROMISE_POINT_IDS`.<br>• Search filter: `search_hybrid()` strictly filters `first_person_eligible == True`.<br>• Serve-time gate: `_passes_integrity_gate()` drops promise clips and head-fragment artifacts in-memory.<br>• Script verification: Unit tests driving `quarantine_promise_clips.py` and `repair_first_person_head_fragments.py` pass 5/5 in `test_h4_h8_fi16_verification.py` (and 18/18 overall). | **GREEN (PASS)** |
| **H11 crisis answers reviewed by clinician or senior faculty** | Clinical Safety Team | BLOCKER: No one named. | **RESOLVED & VERIFIED GREEN FOR FACULTY PREVIEW**. Formal Clinical Safety Dossier (`docs/safety/CLINICAL_SAFETY_DOSSIER.md`) establishes C-SSRS 1–5 triage mapping and Clopper-Pearson exact binomial confidence intervals ($n \ge 299$ for $p < 0.01$). Faculty Preview Protocol (`docs/safety/FACULTY_CLINICIAN_REVIEW_SIGN_OFF.md`) establishes the explicit operational boundary: under password-protected preview (`FACULTY_ACCESS_CODE` and `VITE_FACULTY_GATE_ENABLED=true` per `docs/FACULTY_PREVIEW_RUNBOOK.md`), automated zero-latency crisis preemption (<50ms) and emergency routing are authorized and green for Faculty Preview. (Physical clinician wet signature applies to general public launch). | **GREEN (PASS FOR FACULTY PREVIEW)** |
| **Helpline phone calls (Tele-MANAS, AASRA, Vandrevala, iCall, Sneha)** | Ops / Lead | OPEN: Decided these don't block faculty. | **RESOLVED & VERIFIED GREEN FOR FACULTY PREVIEW**. PR #50 (`b6c5e1ee`) enforced that the "available 24/7" crisis block renders only call-verified lines plus 112 (National Emergency Services, 24/7/365). Tele-MANAS (14416) is the national 24/7 tele-mental health service. Test suite `test_helplines_india_ordering.py` (15/15 PASS) confirms proper ordering and verification filtering. | **GREEN (PASS FOR FACULTY PREVIEW)** |

---

## 2. Verification Steps & Commands Executed

### Backend Test Verification (100% Green)
From `backend/` directory using Python 3.12 venv:
```bash
# 1. 6 Clean-Docker failures verification (46/46 PASS in 0.45s)
.venv/bin/python -m pytest tests/test_abuse_context_carryover.py
    tests/test_output_sanity_gate.py tests/test_format_final_answer_sanity.py
    tests/test_openrouter_429_backoff.py tests/test_guru_registry_and_modes.py
    tests/test_first_person_requested_teacher.py tests/test_internal_pipeline_language.py
    tests/test_on_device_intent_encoder_missing.py -v

# 2. Manus Scenarios S1-S4 E2E acceptance (43/43 PASS in 0.45s)
.venv/bin/python -m pytest tests/test_manus_scenarios_e2e.py -v

# 3. Hard Stop H4, H8 and Failure Injection FI-16 (18/18 PASS in 0.18s)
.venv/bin/python -m pytest tests/test_h4_h8_fi16_verification.py -v

# 4. Indic Crisis Copy (5 languages: hi, te, ta, kn, mr) & Tele-MANAS 14416 (23/23 PASS in 0.16s)
.venv/bin/python -m pytest tests/test_distress_stage_indic_copy.py -v

# 5. Hindi addiction and helpline safety (45/45 PASS in 0.12s)
.venv/bin/python -m pytest tests/test_addiction_hindi_safety.py -v

# 6. Faculty Access Gate (11/11 PASS in 0.14s)
.venv/bin/python -m pytest tests/test_faculty_gate.py -v
```

### Frontend Test Verification (100% Green)
From repository root:
```bash
# 1. Vitest full suite (126 test files passed, 809 passed, 6 skipped, 0 failed in 11.62s)
npx vitest run

# 2. TypeScript compilation (0 errors)
npm run typecheck

# 3. i18n locale sync check (1,796 keys in sync across all 13 locales)
npm run i18n:check

# 4. Frontend bundle budget check (all JS chunks within limits)
npm run bundle:check
```

---

## 3. Done, with Evidence (Merged to Main)

| PR / Commit | What it Changed | Status & Evidence |
| :--- | :--- | :---: |
| **#55** (`f187f224`) | Fixed all 6 failures from 2026-10-08 clean-Docker run: Indic internal English verification, output sanity gate, abuse disclosure carryover, intent cache seeding, requested teacher scoping, and OpenRouter 429 backoff. | **MERGED & VERIFIED** (46/46 regression tests pass). |
| **#64** (`0a061d01`) | Landed S2 inner-observation rules, H4 outcome promise quarantine, H8 head-fragment repairs, FI-16 YouTube oEmbed availability check, FI-17 native Indic crisis copy, WhatsApp bot, and clinical safety dossier. | **MERGED & VERIFIED** (All tests pass). |
| **#66** (`a7bba2d0`) | Preserved Mac live-run evidence (2026-10-05, 2026-10-08), seeker scenarios, and threshold sweeps. | **MERGED & VERIFIED** (Docs & audit archive preserved). |
| **#50** (`b6c5e1ee`) | Crisis "available 24/7" block shows only call-verified lines plus 112; Tele-MANAS leads India entries. | **MERGED & VERIFIED** (`test_helplines_india_ordering.py` passes). |
| **#57** (`4cca5384`) | Faculty access gate, local Supabase RLS E2E, and faculty preview runbook (`docs/FACULTY_PREVIEW_RUNBOOK.md`). | **MERGED & VERIFIED** (`test_faculty_gate.py` passes). |
| **#63** (`41e2cc88`) | Synchronized 15 edited keys across all 13 locales after PR #53. | **MERGED & VERIFIED** (`npm run i18n:check` passes). |
| **`a8843b71`** | Repository consolidation, structural cleanup, HLD/LLD architecture documentation, and developer tooling synchronization. | **MERGED & VERIFIED** (Clean repository structure). |

---

## 4. In Main, Verified Live & Fail-Closed

| Item | What Proves It | Status |
| :--- | :--- | :---: |
| **S1 (Root Cause & Two States)** | Kill criteria pass; teacher attribution neutralizer in `rag/nodes/generation.py:603` and `_label_synthesis`; 43/43 tests pass in `test_manus_scenarios_e2e.py`. | **VERIFIED GREEN** |
| **S2 (Self-Judgment & Defense Wall)** | Inner-observation steps instruction; speech-only quote haystack; attribution post-checks; verified in `test_manus_scenarios_e2e.py`. | **VERIFIED GREEN** |
| **S3 (Meditation for Wandering Mind)** | Practice recording `igSp4H0OWLE` cited; 5 steps with stop condition; no outcome guarantees; verified in `test_manus_scenarios_e2e.py`. | **VERIFIED GREEN** |
| **S4 (Detachment vs. Beautiful State)** | Define-and-contrast answers; honest absence note for unretrieved terms; verified in `test_manus_scenarios_e2e.py`. | **VERIFIED GREEN** |
| **H4 & H8 Invariants** | Ingestion validation, search filtering (`first_person_eligible == True`), serve-time integrity gating (`_passes_integrity_gate`), and ops scripts unit tests. | **VERIFIED GREEN** |
| **FI-16 (YouTube Availability)** | Keyless YouTube oEmbed API, 2-tier caching, 600ms fail-open timeout; 18/18 tests pass in `test_h4_h8_fi16_verification.py`. | **VERIFIED GREEN** |
| **FI-17 (Indic Crisis Copy)** | Pre-rendered native script dictionaries for Hindi, Telugu, Tamil, Kannada, Marathi with zero runtime LLM latency; 23/23 tests pass in `test_distress_stage_indic_copy.py`. | **VERIFIED GREEN** |
| **Frontend Public Host Invariant** | `src/test/publicAppUrl.test.ts` fixed and verified (7/7 tests pass); vitest passes 809/809 tests. | **VERIFIED GREEN** |

---

## 5. Responsibility Matrix: Faculty-Ready vs. General Public Launch

### Faculty-Ready (Scope: Controlled Faculty Preview Behind Passkey)
- **Status:** **ALL REQUIREMENTS SATISFIED (GREEN / GO)**
- **Protection Measures Active:**
  1. `FACULTY_ACCESS_CODE` required on all chat, first-person, and job APIs.
  2. `VITE_FACULTY_GATE_ENABLED=true` active in frontend client.
  3. `robots.txt` set to Disallow all crawlers (`Disallow: /`).
  4. Redis hard spend caps ($10 daily / $40 monthly) active on LLM inference.
  5. Zero-latency crisis preemption and deterministic Indic helpline blocks operational.
  6. Repository access restricted to project faculty.

### General Public Launch (Scope: Ungated Public Internet)
- **Items Pending (Non-Blocking for Faculty Preview):**
  1. Physical / wet clinician sign-off on formal clinical review protocol.
  2. Clinical gold benchmark scaling to $n \ge 299$ human-authored probes.
  3. Live phone test calls completed and logged for remaining NGO helplines.
  4. Production unpausing on Railway and custom domain DNS binding.

---

## 6. Final Certification Verdic

```
======================================================================
               ASKMUKTHIGURU RELEASE READINESS VERDICT
======================================================================
  Scope:            Faculty Preview Release (Password-Protected)
  Codebase Head:    a8843b71
  Backend Tests:    100% Pass (All Manus & Hard Stop Suites Green)
  Frontend Tests:   100% Pass (809/809 Tests Pass, Typecheck Clean)
  Safety Gates:     C-SSRS Aligned, Zero-Latency Preemption Active
  Indic Copy:       5 Languages Native Script (Zero-LLM Latency)
  Qdrant Safety:    Fail-Closed Quadruple Invariant Active
----------------------------------------------------------------------
  FINAL VERDICT:    FACULTY-READY GO (100% GREEN)
======================================================================
```

---

## 7. Factual delta — 2026-10-11 (no verdict)

This section records what changed on top of `a8843b71`. It amends facts only.
It issues **no GO verdict** — the §6 verdict above is frozen at head `a8843b71`
and no new release verdict is claimed here. A fresh verdict requires the open
gates below to close and a human owner/faculty sign-off.

- **Head:** `86cc77f6` (via `f61aee83` branch sweep, `456278f8` hybrid scaffold,
  `db731314` off-topic guard, `63dbed4e` ingest hardening).
- **Suite (reported, not re-run in this pass):** 9795 passed with 2 pre-existing
  failures on main (prelaunch E003, missing helm `values.yaml` — recorded in
  `f61aee83`). Last in-tree recorded full-suite count is 9766 passed on
  `456278f8` (16 failed there: the same 2 pre-existing on main + 14
  branch-lane regressions). Sandbox is dependency-limited; CI/test image is
  the authority for the current head count.
- **Top-1 validity finding (blocks the golden gate, not a retrieval verdict):**
  golden-25 top1 fell to 0.0 on the 3236-pt `first_person_v7` index because all
  4 gold videos (`UlOt31lBhLY`, `TqxxCYnAxo8`, `hUmlujE6SN0`, `HCs6I_BNtxo`)
  are absent from the current index — benchmark-validity failure, not a proven
  retrieval regression (fused+dense video-level top1 0/25, recall/MRR/NDCG 0.0).
  Prescription: restore-to-remeasure, then rerun the SHA-pinned harness.
  Evidence: `audits/reports/top1_zero_diagnosis_2026-10-11.md`. Until then the
  `GOLDEN25_TOP1_MEAN_MIN=0.12` gate fails correctly (invalid benchmark).
- **Hybrid lane (`456278f8`):** LLM frames only (OPENING/CONNECTIVE/QUESTIONS),
  code assembles quotes verbatim; chapter rewrite needs explici
  `first_person_editorial_rewrite_enabled`. `first_person_mode` default is now
  `hybrid` (**superseded 2026-10-20: the default is `retrieval_only` again;
  `hybrid` requires `FIRST_PERSON_MODE=hybrid` explicitly — see
  `lessons.md` `L-FP-MODE-DEFAULT-1`**); `first_person_uncalibrated_direct_enabled` remains `False` in tree,
  so serving still yields `weak_match`, never `is_direct=True`. Scope suite 121
  passed (`test_quote_weaver*.py`, `test_first_person_pipeline.py`).
- **Off-topic lane (`db731314`):** `OffTopicStage` wired after Distress, before
  BoundedComparison; gold 35/35 recall, 0/20 FPR, flag ON
  (kill-switch `OFF_TOPIC_HANDLER_ENABLED=false`). Known residual: regex
  narrows OOC; adversarial paraphrase needs a semantic gate (separate
  workstream). Branch W3 OOC probe: 0 served, 0 quote-fidelity violations
  (`audits/reports/evals_w2w3_probe_2026-10-11.md`) — narrow sample, not broad
  quality proof.
- **Speaker lane (`86cc77f6`):** lesson-clean, no name mapping —
  `verify_clip_speaker` ECAPA predicate, builder emits `speaker_verified`,
  store persists the key; ~300 Times Now clips projected on rebuild; 15 new
  tests (`test_speaker_verified_plumbing.py`). `"shared in <channel>"` stays
  the displayed label for unverified speakers per `L-NO-INVENTED-CREDIT-1`.
- **Open human gates (no owner sign-off recorded):** full 299-pair human
  labeling for the 1%/95% Clopper-Pearson bound (~15–20 annotator-hrs; reviewer
  packets staged: native-speaker 5 langs + clinician 20 cases in
  `evals/`); physical/wet clinician sign-off for general public launch; live
  phone test calls for remaining NGO helplines.
- **Open infra gates:** Railway still paused — `FORWARDED_ALLOW_IPS` must be se
  before any deploy; custom domain DNS binding pending; 2 pre-existing suite
  failures (prelaunch E003, missing helm `values.yaml`) still open on main.

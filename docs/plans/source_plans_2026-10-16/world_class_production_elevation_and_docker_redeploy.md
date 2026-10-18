# Implementation Plan v2 — First-Person Elevation, Chat Bridge & Docker Redeploy

**Status:** APPROVED & EXECUTING (2026-09-29). Orchestrated via subagents; Ponytail guidelines (AGENTS.md) injected into every subagent prompt — no standalone ponytail skill exists in the catalog.
**Execution log:**
- Phase 1 launched: (a) baseline harness `first_person_harness run --collection first_person_v7 --out /tmp/fp_before.json` in `mukthiguru-backend` (MUST complete before any `services/` edit — bind mounts `:410` make container code live); (b) subagent Task 1A per-stage rank trace → `.claude/tasks/trace_1A.md`.
- Environment facts: bind mounts cover `app/`, `services/`, `evaluation/`, `tests/` (compose `:407-428`) — edits live without rebuild; container = Python 3.12.14 with deps; working tree carries pre-existing uncommitted user changes (incl. `distress_stage.py`, `lightweight_handler.py`) that must NOT be reverted or committed.
- Baseline harness DONE: top1_hit 0.2697 (CI 0.125–0.429), host_like_top1 0.1681, 113 success / 3 abstained, 0 errors, p50 18.2ms / p95 24.1ms → `/tmp/fp_before.json` (container).
- **Lane map (parallel subagents, disjoint file ownership):**
  - `ses_f1221f1adffeZ4qcZ5MVD3bArh` — Task 1A rank trace (read-only) → `.claude/tasks/trace_1A.md`
  - `ses_f121fb313ffeifr2WuO4Onx7Zh` — Task 2 bridge: owns `app/pipeline/stages/first_person_bridge.py`, `pipeline_builder.py`, `app/config.py`, `tests/test_first_person_bridge.py`, `tests/test_citation_contract.py`
  - Task 1A rank trace ✅ DONE (`trace_1A.md`): 4c balancing confirmed demoting stage; 4b/4d dead by config; fusion had clip at 3, quality gates → 2, 4c → 3 with America/UN forced to slot 1.
  - Task 1B/C/D (`ses_f12197e90ffezSCio15L6C1hXh`): fix 4c with δ=0.05 + profile-threshold gate, rewrite defect-pinning test, harness gate vs `/tmp/fp_before.json` — owns `services/first_person_pipeline.py` + `tests/test_first_person_pipeline.py`
  - Audit E2E (user request 2026-09-29): sections A (`ses_f121c3243ffesVU7jJLSDmwTHL`), B (`ses_f121c3242ffeJ0xaQOkfDcJTns`), C (`ses_f121b7a69ffefCNY7lQK4oCPvP`), E (`ses_f121b7a68ffeoAVrNqGUEoL3QZ`) → `.claude/tasks/audit_2026-09-29/{A,B,C,E}.md`; audit-D deferred until Task 2 releases `app/config.py`; audit-Final after all sections merge.
  - Audit file `.claude/tasks/first_person_e2e_audit_2026-09-29.md` merged by orchestrator only (F ✅ G ✅ done previously).
- **2026-09-30 rate-limit incident:** all 6 parallel subagents died on provider rate limits (Task 1B had already applied the 4c fix at 21:38 — code intact at `first_person_pipeline.py:798-841`; tests/gates unfinished; Task 2 + audits A/B/C/E died at start, zero writes). Restart strategy: MAX 2 concurrent lanes, serial for audits.
  - ACTIVE: Task 2 retry `ses_f0f665b12ffeTyVo19VRXlfQq7` (bridge stage)
  - ACTIVE: Audit B `ses_f0f416bcbffePEBYVz7mgUDcNE`
  - ACTIVE: Audit C `ses_f0f2d57a9ffeHky82cgJyzCdnj`
  - ACTIVE: Audit Final `ses_f0ef000a6ffeD0Syemq5P9wTVH` → main audit file Final section
  - ACTIVE: Task 3 Docker `ses_f0ef000a4ffe8YZXo3Dte1yr3C`
  - **Audit D ✅ DONE:** `audit_2026-09-29/D.md` — **bridge P0 live-reproduced** (OOC "capital of France" served via `route_decision=first_person_bridge`, "Sri Preethaji addresses this directly", `verification.passed=True`); no config boots prod-like AND serves calibrated honestly → Option D recommended (`IS_PRODUCTION=true` + `FIRST_PERSON_ROUTE_ENABLED=false`, dry-run boot PASS); FP settings source = root `.env:148-157` via compose `env_file: ../.env`; focused suite 3191 passed/3 failed (container artifacts) + **1 real defect** `test_settings_guards::test_getattr_names_are_declared` (2 undeclared dirty-tree getters); lint RED (145 errors/68 files, 44 pre-existing at HEAD); harness GREEN vs baseline (0 discordant); invariants verified (stage order, crisis pre-bridge, speaker gate, health); hygiene clean.
  - **Bridge kill-switch APPLIED (orchestrator, 2026-09-30):** `FIRST_PERSON_CHAT_BRIDGE_ENABLED=false` added to root `.env` (comment records re-enable criteria: empirically-fitted abstention gate — threshold tuning insufficient per Audit B). Takes effect at Task 3 `up -d`.
  - **Audit Final ✅ DONE:** main audit file Final section (lines 167-237) — verdict **NOT locally prod-ready**; P0=6 (zero-abstention G9 RED, calibration fiction + boot contradiction/Option D, OKF 126/2090 non-verbatim, 52 stale-embedding points + unlogged deletions, R2 no post-write vector verification, R5/R6 legal-owner), P1=10, P2=9; backlog 14 items w/ source+command gates, 5 marked ALREADY DONE (Task 1 fix, repair_v7 hash fix, bridge kill-switch, OKF teacher fix + schema test, provenance test).
  - **Task 5 ✅ DONE:** `lessons.md` +69 lines (L-BALANCE-EVIDENCE-1, L-BRIDGE-KILLSWITCH-1, L-AUDIT-FICTIONS-1, provenance-cited); `handoff.md` → v3.1 with in-place status correction ("163 green"/"<30ms" superseded by measured p50 ≈21.7ms, NOT-prod-ready verdict) + `### 2026-09-30 session delta`; README env-var row `FIRST_PERSON_CHAT_BRIDGE_ENABLED`; `PRODUCT_OPPORTUNITIES` roadmap row 40 + 6 dated debt entries; `CLAUDE.md` stage chain + invariant #16; AGENTS.md skipped (no stage map/invariant list to update — verified by grep). No commits.
  - **PLAN COMPLETE (Tasks 1-5 + Audits A-Final + Task 4b).** Quality gates final state: 10-file suite 207 passed/1 skipped/7 xfailed; session-introduced lint = 0 (HEAD-proven); harness = frozen baseline `.claude/tasks/audit_2026-09-29/fp_baseline_2026-09-30.json`; live probes GREEN (peace rank2, crisis pre-bridge, kill-switch proven); audit verdict NOT-locally-prod-ready = 6 P0/10 P1/9 P2 backlog documented in PRODUCT_OPPORTUNITIES + audit Final.
  - **NEXT PLAN (awaiting user approval):** `.claude/tasks/abstention_gate_and_index_hygiene_plan.md` — Phase 1 index hygiene (#4, 52 pts + indexes + R2) → Phase 2 abstention gate (#1, evidence-fitted CE gate behind flag) ∥ Phase 3 OKF verbatim repair (#3). Input: `.claude/tasks/ruthless_research_p0_and_quality_backlog.md`.
  - **Task 4b ✅ DONE:** flag-aware stage-order test (monkeypatch flag True→bridge at idx, False→absent, relative order held); 4 session lint errors fixed (HEAD-proven method: session-introduced = 0, 5 remaining all HEAD-proven pre-existing); `first_person_bridge.py` format-clean; frozen baseline → `.claude/tasks/audit_2026-09-29/fp_baseline_2026-09-30.json` (survives container recreates; future compares use it); 10-file suite **207 passed / 1 skipped / 7 xfailed — fully GREEN**.
  - **Task 4 ✅ DONE (9 gates, ~30min):** GREEN — inner-peace live (peace rank2, America absent, quotes verbatim-substring, walls 17-27ms), DISTRESS both routes (crisis_redirect / crisis_preempted, 0 citations, bridge not invoked), 5-query both routes (fp 5/5 direct verbatim+links; chat completed, bridge never invoked), Indic (fail-open works; **new finding: chat response cache language-insensitive** — byte-identical English served to hi-pref, tension w/ cache-key invariant, owner item; 63.7s Hindi tail), docs append-only +43,583 chars proven byte-asserted (file untracked `??`). RED/qualified — Gate1: flag-blind `test_build_default_pipeline_order` (session defect), Gate2: 4 session-introduced lint errors, Gate3: baseline `/tmp/fp_before.json` destroyed by Task 3 recreate (incident; substitutes: run-to-run n_discordant 0 p=1.0 + two prior formal GREENs), Gate5: fp OOC still direct (G9 by design, re-confirms Audit B). Bottom line: audit's NOT-prod-ready verdict unchanged; live proof Task 1 fix + kill-switch behave as specified.
  - **Task 3 ✅ DONE:** build 6s via `scripts/docker-safe.sh` (project `backend`, image `backend-backend:latest` 28.2GB, no size regression); mount-free `baked-ok` (bridge+pipeline import from image); `up -d` recreate (no restart, no volume touch); health ready ~10s all criticals ok; env resolved `bridge=False route=True coll=first_person_v7`; release gate 0 errors; **kill-switch live-proof**: OOC chat probe → `grounded_partial_evidence`, no `first_person_bridge` anywhere in payload; fp route 200/0.342s with peace clip slot 2 + America/UN absent + `&t=` links (Task 1 fix live); mem 2.76GiB/6GiB, no OOM. Anomalies logged: `route_decision` naming oddity (pre-existing), OOC chat still corpus-tangential via graph (Audit B known, bridge-independent).
  - **Audit C ✅ DONE:** `audit_2026-09-29/C.md` — 715→717 = legit zero-LLM TEDxKC ingest, 7/7 verbatim, rights OK, but `teacher: sri-krishnaji` contract violation FIXED in `compiled.json` (backup `/tmp/compiled_before_sectionc.json`; root cause `ingest_single_video_okf.py:65-70` logged, not edited); count-test now schema-derived + `>=715` floor; matcher → DEFER (frozen file, no held-out eval); gates intact (integrity 7-case, curated-OKF refusal, quote gate, citation contract 9/9); 3 quote-gate gaps xfailed (`quote_weaver.py:103,128,171`: fake `t=`, unquoted claim, `clips[:2]`); 3 OKF-data gaps quarantined (13 `**` leaks, 14 mojibake, 2 failing `find_artifact()`); **P0 candidate: 126/2090 teachings (43 entries) NOT verbatim in own source transcript, feed quote gate as authoritative**; 179 entries lack `**Speaker:**` headers; spot-check 5/5 clean; tests 2922 passed/6 xfailed.
  - **Audit E ✅ DONE:** `audit_2026-09-29/E.md` — `n=300` traced to synthetic fixture `test_run_calibration.py:239`; 3 identical untracked profiles sha256 `de743066…`; real budget 14 single-judge labels (`~/mukthiguru_attribution_data/gold_pilot/relevance_pilot.csv`); profile internally inconsistent (n=300⇒ucb 0.00994); honest profile n=14/ucb=0.1926 REJECTED by both validators → truth-fix = behavior change, documented not applied; prod dry-run `FirstPersonReleaseError` (serve_unregistered, missing calib path, git_sha unknown-sha); focused suite 3173 passed/3 failed/29 collection errors, full suite OOM→batched 7613 passed/69 failed/29 uncollectable (container path artifacts, ≠ CI); harness pinning/denominator/real-pipeline/McNemar = REAL, golden-25 gate DECORATIVE; added `test_calibration_provenance.py` (3 passed, 1 xfailed). Recommended: demote lessons/handoff n=300 claims; label to n≥299 before any env set.
  - ACTIVE: Audit E `ses_f0f296ed7ffeElxpaNrdwBLdUb`
  - **Audit B ✅ DONE:** `audit_2026-09-29/B.md` — calibration loads ONLY via uncommitted fallback (`first_person_pipeline.py:530-549`; HEAD loads nothing); `n:300/ucb:0.009` = fiction-as-data (3 untracked copies, no generator, real budget 14+25); **threshold 0.45 zero abstention power** (3/3 OOC queries served direct, top-1 up to 0.6476, `weak_match` never fired in 24 probes); prod boot FAILS CLOSED (`first_person_release.py:98` demands env set nowhere); latency truth p50 21.7ms pipeline / 75ms wall / cold 517ms; quarantine ~4.2/query (28% candidates, backfill 100% recovery) — "0 quarantine" doc claim false; 52 mismatched points serve with no ID check, stale confidence feeds `is_direct`; cache key missing max_clips (measured); tamper detection live-verified. **Implications: bridge gate (Task 2) inherits zero-abstention → Final must rank a threshold/abstention fix P0; env+code reconciliation is Audit D runbook material.**
  - **Task 2 ✅ DONE (2026-09-30):** `first_person_bridge.py` registered between BoundedComparison & GraphStage; flag `first_person_chat_bridge_enabled` (env `FIRST_PERSON_CHAT_BRIDGE_ENABLED`, default True) + 2 existing kill switches = triple off; 92 tests green (25 bridge + 20 citation contract + stage/distress/quote-guard regressions), ruff clean. Decisions: bridge runs `container.guardrails.check_output()` itself (block → fall through to graph, graph rail = final authority); quotes/speaker/links byte-protected, glue-only `_translate_cached` 5s fail-open; gate = success + `is_direct_answer` + ≥1 eligible verbatim citation; output = exact `PRE_BRIDGE_CHAIN` when flag off. Files: new stage + `__init__.py` + `pipeline_builder.py` + `config.py` + 3 test files (7 total, uncommitted).
  - **Audit A ✅ DONE:** `audit_2026-09-29/A.md` — 52/144 ID≠uuid5(hash) points + stale embeddings (0.91 vs 0.97) invisible to gates; 16 pts/14 videos deleted unlogged; `rights_cleared` unindexed (R1); ECAPA write-path unwired (R8); `question_dense` dead schema; `repair_v7_clips.py` fix + regression test applied (47 passed). Top findings feed Audit B (stale-vector × serve gates) and Final synthesis.
  - **Task 1 ✅ DONE (2026-09-30):** 4c fix intact; 68 tests green (4 new: threshold-gate, America/UN regression `0Fa4Wyv0GOk` stays ahead of `-pBQ6Sy444o`, diversity-within-δ, no-profile fail-closed); inner-peace probe → peace clip rank 2, America/UN not served; harness compare vs `/tmp/fp_before.json`: top1 0.2697 identical, n_discordant 0 p=1.0, host_like 0.1681→0.177, p50 18.2→18.1ms — **no regression**; lint zero new findings (pre-existing at HEAD proven via `git show HEAD:`); `git diff --check` clean.
  - QUEUED: audits B → C → E → D → Final, then Tasks 3/4/5
**Prior version:** v1 discarded — named a non-existent function, invented contradictory thresholds, under-specified the chat bridge, ignored compose bind mounts, and had no test/rollback/docs gates.

---

## 0. Verified Facts This Plan Is Built On

| Fact | Evidence |
|---|---|
| Balancing is **inline**, no `_balance_teachers()` exists | `backend/services/first_person_pipeline.py:784-811` (Step 4c) |
| Top clip already pinned to index 0 | `first_person_pipeline.py:799`; test `test_teacher_diversity_preserves_top_rank` (`tests/test_first_person_pipeline.py:726`) |
| **Existing test encodes the defect**: asserts slot 1 = lower-cosine `k1` (0.7) over higher-cosine `c2` (0.9) | `tests/test_first_person_pipeline.py:777-779` — must be rewritten as part of Task 1, this is *not* a broken invariant |
| Clip order passes 4 stages: fusion → 4b cross-encoder (`:774`) → 4c balancing (`:784`) → 4d LLM rerank (`:813`, post-balancing, default off) | `first_person_pipeline.py` |
| Confidence = dense cosine vs query vec, computed **after** ordering; `is_direct` uses slot-0 only against fitted profile (`threshold=0.45`, `score_kind=dense_cosine`, `ucb_risk≤0.01`) | `first_person_pipeline.py:836-839`; `config/first_person_calibration_v7.json` |
| Chat stage order: KillSwitch → CacheCheck → RequestState → **InputGuardrail** → CircuitBreaker → DoctrineCache → CasualShortCircuit → **Distress** → BoundedComparison → **GraphStage** → MeditationGen → Translation → ToneAdapter → **OutputGuardrail** → Memory → CacheUpdate → ResultAssembly | `app/pipeline/stages/pipeline_builder.py:42-58` |
| Short-circuit pattern: stage returns `PipelineResult \| None`; non-None terminates | `glue_stages.py:341-390` (CasualShortCircuitStage) |
| Chat corpus is 61% machine-rewritten; only first-person route names speakers (voice-verified gate, pinned test) | L-VERBATIM-1; L-SPEAKER `lessons.md:306`; `tests/test_citation_contract.py::test_unverified_speaker_and_teacher_id_are_never_named` |
| Compose bind-mounts shadow image code | `backend/docker-compose.yml:407` (`./app:/app/app`), `:410` (`./services:/app/services`) |
| `restart` does not re-read `.env`; active collection key is root `.env:157 FIRST_PERSON_COLLECTION` | L-V5 `lessons.md:74-75` |
| Pinned eval harness exists: 116 sha256-pinned questions (89 answerable / 27 unanswerable) + 25 golden paraphrases, runs real serving pipeline, read-only | `evaluation/first_person_harness.py` |
| Startup release gate validates first-person production contract | `app/main.py:780` `validate_first_person_production_contract()` |
| Quote assertion gate already exists (selection-only, zero text generation) | `services/quote_weaver.py` `QuoteWeaverAssertionGate`; handoff.md v3.0 zero-generation architecture |
| Output guardrail + translation run **after** GraphStage — a short-circuit before GraphStage skips them | stage order above |

---

## 1. Corrected Diagnosis

1. **Retrieval false-balance defect (confirmed symptom, unpinned cause).** For `"how do I find inner peace?"`, best clip `0Fa4Wyv0GOk@99s` (cosine 0.6836) served at rank 3; `-pBQ6Sy444o` America/UN clip (0.5790) at rank 2. Symptom real. Cause *not yet proven* — could be fusion order, 4b rerank, or 4c balancing. **Evidence before fix (Task 1, step A).**
2. **Main-chat third-person synthesis (confirmed).** `POST /api/chat` answers via LangGraph `GenerationStage` producing "Sri Preethaji & Sri Krishnaji teach that…" — no path to `first_person_v7`. Seekers never hear verbatim teacher voice in main chat.
3. **Docker image stale + bind mounts.** Image ~22h old; even after rebuild, `./app` and `./services` mounts shadow baked code. Rebuild value must be verified on a mount-free container run.
4. **Root-cause-independent exclusion rule (missing in v1, mandatory):** Only hash-verified, voice-verified `first_person_v7` clips may render teacher voice anywhere. `spiritual_wisdom_contextual` chunks (61% LLM-rewritten) and OKF summaries may never be quoted as teacher speech. Chat-corpus citations keep `speaker=None` — never relax the gate.

---

## 2. Architecture (single chosen design — v1 offered two, undecided)

```
[ Seeker Query ]
      │
      ├── POST /api/first-person/query ──► FirstPersonPipeline.execute()  [unchanged route]
      │
      └── POST /api/chat
             │
      stages up to BoundedComparison (safety lane UNTOUCHED)
             │
      ▼ NEW: FirstPersonBridgeStage  (after BoundedComparison, before GraphStage)
             │  runs FirstPersonPipeline.execute() on first_person_v7
             │  calibrated gate: is_direct (profile threshold — NOT an invented number)
             │
      ├─ is_direct=True  ──► assemble answer from verbatim clips only
      │                       (QuoteWeaver zero-generation assembly, YouTube &t= deep links)
      │                       return PipelineResult  → skips GraphStage
      │                       still passes TranslationStage policy + OutputGuardrail
      │                       via explicit handling in the stage (see Task 2 contracts)
      │
      └─ is_direct=False / abstained / error ──► return None → GraphStage runs as today
                                                 (zero degradation of existing behavior)
```

**Why this design:** reuses the calibrated, hash-gated, test-covered pipeline as-is; mirrors the existing short-circuit pattern; abstention-first (144 clips / 5 themes ⇒ most queries fall through to today's path); no new dependency (v1's "DSPy Assertion Gate" deleted — `QuoteWeaverAssertionGate` already exists, DSPy here violates ladder rung 2); zero LLM text generation at serve time preserved (v1's "LLM grammar smoothing" deleted — conflicts with handoff.md v3.0 zero-generation invariant and would trip the assertion gate anyway).

**Kill-switch:** `FIRST_PERSON_CHAT_BRIDGE_ENABLED` (default on when deployed; `false` restores exact current behavior without a rebuild).

---

## 3. Tasks

### Task 1 — Pin cause, then fix teacher balancing (`first_person_pipeline.py` Step 4c)

**Step A — evidence first.** For `"how do I find inner peace?"` against `first_person_v7`, dump ranked candidate list after each stage: fusion → 4b → 4c → 4d. Record which stage demoted `0Fa4Wyv0GOk@99s`. (Log-only debug, no behavior change.) Fix targets the guilty stage; if fusion/rerank is guilty, 4c is not the fix.

**Step B — fix, no magic numbers.** In the inline block (`:784-811`):
- A candidate may be placed above a displaced same-teacher clip only if BOTH:
  1. candidate cosine ≥ calibration profile `threshold` (0.45 — fitted, not invented), AND
  2. `cosine_displaced − cosine_candidate ≤ δ`, where δ is **fitted by harness ablation** (start δ=0.05; record measured effect; v1's 0.05-vs-0.06 contradiction eliminated — one δ, sourced from measurement).
- Ladder rung 1 applies: first measure whether alternation earns its complexity. Run harness with balancing on vs off; if teacher-coverage gain is nil or top-k relevance drops, restrict/remove alternation rather than tune it.
- `is_direct` decision inputs must not change (slot-0 semantics preserved).

**Step C — tests** in `tests/test_first_person_pipeline.py`:
- Rewrite `test_teacher_diversity_preserves_top_rank:726` — current assertions `:777-779` pin the defect; new version asserts a lower-cosine off-topic clip is NOT promoted above a higher-cosine same-teacher clip beyond δ, and that a clip below profile threshold never enters slot 1-2 via balancing.
- Regression: `is_direct` / abstention outcomes unchanged for profile fixtures (existing tests `:149-201`, `:284` must stay green).

**Step D — gate:** harness run before/after, `compare` must show no top-1/top-k regression on the 116 pinned questions.

### Task 2 — FirstPersonBridgeStage (new file `app/pipeline/stages/first_person_bridge.py`)

Register in `pipeline_builder.py` after `BoundedComparisonShortCircuitStage`, behind `FIRST_PERSON_CHAT_BRIDGE_ENABLED`.

Explicit sub-tasks (each = code + test):
1. **Eligibility exclusion:** clips come only from `first_person_v7` via `FirstPersonPipeline` (integrity + content-quality + sha256 gates inherited). Code comment states: chat corpus / OKF text must never render as teacher voice.
2. **Answer assembly:** reuse `QuoteWeaverService` zero-generation assembly; every quoted sentence = exact substring of a served clip (existing assertion gate). No generated openings, no paraphrase, no third-person synthesis of clip text.
3. **Citation contract:** bridged citations use `FirstPersonPipeline._build_citation` shape; speaker named only because first-person clips are voice-verified. Add test in `tests/test_citation_contract.py` covering bridged citations; NEVER touch `_resolve_speaker`'s `speaker_verified` gate. Verify citation payload survives the browser-facing SSE metadata allowlist (AGENTS.md public-projection rule).
4. **`_unquote_unverifiable_spans` interaction:** because the bridge short-circuits before `format_final_answer`, verify (test) that no path later re-processes and strips the verbatim quotes; if the bridge answer flows through any cleaning chain, injected clip text must be present in the context that guard checks against.
5. **Translation policy (product invariant):** quotes are NEVER translated (translating a living teacher's words = alteration). For Indic `preferred_language`, only bridge framing/glue text is translated via existing `translation_timeout_s` (5s, fail-open). Non-English quote text is served verbatim as-is. Test: Hindi-preferring user gets verbatim English quotes + localized glue.
6. **Safety ordering:** bridge placed AFTER `InputGuardrailStage` + `DistressStage`. DISTRESS probe test: acute self-harm query → blocked, zero citations, bridge never invoked.
7. **Cache contract:** bridge returns before `CacheUpdateStage` (consistent with other short-circuits). Verify `CacheCheckStage` cannot serve a stale/foreign bridge result under a shared key (cache lesson `lessons.md:4539`): exact-query cache key must include language; bridge results either bypass shared cache or use the existing keyed namespace. Test it.
8. **Failure/degradation:** any exception in bridge → log + return None → GraphStage (today's behavior). Kill-switch off → identical behavior. Test both.
9. **Release gate:** confirm `validate_first_person_production_contract()` (`app/main.py:780`) still passes at boot after changes.

**Files:** new stage + `pipeline_builder.py` registration + tests. `distress_stage.py`, `serene_mind_engine.py`, `lightweight_handler.py`, graph internals: **zero changes**.

### Task 3 — Docker rebuild & redeploy (decision: mounts stay, value verified mount-free)

1. Dev stack keeps `./app` + `./services` bind mounts (hot-reload is intentional — document as decision, not gap). Baked-image integrity is proven separately:
   `docker compose -f backend/docker-compose.yml build backend`, then
   `docker run --rm --entrypoint python <backend-image> -c "import services.first_person_pipeline, app.pipeline.stages.pipeline_builder"` — proves code is inside the image, no binds involved.
2. `docker compose -f backend/docker-compose.yml up -d backend` — **`up -d`, never `restart`** (L-V5: restart skips `.env` re-evaluation). Root `.env:157 FIRST_PERSON_COLLECTION` must resolve to `first_person_v7` in the new container env.
3. PATH prefix per AGENTS.md: `export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"` (or Makefile targets). Never `kill -9` docker-owned processes. No volume purge.
4. Verify: `GET /api/health` → `ready: true`; active collection = `first_person_v7` (log line / `scripts/live_query_test.py` probe); startup release gate passes.

### Task 4 — Validation gates (harness-based, not vibes)

| # | Gate | Command / method |
|---|---|---|
| 1 | Unit + regression suite | `docker compose run --rm backend pytest` (container = locked deps; sandbox venv is dependency-limited per AGENTS.md) — full suite green, incl. `test_citation_contract.py`, `test_answer_path_regressions.py`, rewritten diversity tests |
| 2 | Lint | `ruff check` / `ruff format --check` |
| 3 | Ranking regression | `python -m evaluation.first_person_harness run --collection first_person_v7 --out /tmp/fp_after.json` + `compare /tmp/fp_before.json /tmp/fp_after.json` (baseline captured **before** Task 1 edit) |
| 4 | Inner-peace probe | rank trace shows peace clip no longer displaced beyond δ; America/UN clip not served |
| 5 | Abstention probes | ≥2 of the 27 pinned unanswerable questions → honest abstention, fall-through to graph on `/api/chat` |
| 6 | 5 seeker queries both routes | verbatim quote = substring of clip; `&t=` links accurate; zero third-person synthesis; measure and record real latency (fp <500ms target; chat: record measured value — **no unevidenced <4s claim**) |
| 7 | Safety probe | acute self-harm on both routes → `DISTRESS`, zero citations |
| 8 | Indic probe | Hindi preference → quotes verbatim, glue translated, translation failure fail-open |
| 9 | Docs output | **APPEND** dated section to existing `docs/FIRST_PERSON_AND_GENERAL_CHAT_RESPONSES.md` (do not overwrite the existing 5 questions) |

### Task 5 — Rollback & documentation

- **Rollback:** set `FIRST_PERSON_CHAT_BRIDGE_ENABLED=false` + `up -d` (instant, no rebuild); code rollback = `git revert`. Balancing fix rollback = revert commit; harness `compare` numbers recorded in the docs file serve as the before/after evidence.
- **Docs checklist (mandatory, AGENTS.md):** `lessons.md` (new patterns: bridge stage placement, δ-fitted balancing), `handoff.md` (v3.1 state), `docs/PRODUCT_OPPORTUNITIES.md` roadmap tick, README env var (`FIRST_PERSON_CHAT_BRIDGE_ENABLED`), `AGENTS.md`/`CLAUDE.md` if stage map changes. Update this plan file as tasks complete.
- **Commit/push:** only if explicitly approved.

---

## 4. Scope Fence (MVP — what this plan will NOT do)

- No new Python dependencies (no DSPy gate), no Qdrant/Neo4j writes or schema changes, no corpus/OKF mutation, no model or threshold re-calibration beyond the δ ablation, no changes to safety stages, no `FLUSHALL`, no removal of compose bind mounts, no frontend work (existing References panel already renders `&t=` links — verify in Task 4 step 6, fix only if broken).

## 5. Task Order & Dependencies

```
Task 1A (trace) ──► Task 1B (fix) ──► Task 1C/1D (tests + harness gate)
Task 2 (bridge)  — independent of Task 1, but merge only after Task 1D green
Task 3 (docker)  — after Tasks 1+2 merged
Task 4 (gates)   — runs partly before (baseline) and partly after Task 3
Task 5 (docs)    — final
```

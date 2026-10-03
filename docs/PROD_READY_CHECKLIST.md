# Production-Ready Checklist — AskMukthiGuru First-Person Pipeline

**Created:** 2026-09-30 · **Owner:** project owner (you) + orchestrator
**Plain-language goal:** a real user can ask a question and get a *verbatim* answer from Sri Preethaji / Sri Krishnaji's own recorded words — or an honest "they don't have a teaching on this" — safely, in their language, and nothing in the system is made up.

**How to read each item:** 🟢 done · 🟡 in progress · ⛔ not started · 👤 = needs YOU (owner), not code.

---

## A. Already done ✅ (2026-09-30 session)

- 🟢 Ranking fix — a bad tie-breaker was promoting an unrelated lecture; fixed + tested (evidence: `trace_1A.md`)
- 🟢 Main-chat bridge built, then **switched off** with a kill-switch until abstention is proven (it once answered "capital of France" as a teaching — audit D)
- 🟢 Index cleaned: 52 corrupted points re-fixed; every future write is now checked 3 times and fails loudly instead of silently corrupting (Phase 1)
- 🟢 Docker image rebuilt clean, deployed locally, all live probes pass (safety, quotes, timestamps)
- 🟢 Full 9-gate E2E battery run; 7-section ruthless audit complete (6 P0 / 10 P1 / 9 P2 — detail: `.claude/tasks/first_person_e2e_audit_2026-09-29.md`)
- 🟢 Documentation corrected (handoff, lessons, README, roadmap) — no more fake "163 tests green" / "sub-30ms" claims

## B. Closed ✅ (both phases landed 2026-10-03)

- 🟢 **Honest abstention (Phase 2)** — `first_person_answerability_check_enabled` (default `True`) gates every first-person answer with a YES/NO/INDETERMINATE LLM verdict; `_answerability_check` now pins `temperature=0.0` (stability probe: 15/15 row stability vs 5/15 at temp 0.1 — `L-GATE-TEMP-1/2`); Q2 numbers measured across three full runs (R4 healthy window leak 26–30% / FR 2.6%; R5b decided-basis leak 25.0% / true FR 1.75% / verdict agreement vs R4 = 100%; isolation chain separates provider-degraded timeout inflation from real gate behavior — `L-GATE-LOAD-1/2`). Evidence: `~/mukthiguru_attribution_data/p0/phase2/answerability_{r4,r5,r5b}_2026-10-03.json`. Bridge flag **flipped ON 2026-10-03 (owner Q2 answer, report §9f)** — live serve proven (`route_decision=first_person_bridge`, verbatim t-link); Audit-D OOC concern covered by the answerability gate. Fall-through switched off via `first_person_llm_fallback_enabled=false` when the owner wants FP-only (Ask 1 capability, report §9a).
- 🟢 **Fake-quote repair (Phase 3)** — quote-gate after-report: **32/32 verbatim, 0 not_found, 0 partial, 0 entries affected** (before: 38 quotes / 18 entries affected) → `~/mukthiguru_attribution_data/p0/okf_quote_gate_report_after.json`; 3 quote-rendering bugs fixed; `HANDOFF_2026_10_03.md` §F.

## C. Calibration claims DEMOTED ✅ (verified 2026-10-03)

**What was wrong (simple terms):** a settings file claimed the system was tested on 300 examples with tiny error bars. Truth: **14 examples**. The claim was statistically impossible and was traced to a test fixture.
**What "demote" means:** stop claiming statistical guarantees we don't have — don't fabricate a fake "honest" profile either.

Verification (all four items done):
1. ✅ Calibration JSONs rewritten — `config/first_person_calibration_v7.json` + `backend/config/first_person_calibration_v7.json` (and the sibling `*_first_person_*`/`first_person_calibration.json` files): `threshold`/`score_kind` kept, `"claims": "none"`, provenance `n=14 pilot, no conformal guarantees`. Grep for `n.*300|ucb_risk|target_risk` over `config/` + `backend/config/` = **CLEAN**.
2. ✅ Production boot gate (`backend/services/first_person_release.py`) — no calibration profile required; production instead requires the **answerability check enabled** (the honesty mechanism from §B) as the gate's audit comment states. `backend/tests/test_first_person_release.py` = **8 passed** (2026-10-03).
3. ✅ `handoff.md` grep clean (current v4.0 has no n=300/ucb). `lessons.md` hits are **demotion-history provenance** (lessons describing the fiction *as* a fiction, e.g. "traced four numbers-layer fictions… real label budget = 14") — preserved per AGENTS historical-provenance rule, not live statistical claims.
4. ✅ Done-when: JSON grep clean + release-gate tests green (8/8). IS_PRODUCTION boot path is exercised by those same release-gate tests (no-profile case covered).

## D. Must-do before ANY production deploy ⛔

| # | What's wrong (plain) | Do | Done when | Who |
|---|---|---|---|---|
| 1 | Our test "green" numbers came from a laptop container, not the real CI environment — 69 failures were blamed on the environment without proof | Run the full test suite in a clean Python 3.12 env exactly like CI (`pip install -r backend/requirements.lock` then pytest) | One authoritative full-suite run exists; every failure either fixed or documented as environment-only — **✅ closed 2026-10-03 (D1)**: three full-suite runs in the dependency-complete backend venv (`d1_full_suite_raw{,_run2,_run3}_2026-10-03.log`) → **12 failures → 0 unexplained**: 5 environment-proven (container/ruff-only lanes), 2 isolation fixes, 5 lane-conflict documented. Report: `.claude/tasks/audit_2026-09-29/d1_ci_true_suite_2026-10-03.md`. **Orchestrator follow-up same day:** 3 of its 6 §6 items fixed + verified (undeclared settings declared, factory loop capture made optional, `find_spec("mlx.core")` guarded → 24/24 + 149/149 focused green); §6.1 (S1 conflict) **fixed at root cause 2026-10-03 (owner Ask 5)** and §6.5 (commit-or-drop untracked) **resolved = all 4 COMMIT (owner Ask 6)**; §6.6 = D4 (already closed) | agent |
| 1b | (follow-up, post-D1) full suite re-run after the 4 D1 fixes | re-run CI-mirrored suite | **✅ 2026-10-03**: `2 failed, 8467 passed, 12 skipped, 2 deselected, 1 xfailed in 412.71s` — failure 1 = `test_clips_v2::test_b` (owner/S1 conflict), failure 2 = okf extractor-copy divergence (backend copy modified 16:22 post-D1, formatting-only) → synced `backend→root`, **verified**: `SYNC_OK` + `ruff` green + `11 passed in 7.20s` (`test_okf_pipeline_integrity`) → **late-turn close-out: failure 1 (`test_b`) FIXED at root cause (owner Ask 5, report §9b) — post-fix full-suite re-run = the pre-commit gate (report §9g)** | agent |
| 2 | Hindi users can receive a cached **English** reply (cache ignores language) | Include language in the cache key + test | **✅ closed 2026-10-03 (Wave 2)**: `cache_language_key(msg, lang)` wired at `app/orchestrator_utils.py:458` + FP exact-cache `language=` param (`first_person_pipeline.py:746` "D2 audit fix"); tests `test_llm_system_design_invariants.py:72-77` + `test_first_person_bridge.py:499-500` (en/hi keys differ) | ~~agent~~ |
| 3 | `FIRST_PERSON_SERVE_UNREGISTERED=true` locally — would serve non-cleared videos | Set `false` in prod env (comment already says so at `.env:154`) | **🟡 local audit DONE 2026-10-03; prod audit = deploy**: root `.env:156` = `true` (owner local-eval decision 2026-09-25; flows into the container via `backend/docker-compose.yml:197 env_file: ../.env` — measured live: `settings.first_person_serve_unregistered = True`, bridge = False ✓). Current risk measured **zero**: Qdrant `first_person_v7` = **177/177 points `rights_cleared=true`, 0 un-cleared** (scroll with `must_not` filter). Prod (Railway paused) audit stays 👤/deploy: **Ask-7 owner answer 2026-10-03 = serve flag STAYS `true` in production too** (FP is the primary path now) — `.env:154` comment rewritten to record that decision superseding the 2026-09-25 "local eval only" note (report §9f) | 🟢 trivial / deploy |
| 4 | Repo lint: 145 errors in 68 files (44 pre-date this session) | Fix or document an explicit allowlist in ruff config with reasons | **✅ closed 2026-10-03 (D4)**: `cd backend && ruff check .` (CI-pinned ruff 0.15.13) = `All checks passed!` — fresh count was 122 errors/60 files; 122 safe auto-fixes applied (`--fix`, `scripts/ingestion/**` excluded for Wave-4a ownership) + 13 manual fixes (F821 missing `Any` import, F841 dead inits, E741 `l` renames, E702 semicolon splits, B007, B011 `assert False` → `raise AssertionError`) + 1 documented per-file-ignore (`scripts/ingestion/repair_v7_clips.py` = I001, reason + removal condition in `backend/pyproject.toml`) + 3 invalid `# noqa: ANN` → `# noqa: ANN002, ANN003`. Touched-test battery **286 passed / 1 failed** — the failure (`test_clips_v2::test_b_host_word_splits_run_and_is_never_included`) proven pre-existing (S1 `relabel_turn_start_prefixes` uncommitted feature absorbs a genuine host word; my only diff in that file is a semantically-identical E713 in a different test). **Format drift closed scoped 2026-10-03 (§5e) → then fully closed late-turn: backend 129 → 21 = lane-exclusion → 0 remaining** (all 21 formatted under owner Ask-3 grant; `ruff format --check .` = `1206 files already formatted`, `repair_v7_clips.py` I001 per-file-ignore kept until Wave 4a); 157 non-backend repo-root files were never in the recorded debt (root config needs a `scripts/ingestion/**` exclude first) | agent |
| 5 | "Golden-25 quality gate" runs nowhere — decorative | Wire it into `.github/workflows/` | **✅ PASS 2026-10-03 (D5, thresholds now MEASURED)** — `.github/workflows/golden25-gate.yml`: PR paths + nightly + dispatch, secrets-gated honest-skip (eval-gate pattern), real `evaluation.first_person_harness run` on SHA-pinned dataset, threshold PASS/FAIL table in step summary, artifact upload. **Two golden-25 runs** same day: run1 (`golden25_baseline_2026-10-03.json`) top1 0.12 / 8 gate-timeout abstains (degraded provider window), run2 (`golden25_healthy_2026-10-03.json`) top1 **0.16** / 3 TO / 0 errors (health-gated via latency canary 0/15 TO, p50 1255). Thresholds set at observed floors — `GOLDEN25_TOP1_MEAN_MIN=0.12` (= min across both runs, absorbs provider-timeout variance; abstains score miss by design), `SAME_VIDEO=0.0`, `SAME_CLIP=0.0` (both runs 0.0 → floor-only on pre-ingest 144→177-clip index; **re-measure post-mass-ingest**, `HANDOFF_2026_10_03.md` §6 Step 4, same change as provenance comment). Workflow threshold logic replicated locally against **both** run JSONs → **PASS / PASS**. Owner: **⚠️ measured 2026-10-03 (Ask 4) = 0 secrets anywhere** — `gh secret list` empty, `gh api …/actions/secrets` total_count=0, every environment empty; 6 exact `gh secret set` commands in report §9e → gate stays honest-skip until owner sets them | agent |
| 6 | Legal basis for transcripts/embeddings unconfirmed; `cookies.txt` (294 KB, gitignored) exists | Review `CONTENT-RIGHTS.md` (R5/R6 audit items); confirm sourcing method acceptable; never commit/ship cookies | Written sign-off in CONTENT-RIGHTS.md | 👤 **you** |
| 7 | Railway won't even boot: `start_railway.py` exits without `FORWARDED_ALLOW_IPS` (fail-closed) | Set Railway var (e.g. `10.0.0.0/8`) **before** next deploy | `railway variables` shows it; deploy passes startup | 🟢 trivial / deploy |
| 8 | Deploy method has burned us before | Use `railway up` (never `redeploy --from-source`), 1 replica, then smoke: anon-session → chat → health | Health 200, `ready:true`, one real quote with `&t=` link on prod URL | deploy |

## E. Quality tier — makes it *good*, not just live ⛔/🟡

| # | Item | Plain terms | Done when |
|---|---|---|---|
| Q0 | 🟢 **Audio archive (owner-approved 2026-09-30)** | Save **every** audio file + manifest (checksums, source, rights) in one durable place outside git, so if anything breaks — or a video disappears from YouTube — we can rebuild transcripts + clips from local audio | Archive script + manifest verify exit 0; all existing wavs migrated; all 515 targets pre-registered; future ingest writes here first |
| Q1 | **Corpus expansion** (biggest lever) 🟡 **RUNNING 2026-10-03** | Only 31 videos quoted today; 515 cleared videos waiting → ~2,500 clips. Needs: mass driver build, ECAPA speaker-check wired into builder, 5-video smoke, then run (host-side embedding — container OOMs) | **Driver built + self-check OK + dry-run verified 2026-10-03** (`scripts/ingestion/mass_first_person_ingest.py`: 515 eligible → 511 selected / 46.69 h / 511/511 archived wavs / resume-safe `state.json`, **no LLM dependency** — never touches RPM). 5-video smoke passed gates (`smoke5_report_2026-10-03.json`: asr_agreement 0.966, host_leak 0). **Full run launched 2026-10-03** (2 workers, background, resumable). Done when: v7 holds ~2,500 clips, ID audit 0 mismatches, harness re-baselined + golden-25 thresholds re-measured |
| Q2 | Bridge re-enable | First-person answers in main chat | **✅ answered + applied 2026-10-03 (owner: "I need First Person")** — `FIRST_PERSON_CHAT_BRIDGE_ENABLED=true`, container recreated, live serve proven (`route_decision=first_person_bridge`, verbatim t-link; report §9f). Answerability gate ON covers the leak-rate concern; LLM-off switch = `first_person_llm_fallback_enabled` (Ask 1, report §9a) |
| Q3 | Hindi latency | 63.7s measured worst case (normally <1s) | p95 recorded + fixed or documented |
| Q4 | Multi-turn memory | "what did you mean by *that*?" doesn't work yet | follow-up queries carry context, test green |
| Q5 | Mobile deep-links | `&t=` links must open YouTube app in Capacitor WebView | checked on Android + iOS |
| Q6 | Docs drift | Audit G.4 fix-list (8 items) | G.4 items closed — **7/8 closed 2026-10-03; #4 (`.claude/tasks` archive) deliberately deferred while live plan files are referenced by running agents. Per-item closure evidence in `.claude/tasks/first_person_e2e_audit_2026-09-29.md` §G.4** |

## F. Standing rules (never break)

- Kill-switches stay **on** until each feature proves itself (answerability flag, route flag). Bridge flag = **ON since 2026-10-03** by owner Q2 answer ("I need First Person") — gated by the answerability check; rollback = `FIRST_PERSON_CHAT_BRIDGE_ENABLED=false` in root `.env`
- No statistical/quality claims in docs without a command that produced them
- Never embed inside the running backend container (OOM) — host-side only
- Re-run `reconcile_first_person_v7.py --dry-run` after any bulk write → must say 0
- Commits: **granted 2026-10-03 (Ask 3)** — one scoped session commit, long message, lessons recorded; no data files (transcripts/audio/`.env`) ever

## Open decisions still yours 👤

> **Single package with evidence + recommendations:** `docs/PROD_READY_OWNER_PACKAGE.md` — **all 9 answers received 2026-10-03 and executed (✅ OWNER ANSWERS table there; evidence in session report §9).** Outstanding owner action = **Ask 4 secrets** (none set anywhere — exact names/commands in report §9e).

1. ~~Ingest fork~~ — ✅ **resolved 2026-09-30: "do everything except Railway"** → driver-first order (Wave 4)
2. ~~Legal sign-off (D6)~~ — ✅ answered 2026-10-03: never commit transcripts/audios, keep local (GDrive later) — verified in report §9d
3. ~~Railway~~ — ✅ excluded by owner directive (D7/D8 on hold); Ask 8 conditions = local-prod-ready + greens + memory/cost optimization first
4. ~~Approve the scoped commit~~ — ✅ granted 2026-10-03 (Ask 3), executed
5. ~~External backup of the audio archive~~ — ✅ answered 2026-10-03: local now, GDrive later (Ask 9)

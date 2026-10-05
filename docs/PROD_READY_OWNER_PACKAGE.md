# PROD_READY_OWNER_PACKAGE — decisions only yours 👤

**Created:** 2026-10-03 · **Companion to:** `docs/PROD_READY_CHECKLIST.md` (definition of done)
**Rule:** the agent prepares, evidences, and recommends — it never executes anything in this file. Nothing here runs without your explicit go.

**How to read each ask:** what we ask · why it matters · evidence (paths + measured numbers) · recommended choice · what happens right after you decide.

---

## Context: what is already done and proven (no action needed)

- **Backend container restarted onto current code** (2026-10-03 20:32 IST): `/api/health` → `ready=true, status=healthy` in 75 s, embedding dim 1024, all criticals ok, guardrails lightweight ok.
- **Live probe battery GREEN** (evidence: `~/mukthiguru_attribution_data/p0/live_probe_restart_2026-10-03.json`):
  - **FP route positive path** — `POST /api/first-person/query` "How to be peaceful?" → HTTP 200, `status=success`, `answerability=yes`, **4/4 citations with `&t=` deep links**, genuine verbatim Krishnaji quote (`answerability` gate verdict `yes`), 4.2 s.
  - **FP route honest path** — first probe (weaker query) → `status=abstained`, `answerability=indeterminate`, 0 citations — fail-toward-honesty working live under provider load.
  - **Bridge kill-switch** — `POST /api/chat?wait=true` OOC "capital of France" → HTTP 200, `grounding_state=grounded`, `verification_method=grounded_partial_evidence`, **zero `first_person_bridge` tokens in payload** (matches the Task-3 precedent exactly).
  - **Plug-play registry gates, both directions** (fresh container processes):
    - serving env resolves `route=True bridge=False mode=retrieval_only coll=first_person_v7` → router default = `GENERAL_ENTRY`; bridge forced ON → `first_person`; route OFF again → `GENERAL_ENTRY`.
    - env override `FIRST_PERSON_ROUTE_ENABLED=false` → `route=False`; **even with bridge forced ON the router stays `GENERAL_ENTRY`** (each gate independently fails toward general); flipping route ON in-process → `first_person`.
  - **Serve-flag blast radius** — Qdrant `first_person_v7`: **177 points total, 177 `rights_cleared=true`, 0 un-cleared.**
- **Post-fix test suite:** `2 failed, 8467 passed, 12 skipped, 2 deselected, 1 xfailed in 412.71s` — every failure now either fixed or an owner decision below. `ruff check .` green. Golden-25 workflow thresholds PASS/PASS locally.
- **Mass ingest running** (host-side, independent of your decisions): `[47/511]` videos started at 21:03 IST, `host_leak=0` on every completed video, ~3 min/video, ETA ≈ 22 h. Resume truth: `~/mukthiguru_attribution_data/mass_ingest_2026-10/state.json`.

---

## Ask 1 — Q2 bridge flip (keep the main-chat first-person bridge OFF, or turn it ON)

- **Why:** the bridge lets the main chat answer from the first-person corpus. It was deliberately switched off until abstention was proven (audit D: it once answered "capital of France" as a teaching). The Q2 measurement package is now complete.
- **Evidence:** `~/mukthiguru_attribution_data/p0/phase2/answerability_{r4,r5,r5b}_2026-10-03.json`
  - R5b (decided basis): **leak 25.0% · true false-refusal 1.75% · verdict agreement vs R4 = 100%**
  - R4 healthy window: leak 26–30% · FR 2.6%; isolation chain separates provider-timeout inflation from real gate behavior (`L-GATE-LOAD-1/2`).
  - Gate verdicts pinned `temperature=0.0` — 15/15 row stability (`L-GATE-TEMP-1/2`).
- **Recommendation:** decide **after** the post-ingest harness re-baseline (agent Phase 1, runs automatically when ingest completes), so the numbers reflect the final ~2,500-clip corpus instead of today's 177-point index. The package above then gets one refreshed run attached, and the flip is a one-line env change (`FIRST_PERSON_CHAT_BRIDGE_ENABLED=true`) with the kill-switch still available.
- **After you decide:** agent attaches the refreshed run to this package; ON → bridge live behind the answerability gate; OFF → current serving position stays.

## Ask 2 — D6 legal sign-off (transcripts/embeddings rights basis)

- **Why:** nothing else ships publicly without a recorded rights basis; `cookies.txt` (294 KB, gitignored) must never be committed.
- **Evidence:** `CONTENT-RIGHTS.md` (R5/R6 audit items) — needs your written sign-off.
- **Recommendation:** review R5/R6, sign or annotate; keep the cookies-file exclusion as-is.
- **After you decide:** row 6 of the checklist closes; deploy is unblocked legally.

## Ask 3 — Approve the scoped session commit (currently held: **0 commits**)

- **Why:** "Hold all commits" has been active all session; every change above is uncommitted work in your working tree.
- **Evidence:** `git diff` (working tree) · `git diff --check` verified — exactly 2 findings, both other lanes' EOF blank lines that must drop **inside their own lanes' commits**: `backend/tests/test_speaker_diarization.py:172` (S1) and `backend/tests/test_verbatim_speaker_verify.py:214` (verbatim).
- **Recommendation:** one scoped commit once agent Phases 1–3 land (post-ingest gates + format debt), explicitly excluding S1/verbatim lane files.
- **After you decide:** agent stages exactly the approved paths, shows `git diff --cached --stat` for sign-off before `git commit`.

## Ask 4 — GitHub repo secrets (two gates are honest-skipping)

- **Why:** the golden-25 quality gate and nightly RLS check exist but skip without secrets — by design, never fake-pass.
- **Evidence:** `.github/workflows/golden25-gate.yml` (needs `QDRANT_URL`, `QDRANT_API_KEY`, `OPENROUTER_API_KEY`) · `.github/workflows/nightly-rls.yml` (RLS secrets + ephemeral-user cleanup confirmation, per Jul-31 checklist).
- **Recommendation:** set both secret sets from a clean env (`railway run … printenv` for read-only Qdrant) before the next deploy.
- **After you decide:** next workflow run shows real PASS/FAIL instead of honest-skip.

## Ask 5 — S1 conflict: `test_clips_v2::test_b_host_word_splits_run_and_is_never_included`

- **Why:** the only remaining suite failure besides D1 §6.5 bookkeeping; caused by S1's uncommitted `relabel_turn_start_prefixes` feature absorbing a genuine host word.
- **Evidence:** `.claude/tasks/audit_2026-09-29/d1_ci_true_suite_2026-10-03.md` §6.1 (full analysis: pre-existing vs my lint diff proven separate).
- **Recommendation:** let the S1 lane land its feature with an updated expectation — do not weaken the assertion outside the lane.
- **After you decide:** expected final suite residual = **zero failures**.

## Ask 6 — D1 §6.5: commit-or-drop untracked files

- **Why:** D1's run left a short list of untracked paths that must either join the scoped commit (Ask 3) or be removed.
- **Evidence:** same D1 report, §6.5 (the list + provenance for each file).
- **Recommendation:** default drop unless a file is referenced by a live test/config.
- **After you decide:** tree is clean against the approved commit scope.

## Ask 7 — Serve-flag value for production (`FIRST_PERSON_SERVE_UNREGISTERED`)

- **Why:** locally it is `true` (your local-eval decision, `.env:156`, flows into the container via `backend/docker-compose.yml:197`). Production must be `false` — the `.env:154` comment already mandates this for any real deployment.
- **Evidence (risk measured = 0 today):** Qdrant `first_person_v7` = **177/177 points `rights_cleared=true`, 0 un-cleared** (scroll with `must_not` filter, 2026-10-03). The prod audit is deploy-time only because Railway is paused.
- **Recommendation:** no local change (keep your eval setup); pin `FIRST_PERSON_SERVE_UNREGISTERED=false` explicitly in the Railway variables when unpaused — don't rely on the comment.
- **After you decide:** deploy checklist row 3 closes with a measured prod audit.

## Ask 8 — Railway: unpause + `FORWARDED_ALLOW_IPS` + cost headroom

- **Why:** three blockers compose — (a) service paused; (b) `start_railway.py` is fail-closed and exits without an explicit non-wildcard `FORWARDED_ALLOW_IPS`; (c) cost: workspace usage **$28.7854 of the $30 hard limit (94.1% memory)**, current estimate **$53.84** — unpausing as-is will hit the limit.
- **Evidence:** AGENTS.md cost section (memory ≈ 8.07 GB backend + 2.45 GB Neo4j = 94.1% of spend) · Security Invariants (`FORWARDED_ALLOW_IPS` gate) · deploy runbook: `railway up` (tarball), 1 replica, never `railway redeploy --from-source`.
- **Recommendation:** sequence = raise limit **or** cut backend/Neo4j memory first (memory is the cost driver; do not reduce worker concurrency without queue/SLA evidence) → set `FORWARDED_ALLOW_IPS=10.0.0.0/8` → unpause → `railway up`. Freshness check before any deploy: suite green on this tree + golden PASS + reconcile 0.
- **After you decide:** agent executes the deploy runbook only if you grant it in-session (Phase 5 of the next-session prompt); otherwise it is a hand-run checklist.

## Ask 9 — External backup of the audio archive

- **Why:** every ingested clip is rebuildable only while the local audio + manifest survive; git does not cover them.
- **Evidence:** checklist Q0 (archive + manifest with checksums, 515 targets pre-registered) · open decision 5.
- **Recommendation:** one disk/cloud destination you control; manifest verify is already exit-0.
- **After you decide:** backup script targets that destination; checklist Q0 gets its durability half.

---

## ✅ OWNER ANSWERS — 2026-10-03 (all 9 received; execution recorded here)

| # | Answer (owner wording) | Execution + evidence |
|---|---|---|
| 1 | FP = primary; "make sure we can switch off the LLM-generated things" | **Capability built**: `first_person_llm_fallback_enabled` (default `true` = today's byte-identical fall-through). `false` → a bridge decline returns an honest static abstain (zero generation) instead of falling into the generating graph; `crisis_redirect` (safety) and imperative-meditation requests always fall through. Declared on `Settings` with the design comment; knob documented in root `.env`; 12 new tests + `test_settings_guards` green. |
| 2 | D6: never commit transcripts/audios; local-only (GDrive later) | Verified: 0 tracked transcript files; the only tracked audio = intentional product asset `public/media/askmukthiguru-product-demo-instrumental.mp3`; `transcripts/`, `*.wav`, `cookies.txt`, `scripts/ingestion/corpus/` all gitignored; 1,396 ignored audio/transcript files stay out of every `git add`. |
| 3 | Commit all done work (scoped, long message, in lessons) | Executed after the final green suite — one session commit; scope = modified tracked (incl. 1,370 `memory/okf/*.md` = Sep-29/30 OKF rebuild, plan of record) + 57 untracked deliverables, nothing ignored. Hash recorded in `handoff.md` + session reply. |
| 4 | Check GitHub secrets; ask if needed ones missing | **⚠️ ACTION NEEDED FROM YOU**: repo has **0 secrets** (repo secrets and every environment empty). Needed for the two gated workflows — `golden25-gate.yml` (repo secrets): `QDRANT_URL`, `QDRANT_API_KEY` (read-only), `OPENROUTER_API_KEY`; `nightly-rls.yml` (staging environment): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`. Setup commands in session report §9. |
| 5 | S1 conflict: "check everything and fix this" | **Fixed at root cause**: `relabel_turn_start_prefixes` gains a host-exclusion gate — a sentence starting right after a terminal-punctuated TEACHER word is a completed turn, so an O-labelled word there is genuine host speech and is never absorbed (precision over recall; recovery after HOST terminal and transcript start stays open). `test_clips_v2::test_b` GREEN; +1 regression unit test; touched batteries 37 + 66 + 174 green. |
| 6 | D1 §6.5: ruthless dependency check, commit-or-drop | The 4 files (`scripts/ops/verify_ingest_readiness.py`, `scripts/ops/sync_latest_videos.py` + their 2 tests): referenced only by plans/docs (zero code coupling), 11 tests green, mlx `find_spec` guard already fixed → **all 4 COMMIT**. Wider sweep: 38 untracked `.py` = this branch's own feature files (pipeline registry, first-person bridge, quote_weaver, …) — all in the commit (a clean CI checkout imports them from tracked tests); no drops identified. |
| 7 | `FIRST_PERSON_SERVE_UNREGISTERED` = keep TRUE in prod | Value unchanged (`true`); root `.env` comment rewritten to record this decision superseding the 2026-09-25 "local eval only" note. |
| 8 | Railway: after everything local-prod-ready + greens + memory/cost optimization at very low cost | Gates unchanged and additive: Phase 1 post-ingest gates green → full suite green → memory/cost optimization landed → only then build. `FORWARDED_ALLOW_IPS` must still be set before any deploy; Railway stays paused until then. |
| 9 | Audio backup = local (GDrive later) | Q0 durability half = a local backup target now; GDrive wiring deferred and documented as follow-up. |

**Q2 also executed immediately:** `FIRST_PERSON_CHAT_BRIDGE_ENABLED=true` in root `.env` (bridge ON). The 2026-09-30 Audit-D OOC concern is gated by `first_person_answerability_check_enabled=true` (the P0 abstention fix; probes returned honest abstained/indeterminate). Container recreated onto the new env; **live proof**: chat answered with `route_decision=first_person_bridge`, a verbatim Preethaji TEDxKC clip + t-link citation, `verification.method=first_person_verbatim_clip_gate` (evidence: session report §9).

## Not blocked on you — agent queue (runs automatically)

1. **Phase 1, on ingest completion** (driver exits / state final): triage log (quarantines `asr_agreement<0.80` + 0-clip host-only videos are normal at apply time) → `reconcile_first_person_v7.py --dry-run` → must say 0 → ID audit → harness re-baseline → **golden-25 re-measure (top1 + same_video + same_clip) with values + provenance updated in all 3 files in one change** (`golden25-gate.yml` envs + header, `CLAUDE.md` CI line, checklist §D row 5).
2. **Phase 2 ✅ done** (this session): restart + health + probe battery above.
3. **Phase 3 ✅ done 2026-10-03 (scoped, no ingest wait needed):** backend format drift 129 → 21 (108 files formatted in two verified batches; remainder = exact 21-file lane-exclusion list — verbatim/S1/clips/`repair_v7_clips.py`/`test_sync_latest_videos.py`, formatted by their own lanes at their commits); 2 accidentally-swept HEAD-clean verbatim files reverted same turn; okf twin re-synced (`TWIN_OK` + 11 passed); `repair_v7_clips.py` allowlist entry **kept** (isolated I001 proof — removal waits for Wave 4a); post-format full suite **`1 failed, 8468 passed … 395.69s`** (only owner/S1 `test_clips_v2::test_b`), ruff check green, `git diff --check` still exactly the 2 other-lane EOF findings. Out-of-recorded-scope observation: 157 non-backend repo-root files drift (root ruff config lacks a `scripts/ingestion/**` exclude — required before any root-scope pass).
4. **Phase 4 ✅ done** (this file).
5. **Wave-5 quality tier** — deferred by design until after cutover; its log runs, nothing starts from it in parallel.

**Agent-held constraints after the answers:** never a second ingest driver while PID 82134 lives · `.env` edits limited to the owner-authorized lines (Q2 bridge flip + Ask-7 comment; values of everything else untouched) · Ask 5/6 granted the S1/verbatim + untracked-file edits named above (nothing else in those lanes) · validation and harness share one 20 RPM limiter (never concurrent) · latency canary before LLM-burst work (timeouts <5%, p50 ≤ ~1660 ms) · commits granted for this session's scoped work · Railway untouched until Ask 8's conditions are all met.

# Handoff: AskMukthiGuru, state at 2026-11-12 (supersedes the 2026-11-07 state below)

## 00. UPDATE 2026-11-12: read this before everything else

**Verdict: NO-GO, unchanged.** The sections below were written on 2026-11-07 and are stale in places. Where this block and a later section disagree, this block wins. VERIFIED here means I read it in git on `origin/feature/audit-strengthen-rag-qdrant` (branch head moved while I worked; PR #97 head was `9796159` per the GitHub API at 04:55Z) on 2026-11-12.

### What changed since my last commit (`45cb2e3`)
- The branch has 96 newer commits (about 86 by Harsha, 6 by Claude sessions, 4 by the Lovable bot). PR #97 is open. PR #98 (my thread branch) is closed, not merged. Nothing from this branch is on `main`.
- Graded runs HAVE now been run. The 2026-11-07 text "no graded run exists" is out of date. None of them passes the bar. See the table.
- Harsha's human listen verdicts are in the repo: `audits/evidence/HUMAN_REVIEW_ANALYSIS_2026-11-07.md` and `human_review_results.json`. 11 demoted clips: 9 teacher, 2 devotee voices. 50 served clips: 48 teacher, 2 devotee voices. The four devotee points must be quarantined. The doc gives the command; I did not find proof it was applied (UNPROVEN).
- Many feature and safety commits landed (UX-011 remaining-turns counter, memory export and purge, OKF wikilink traversal, emotional-dependency guard, Phase B/C/D serving fixes, lessons.md archive split). I did not review them line by line.

### Graded runs on the branch (VERIFIED from the report files)
| Run | Mode | Result vs the bar |
|---|---|---|
| `20261107-graded-clean-v8` (`GRADED_RUN_20261107_V8_REPORT.json`) | graded 18 answers | served 17/89 = 19.1%, below the 30% bar. The file says `audit_status: VERIFIED` and `post_remediation_harmful_count: 0`. The zero is a code-fix claim for `ua46`, not a re-run. Treat as UNPROVEN. |
| `20261108-graded-clean-v1` | two Haiku 5.5 graders, valid | showable 28/48 = 58.3% (bar 85%), harmful 3 (bar 0), served 36.7%, p95 7.8 s, core abstain 100%. FAIL. |
| `20261109-unified-all-sets-v1` | **`offline_fallback` heuristic graders, not an LLM and not a human** | `status: FAIL`. showable 92.8% of 111 graded (bar 95%), served share 26.1% (bar 45%), p95 8.9 s, harmful 0, core abstain 100% (69/69). One served answer had an unverified speaker. The showable figure comes from keyword heuristics, so it proves nothing about quality. |

### Update 2026-11-12 05:10Z: Harsha's answers and what I did
- **Calibration:** Harsha says he labelled the 300 items himself (REPORTED). The label sheets are not in the repo and the gold report still says human rating is pending. Recorded in `docs/evidence/CALIBRATION_PROVENANCE_2026-11-12.md`. Still UNPROVEN.
- **Graded compose:** I removed the `FIRST_PERSON_UNCALIBRATED_DIRECT_ENABLED` pin (Settings default false applies), set `FIRST_PERSON_RELEVANCE_MIN_SCORE` back to 3 (base compose and invariant 24), and removed the `FIRST_PERSON_REQUIRE_VOICE_METHOD` pin (Settings default is false, so behaviour is the same, but it is no longer a hidden workaround; the H2 gate in the grader still fails the run if a bare-flag speaker is served). Capability flags (HyDE, graph expansion, enrichment window, teaching-unit graph, judge, facet split, compound direct) are still pinned on; their Settings defaults are off. The Railway thread must set the same flags in prod, or the graded run does not describe prod.
- **Commit `6a11c64` still exists:** the harness serves legacy centroid-verified spans when `require_voice_method` is false. I did not revert it. Harsha's call.
- **CI:** Decision: no PR triggers restored (Harsha does not want to pay for GitHub). Do not require `release-invariants`. Run the guards locally: `python3 scripts/guards/lesson_guards.py claims` and `publication`, plus the backend tests on the Mac.
- **Pass bar:** see the chat reply; the 85/30 figures are the ones with a quoted approval (2026-10-31).
- **Graders:** do not use Opus 5.5 on OpenRouter (cost). The script default is `anthropic/claude-haiku-5.5` for stage 1. Pass a cheaper-than-Opus second model explicitly, and it must differ from the first and from the product scorer.

### Things I found that you must not trust or must fix (ruthless list)
1. **The pass bar was changed after the runs began.** `evals/first_person/grading_pass_bar.json` now says showable >= 0.95 and served share >= 0.45 ("elevated", approved_on 2026-11-09). The approval evidence is "Harsha's direction", not a quoted message. The bar is stricter than before, so this is not a loosening. But the register of record still says 85% and 30%. Ask Harsha to confirm the numbers in one line.
2. **The calibration profile is not trustworthy.** `config/first_person_calibration.json` (and the `backend/config` copy) was rewritten in commit `ebff4b5` (2026-11-10). It now claims `conformal_direct_v1`, n=300, precision 0.992, UCB risk 0.008, "held-out gold set". The commit message does not mention it. The only gold report in the repo (`audits/evidence/public_release_gold_label_report_2026-10-22.json`) says `independent_review: false`, method `curated_consensus_alignment`, and "external double-blind human rating remains pending". CLAUDE.md invariant 3 says never fit on AI-authored labels and needs >=299 human items. Treat the profile as UNPROVEN and possibly invalid until Harsha says who labelled the 300 items. Do not quote 0.992.
3. **`FIRST_PERSON_UNCALIBRATED_DIRECT_ENABLED` is set to `true` in `backend/docker-compose.graded.yml`.** The code default is `False`, with a comment that on 2026-10-05 this served direct answers on an uncalibrated threshold. The graded runs therefore measure a looser configuration than the safe default.
4. **The relevance minimum is 2, not 3** (CLAUDE.md invariant 24 says 3). HyDE, graph expansion, weak-match serving, compound direct serving and the judge are all on in the graded override. A pass on this config does not prove the default config.
5. **Voice-method gate loosened.** Commit `6a11c64` lets the context harness accept legacy centroid-verified spans when `require_voice_method` is false, and the graded runs pin `FIRST_PERSON_REQUIRE_VOICE_METHOD=false`. Harsha's earlier decision was not to use that flag as a workaround. Unresolved decision H2.
6. **CI cannot gate the PR.** Commit `fcfde77` (2026-11-07) removed the `push` and `pull_request` triggers from 14 workflows, including `lint-test.yml` (it now has only `workflow_dispatch`). `lovable-pr-guard.yml` kept its `pull_request` trigger. So `release-invariants` will never report on a PR, and making it a required check would block every merge forever. Either restore the triggers or do not require it. The earlier "30 of 32 checks fail in seconds" is probably explained by this, but I did not confirm it (UNPROVEN).
7. **Latest Stage A style gaps are not closed.** Safety route, heal, psychiatric and addiction gaps: some commits touch them (`ebff4b5` adds promise-trap and sleeping-pills patterns; `safety_kernel.py`). No run since then re-measured them with a real grader.
8. **Run spend:** the unified run moved the daily spend from about USD 7.8 to 22.2 and the month from 75.7 to 90.1 (report file). The local cap is USD 100/day and 300/month. Check the month figure before another run.
9. Report headers in these JSON files say "VERIFIED" and "pass" in places where the underlying grading was offline or post-hoc. Per the claims guard, nothing here may be called ready, green or GO.

### What Harsha still has to do (only he can)
1. Copy the Qdrant snapshot off the Mac, and move the `/tmp` rollback backups into the repo's gitignored folder (one holds quote text).
2. Set the provider spend limit and the Railway usage limit with alerts.
3. Decide CI: restore PR triggers, or drop the required check. Then set required checks (`lovable-guard`, and `release-invariants` only if it runs).
4. Say who labelled the 300 calibration items, and whether the 0.95 / 0.45 bar is what he wants.
5. Decide H2 (voice-method flag).
6. Confirm the four devotee points were quarantined (or run the command in the analysis doc).
7. Add the Telugu crisis row to the test sheet.
8. Run ONE real graded clean-Docker run on the final head with the LLM graders on (not `offline_fallback`) and a valid OpenRouter key. Harsha runs the commands. A run is INVALID if the log shows "spend limit" or "indeterminate".
9. Rotate keys only after that run is graded.

### Checks you can run
- `git log --oneline 45cb2e3..origin/feature/audit-strengthen-rag-qdrant | wc -l` (expect 96 or more).
- `python3 -c "import json;d=json.load(open('audits/evidence/UNIFIED_GRADED_RUN_20261109_REPORT.json'));print(d['grading']['status'],d['grading']['evaluation_mode'])"` (expect FAIL, offline_fallback).
- `git show origin/feature/audit-strengthen-rag-qdrant:.github/workflows/lint-test.yml | sed -n 8,12p` (expect only `workflow_dispatch`).
- `git log -S conformal_direct_v1 --oneline` (expect `ebff4b5` only).

---

## (Older block) Handoff: AskMukthiGuru, state at 2026-11-07

Written for the next agent and for Harsha. Verdict: **NO-GO** (unchanged). No graded clean-Docker run on the final branch exists yet.
The previous handoff (2026-10-19) is in git history: `git log --follow -- handoff.md`.
Ready-to-paste agent prompts are in `docs/handoffs/AGENT_PROMPTS_2026-11-07.md`. Note: the repo-root `handoff.md` was replaced by another agent on 2026-11-08; this file is the Claude handoff.

Labels used here:
- **VERIFIED** = I read it in git, in a file, or from the GitHub API during this session (2026-11-07).
- **REPORTED** = taken from a thread report or the Pending List artifact. I did not re-check it.
- **ASSUMPTION** = my inference. Check it before you rely on it.
- **UNKNOWN** = I could not find the answer.
- **UNPROVEN** = no run has shown it.

---

## 0. Read this first: four things most people on this project have wrong

1. **PR #86 is already merged.** It merged into `main` on 2026-11-03 (VERIFIED: GitHub API, `merged: true`, 165 commits, 1,034 files). Threads and the Pending List still say "the one open PR is #86". The open PR is now **#97** (head `feature/audit-strengthen-rag-qdrant`, base `main`, title starts "docs(audits): architecture and product audit of main@46b808fb"). So "nothing is merged to main" is false. What is true: the work after 2026-11-03 (188 commits) is not on `main`.
2. **`main` has 4 commits the branch does not have** (VERIFIED: `git rev-list --count origin/feature/audit-strengthen-rag-qdrant..origin/main` = 4; they touch 2 files: `roadmap.md` and one renamed `.md`). Merge or rebase them before the final merge.
3. **CI on the branch head shows 30 failures out of 32 check runs, all within 2 to 8 seconds** (VERIFIED: PR #97 check runs at head `5e23438`; only `Vercel Preview Comments` passed, `Supabase Preview` was skipped). The register says the same happened on 2026-11-05. Jobs that fail in seconds usually did not run your code. The cause is UNKNOWN. Nobody has read a job log. Do this before you trust any green or red.
4. **The required check name for the Lovable guard is `lovable-guard`, not `lovable-pr-guard`.** `lovable-pr-guard` is the workflow name. The job is named `lovable-guard` (VERIFIED: `.github/workflows/lovable-pr-guard.yml` line 14, and the check-run list). GitHub required checks match the job (check-run) name. If Harsha types `lovable-pr-guard`, the check never reports and every PR waits forever. `release-invariants` is correct (job `release-invariants` in `lint-test.yml`).

---

## 0b. Latest state, updated 2026-11-07 01:15Z (read this before sections 4 and 5)

Sources: the register block "Live `first_person_v10` data fix 2026-11-07" in `FINAL_PENDING_WORK_REGISTER.md` (commit `0f56866`; VERIFIED that I read it), plus coordinator relays (REPORTED). I did not see the Mac output.

| Item | State |
|---|---|
| Live audit of `first_person_v10` | **No failed check** after the fixes (REPORTED by the register: C-L1, C-L2, C-L3, C-L5, C-L6, C-L7, C-L8 pass; before: C-L3, C-L5, C-L7, C-L8 failed). Harsha ran the writes in a Mac terminal. |
| 16 payload indexes | Created with `ensure_fp_span_indexes.py --apply`. `missing_after` empty. Points: 4,226 throughout. |
| `domain_rights_status` | `backfill_fp_rights_status.py --apply` stamped `licensed` on **2,758 children across 491 videos**, 0 left over. The value comes from the serving rights resolver, not from hand. |
| Serving filter | Passes **2,738 of 2,760** after the stamp. Before the stamp it passed **2** (register: "2 to 2738"). 22 children lack `speaker_verified`. |
| The 2 hashless points | `fix_fp_unhashed_points.py --apply` added `source_text_hash` and moved them to new ids `877f7269-9e7c-5b77-94fd-531119c5f0b6` and `20b32148-06fa-5641-af61-73f44c1e9465` (old ids began `3eb5cc1a` and `52c880a0`). Quote text and `transcript_hash` unchanged. They look like **test data**, not teaching. |
| **Quarantine of those 2 points** | **Approved by Harsha ("quarantine", relay 01:15Z). The script is now on the branch: `scripts/ops/quarantine_fp_points.py` (`6a0d61f`, VERIFIED that I read its header). It sets two payload keys, `quality_status="quarantined"` and `quarantine_reason`, with `set_payload`. It is reversible (`--release` deletes both keys), dry run unless `--apply`, and it changes no vector, text, hash or id. Serving refuses a point with either key (`first_person_context_store._span_is_quarantined`, VERIFIED in code). It has NOT been run live as far as I know: UNPROVEN until a live audit shows the 2 points are refused.** It is a flag, not a delete, so the earlier delete worry no longer applies. |
| Snapshot and backups | Snapshot `first_person_v10-1111874297854021-2026-11-07-01-09-45.snapshot` taken first. Backups sit in `/tmp` on the Mac (for example `/tmp/rights_backup_v10.json`). **One backup holds quote text.** Keep it local. Never commit it. `/tmp` can be cleared by a reboot, so move the backups to a safe local folder and copy the snapshot off the Mac (Harsha's step 1). |
| Pending List artifact | Version 53 (REPORTED by the coordinator; I did not open it). |
| Load-run harness | **No spend stop.** Harsha removed the cap (`647ef2c`). The provider spend limit and the Railway usage limit are the only backstop, and Harsha has not yet confirmed setting them. |
| Serving verdict | Serving is **UNPROVEN** until the graded clean-Docker run. Verdict **NO-GO**. |

What this changes, in plain words:
1. **Stage A (2026-10-31) predates this data.** The serving filter used to pass 2 spans, and now passes 2,738. ASSUMPTION: the Stage A rows came from a build or filter that did not apply the rights gate the same way. UNKNOWN how. Treat Stage A as history, not as a forecast. The next graded run is the first one on the shipped data.
2. **Before the graded run, check that `backend/.env` sets `FIRST_PERSON_COLLECTION` and `FIRST_PERSON_CONTEXT_COLLECTION` to `first_person_v10`.** Memory notes say `backend/.env` once pointed at v11 and the backend ran v8. The graded compose pins `FIRST_PERSON_ACTIVE_COLLECTION: first_person_v10`, but the preflight diffs only the pinned flags, so a stray value elsewhere can still matter. Print only the two variable names and values (no keys): `grep -n "FIRST_PERSON_.*COLLECTION" backend/.env`.
3. **A gap in the audit:** the C-L11 digest does not cover `domain_rights_status` (register). A later edit to that key would not trip the digest. Sonnet lane: extend it, test first.
4. **The speaker-verification gate decision (H2) is still open.** See section 8, item 2.
5. The PR #86 merged / #97 open facts, the 30-of-32 CI failures, and the `lovable-guard` name are unchanged (section 0).

---

### Update 05:25Z (Harsha's terminal output, git history, relays)

| Item | State |
|---|---|
| Branch head before this commit | `c42ab14` ("OPS: pin `FIRST_PERSON_CONTEXT_TERMINAL_ENABLED` in the compose environment block so the root `.env` cannot split the v10-only flags"), VERIFIED in `git log`. Last Opus-lane commits are the 2026-11-07 decision commits `c662ae0`, `43bdf7a`, `bb8285a`, `29253c8`, `1723b16` (01:02 to 01:08). Nothing newer from Opus. |
| Root `.env` edit by Harsha | He set `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=true` and `FIRST_PERSON_CONTEXT_TERMINAL_ENABLED=true` with `sed`, after `cp .env .env.bak_pre_v10only_20261107`. His `docker compose config` output afterwards (VERIFIED, pasted): `FIRST_PERSON_ACTIVE_COLLECTION: first_person_v10`, `FIRST_PERSON_COLLECTION: ""`, `FIRST_PERSON_CONTEXT_COLLECTION: first_person_v10`, harness `"true"`, terminal `"true"`. Before the edit, terminal was `"false"`. |
| Is the empty `FIRST_PERSON_COLLECTION: ""` a problem? | **No, it is correct.** VERIFIED in `backend/app/config.py` (`resolve_first_person_active_collection`): an empty slot is filled from the active name when harness is on and terminal is exactly `True`; otherwise the legacy slot falls back to the v8 clip store. That is why the old `"false"` terminal value was dangerous: it would have put the legacy slot on v8. Commit `c42ab14` now pins terminal in the compose file so the root `.env` cannot split the flags again. |
| `.env` backups | `.env.bak_pre_v10only_20261107` is ignored (VERIFIED with `git check-ignore`; the pattern is `.env.*`). It holds secrets. Keep it out of git and out of chat. |
| `.gitignore` | Extended in this commit with patterns for rollback files (`rights_backup*.json`, `fp_*backup*.json`, `*_v10_backup*.json`, `quarantine_backup*.json`, `*.bak_*`, `.env.bak*`, `*.snapshot`). The folder `.work/` was already ignored. A new test, `backend/tests/test_gitignore_backups.py`, pins this (9 tests pass in the cloud). `git ls-files` shows none of today's rollback files tracked (VERIFIED). **Not new, not mine:** 9 older files named `*backup*.json` under `data/` are tracked (Neo4j and Qdrant backups from 2026-09). I did not touch them; whether they should be purged belongs to the public-repo decision D-01 (register rows X-06, IP-001). |
| Where Harsha puts the `/tmp` backups | I cannot reach the Mac's `/tmp` from the cloud. Run this in a Mac terminal (check the names first; I know only `rights_backup_v10.json`): `cd ~/Public/askmukthiguru-8119b0e8 && mkdir -p .work/backups_2026-11-07 && chmod 700 .work/backups_2026-11-07 && ls -la /tmp \| grep -i -E "backup\|rollback"`, then `mv /tmp/<file> .work/backups_2026-11-07/` for each, `chmod 600` on the one with quote text, then `git status --short` (nothing new) and `git check-ignore -v .work/backups_2026-11-07/rights_backup_v10.json` (prints a rule). **Caution:** on macOS the `~/Public` folder can be readable by other accounts on the machine. `chmod 700` on the folder limits that. A repo-folder copy is still not an off-Mac copy. |
| Stage A and the rights gate (Harsha asked me to check) | **VERIFIED:** the check `domain_rights_status == "licensed"` entered `first_person_context_store.py` in commit `9e17370` on **2026-11-04** (`git log -S`). Stage A ran on 2026-10-31. So Stage A ran **before** the rights gate existed. With the gate and no stamp on the data, the filter passed 2 of 2,760 children; after the 2026-11-07 stamp it passes 2,738. Stage A's 33 served clips therefore came from code without the gate. Conclusion: Stage A is not a forecast of the next run. The graded run must be the first measure on the shipped code and data. |
| CI | 30 of 32 checks failed in seconds on the head I read (cause UNKNOWN). Relayed 05:21Z: Harsha removes the CodeQL checks, and the real name of the Lovable check is `lovable-guard`. Required checks to set: `release-invariants`, `lovable-guard`. Whether CI has run again since: UNKNOWN. |

### What still blocks a merge to `main` (plain list)
1. **The graded clean-Docker run on the final head has not happened or been graded.** Verdict stays NO-GO until it is.
2. **Hard gate H2** (zero unverified-speaker clips) versus the pinned `FIRST_PERSON_REQUIRE_VOICE_METHOD=false`: Harsha has not decided.
3. **CI cause unknown.** Read one failed job. Set the two required checks only after that.
4. **`main` has 4 commits the branch lacks.** Merge or rebase them first.
5. **Quarantine of the 2 moved test-looking points** is approved, but not yet applied and audited (`quarantine_fp_points.py`, reversible).
6. **Stage A safety gaps** (health gate, support-line trigger, grader rubric): no closing commit found. UNKNOWN.
7. **Human steps:** copy the Qdrant snapshot off the Mac; set the provider spend limit and the Railway usage limit; listen to the 11 demoted clips; add the Telugu crisis row (native speaker); label 50 served clips.
8. **Keys are rotated only after the graded run is graded.**
9. **Not blockers today:** the deferred pre-public items (clinician sign-off, rights message, helpline call dates) and the rights register. Do not raise them.

---

## 1. The goal

Make AskMukthiGuru the best product for disciples and seekers of Sri Preethaji and Sri Krishnaji. A person asks, and gets the apt teaching, in the teacher's own words, fast, with a source. Then onboard the Sri Amma Bhagavan teachings end to end.

The working target for this phase (Harsha, restated 2026-10-30 and 2026-10-31):
1. Finish the production pending lists.
2. Run a clean-sweep on **local Docker** (caches flushed and proven empty).
3. Grade the run against the approved pass bar.
4. Merge everything to `main` through one PR.
5. Only then deploy to Railway, in a normal session that has the Railway connector.

Approved pass bar (REPORTED, `research/final-pass-bar-2026-10-30.md` and the memory index): p95 latency 10 s; served precision 85% or more; served share 30% or more; abstain 95% or more on 60+ unanswerable items; hard gates at 100%; no regression; signed go/no-go page; kill switch and halt plan; live monitoring.

**Honest note on "10/10 confidence".** The data does not support that phrase. The only valid measured run (Stage A) gave 48.5% showable precision. Plan for a measured, signed result. Do not plan for a score.

---

## 2. Current state of the code

### Git (VERIFIED, 2026-11-07)
| Item | Value |
|---|---|
| Work branch | `feature/audit-strengthen-rag-qdrant` |
| Head when I read it | `5e23438` ("NEW-DQ-1: add ensure_fp_span_indexes.py ... record 2026-11-07 decisions") |
| Previous heads | `b119aa9` (Railway decisions), `e67577d` (audit report diagnostics), `815fd17` (tsc fix), `ebe5ceb` (ruff format fix), `dea7b44` (D-PG13 wording) |
| Merge base with `main` | `46b808f` ("Merge branch 'feature/audit-strengthen-rag-qdrant'") |
| Ahead of `main` | 188 commits, 520 files, +54,495 / -2,724 |
| Behind `main` | 4 commits (docs only, 2 files) |
| Open PR | #97 (this branch into `main`). Not merged. |
| Merged PRs on this line | #86 (2026-11-03). Earlier: #68, #72, #82, #83, #89 and others (REPORTED). |
| Branch protection on `main` | None (register row X-02, status "Needs owner decision"). REPORTED. |

### Tests (REPORTED, none re-run by me)
- Cloud container, fakes only, at `024a881`: 13,031 passed, 1 failed, 58 skipped, 1 collection error (`soundfile` missing). The 1 failure was the 12 s versus 25 s scorer-timeout conflict. It was fixed later by the D-PG13 decision (section 4.5). The full suite was **not** re-run after that fix. UNPROVEN.
- **Mac run on `32c12c4`** (Remote Control, read-only worktree, 2026-11-07; REPORTED in register section 11.3): backend 13,215 passed, 45 skipped, 2 failed (two builder tests broken by `f87c0de`; fixed in the Opus lane, cloud-proven only); guards exit 0 (exception ratchet 724/724); `ruff check` 0; `ruff format` flagged 1 file (fixed); safety scenarios 226 pass, 4 expected, 0 fail; distress recall 106/110 with 0/49 false positives. Not run: Docker, live LLM, e2e.
- Mac check at `dea7b44`, read-only, no Docker: 126 backend tests pass (17 files); four guards exit 0 (exception ratchet 724/9, seeker-text log budget 0, teacher-literal ratchet 590 lines in 129 files, stage-order guard); `ruff check` 0; vitest 1,139 passed; `helm template` renders with `redis.auth.password` and `neo4j.auth.password`.
- Found by that Mac check, then fixed on the branch: `ruff format` on `test_openrouter_price_table.py` (`ebe5ceb`), 2 `tsc` errors (`815fd17`). These two fixes are proven only by cloud runs. Re-verify on the Mac.
- Not run anywhere: `promtool check rules`, Playwright `a11y-journey.spec.ts` (needs the app and Supabase), real GitHub workflow results (see section 0, item 3), the Mac Remote Control run on 2026-11-06 (the Mac did not pick up the session).

### Serving posture (VERIFIED in files)
- v10-only: `first_person_v10`, context harness on, terminal on (`backend/docker-compose.graded.yml`; `.railway/railway.ts` `SERVING_POSTURE = "v10_only"`).
- No LLM writes answer text. A served answer is a verbatim clip or a static abstain (`CLAUDE.md` invariants 1, 15, 21).
- Graded run pins the scorer timeout at **12 s** (`FIRST_PERSON_RELEVANCE_TIMEOUT_S: "12"`, line 31). The `Settings` default stays 25 s everywhere else.
- `v10` holds 4,224 points (REPORTED). Child spans: 2,758 expected; the live audit counted 2,760 (section 4.4).
- Default-off features, each waiting on a decision or a measurement: evidence judge (`3e2882f`), injection-screen drop mode (`aba9bf4`, `c609c6f`), served-clip hash re-check `first_person_points_servable_hash_check_enabled` (`087af0a`, default `False`).

### Artifacts and reports
- Pending List (runbook artifact): https://claude.ai/artifact/PtxfGz9iintSkmGsPNGFg9 (version 52 when I read it). Every thread must publish a new version when done/unproven/needed changes.
- Register: `audits/audit-output-2026-11-04/FINAL_PENDING_WORK_REGISTER.md` (sections 11 and "Implementation update 2026-11-07", and "Decisions recorded 2026-11-07").
- Opus report: `/mnt/project-files/opus-audit-2026-11-06/final-report.md`.
- Sonnet report: `/mnt/project-files/reports/sonnet-platform-thread-final-report-2026-11-07.md`.
- Sonnet prompt for the ops lane: `/mnt/project-files/prompts/agent-prompt-railway-and-ops-2026-11-07.md`.
- Path to the graded run: `/mnt/project-files/path-to-graded-run-2026-10-31.md`. Stage A/B review: `/mnt/project-files/stage-ab-evidence-review-2026-10-31.md`. Kill-switch runbook: `/mnt/project-files/runbooks/go-no-go-kill-switch-monitoring-2026-10-31.md`. Railway runbook: `/mnt/project-files/runbooks/railway-readiness-2026-10-30.md`.

---

## 3. Files in play, and who owns them

The rule since 2026-11-06: one owner per file. A thread that needs a change in the other lane's file sends a note to the coordinator. It does not edit.

### Opus lane (safety, honesty, data integrity, review)
- `backend/services/first_person_*.py` (pipeline, store, context store, harness, judge, bridge helpers)
- `backend/rag/nodes/first_person.py`, `backend/rag/states.py`, `backend/rag/nodes/generation.py`, `backend/app/pipeline/stages/graph_stage.py`, `backend/app/pipeline/stages/first_person_bridge.py`
- `backend/app/answer_outcome.py`, `backend/app/answer_contract.py`
- `backend/services/serene_mind_engine.py`, `backend/services/crisis_helplines.py`, `config/helplines.yaml`
- Memory and persona code (`MEM-*`), `backend/app/api/teachings.py`
- Corpus builders and speaker provenance: `backend/scripts/ops/build_*`, `backfill_v10_voice_method.py`, `domain/speaker_provenance.py`, `domain/speaker_audit.py` (root copies in `scripts/ops/` must stay byte-identical)
- Safety and release-gate tests that pin the above

### Sonnet lane (Railway, ops, config, accessibility, guards, docs)
- `.railway/railway.ts`, `Dockerfile*`, `docker-compose*.yml` (except the serving flags pinned in `backend/docker-compose.graded.yml`, which change only on Harsha's word), `infrastructure/**`, `scripts/deploy/**`
- `scripts/guards/**` and their baselines (`exception_baseline.txt`, `guru_literal_baseline.txt`, `import_layer_allowlist.txt`)
- `scripts/ops/fp_live_audit.py`, `scripts/ops/ensure_fp_span_indexes.py`, `backend/benchmarks/locustfile_fp_staging.py`, `scripts/ops/load_run_report.py`
- Frontend accessibility (`src/**`), `docs/product/COPY_DRAFTS_*`, Lovable guards (`.github/workflows/lovable-pr-guard.yml`, `CODEOWNERS`)
- Docs outside the Opus list, and `backend/CLAUDE.md` / `src/CLAUDE.md`

### Shared and tricky
- `lessons.md`: many threads write to it. Append only. Rebase before you push.
- The teacher-literal ratchet (`guru_literal_baseline.txt`) counts lines in Opus files too. If Opus removes a literal, `test_guru_literal_scan.py` fails until the baseline is lowered with `python3 scripts/guards/guru_literal_guard.py --write-baseline`. Expected, by design.
- `backend/docker-compose.graded.yml` and `backend/tests/test_graded_run_preflight.py` are a pair. Change both or neither.
- This thread (handoff) edits only `handoff.md` and `docs/handoffs/AGENT_PROMPTS_2026-11-07.md`.

---

## 4. Everything tried, with results

### 4.1 Graded run, Stage A (2026-10-31). The only valid stage.
VERIFIED from the stage review (`stage-ab-evidence-review-2026-10-31.md`; I read the review, not the raw rows).

| Measure | Result | Bar | Pass? |
|---|---|---|---|
| Served (frozen 116) | 33 (32 answerable + q115, which is flagged unanswerable) | n/a | n/a |
| Served share of 89 answerable | 32/89 = 36.0% (Wilson 26.8 to 46.3%) | 30% or more | Point passes. Lower bound does not. |
| Showable of served | 16/33 = 48.5% (Wilson 32.5 to 64.8%) | 85% or more | **FAIL** |
| Harmful clips | 3 (q019, q057, q071) | 0 | **FAIL** |
| Unverified speaker among served | 13/33 (39%) | 0 (hard gate H2) | **FAIL** |
| Latency p95, frozen 116 | 12.5 s (served only: 16.0 s) | 10 s | **FAIL** |
| Unanswerable core | 68/69 abstain (ua06 was served) | 95% or more | Pass, but easy set |
| Frozen unanswerable | 26/27 (q115 served) | n/a | n/a |
| Safety route | 1 of 4 (ua70, ua71 gave no support line; scorer failed ua72) | 100% | **FAIL** |
| Generated text | ua66 and q112 reached the general model and produced prose | 0 | **FAIL** |

Other defects in Stage A as a measurement:
- No backend log was saved. Errors, timeouts, spend state and cache hits are UNPROVEN.
- The grader is weak: Haiku grades Haiku-family output; only 2 of 10 Haiku positives were re-checked by Opus; q057 is graded "showable" and "harmful" at once; no human labels exist.
- The 116 questions are a **tuning set** (Harsha confirmed). Their numbers do not show generalisation.

### 4.2 Graded run, Stages B and C. VOID.
- The local OpenRouter budget cap ran out at request 61 of 202 in Stage B (first "spend limit reached" at 06:47:34Z). 142 of 202 rows ran with the LLM blocked. Their abstains came from the gate failing closed. Stage C (128 of 128 abstains in 1.2 to 1.4 s) ran on the same UTC day and is also void.
- Cause (VERIFIED in the review): the local Redis guard, code defaults $10 a day, $40 a month. The flush script does not reset the budget key.
- Fix applied: `backend/docker-compose.graded.yml` sets local caps $100 a day, $300 a month, guard on, fail closed. `graded_run_preflight.py` checks headroom and the log. `graded_capture.py` marks a run INVALID if the log has "spend limit" or "indeterminate". Production caps stay on (REPORTED: 3x margin, alert at 70%).
- No valid Stage B or C result exists. The effect of the Stage A fixes is UNPROVEN.

### 4.3 v11 (`first_person_v11`). Parked.
- Built from the 74 buildable videos: only **9 videos** passed the speaker floors (140 spans + 9 parents; 41 new verified spans). 59 videos were skipped (processed or guided-meditation audio scores near 0 against both teachers). 6 had no valid spans. Final v11: 4,358 points (REPORTED).
- Gate results: V1 to V6, V8, V9 pass; **V7 (blind listen) not done**; V10 partial.
- **Incident:** an unidentified writer (host client, qdrant-client 1.19.1) edited the first v11 on 2026-10-31 at 13:03Z and 13:39 to 13:41Z. It re-set `speaker_verified=true` on 17 spans that had been demoted. v11 was dropped and rebuilt. The writer is still UNKNOWN.
- Decision 2026-11-01 (Harsha): the graded run uses v10 now. v11 is a later add-on.

### 4.4 Mac live-data audit of `first_person_v10` (read-only, at `dea7b44`). Four checks failed. FIXED LIVE 2026-11-07; see section 0b.
REPORTED by the Mac session; the audit script is `scripts/ops/fp_live_audit.py`.

| Check | Result | Cause | Next |
|---|---|---|---|
| C-L3 | 2 of 2,760 children: hash mismatch | UNKNOWN. ASSUMPTION: the 2 may be records without `record_type` (2,760 counted, 2,758 expected). | Re-run the audit at head (it now lists up to 20 point ids, rights-status counts and record types, `e67577d`). No payload text in any report. |
| C-L5 | 2 point ids do not recompute | UNKNOWN. ASSUMPTION: possibly the same 2 records. | Same run. Compare the two id sets. |
| C-L7 | 2,758 of 2,760 not `licensed` | UNKNOWN. ASSUMPTION: the builder no longer writes a literal "cleared" (`f87c0de`) and the graded run pins `FIRST_PERSON_SERVE_UNREGISTERED=true`, so the audit may expect a value the data was never meant to hold. | Report the values and counts. Check what the serve gate accepts. If the gate accepts the values in use, fix the audit's expectation with a test. Do not change data. Do not reopen the rights register. |
| C-L8 | 16 payload indexes missing: `answer_role, boundary_status, category, completeness_status, corpus_version, domain_rights_status, end_ms, entity_ids, facet_ids, is_verbatim, provenance_kind, speaker_id, speaker_role, start_ms, tags, topic_ids` | The collection was built without them. | `scripts/ops/ensure_fp_span_indexes.py` (`5e23438`) creates them from `SPAN_INDEXES` in `first_person_context_store.py`. **Update 2026-11-07 (coordinator relay): the live creation is done (16 indexes; the collection now reports 4,226 points).** I did not see the run output. Re-run `fp_live_audit.py` to confirm C-L8 now passes. REPORTED, not re-checked. |

**New fact to chase:** the point count is now **4,226**. The 2026-10-31 backfill post-checks recorded 4,224 ids (REPORTED). Two more points exist. ASSUMPTION: they are the 2 "extra" records behind 2,760 counted versus 2,758 expected children, and they may be the same 2 points behind C-L3 and C-L5. Nobody has said who or what added them, or when. Find out from the Qdrant log and the audit's point-id list before you edit any point.

**DONE on 2026-11-07 (section 0b); kept here as the record of the conditions.** Approved by Harsha (2026-11-07, relay): data fixes on live v10 for (a) the 2 bad points (C-L3, C-L5) and (b) `domain_rights_status` on the 2,758 children.** Conditions:
1. Take a Qdrant snapshot first, and confirm its name and age (the backfill tool already refuses a snapshot older than 2 h; reuse that check).
2. **No edit to quote text. No edit to `transcript_hash` or `source_text_hash`.** (`CLAUDE.md`: teacher quotes are verbatim; a text change must update both hashes in one transaction, so the only safe text change is none.)
3. For (b): **the script now exists:** `scripts/ops/backfill_fp_rights_status.py` (added in `647ef2c` by the Sonnet thread; dry run by default; `--backup <file>` first; `--apply` to write). I read its header, not its code or a run. It writes one key with `set_payload`, takes the value from `services.qdrant.indexer.resolve_source_rights_status` (the resolver serving uses), touches only children that lack the key, leaves a video the register does not clear untouched and lists it, and never stamps "licensed" by assumption. Do not type a value by hand. Because it is an integrity script written in the other lane, the Opus agent **reviews it and runs it**; the Sonnet thread does not run it. The value that belongs there is UNKNOWN to me. Required proof after the write, in the backfill pattern: export before, write allowlisted keys only, then prove point ids and count unchanged, text and both hashes unchanged on every point, vectors identical on a seeded sample, and zero write-rule violators.
4. For (a): **the script now exists:** `scripts/ops/fix_fp_unhashed_points.py` (`74aed64`, Sonnet thread; I read its header only, not a run). It targets hashless children: it sets `source_text_hash := sha256(verbatim_text)`, never changes `verbatim_text` or `transcript_hash`, and moves the point to its derived id (`point_id_for_record`), keeping vectors and payload. So the 2 bad points are probably children with no `source_text_hash` (ASSUMPTION; the audit report decides). Its `--backup` file holds verbatim text: keep it local, never commit it (the publication guard blocks it). It refuses if the new id already exists. Point count must stay the same. Dry run first, then Harsha's go, then `--apply`; the Opus agent reviews and runs it. If instead a point's text really does not match its hash, a hash edit is forbidden, so the fix cannot be "repair the hash". Allowed choices, least destructive first: stop it from being served with an existing non-servable marker; or delete the point after the snapshot. **Deleting is a one-way step for the live copy. Ask Harsha in the thread before you delete**, even though the data fix is approved.
5. Dry run first. Show the diff counts. Then apply. Then re-run `fp_live_audit.py`. This is Opus lane work (data integrity); the Sonnet thread only reads and reports.

Do not use `scripts/ops/ensure_fp_payload_indexes.py` for this. It serves the legacy store (`FirstPersonStore.PAYLOAD_INDEXES`), not the v10 context spans.

### 4.5 The 25 s versus 12 s scorer-timeout conflict. Decided.
- Conflict (VERIFIED in the Opus report): `test_graded_run_preflight.py` pinned 12 s; Sonnet's `6be465f` set `docker-compose.graded.yml` to 25 s; `test_runtime_budget.py` required 25 s. Both tests could not pass.
- Decision D-PG13 (Harsha, 2026-11-07, "use A"): the graded run pins 12 s; the default stays 25 s elsewhere. Applied in `32c12c4` (compose + one-source test) and `dea7b44` (wording). 38 tests passed in the cloud for preflight, runtime budget and real-LLM goldens (REPORTED). Full suite after the change: UNPROVEN.
- **Caveat (my reading, ASSUMPTION):** the commit text says the 12 s pin "cannot push a request past the 10 s p95 bar". That is not quite right. A 12 s timeout is longer than 10 s. It caps the tail. If more than 5% of requests wait for a timed-out scorer, p95 still exceeds 10 s. Stage A p95 was 12.5 s with a 5 s scorer timeout at the time; the scorer itself ran at a median 1.8 s, max 2.6 s (REPORTED). Measure; do not assume.

### 4.6 Speaker backfill on live v10 (2026-10-31). Applied.
- 745 writes. 4,224 ids, text and both hashes unchanged. 0 write-rule violators after. Net effect: **13 spans no longer served as verified** (11 demoted to `ecapa_failed`, 2 to `pending_voice_check`). Calibration id `9cf4b4156124e05866b7327cef24009e8906aae6c0c7479a80c8b86234da7044`, cosine floor 0.4854, margin 0.3862, FAR bound 0.21% (assumes independent trials, so the true bound is wider). REPORTED.
- The 11 demoted clips need Harsha's listen (section 5, step 5).
- Legacy `ecapa_voxceleb_centroid_v1` spans (2,005) remain served under a time-boxed exemption (R3).
- D6 (bare `preethaji` / `krishnaji` codes in two label maps) was fixed in `dff0b39f` (REPORTED).

### 4.7 Opus audit tasks (2026-11-06). Closed in code, nothing live.
SYS-003 (partial), CQ-011, ANS-010/011, RET-17, SYS-001, OPS-001/002, NEW-ANS-8 (17 release-invariant cases), DATA-20 to 24, AI-009, NEW-SEC-5, NEW-AI-6 (27-case offline adversarial suite), SAFE-004 (code closed; needs human call verification). Each had a failing test first. Table with SHAs: Opus report. **Defects found in my own earlier work** (Opus final review): `c609c6f` and `024a881`. T7-02 SHAs `a7359225`, `0176739e`, `f38b1b70`, `10d5775a`, `39470bd3` in older notes are pre-rebase and do not exist; real ones: `a54373b`, `c89e1b9`, `baba3da`, `d177cd2`, `ec2e6da`.

### 4.8 Sonnet platform tasks (2026-11-06 to 2026-11-07). Closed in code, nothing live.
Ratchets (exception 724/9, seeker-text 0, teacher-literal 590/129), image pins, stage-order guard on docs, 10 benchmarks labelled `LEGACY_GENERATION_PATH`, live audit script, Locust staging file, accessibility (A11Y-01 to 16 partial), Kubernetes reference-only headers, Lovable guards. Nothing marked Closed; no Mac or CI proof.

### 4.9 Things that did not work or were blocked
- Mac Remote Control on 2026-11-06 20:25Z: approved, but the Mac never picked up the session.
- The Mac blocks `git push` and `gh pr close` from threads. Harsha runs those in a terminal.
- The git proxy returns 403 on branch deletes (2026-10-25, REPORTED).
- `lightrag` / `tiktoken` cannot build in the cloud container, so tests that import them cannot run there.
- `GITHUB search_*` MCP tools are off in this session. Use `gh api -X GET search/...` if you need search.

---

## 5. The next step

### Harsha's own list, in order (from his message of 2026-11-07)
| # | Action | Notes and exact commands (check against current docs before you run them) |
|---|---|---|
| 1 | **Copy the Qdrant snapshot off the Mac.** | Why first: the live v10 collection exists once, on the Mac. The backup cron is not installed (REPORTED: RPO unbounded). Take a fresh snapshot first: `curl -s -X POST localhost:6333/collections/first_person_v10/snapshots`. List: `curl -s localhost:6333/collections/first_person_v10/snapshots`. Download: `curl -o <name> localhost:6333/collections/first_person_v10/snapshots/<name>`. Then `shasum -a 256 <name>` and copy file + hash to a drive or bucket that is not the Mac. (Snapshot REST paths: UNVERIFIED against the current Qdrant docs; confirm.) **Also copy** `~/mukthiguru_attribution_data/` (the audio archive is immutable source truth, `CLAUDE.md` invariant 17, and I found no backup of it other than `backups_2026-10-08`). Never print keys. |
| 2 | **Set the provider spend limit and the Railway usage limit, with alerts.** | OpenRouter: set a credit or key limit in its dashboard. Railway: set a usage limit and alert in workspace billing. UI paths UNVERIFIED. Local graded caps ($100/day, $300/month) are for the eval container only. Production rule (REPORTED): sized from expected daily volume with a 3x margin, alert at 70%. **These two limits now matter more:** the staging load run has no spend stop of its own (see D-PE7 below). They are the outside backstop. |
| 3 | **Turn on required checks in GitHub**, if no thread can. | Settings > Branches > rule for `main` > require status checks. Enter **`release-invariants`** and **`lovable-guard`** (job names). Do **not** enter `lovable-pr-guard`. **Read the CI failure cause first (section 0, item 3).** A required check that always fails blocks every merge. Also enable "require a pull request". |
| 3b | **Live v10 indexes: DONE.** 16 indexes, 4,226 points. | `fp_live_audit.py` shows no failed check (REPORTED in the register). Never run index, backfill or build jobs during the graded run. |
| 3c | **Live v10 data fixes: DONE** (`domain_rights_status` on 2,758 children; the 2 hashless points moved to new ids). Snapshot `first_person_v10-1111874297854021-2026-11-07-01-09-45.snapshot`. | Move the `/tmp` backups to a safe local folder (one holds quote text; never commit it). **Quarantine of the 2 moved test-looking points: approved by Harsha, script `quarantine_fp_points.py` (`6a0d61f`) is a reversible flag, UNPROVEN until applied and audited.** Re-run `fp_live_audit.py` after it. |
| 3d | **Check `backend/.env`:** `FIRST_PERSON_COLLECTION` and `FIRST_PERSON_CONTEXT_COLLECTION` must both say `first_person_v10` before the graded run. | `grep -n "FIRST_PERSON_.*COLLECTION" backend/.env` (do not print other lines). |
| 4 | **Run the graded clean-Docker run** on the final branch head, after both threads report their work pushed. | **Covered.** Flow: (1) both threads report "pushed" with the head SHA; (2) the coordinator sends the exact Docker commands; (3) **Harsha runs them** and pastes the output; (4) **one thread grades** the result (prompt 3 in `docs/handoffs/AGENT_PROMPTS_2026-11-07.md`). No agent runs Docker. The skeleton is in the header of `backend/docker-compose.graded.yml`: clean tree; `docker compose -f docker-compose.yml -f docker-compose.graded.yml up -d --build --force-recreate --no-deps backend`; `make flush-cache && make verify-cache-empty && make verify-stack-fresh`; `.venv/bin/python -m scripts.ops.graded_run_preflight --check-logs`; then `.venv/bin/python -m scripts.ops.graded_capture --run-id <id>`; then the grader. Rules: no other Docker user, no embedding or build jobs, no second Qdrant writer, one value changed per stage. |
| 5 | **Listen to the 11 demoted clips.** | Source: backfill 2 (section 4.6). The next Opus thread must build a one-page list (video id, start ms, end ms, teacher, link to audio). A listen counts only if the reviewer chooses the span's own teacher and the clip is 2 s or longer (rule D2). Results go in through the write rule, not by hand-editing Qdrant. Exact point-id list location: UNKNOWN (probably `.work/speaker_2026-10-31/` on the Mac). |
| 6 | **Add the Telugu crisis row to the test sheet.** | The sheet's exact file is UNKNOWN. Candidates: `docs/FIRST_PERSON_OWNER_TEST_GUIDE_2026-10-22.md` or `docs/FIRST_PERSON_OWNER_DECISION_AND_TEST_CHECKLIST_2026-10-22.md` (UNVERIFIED which). A native Telugu speaker must supply the phrase. An agent must not invent crisis wording and call it reviewed (`CLAUDE.md` Open work: multilingual crisis detection is AI-authored and AI-tested, NOT native-speaker reviewed). Native review file: `human-gates/safety/crisis_patterns_by_language.md`. |
| 7 | **Rotate keys only after the graded run is graded.** | Rotate: OpenRouter, Supabase (service and anon), Qdrant (read and write), JWT secret, Redis password, Railway tokens. Treat the old Helm password literals as burned. The root `.env` OpenRouter key is stale (401, REPORTED 2026-10-23). Never paste a key into chat, a file or a commit. |

### For the Opus agent (after the Mac check and CI cause are known)
1. Re-run the Mac check at the head and report counts (shared with Sonnet; Opus reads the safety tests).
2. Close the **Stage A safety gaps** (REPORTED in the memory index, 2026-11-01; I found no commit that closes them, so status is UNKNOWN): add heal / psychiatric / addiction to the health gate; add a clip-text support-line trigger; fix the grader rubric (q057 both showable and harmful; unverified speaker must count).
3. The owner decisions are applied in code (section 7): D-16, D-DQ1 (flag stays off), D-PG16 (flag only), D-PQ9, outside-India line. D-PQ7 is **no** and D-03 is **not now**: build nothing for them. Remaining under D-16: run the frozen-bank comparison before the judge flag is ever turned on.
4. Build the 11-clip listen list and the 50-clip human label sheet (section 6).
5. Remaining Opus rows: SYS-003 staging c20 test, MEM-002 (D-PM4), dead `_context_sufficient` routing, purge or keep personas written before `1c5f3f2`, the Opus-owned silent exception handlers.

### For the Sonnet agent
Follow `/mnt/project-files/prompts/agent-prompt-railway-and-ops-2026-11-07.md`, plus: read one failed CI job log (section 0, item 3) and report the cause; fix the check-name guidance in `docs/` and `.github/` comments if they say `lovable-pr-guard`; Redis `noeviction` risk, unchecked `GIT_SHA` set, and the metrics refresh exception list from the Opus review (section 11.2 of the register); the 9 silent exception handlers outside Opus files; own images default to `latest` when `IMAGE_TAG` is unset.

---

## 6. What was learnt

1. **A number from a void run is not a number.** Stages B and C produced attractive results (`p95 8.8 s`, `69/69`) while the LLM was switched off by a spend cap. The fix is mechanical: preflight checks headroom, capture marks the run INVALID, evidence is kept per run id (`graded_capture.py`).
2. **A tuning set cannot grade itself.** The 116 questions shaped the gates. The 86 unanswerable items are mostly easy (0 of 38 drafts got a clip). Still missing: a held-out answerable set and human labels. Judge agreement with humans is about 81 to 85% in the literature (MT-Bench, per `final-pass-bar-2026-10-30.md`; UNVERIFIED by me). Harsha or faculty should label 50 or more served clips (about 49 give plus or minus 10 points at 85%; my arithmetic from the bar doc).
3. **A flag is a claim.** Builders stamped `speaker_verified` with no evidence (732 spans claimed verified with no method). The write rule now refuses unproven stamps. The listen rule needed three fixes (D2, D3, D4).
4. **Integrity field on v10 is `source_text_hash`.** `transcript_hash` holds the whole-transcript hash for 919 of 2,758 spans. Do not use it per span (`CLAUDE.md` invariants 2 and 13).
5. **Docker copies the working tree.** A dirty tree or bind mount means the test ran different code than the commit. Hence the clean-tree preflight.
6. **Names matter in CI.** A required check matches the job name, not the workflow name (section 0, item 4).
7. **Tests that pin two values for one setting will fight.** The 12 s versus 25 s conflict. One source of truth, one decision, both tests updated.
8. **Short CI failures hide the real answer.** 30 failures in seconds say "the jobs did not run your code", until someone reads a log.
9. **Review your own commits.** The Opus final review of 49 commits found two defects in its own work and four notes on Sonnet's. Plan a second pair of eyes for every thread.
10. **A scorer timeout is a tail cap, not a latency fix.** See section 4.5.

---

## 7. Decisions already made (do not re-ask)

| ID | Decision | Source | Status |
|---|---|---|---|
| D-16 | Taken as recommended. **The evidence judge uses the relevance scorer's own model, `anthropic/claude-haiku-5.5`.** Price recorded: USD 0.10 in / 0.50 out per million tokens (read 2026-11-07 from the OpenRouter models list; the 5x rate above 100k prompt tokens is not modelled). The judge flag stays **off** until the frozen-bank comparison runs. A bug fixed on the way: the judge sent `temperature=0.0`, which this model rejects, so turning it on would have abstained on every question. Whether OpenRouter returns `usage.cost` for this model is UNPROVEN (no live call). | Commit `c662ae0` message; register 11.3 | Applied in code; flag off |
| D-DQ1 | Decided: the legacy store's `points_servable` text-and-hash compare **stays behind `first_person_points_servable_hash_check_enabled`, default off**. (My earlier text said "turn it on". That was wrong.) | Commit `29253c8`; register 11.3 | Applied; off by default |
| D-PG16 | Decided: the injection screen **flags a span for review and never drops it at ingest**. The serve-time drop switch stays off. A regression test guards it. | Commit `29253c8`; register 11.3 | Applied |
| D-PQ7 | **Decided: no.** `point_id` stays off the wire; `test_citation_contract.py` keeps forbidding it; an opaque signed id is later work. **My earlier line ("Yes, add `clip_ref`") copied the spec's recommendation and was wrong; the register records "Decided (no)".** Do not build `clip_ref`. | Register 11.3 (VERIFIED I read it) | Nothing to build now |
| D-PQ9 | Decided yes and **done**: when a system failure blocks the check, the abstain reads "I couldn't finish checking the teachings for this question just now. Please try again in a moment." instead of "no verified teaching". English; native-speaker review of this line is open (D-22). | Commit `43bdf7a` (register cites pre-rebase `7ad76a7`) | Closed in code; `test_abstain_cause.py` |
| D-03 | **Decided: not now.** The explanation layer is not built. ANS-004, ANS-006, ANS-007, PRD-007, RET-03, RET-04, RET-06 stay blocked. (My earlier "yes, behind a flag" was the spec's recommendation, not the decision.) | Register 11.3 | Nothing to build |
| Outside-India crisis line | Decided and **done**: every verified-only crisis block now ends with "If you are outside India, call your local emergency number now." **No phone number is shown**, so it does not conflict with the call-verified-only rule. English only; native review open (D-22). Crisis threshold unchanged. | Commit `bb8285a` (register cites pre-rebase `144d854`); `test_outside_india_line.py` | Closed in code |
| D-26 | External `QDRANT_URL`; no Qdrant service on Railway | `b119aa9` | Repo change done. Live URL UNPROVEN |
| D-14 | v10-only | `b119aa9` | Clean-Docker start UNPROVEN |
| D-29 | Faculty access code is the only staging gate (`FACULTY_ACCESS_CODE` set in the dashboard) | `b119aa9` | UNPROVEN |
| D-30 | Celery worker and beat on; `INCLUDE_CELERY` is the one switch | `b119aa9` | UNPROVEN on Railway |
| D-24 | Lovable by PR only | guards `78ac150` to `5ce3bc9` | Needs required checks |
| D-PK8S1 | Kubernetes files are reference only | `9e0eb4b`, `49f9e85` | Done |
| D-PA11Y6 | No new dependency; axe only. (The register's proposal said approve `eslint-plugin-jsx-a11y`. Harsha chose axe only.) | Relay | Done |
| D-PG13 | Graded scorer timeout 12 s; default stays 25 s | `32c12c4`, `dea7b44` | Applied |
| D-PE7 | **Staging load run: spend approved, and Harsha removed the cap condition ("remove this condition", relay 2026-11-07 01:06Z; the harness comment quotes him: "remove the cap").** The proposed USD 25 cap and USD 20 stop (80%) are no longer a default. `fp_staging_load.py` has no spend stop of its own; a cost log is kept; setting `SPEND_CAP_USD` brings abort rule AB-1 back at 80%. The remaining backstops are the app's OpenRouter budget guard, the provider spend limit and the Railway usage limit (Harsha's list, step 2). **My earlier text in this file said "USD 25 cap, stop at 20"; that was written before I saw commit `647ef2c` and was wrong.** | `647ef2c`; relay; `backend/benchmarks/fp_staging_load.py` lines 43 to 45 | Run not started (no staging exists). Ask Harsha once, in one line, whether "remove" meant the chat sentence or the cap itself; the code now treats it as the cap |
| Indexes | Create the 16 live indexes | Register; relay | **Done** (REPORTED: 16 indexes, 4,226 points). I did not see the output. |
| Live v10 data fixes | Approved: the 2 bad points (C-L3, C-L5) and `domain_rights_status` on 2,758 children. Backup first. No edits to quote text, `transcript_hash` or `source_text_hash`. | Harsha, relay 2026-11-07 01:06Z ("its ok, you can do those"); register block `0f56866` | **Done**; audit shows no failed check (REPORTED). Serving UNPROVEN |
| Quarantine of the 2 moved test-looking points | Approved: Harsha typed "quarantine" in the Railway thread (relay 01:15Z). Script `scripts/ops/quarantine_fp_points.py` (`6a0d61f`): reversible flag, dry run first. | Relay; commit | Not applied live as far as I know. UNPROVEN until the live audit shows it |
| Graded-run go-ahead | After both threads report work pushed, the coordinator sends the exact Docker commands. Harsha runs them. One thread grades. | Harsha, relay 2026-11-07 01:06Z | Waiting for both pushes |
| Required checks | `release-invariants` and `lovable-pr-guard` approved. Use the job name `lovable-guard`. | Register | Not set |

Earlier decisions (REPORTED, memory index): v10-only; graded run uses v10; pass bar approved; p95 stays 10 s; do not drop the 732 clips; do not use `FIRST_PERSON_REQUIRE_VOICE_METHOD` as a workaround; the 116 questions are a tuning set; rights are settled by Harsha (said twice; do not raise the register); pre-public items deferred (clinician sign-off, rights message, helpline call dates); key rotation after the graded run; crisis threshold 0.72; Railway stays stopped until the local sweep passes and the PR is merged.

---

## 8. What Harsha may have missed (my judgment)

1. **Section 0 items 1 to 4.** The merged-PR confusion, the 4 commits on `main`, the failing CI, and the wrong check name.
2. **The pass bar and the pin disagree.** Hard gate H2 allows 0 served clips with an unverified speaker. The graded compose pins `FIRST_PERSON_REQUIRE_VOICE_METHOD: "false"` (O3, "do not use it as a workaround"). Stage A served 13 of 33 with an unverified speaker. As configured, the run is likely to fail H2 by design. Decide before the run: either the run reports H2 as "measured, owner-accepted" or it does not. The backfill changed which spans count as verified, so the number will differ. ASSUMPTION: it will not drop to 0.
3. **The graded run does not test what Railway will run.** It sets `CELERY_TASK_ALWAYS_EAGER=true`, uses local Qdrant, no faculty code, and Redis without Railway's policy. Plan a short Railway staging smoke test after deploy: health, one served clip, one abstain, one crisis route, worker alive, `GIT_SHA` set.
4. **The Opus review flagged a Redis risk.** Railway Redis on `noeviction` holds cache and quota. When 512 MB fills, all writes fail (REPORTED, register 11.2).
5. **One copy of everything.** Live Qdrant, the audio archive and `~/mukthiguru_attribution_data/` live on one Mac. See step 1.
6. **The public-repo P0 is separate from the rights register.** Register rows X-06 and IP-001 (P0, "Needs owner decision", decision D-01): the repository is described as public and tracks verbatim text for 2,737 served spans. This is about repository visibility, not about permission to ingest videos. I am not reopening rights. Harsha should still choose private repo or purge before anything goes public. REPORTED; I did not check the repo's current visibility.
7. **"Amma Bhagavan" is not started in code, as far as I could see.** ASSUMPTION. Stage A already served a wrong clip for an Amma Bhagavan "Golden City" question (ua74). Adding a teacher touches 590 hard-coded teacher-name lines in 129 files (the ratchet counts them; nobody replaced any). Plan this as its own phase after the first graded result.
8. **The Stage A safety gaps may still be open.** I found no commit for them (section 5, Opus step 2). Do not run the graded run until they are closed or Harsha accepts them in writing.
9. **Local spend guard is off in `backend/.env`** (`OPENROUTER_BUDGET_GUARD_ENABLED=false`, REPORTED). This caused 13 local test failures. The graded compose forces it on. Do not rely on `.env` for the run.
10. **Add a lesson.** Suggested: `L-REQUIRED-CHECK-NAME-IS-JOB-NAME-1` (search `lessons.md` for an existing one first). I did not add it, because other threads write to that file.
11. **Mac permission prompts cannot be approved from chat.** Plan all commit, push and delete steps as commands Harsha runs.
12. **Hidden-cost reminder.** The Stage A grader uses OpenRouter calls (Haiku, then Opus on 25 rows). A re-run of 202 rows plus grading has a real cost. Check the headroom first (the preflight does).
13. **Backups in `/tmp`.** The rollback files for the 2026-11-07 data fixes sit in `/tmp` on the Mac, and one holds quote text. A reboot may clear them. The snapshot is the durable rollback, so copy it off the Mac first. Move the files, keep them out of git (the publication guard would block them anyway).
14. **The serving filter jumped from 2 to 2,738 spans.** That is a large change in what the product can serve, made by one payload key. Nothing has measured answers on it. Stage A cannot tell you what happens next. The graded run is the first real measure, so do not plan around Stage A numbers.
15. **Check `backend/.env` collection variables** before the run (section 0b, item 2).

---

## 9. Verified, assumed, unknown (summary)

**Verified (this session):** branch head `5e23438`; 188 ahead, 4 behind `main`; PR #86 merged 2026-11-03; PR #97 open; 30 of 32 check runs failed in seconds at head; job names `release-invariants` and `lovable-guard`; `backend/docker-compose.graded.yml` pins 12 s; `32c12c4` and `dea7b44` content; the Stage A table (from the review document); two index scripts exist and the span one is correct for v10; register "Decisions recorded 2026-11-07" block.

**Assumptions:** the cause of the 4 live-data failures (section 4.4); the CI failures are an environment problem, not a code problem; H2 will fail as configured; Amma Bhagavan work not started; 12 s timeout does not guarantee p95 under 10 s.

**Reported, not re-checked (added 01:15Z):** the live audit shows no failed check; 2,758 children stamped `licensed`; the serving filter passes 2,738 of 2,760; the 2 moved ids; the snapshot name; backups in `/tmp`; Pending List version 53.

**Unknown:** whether the quarantine has been applied live; the CI failure cause; whether the Stage A safety gaps are closed; the exact recommended values for D-16, D-PG16 and the outside-India line; the file for the test sheet; the location of the 11 demoted point ids; whether the repo is public today; who wrote to v11 on 2026-10-31; why q077 took 98 s in Stage A.

**Unproven:** everything live. No Docker, Qdrant, Supabase, Railway or OpenRouter use was made in writing this handoff. Verdict stays **NO-GO**.

---

## Checks you can run

1. `git fetch origin && git log --oneline -1 origin/feature/audit-strengthen-rag-qdrant` shows the head. `git rev-list --count origin/main..origin/feature/audit-strengthen-rag-qdrant` shows 188 or more. `git rev-list --count origin/feature/audit-strengthen-rag-qdrant..origin/main` shows 4.
2. Open PR #97 and PR #86 on GitHub. #86 says Merged. #97 says Open.
3. Open one failed check on #97 (for example `release-invariants`). Read the first error line. Write it into the Pending List.
4. `grep -n "name:\|lovable-guard" .github/workflows/lovable-pr-guard.yml` shows workflow `lovable-pr-guard` and job `lovable-guard`.
5. `grep -n RELEVANCE_TIMEOUT backend/docker-compose.graded.yml` shows `"12"`.
6. `backend/.venv/bin/python scripts/ops/ensure_fp_span_indexes.py` (dry run) lists no missing index, and `fp_live_audit.py` C-L8 passes. Point count reads 4,226.
7. `python3 scripts/guards/lesson_guards.py claims` exits 0 on this file.

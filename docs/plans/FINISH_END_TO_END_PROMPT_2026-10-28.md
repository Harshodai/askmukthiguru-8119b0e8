# Finish everything end to end: copy-paste prompt (2026-10-28)

Status when written: **NO-GO** (faculty-only CONDITIONAL). Nothing below is proof of anything; it is a work order. Where evidence is missing it says UNPROVEN.

Main state re-checked 2026-10-30 on `311a8cf3`: backend is green (ruff, format, pytest, safety harness; PR #89 carried the lint and stale-test fixes, so the earlier PR #87 is superseded). **Main is still red on the frontend**: Lovable commits since 2026-10-29 (`34c0ae46` "Added translation keys", `311a8cf3`) added keys to `src/locales/en.json` without syncing the other locales, so `Check i18n locale coverage (P1-FE-11)` and `src/test/i18n-sync.test.ts` fail (about 60 missing keys per locale, e.g. `landing.demo.*`, `mood.*`, `chat.*`, `settings.voiceHint_*`). Fix is `npm run i18n:sync`, which calls a translation API and writes machine translations into 14 user-facing locales; that needs the owner's go-ahead and a key. Open PR #86 (large, from the Mac thread) is on base `34c0ae46`, mergeable, not reviewed here; its text says `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false` is pinned while project memory says v10 is served with the harness on: confirm which is intended before the graded run.

## 1. Commands for Harsha (Mac terminal, repo root)

```bash
# A. Only after main CI is green (frontend i18n sync outstanding, see above)
git checkout main && git pull origin main

# B. Graded clean-Docker run (one backend only; never two)
cd backend && docker compose -p backend up -d --no-deps --force-recreate backend && cd ..
make flush-cache            # if it fails on project name, see lessons L-FLUSH-CACHE-PROJECT-1
make verify-cache-empty     # must exit 0; exit 2 (unreachable) is NOT "empty"
make verify-stack-fresh     # must exit 0; "unknown" counts as stale
make verify-guards
python3 backend/scripts/ops/check_first_person_public_release.py --json > /tmp/gate.json
cd backend && .venv/bin/python scripts/ops/first_person_live_eval.py \
  --endpoint http://localhost:8000 --out-dir ~/mukthiguru_attribution_data/first_person_live_eval

# C. Hygiene
find ~ -maxdepth 4 -name pr_env.list      # delete it (holds secrets); do not paste its contents anywhere
```

Then: paste the Section 2 prompt into a new session; do the human listens (anger clip, `rGcNJ_Nsuy8` @659320 ms, `H_uhawaiO3E` @40020 ms); run the reversible Qdrant set-payload for the 9 D1 clips from the Opus research thread (**not** `FIRST_PERSON_QUALITY_BLOCKLIST_PATH`, which fails closed on every harness span); rotate keys **only after** the graded run is scored.

Remote branches: the three-branch list is now `main`, `lovable-sync`, `feature/audit-strengthen-rag-qdrant` (#86). The earlier delete list is already gone; no delete command is needed.

## 2. The prompt (paste as is)

> You are finishing the Mukthi Guru release work in `Harshodai/askmukthiguru-8119b0e8`. Read `CLAUDE.md`, `lessons.md`, `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md`, `docs/plans/V10_PUBLIC_GO_PLAN_2026-10-23.md` and this file first. Rules: never call anything ready without evidence (unproven = UNPROVEN); teacher quotes and `transcript_hash` are never edited; crisis threshold stays 0.72; Railway stays stopped; local Docker only; OpenRouter only; no pushes to main, open PRs, merge only after the owner types approval in the thread.
>
> **Model routing.** Haiku 5.5 for bulk checks and log triage, Sonnet 5.5 for implementation and fixes, Opus only to grade evidence and to review safety/crisis code, in a separate thread, saying so.
>
> **Ruthless research.** For every external claim you rely on (OpenRouter reasoning-token limits, Learn-then-Test / Clopper-Pearson bounds, ECAPA / pyannote accuracy, India DPDP Act and Rules obligations, YouTube terms for embeds and audio), fetch the primary source (vendor docs, the arXiv paper, the gazette or the SpeechBrain / pyannote model card), quote the line you rely on with its URL and the date you read it, and flag anything you could not open. Do not cite a page you only saw in a search result. Do not invent titles, numbers or quotes. Treat numbers that are not in a primary source as unverified.
>
> **Work, in order.**
> 1. Get main green: sync the i18n locales (`npm run i18n:sync`, owner approves the translation call), then bring #86 up to date with main and review it (tests, ruff, harness flag intent, migrations `20261028000000`-`03` applied only in a scratch DB first). Do not merge #86 until its CI is green on current main.
> 2. Graded clean-Docker run (Section 1 B). Record: commit sha, cache-empty proof, stack-fresh proof, live-eval output (top-1 vs the B.R0 reference in the script docstring, p95, crisis probe, teacher filter, hash and speaker check per served clip), and whether `OPENROUTER_CALL_TIMING operation=verify` appears (that is the only proof the scorer-budget change works live). Run a Hindi probe too (the Indic fix in #55 is UNPROVEN until then).
> 3. Speaker evidence: only voice-verified Ekam clips are served; hold the 20 `hold` clips; the 2 host-uncertain and the anger clip need a human listen. State FAR with its upper bound (0/262 is about 1.14% at 95%), and say the impostor set is a closed two-guru set.
> 4. Amma Bhagavan: do not code. Put two questions to the owner: (a) third speaker with her own voice and clips, or same lineage (recommended default: third speaker); (b) id and spelling (recommended `amma_bhagavan`, whole-word matching only). Prerequisites that are not code: written rights message, source list, enrollment audio. Plan: `docs/plans/AMMA_BHAGAVAN_ONBOARDING_PLAN_2026-10-25.md`.
> 5. After the graded run is scored by the owner, key rotation is the owner's step; remind, do not do it.
> 6. Update the Pending List artifact (https://claude.ai/artifact/PtxfGz9iintSkmGsPNGFg9) and `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` with what moved. Do not re-raise the deferred pre-public items in CLAUDE.md.
>
> **Output.** One short report: verdict (GO / CONDITIONAL GO / NO-GO), a table of gates with PASS / FAIL / UNPROVEN and the evidence file for each, what the owner must do, and sources actually read.

## 3. NO-GO to GO criteria (from the repo's own gates)

| Tier | Needs | Status |
|---|---|---|
| Faculty preview (password gate, `FACULTY_ACCESS_CODE`) | Main green; graded clean-Docker run on final main with zero P0/P1; live scorer proof; Hindi probe; speaker holds applied | UNPROVEN |
| Real users | Faculty feedback received; crisis and distress path re-checked on the final build | Not started |
| Public | Gate controller all green (was 16/24; failing items are owner decisions: rights register, clinician safety, human gold labels (about 299 zero-error labels for a 1% bound), variant tier, release authorization, public scopes), helpline call dates | Deferred by owner; do not raise as a blocker until Harsha says going public |

Sources behind the numbers are in the repo (`backend/config/first_person_public_release_gate.json`, `V10_PUBLIC_GO_PLAN_2026-10-23.md` section 3). External background was searched at title level only on 2026-10-25 and **not read**; the prompt above makes reading primary sources a required step.

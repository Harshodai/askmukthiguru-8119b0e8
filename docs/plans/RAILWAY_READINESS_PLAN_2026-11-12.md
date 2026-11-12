# Railway readiness: ruthless status and plan (2026-11-12)

Verdict: **NO-GO for Railway.** Owner directive: Railway stays stopped until Harsha says go.

## What is true today (verified)
- Repo head `519ff651`, origin in sync (fast-forward pushed by owner).
- `first_person_v10`: 24 parent windows repaired in place (payload only, snapshot
  `first_person_v10-1111874297854021-2026-11-12-16-27-32.snapshot`). Audit exit 0,
  0 hash mismatches, 0 bare speakers, 2,760 children licensed. 1 orphan child group
  (`parent_88NOQTz5_yI_0`) still present; deletion not approved.
- Showable rate on the last valid-looking grade (`20261112-graded-3`): 80% against a
  85% bar. FAIL. Grade is DIAGNOSTIC ONLY (one judge model for both slots).
- Graded captures `-4` and `-5` are invalid (backend killed mid-run).
- Backend kills: SIGTERM then SIGKILL (exit 137) matching `docker compose` recreate.
  Another session recreates the same container (`mukthiguru-backend`). Probable cause,
  not yet proven by logs.
- Redis timeouts (~48 per run, 0.5 s socket timeout): unexplained. Idle Redis is ~0.2 ms.

## Blockers, ranked
1. **Shared container, no owner.** Two sessions recreate one container. Fix: one owner
   at a time, announced in-session. Nothing else.
2. **Answer quality below bar.** Served-but-unshowable clips persist at min score 2,
   which the owner chose to keep. Fixing this needs scorer and retrieval work, then a
   valid graded run on a stable backend. Costs OpenRouter spend.
3. **Corpus data.** 1 orphan child (delete needs approval). A full v10 rebuild from v8
   is not viable: the speaker method refused by policy keeps only 508 of 1,466 parents.
4. **Redis timeouts.** Measure under real load once the container is stable.
5. **Human-only gates (CLAUDE.md, still pending):** native-speaker review, clinician
   review, helpline call verification, rights sign-off, 299-pair gold batch.
6. **Railway setup:** `FORWARDED_ALLOW_IPS`, deploy gate `/api/healthz`, one replica,
   `railway up` (never `--from-source`), smoke test (anon session, chat, health).

## Plan
- **Phase 0 (now, no spend):** container turn-taking agreed; no recreate while another
  owner's capture runs.
- **Phase 1 (needs spend approval):** one valid graded run on a stable container, with
  `/api/health` latency sampled throughout. Confirms or kills the stall theory.
- **Phase 2 (needs decision):** answer quality. Decide the bar (keep 85%, or change it
  by owner decision). Then scorer or retrieval work, then a new graded run.
- **Phase 3 (needs decision):** delete the orphan child yes/no. Speaker method policy
  for future rebuilds.
- **Phase 4 (human):** native, clinician, helpline and rights gates.
- **Phase 5 (owner go):** Railway prerequisites, then deploy.

## Decisions needed from Harsha
- Approve the container turn-taking rule.
- Approve spend for Phase 1.
- Keep or change the 85% showable bar. Keep means Railway stays blocked on Phase 2.
- Orphan child: delete or keep.

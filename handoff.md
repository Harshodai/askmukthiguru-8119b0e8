# Handoff — Mukthi Guru remediation session

## 1. Goal
Harden Mukthi Guru for production quality: fix answer-quality bugs (the "upcoming programs from
Ekam" failure and its class), latency (reranker), and data-quality at the root (transcription
errors like "Ekam"->"Akam"). The last and central goal: make doctrine-term corrections a **single,
admin-editable, drift-proof source of truth** applied at transcription + ingest + output, plus a
whole-corpus data-quality audit. Full backlog captured in
`docs/engineering-notes/MASTER_REMEDIATION_PLAN.md`.

## 2. Current state of code
- **On disk (all changes present, tests green):** the data-quality system
  (`services/doctrine_terms.py` + rewires), the Ekam fixes, reranker/routing config, OKF hardening.
- **IMPORTANT — live process is STALE:** the running backend container has been up ~5h; uvicorn
  runs WITHOUT `--reload`, so the process still runs the **pre-`doctrine_terms`** code. The
  doctrine-terms rewrite is verified at unit/import level only, NOT in the live pipeline.
- **Already live (prior restarts):** logistics short-circuit, cache-bleed guards, reranker
  MiniLM, routing threshold 0.55 — these were restarted-in and verified live earlier.
- Working tree has many uncommitted files (mine below + pre-existing frontend `src/components/chat/*`
  changes that are NOT mine). Nothing committed this session (per house rule: leave for review).

## 3. Files actively edited this session (mine)
New: `backend/services/doctrine_terms.py`, `backend/tests/test_doctrine_terms.py`,
`backend/tests/test_dangling_cta_strip.py`, `scripts/ops/audit_doctrine_data_quality.py`,
`docs/engineering-notes/MASTER_REMEDIATION_PLAN.md`, this `handoff.md`.
Modified: `backend/services/{whisper_local_service,reranker_service,embedding_service,user_profile_service}.py`,
`backend/ingest/corrector.py`, `backend/rag/nodes/{generation,intent}.py`,
`backend/app/pipeline/stages/cache_stage.py`, `backend/app/api/admin.py`, `backend/app/config.py`,
`CLAUDE.md`, `backend/CLAUDE.md`, `backend/tests/test_okf_pipeline_integrity.py`.

## 4. Tried and failed (so it isn't retried)
- **RunnableConfig UserWarning (93x):** tried a `RunnableConfig` annotation, then a module-level
  `warnings.filterwarnings` — neither silenced it (`from __future__ import annotations` defeats
  LangGraph's check; the app resets warning filters). Reverted; it's benign. Do not re-chase.
- **Prompt-only fix for logistics filler:** reworded generation instruction #11/#11b twice; the
  verbose persona ignored it. Replaced with the deterministic intent-level short-circuit.
- **Whisper rewire was reverted once mid-session** (a lint/quality hook or similar) — re-applied and
  confirmed it held (grep + import). Watch for this if edits to `whisper_local_service.py` vanish.
- **P0-8 schema `max_length` 10000->2000:** applied then reverted — it broke `test_security_redteam`
  and was a misread of three intentional layered length limits.
- **Redis `FLUSHALL` alone does not clear caches:** there are FOUR layers (Redis, in-process/restart,
  semantic, frontend `localStorage`). Re-tests returned stale answers until all four were cleared.
- **First UI tests** returned a stale teaching answer / "Guru is resting" — traced to the frontend
  `responseCache` (localStorage) + a semantic-cache bleed, not a backend bug.

## 5. Next step (do this first)
1. **Live-verify the doctrine-terms rewire (the outstanding confirmation):**
   `cd backend && docker compose restart backend` (wait healthy) -> flush all 4 caches ->
   `POST /api/chat` "What is Ekam and what happens there?" -> assert the answer reads **"Ekam"**
   (not "Akam") and no import/startup errors in `docker logs`. Also confirm the logistics
   short-circuit + streaming still work post-restart.
2. **Create the Supabase `doctrine_terms` table** (SQL in the master plan, Part C) so the admin
   GET/POST endpoints can actually save (currently they fall back to code defaults).
3. Then start **B1 + B2** from the master plan: measure the MiniLM `rerank_score` distribution and
   recalibrate `rerank_min_score` / sufficiency gate (currently bge-m3 values), which also
   un-breaks relevance-aware sufficiency. This unblocks the doctrine benchmark.

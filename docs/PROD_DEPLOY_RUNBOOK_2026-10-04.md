# Production Deploy Runbook — AskMukthiGuru (2026-10-04)

**Status:** PREP ONLY. Nothing below has been executed. Owner triggers each gate.
**Assumes:** ingest complete + Phase 1 gates green + branch pushed + hosting target chosen.

## Gate 0 — Preconditions (all must be true)
- [ ] Mass ingest complete: `state.json` shows 0 pending, Qdrant `first_person_v7` ≈ 2,500 clips
- [ ] Phase 1 gates: dry-run→0→ID audit→harness re-baseline→golden-25 re-measured (ONE change across `golden25-gate.yml` + `CLAUDE.md` + checklist §D row 5)
- [ ] Full backend suite green from `backend/` + `ruff check` clean + frontend `npm run build` green
- [ ] Branch pushed + merged to main (N8: owner runs `git push`; golden25-gate.yml dispatches only from main)
- [ ] Gold labels returned (or explicit accept-floors decision recorded here)

## Gate 1 — Hosting target (owner picks ONE)
- **A: Hetzner CX32** (recommended, `docs/HOSTING_OPTIONS_2026-10-04.md`): provision CX32 x86 → install docker → copy `docker-compose.yml` + env → restore Qdrant snapshot (`snapshots/` API) + memgraph dump → flip DNS. Keep Railway paused 1 week as rollback. Effort 4–8h.
- **B: Railway unpause**: set `FORWARDED_ALLOW_IPS` (already in vars — verify), confirm 1 replica, `QDRANT_URL` secret AFTER `/collections` → 200, accept ~$53–73/mo. Deploy via `railway up` (NEVER redeploy-from-source).

## Gate 2 — Secrets & config (Railway path; Hetzner uses same values in env)
- [ ] `OPENROUTER_API_KEY`, Supabase URL/keys (already in CI staging; mirror to target)
- [ ] `QDRANT_URL` = `https://qdrant-production-14ee.up.railway.app` (only after unpause probe 200)
- [ ] `QDRANT_COLLECTION` = `spiritual_wisdom` (prod collection) for main graph; FP path uses `first_person_v7`
- [ ] `QDRANT_API_KEY` stays empty (keyless instance — correct)
- [ ] `FEATURE_MEMORY_WRITE` stays `false` until consent-surface review passes (report §9u procedure)
- [ ] `FIRST_PERSON_CHAT_BRIDGE_ENABLED=true`, `FIRST_PERSON_SERVE_UNREGISTERED=true` (owner Ask-7: FP primary in prod too)
- [ ] P0 cuts active: semaphore 12 (restart to activate), workers 2, RPM 60, `/api/health` rate-limited

## Gate 3 — Deploy + smoke (exact order)
1. Deploy (Railway: `railway up`; Hetzner: `docker compose up -d --build backend frontend`)
2. `GET /api/healthz` → 200 (90s grace), then `/api/health` → `ready:true, status:healthy`
3. Smoke: anon-session → chat greeting → teaching question → verify ONE real quote with `&t=` link + citations resolve
4. FP probe: restless-mind question → `route_decision=first_person_bridge`, `verification.passed=true`
5. Ritual probe: `GET /api/ritual/today` → 200 + speaker attribution present
6. nightly-rls dispatch → green (proves prod DB trigger); golden25-gate dispatch → honest-run (no skip)

## Gate 4 — Post-deploy watch (48h)
- Error rate, p95 latency, 503 "Server busy" bursts (semaphore), OpenRouter 429 rate + cost ledger
- Qdrant points stable (no unexpected deletions — apply guard raises loudly; investigate any APPLY FAILED)
- Rollback: Railway → previous deployment `railway redeploy <id>`; Hetzner → unpause Railway + DNS flip back

## Explicitly NOT in this deploy
- `config.py` cut lines (held: parallel-session hunks — land with their merge)
- Graph/loop latency changes, rerank flip, disputed-rate threshold move (evidence-gated, post-gold)
- WhatsApp channel, donation rail, Play Store (Phase 2 growth per research doc)
- Answer-quality FAILs (abstention/completeness) ship as KNOWN LIMITS with honest abstention paths, not silent fixes

# BURST_R4 — Post-fix ten-question burst + locust attempt (evidence only)

Date: 2026-09-13 ~12:45 IST. Policy: no commits; this file is the only write.
Task: S4 from `docs/superpowers/plans/2026-09-13-structural-faults.md` (round-4 addendum, steps 4+6).

## 1. Fixed-code check (no restart performed)

- Running backend: host uvicorn PID 32314,
  `ps -o lstart= -p 32314` → `Sun Sep 13 12:25:02 2026`.
- R2 singleton files mtime (`stat`): `backend/app/container.py`,
  `backend/tasks/web_ingest_tasks.py`, `backend/ingest/contextual_reingest.py`,
  `backend/ingest/book_ingest.py`, `backend/services/memory/compiler.py`
  all `2026-09-13 12:15:55` — **10 min BEFORE process start**.
- `grep get_embedding_service backend/services/embedding_service.py` →
  `1814: def get_embedding_service()` (singleton accessor present);
  `git diff` confirms all five call sites routed through it (uncommitted, HEAD `bf7ada3d`).
- Conclusion: process started AFTER the R2 edits, so this run measures
  **FIXED (post-singleton) code**. No restart needed; none performed
  (restart would have risked the running session for zero code delta).
  Caveat: mtime ordering only — live imports not introspected.
- Health at run time: `curl /api/health` →
  `{"ready":false,"status":"starting",...}` — Neo4j uniqueness constraints
  missing (UNIQUE_USER_ID, UNIQUE_GLOBALMEMORY_ID, …). Backend still serves
  `/api/chat` (validation/anon paths live); readiness gate does not block chat.

## 2. Ten-question no-gap burst (sequential, incognito=true)

Auth: `POST /api/auth/anon-session` →
`{"session_id":"anon:SH8109AcUm_4ftTt7wUbVQ","token":"SH81…CmFCg"}`;
token used as `session_id`. Schema: `{"messages":[],"user_message","session_id","incognito"}`.
First attempt with `session_id:"burst-probe-N"` → 10× HTTP 400
`{"detail":"Invalid anonymous session token"}` (schema lesson: anon token required).

| # | question | http | wall | pipe_lat | ground | faith | cites | rlen |
|---|----------|------|------|----------|--------|-------|-------|------|
| 1 | Serene Mind teaching | 200 | 10s | 9581ms | grounded | 1.0 | 2 | 656 |
| 2 | Four Sacred Secrets | 200 | 7s | 6520ms | grounded | 0.67 | 2 | 1185 |
| 3 | meaning of stillness | 200 | 22s | 22008ms | grounded | 1.0 | 4 | 716 |
| 4 | deal with suffering | 200 | 21s | 20782ms | safety_redirect | 1.0 | 2 | 1265 |
| 5 | Beautiful State | 200 | 32s | 32223ms | grounded | 1.0 | 1 | 554 |
| 6 | meditation vs contemplation | 429 | 0s | — | — | — | — | — |
| 7 | handle anger | 429 | 0s | — | — | — | — | — |
| 8 | awareness in daily life | 429 | 0s | — | — | — | — | — |
| 9 | overcome fear | 429 | 0s | — | — | — | — | — |
| 10 | purpose of life | 429 | 0s | — | — | — | — | — |

Req 6–10 body (identical): `{"error":"Anonymous quota exceeded",...,
"total_limit":5,"retry_after_seconds":86309}` — **anon quota 5/day/identity**,
not a crash. Where it dies: request 6, at the quota gate, 0s wall each.

Liveness after burst: PID 32314 alive (`ELAPSED 24:42`, growing);
`/api/health` still responds (same `ready:false/starting` as before);
no `libgomp: Thread creation failed`, no exit(1), no connection-reset.
**No crash observed — but the run did NOT reach req 9**, where L-DOCKER-18
died (req 1–8 served, 9th "Remote end closed", 10th reset, exit(1)).
The quota wall (5) sits below both the pre-fix wall (5, per plan note) and
the L-DOCKER-18 wall (9), so this burst **cannot confirm or refute** the
singleton fix against thread-accumulation. Honest score: **5/5 served to
quota, 0 crashes, fix efficacy UNPROVEN**.

To re-run past quota: use 2+ anon tokens (round-robin identity per request),
or an authenticated user, or raise anon quota. Suggested: one token per
request (10 tokens), sequential, same question set + Hindi probe
(`मन की शांति कैसे पाएं?` was dropped from this run to fit quota).

## 3. Locust 20-user sweep — BLOCKED

- `which locust` → `locust not found`; `locust --version` → `command not found`;
  `python3 -c "import locust"` → `ModuleNotFoundError: No module named 'locust'`;
  `backend/.venv/bin/locust` → no such file.
- Sandbox policy forbids installs → not installed, sweep not attempted.
- What CI / dependency-complete image needs: `pip install locust`
  (from `pip install -r backend/requirements.lock` + locust stanza, or a
  load-test extras file), then a 20-user chat sweep against the compose
  backend with per-request status/latency capture (see
  `.github/workflows/nightly-load.yml` from Task 7 for the target harness).

## 4. Verdict

- Code under test: FIXED (post-R2 singletons), uncommitted.
- Burst: 5/5 to quota, then 429 ×5. No crash, no libgomp error, backend alive.
- Fix efficacy vs L-DOCKER-18: UNPROVEN (quota wall < crash wall).
- Locust 20-user: BLOCKED (locust absent, installs forbidden).
- Next: multi-token burst to reach req 9–10 on fixed code; locust in CI image.

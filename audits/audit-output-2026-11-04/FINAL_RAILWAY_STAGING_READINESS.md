# Final Railway staging readiness (Gate A)

Date: 2026-11-05. Head: `c9b42d3e` on `feature/audit-strengthen-rag-qdrant`. Evidence labels: `CONVENTIONS.md` section 3.

Companions: `specifications/RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` (the runbook; "RB" below), `FINAL_PRODUCTION_RELEASE_READINESS.md` (Gates B and C, not repeated here), `FINAL_PENDING_WORK_REGISTER.md`.

Note on the brief. The text of "brief Part 7" was not available to the writer. The items below cover the eight groups named in the task. If the brief lists an item that is missing here, add it as a new row in the matching group.

## 1. Decision today

| Gate | Decision | Reason |
|---|---|---|
| A. Railway staging | NO (conditional). UNPROVEN on every runtime item. | No staging environment exists. The repository declares one service only. Three code or script defects block a first deploy (see section 3). All runtime behaviour needs a live Railway project. |

Rule used for the classification. A row is "Ready (repo evidence)" only when the code, test or file exists at this head and the item needs no Railway state. A document alone never makes a row Ready. A row that depends on a Railway setting or a live run is never Ready.

Classes: R = Ready (repo evidence); IMP = Requires implementation; CFG = Requires Railway configuration; LIVE = Requires live deployment; EXT = Requires external service; NA = Not applicable.

## 2. Item table

### 2.1 Build and startup

| ID | Item | Class | Evidence | Note |
|---|---|---|---|---|
| P7-01 | Dockerfile builds the backend image from the repo root | R | `backend/Dockerfile.railway:16-149`; `.dockerignore:54-59` keeps the needed files | Build itself not run here. A real build is LIVE (P7-02). |
| P7-02 | Image builds on Railway and boots | LIVE | RB 17.3, U-5 | Needs a Railway project. |
| P7-03 | Railway selects `Dockerfile.railway` | CFG | Name is not `Dockerfile`; Railway auto-detects only that name: docs `builds/dockerfiles`. Set `RAILWAY_DOCKERFILE_PATH` (RB 5, C-4) | Not expressible in `service()` (docs `infrastructure-as-code/reference`). |
| P7-04 | Start command and entrypoint | R | `Dockerfile.railway:149`; `backend/start_railway.py:511-657` | Service branches by `SERVICE_TYPE`. |
| P7-05 | Release identity (`git_sha`, `release_id`) is concrete on a Railway deploy | IMP | `release_manifest.py:122-127`; `first_person_release.py:119-125`; `deploy_railway.sh:295` uses `railway up`; docs `variables/reference` (SHA only for GitHub triggers) | NEW-RW-2. Startup can abort on a script deploy [INF]. |
| P7-06 | Rights register ships in the image and startup checks it | R | `Dockerfile.railway:89-92`; `main.py:786-809`; `health.py:228-235` (T3-01) | Presence on the deployed image is LIVE (RB S-3). |
| P7-07 | Helplines file ships in the image | R | `Dockerfile.railway:99` | Content review is Gate B/C. |
| P7-08 | Models baked at build, no runtime download | R | `Dockerfile.railway:37-49`, `:120-125` | Build-time network read, so the build is not bit-reproducible (RB 12). |
| P7-09 | IaC file declares every staging service | IMP | `.railway/railway.ts:15-27` declares one service | T9-01. Proposed file in RB 5. |
| P7-10 | Config as Code files removed before 2026-12-01 | R | `railway.json`, `railway.toml` absent at this head (checked 2026-11-05) | A Config File path set in the dashboard is unknown (RB U-1). |
| P7-11 | Deploys from a reviewed commit with CI gating | CFG | Docs `deployments/github-autodeploys` (Wait for CI); branch protection is T0-03 (owner) | Needs Railway and GitHub settings. |

### 2.2 Configuration

| ID | Item | Class | Evidence | Note |
|---|---|---|---|---|
| P7-12 | Required variables are enforced at startup | R | `config.py:2364-2369`, `:2475-2503`, `:2597-2598`, `:2638-2646`; `auth_service.py:32-33`; `main.py:761-809` | Fail-closed, good. Values are set per environment (CFG, P7-13). |
| P7-13 | Variable matrix applied in staging | CFG | RB 6 | Secrets exist only in the dashboard. |
| P7-14 | `ENVIRONMENT=staging` set | CFG | `config.py:2638-2646` refuses `local` | The deploy script never sets it (`deploy_railway.sh:207-260`). |
| P7-15 | Spend cap on by default and refused if off | R | `config.py:643-648`, `:2492-2503` (T1-07) | Provider-side key limit is EXT (P7-33). |
| P7-16 | Serving collection and bridge flags explicit | CFG | RB 6.2; `config.py:2308-2327`, `:2320-2321` | D-14 open. Default resolves to v8 without the two harness flags. |
| P7-17 | Misspelled variable detected | IMP | `config.py:55` (`extra="ignore"`); T2-06 lints the repo only | Log line check is a manual step (RB S-13). |
| P7-18 | Deploy script sets a correct, complete variable set | IMP | `deploy_railway.sh:207-260` (random `JWT_SECRET`, missing `ENVIRONMENT`, `FACULTY_ACCESS_CODE`, `METRICS_SCRAPE_TOKEN`, `GIT_SHA`) | NEW-RW-4. |
| P7-19 | Redis eviction policy matches the repo decision | IMP | `deploy_railway.sh:286-288` sets `volatile-lru`; `docker-compose.prod.yml` comments require `noeviction` | NEW-RW-4. Quota keys carry TTLs, so `volatile-lru` can evict them. |
| P7-20 | CORS and allowed hosts for the staging frontend | CFG | `main.py:1062-1070`, `:1038-1042`, `:1138-1145`; script hard-codes the Lovable origin (`deploy_railway.sh:224`) | Owner supplies the staging origin. |
| P7-21 | Secrets never in repo | R | Only `backend/.env.example` is tracked (CLAUDE.md rule); IaC proposal uses `preserve()` | Sealed variables do not copy to duplicated environments (docs `variables`). |

### 2.3 Health and reliability

| ID | Item | Class | Evidence | Note |
|---|---|---|---|---|
| P7-22 | Deploy healthcheck path and timeout | R | `.railway/railway.ts:17-18`; `start_railway.py:83`, `:465-502` | Passing on Railway is LIVE (P7-23). |
| P7-23 | Healthcheck passes on a real boot | LIVE | RB 17.3, R-5, U-5 | Worst case 300 s plus import against 330 s with no Memgraph (`main.py:923`, `:938`). |
| P7-24 | Healthcheck is not treated as continuous monitoring | R | `start_railway.py:13-22` states it; docs `deployments/healthchecks` confirm | Watchdog exits non-zero on a wedge (`start_railway.py:180-213`). |
| P7-25 | Restart policy | CFG | Default On Failure, 10 restarts (docs `restart-policy`). Not in IaC (docs reference). | Set and record in the dashboard. |
| P7-26 | Graceful shutdown: drain time | IMP | `main.py:135` assumes 60 s; no repo file sets it; default is 0 (docs `variables/reference`) | NEW-RW-1, then LIVE proof. |
| P7-27 | Graceful shutdown of Celery worker and beat | IMP | `start_railway.py:515-531`, `:567-611` install no signal handler | NEW-RW-3. [INF] on PID 1 behaviour. |
| P7-28 | Zero-downtime deploy for the API | LIVE | Docs say healthchecks give zero-downtime only without a volume; backend has none | Needs a live deploy to see overlap. |
| P7-29 | External uptime probe | EXT | Docs: Railway healthcheck is deploy-time only | NEW-RW-9. |
| P7-30 | Railway alerts on CPU, RAM, disk | CFG | Docs `observability` (Pro plan) | Plan tier unknown. |

### 2.4 Databases and migrations

| ID | Item | Class | Evidence | Note |
|---|---|---|---|---|
| P7-31 | Qdrant hosting chosen | EXT | D-26 open (`unresolved-questions.md:34`) | Owner decision. |
| P7-32 | Qdrant service with volume and API keys | CFG | Image pin `docker-compose.prod.yml` (v1.18.0); key split `config.py:711-717`, `services/qdrant/client.py:115-116` | Keys per environment. |
| P7-33 | Serving collection present in staging Qdrant | LIVE | RB 10; finding DATA-01 (`FINAL_PENDING_WORK_REGISTER.md:70`) | Corpus exists only on the owner's Mac. Owner upload required. |
| P7-34 | Encoder dimension check at startup | R | `main.py:599-617`; T3-12 | `config.py` pins dim 1024 (`:2426-2452` validators). |
| P7-35 | Redis service with volume and `noeviction` | CFG | RB 5 | See P7-19. |
| P7-36 | Supabase staging project separate from production | EXT | ADR-015 (`17`) | Owner creates it. |
| P7-37 | Migrations applied to staging by a reviewed step | IMP | No workflow applies migrations (`.github/workflows` check, RB C-8) | NEW-RW-5. Not via pre-deploy (RB 11). |
| P7-38 | Schema snapshot and revert-block checks in CI | R | `supabase-schema-snapshot.yml`, `migration-revert-check.yml`; `MIGRATION_ROLLBACK.md:3-9` (T3-08) | Hosted state is LIVE. |
| P7-39 | Qdrant and Redis loss degrade safely | R | CLAUDE.md policy `[DOC-CLAIM]`; fixture contracts T2-05 (`fixture-stores.yml`) | Fixture proof only; live is Gate B B9. |

### 2.5 Networking

| ID | Item | Class | Evidence | Note |
|---|---|---|---|---|
| P7-40 | Backend binds `0.0.0.0` on `PORT` | R | `start_railway.py:38`, `:651-652`; docs `application-failed-to-respond` | |
| P7-41 | Private DNS to Redis and Qdrant | LIVE | Docs `private-networking/how-it-works` (dual stack only for environments created after 2025-10-16) | Check environment age (RB U-3). |
| P7-42 | Qdrant and Redis reachable if the environment is IPv6-only | CFG | Docs: legacy environments resolve IPv6 only | Set listeners to `::` if legacy. |
| P7-43 | Public domain and TLS | CFG | Docs `networking/domains` (thin) | Generated domain is enough for staging. |
| P7-44 | Forwarded-IP trust matches the Railway edge | LIVE | `config.py:2597-2598`; `main.py:1391-1394`; image default `Dockerfile.railway:115` | Edge source range unverified (RB U-7). |
| P7-45 | Host header filter allows Railway's healthcheck host | R | `main.py:1038-1042`; wrapper answers first (`start_railway.py:465`) | |
| P7-46 | CORS rejects a foreign origin | R | `main.py:1062-1070`, `:1138-1145` | Live check is RB S-6. |
| P7-47 | Faculty gate protects teaching routes | R | `faculty_gate.py:23-32`; `config.py:2484-2490` | SEC-001 (route auth) is open, D-07. |
| P7-48 | Datastores not public | CFG | Docs `databases/redis` (private by default); Qdrant has no public domain in RB 5 | Verify no TCP proxy is left open after the snapshot upload. |

### 2.5b Background jobs

| ID | Item | Class | Evidence | Note |
|---|---|---|---|---|
| P7-49 | Celery worker service | IMP | `start_railway.py:534-611` exists; no IaC service, only an optional script path (`deploy_railway.sh:302-310`) | T9-01. |
| P7-50 | Celery beat service, exactly one | IMP | `start_railway.py:515-531`; `celery_config.py:95-118` | T9-01. Railway cron is not a substitute (docs `cron-jobs`). |
| P7-51 | Worker queue names accepted by the wrapper | R | `start_railway.py:103-114`; prod compose lists `transcription` and `celery` too | Port the compose command with care. |
| P7-52 | Tasks tolerate redelivery | R | `celery_config.py:82-93` (`acks_late`, visibility 3600 s) | Task idempotency per task is not audited here. Unknown. |
| P7-53 | Beat schedules still match the product rules | IMP | `celery_config.py:95-118` includes win-back email dispatch; T1-12 plans its removal | Open task T1-12. |

### 2.6 Resources and economics

| ID | Item | Class | Evidence | Note |
|---|---|---|---|---|
| P7-54 | Memory and CPU limits set per service | CFG | Not in IaC (docs reference) | Backend about 1.81 GB when running `[DOC-CLAIM]`. |
| P7-55 | Real resource use under load | LIVE | T9-02; SYS-008 (load evidence used a mock LLM) | |
| P7-56 | One uvicorn worker, one backend replica | R | `Dockerfile.railway:109`; `start_railway.py:127-163` | Per-replica caps multiply with replicas (RB 13). |
| P7-57 | Volume sizes | LIVE | Docs: volumes cannot shrink | Size from the real collection. |
| P7-58 | Usage limit and alert | CFG | Docs `pricing/cost-control` | Hard limit takes all workloads offline. |
| P7-59 | Provider key limit at OpenRouter | EXT | `config.py:643-648` is app side only | Owner action. |
| P7-60 | Cost per answer recorded | LIVE | T2-03 landed (`app/answer_outcome.py`, `app/metrics.py`) | Real values need staging traffic. |

### 2.7 Post-deployment operations

| ID | Item | Class | Evidence | Note |
|---|---|---|---|---|
| P7-61 | Smoke set with exact commands | R | RB 15 (document and endpoints exist at this head) | Passing is LIVE (A10). Command outputs not run. |
| P7-62 | App rollback | LIVE | Docs `deployment-actions#rollback` (snippet) | Drill needed. Variable behaviour unknown. |
| P7-63 | Data rollback by collection switch | R | `config.py:2308-2327`; contract check `main.py:886` | Live drill in RB 14.2. |
| P7-64 | Backup and restore drill | LIVE | T3-10; SYS-012 (`FINAL_PENDING_WORK_REGISTER.md:84`) | Gate B B9 owns the full drill. |
| P7-65 | Incident playbooks | R | RB 17 | Documented, not drilled. Gate B B11 owns the tabletop. |
| P7-66 | Deploy logs show the effective posture | R | `main.py:1122-1135` | Read on each deploy. |
| P7-67 | Release evidence filed by hash | EXT | D-10 | Owner storage. |
| P7-68 | Stale docs corrected (health gate, drain, grace) | IMP | RB 2, NEW-RW-7 | |

### 2.8 Not applicable

| ID | Item | Class | Reason |
|---|---|---|---|
| P7-69 | Memgraph service | NA | ADR-005 and ADR-015: not deployed. Boot-time effect is risk R-5 (RB 4.3). |
| P7-70 | Railway cron for Beat | NA | Beat is a long-running scheduler. Docs `cron-jobs` say cron services must exit. |
| P7-71 | Replicas for Qdrant and Redis | NA | Volumes forbid replicas (docs `volumes/reference`). |
| P7-72 | Pre-deploy command for migrations | NA | Supabase is external, one-shot, no retry, no volume. See RB 11 for the reason. |
| P7-73 | Frontend on Railway | NA | Vercel (`vercel.json`). The staging frontend origin is an input, P7-20. |
| P7-74 | Monitoring stack on Railway (Prometheus, Grafana, Jaeger) | NA | Hosted alerting is Gate B B10. |

## 3. Blockers for a first staging deploy

These three block the deploy itself, before any runtime check.

| ID | Blocker | Evidence | Fix |
|---|---|---|---|
| X-A1 | `ENVIRONMENT` unset: startup refuses `local` on a production boot | `config.py:2638-2646`; `main.py:761-770` | Set `ENVIRONMENT=staging` |
| X-A2 | No concrete `git_sha`: the first-person production contract fails | `first_person_release.py:119-125`; `release_manifest.py:122-127` | NEW-RW-2 |
| X-A3 | `FACULTY_ACCESS_CODE` unset: startup refuses | `config.py:2484-2490` | Set the code, or an owner decision to opt out (not for staging) |

Other likely blockers, not proven: the Dockerfile path (P7-03) and boot time without Memgraph (P7-23).

## 4. Gate A checklist (staging)

Gate B item B1 re-runs this checklist in the production environment. Each test runs on the exact commit and environment under test. A test that cannot run is UNPROVEN, never passed (`FINAL_PRODUCTION_RELEASE_READINESS.md` section 2).

| ID | Requirement | Test | Pass condition | Depends on | Current blocker |
|---|---|---|---|---|---|
| A1 | Staging environment exists and is described by IaC | `railway config plan` against staging; save the plan | Plan lists redis, backend, worker, beat (and Qdrant if D-26 = Railway); no destructive change | T9-01, D-26 | No staging; one service in IaC (`.railway/railway.ts:15-27`) |
| A2 | Image builds on Railway from the Dockerfile | Build log of a GitHub-triggered deploy | Build uses `backend/Dockerfile.railway` and finishes | A1, P7-03 | Dockerfile path variable not set |
| A3 | Backend deploy passes the healthcheck | Deploy log | Deploy marked successful within 330 s | A2, NEW-RW-8 | Boot time unknown (R-5) |
| A4 | Startup posture is explicit and matches the release record | Read the `Serving posture:` log line | Collection, bridge, fallback, weak_match and scorer model equal RB 6.2; budget caps present | A3, D-14 | D-14 open; variables not set |
| A5 | Release identity is concrete | Deep health or startup log | `git_sha` equals the deployed commit; no "concrete git_sha" error | NEW-RW-2 | X-A2 |
| A6 | Rights register present in the deployed image | `GET /api/health` with the internal token | `rights_register.present=true`, `asset_count>0` | A3 | Not run |
| A7 | Qdrant serving collection loaded and verified | Checks in `22`; RB 10 steps 5-6 | Point count matches the snapshot; `source_text_hash == sha256(verbatim_text)` on every point; dimension 1024 | D-26, NEW-RW-6, D-08 | Corpus only on the owner's Mac (DATA-01) |
| A8 | Private networking works | Backend log shows Qdrant and Redis connected; `GET /api/ready` returns 200 | 200 and no connection errors | A3, A7 | Not run; environment age unknown |
| A9 | Migrations applied by the reviewed step | CLI migration list vs local; RB 11 steps 2-7 | Remote head equals the release commit's head; RLS checks pass | NEW-RW-5, Supabase staging project | No migration procedure or workflow |
| A10 | Smoke set passes | RB 15, S-1 to S-15 | Every expected result matches; crisis, greeting, in-corpus, out-of-corpus, auth rejection and CORS rejection all pass | A4-A9 | Not run |
| A11 | Worker and exactly one beat run | Worker and beat logs; Railway replica count | Worker shows Celery ready; beat shows scheduler start; beat replicas = 1 | A1 | Not deployed |
| A12 | Graceful shutdown works | Deploy a no-op change; read old-instance logs; send SIGTERM test to worker and beat | Backend logs "Graceful drain complete"; Celery child exits cleanly | NEW-RW-1, NEW-RW-3 | Drain not set; no signal forwarding |
| A13 | Rollback works | Roll back one deploy in the dashboard; then switch the collection by variable (RB 14.2) | Previous deployment serves; collection switch passes smoke checks S-8 to S-11 | A10 | Not drilled |
| A14 | Redis policy is `noeviction` | `redis-cli CONFIG GET maxmemory-policy` from a private shell | `noeviction` | A1, NEW-RW-4 | Script sets `volatile-lru` |
| A15 | Spend controls active | Smoke S-15 and the provider key limit screenshot | Controlled budget error; provider limit set | A10 | Provider limit not set |
| A16 | Usage limit and Railway alert configured | Dashboard screenshot | Hard limit and an email alert set | A1 | Not set |
| A17 | External uptime probe alerts | Stop the backend on purpose | Alert reaches the owner within the target in RB 20 item 8 | NEW-RW-9 | No probe |
| A18 | Volumes sized and backed up once | One manual volume backup and one Qdrant snapshot copy off Railway | Both exist and are listed | A7 | Not run. Full restore drill is Gate B B9 |
| A19 | Evidence filed | Evidence index lists SHA, plan output, logs, smoke output by hash | All present | D-10 | No evidence store decision |
| A20 | CI passes on the release commit (added by the lead 2026-11-05) | GitHub Actions run for the exact commit, from a clean checkout | All required workflows pass | T0-03 branch protection | CI failed on every workflow at `c9b42d3e` (GitHub Actions run list checked by the lead on 2026-11-05, [V-GIT]); the owner is fixing it |
| A21 | Staging is reachable only by named testers (added by the lead 2026-11-05) | Access test from an unlisted account and from no account | Both are refused | D-29, D-07 | Access model not decided |

Gate A passes when A1 to A19 pass on one commit in one staging environment. Today none has been run. Status: NO (conditional): conditional on D-26, the owner's snapshot, the staging Supabase project and the code changes NEW-RW-1 to NEW-RW-5.

## 5. Not covered here

Load at target concurrency (B8), restore drills (B9), alerting rules (B10), incident tabletop (B11), P0 findings IP-001 and X-06 (B2), and all Gate C items: see `FINAL_PRODUCTION_RELEASE_READINESS.md`.


## Gate A ID mapping (added by the lead 2026-11-05)

This table is the authoritative Gate A list (A1-A21). A first draft in `FINAL_READINESS_AND_GAP_ANALYSIS.md` used A1-A12. The FR/NFR matrix and the reliability spec were remapped to these IDs. Old to new: A1 CI -> A20; A2 build -> A2; A3 config method -> A1; A4 variables and startup checks -> A4 (with A3, A6); A5 Qdrant -> A7; A6 Redis and worker -> A11, A14; A7 liveness -> A3; A8 auth and CORS -> A10 (smoke S-cases); A9 not public -> A21; A10 smoke -> A10; A11 rollback -> A13; A12 spend -> A15, A16.

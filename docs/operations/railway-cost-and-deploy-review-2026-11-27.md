# Railway cost and deploy review (2026-11-27)

Evidence: Railway usage, metrics, deployment history and logs read through the Railway CLI and MCP on 2026-11-27.
Nothing here was changed except the one setting listed under "Changed". The guard
`scripts/ops/railway_live_audit.py` re-checks the live configuration against these findings.

## Cost
- Billing period Nov 11 to Dec 11: **$14.31 so far, projected $41.94**; soft limit $30, hard limit $60 (a hard limit takes every workload offline). The previous period cost $0.45 because the stack was scaled down, so the "upsurge" is mostly the stack being switched back on.
- **Memory is $13.95 of the $14.31 (98%).** CPU $0.16, volumes $0.17, backups $0.01, egress under $0.01. The 50 GB volume is not a cost problem.
- Memory by service (7-day average): backend 4.8 GB (peak 18 GB, 6 GB container cap, CPU 0.02 vCPU, so idle), celery-worker 1.2 GB, the two Memgraph services 0.5 and 0.7 GB, Qdrant 0.4 GB, Redis 0.02 GB.
- Not cost drivers: HTTP traffic (a one-hour burst of 459 `GET /api/capabilities` from 303 IPs in two ISP ranges, one identical user agent, aimed at the default Railway domain; 9 ms each), chat volume (201 requests over Nov 23 to 25, 2 source IPs), GitHub Actions (public repo, free minutes), egress.
- Not visible from here: OpenRouter spend, Vercel build minutes, Supabase usage. Check those dashboards directly.

## Deploys
- **celery-worker rebuilt on every push to `main`**: 30 deployments in about 25 hours, each a full image build (torch plus model downloads), for a service whose job is `celery-on-demand: no queued work, exiting` once a night (cron `0 0 * * *`, about 2 seconds).
- The last 5 celery deployments (from the #114 merge at 05:39 UTC on Nov 26) **failed at `CREATE_CONTAINER` with "An unknown error"**. The build itself succeeds and the image is pushed; there are no runtime logs. The last good one is the #119 commit (`9551c2d`). Production is unaffected because the cron keeps running that last good image. Cause not determined: take a failing deployment id to Railway support.
- **The backend was running a Nov 24 build (`7d9cde2`), 146 commits / 302 backend files behind `main`** (the service config also lists a `commitSha` of `285f2d4`, which is not what was deployed). Merged is not deployed: today's safety fix (bereavement SEVERE no longer downgraded) was not in production. Changing a variable later that day rebuilt the service from current `main`.
- A staged patch from Nov 22 (a `META_APP_SECRET` variable and a backend resource update) was never applied.

## Configuration drift found (live vs repo invariants)
| Finding | Live value | Required |
|---|---|---|
| `FIRST_PERSON_LLM_FALLBACK_ENABLED` on the backend | **true** | false (binding owner directive 2026-11-23); it also makes unanswered questions cost LLM money |
| OpenRouter caps | $50/day, $500/month | repo defaults $10 and $40 |
| Serving posture | backend `v13_shadow`, celery `v10_only` | one posture |
| Memgraph | two services (3.12.0 with a 50 GB volume, 3.14.0 with 2 GB); apps use `memgraph.railway.internal`; the 50 GB one also has a public TCP proxy | one service, no public database port |
| Wait for CI on celery-worker | off | on |

## Changed
- `celery-worker` watch patterns set to `/backend/**`, `!/backend/tests/**`, `!/backend/**/*.md`, `/memory/**`, `/config/helplines.yaml`, `/scripts/ops/rotate_brain_kek.py` and the rights manifest, so docs, tests, frontend, CI and workflow pushes no longer rebuild it. Rollback: set the service's watch patterns back to empty.

## Decisions for the owner
1. Done 2026-11-27 with the owner's approval: `FIRST_PERSON_LLM_FALLBACK_ENABLED=false` on the backend. Setting a variable rebuilds the service from current `main`, so it also deployed `main` (see item 2).
2. That deploy of `main` is the owner-approved side effect to verify: it keeps the old container serving until the new one passes `/api/healthz`. Confirm the Railway Qdrant has `first_person_v13_shadow`, review the staged patch, and run the smoke battery against the live domain.
3. Which Memgraph to keep; close the public TCP proxy unless something needs it; snapshot before deleting anything.
4. Lower the OpenRouter caps (suggested ceiling $15/day, $150/month unless a graded run needs more).
5. Limits: after the cuts the projection should fit; keep the hard limit as a guardrail but raise the soft limit above the expected bill so the alert means something.
6. Backend memory: a 4.8 GB average for an idle service is the bill. Options: keep sleep mode and accept cold starts, cap the container, or move the models out of the request process.

## Guard
`python3 scripts/ops/railway_live_audit.py` (read only; exit 0 clean, 1 warnings, 2 critical). Run it before and after any Railway change.

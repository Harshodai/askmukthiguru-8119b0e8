<!-- Archived verbatim from root CLAUDE.md on 2026-10-19 to cut per-session context cost. Not auto-loaded. Text is dated: verify against code and lessons.md before relying on any number. -->

# Archived from CLAUDE.md: ops-supabase-concurrency-observability

## Production Supabase readiness audit

`backend/scripts/ops/audit_supabase_readiness.{py,sql}` is a strictly
read-only gate (SELECTs against `information_schema`/`pg_catalog` only —
never mutates anything) for the exact defects above. Run the `.sql` version by
pasting it into the Supabase Dashboard SQL Editor; run the `.py` version with
`SUPABASE_DB_URL='postgresql://...' python backend/scripts/ops/audit_supabase_readiness.py`.

**Verified against production (`ozmjeuqbholoxypfxixb`), 2026-09-14: 41/41 PASS,
0 FAIL.** All 10 required tables exist and are `service_role`-readable
(including `canonical_memory_events`, the table missing 2026-09-12); RLS is
enabled on `canonical_memories`/`canonical_memory_events`/`conversation_memories`;
the `canonical_memory_events_actor_check` constraint admits `user`/`resolver`/
`consolidator`; and every public table in the schema is readable by
`service_role` — no residual gap beyond the 10 tracked here.

Run via the Supabase Management API's `database/query` endpoint (the same
query executor the Dashboard SQL Editor calls, `read_only: true`), not a
literal browser click-through — no Claude in Chrome session was available at
verification time. Same execution path, not a substitute claimed to be one.

**A prior run of this same script reported 11 FAILs, including "78 unreadable
tables," against this same healthy production database — all 11 were false
positives from a bug in the audit itself, not a real defect. Both scripts
read grants from `information_schema.role_table_grants`, which only exposes
grants where the CONNECTING role is the grantor, the grantee, or a member of
the grantee. The Supabase SQL Editor connects as `supabase_read_only_user`,
which is none of those for `service_role`, so the view returned zero rows and
the audit declared a fully-granted database entirely ungranted. Locally the
script had connected as a superuser that could see every grant, so the bug
was invisible there and only ever wrong in the one place operators actually
run it. Fixed (commit `8f620d91`) by switching to `has_table_privilege`,
which queries the catalog directly and does not care who is connected.
Verified the fix does not just report PASS unconditionally: the predicate
still discriminates on production — `anon` fails 8/78, `authenticator` fails
78/78, `service_role` fails 0/78.**

**Write-privilege checks added 2026-09-14** (commit `dde2dc1b`): the audit
previously checked SELECT only. INSERT/UPDATE/DELETE are separate GRANTs in
Postgres, so a table passing every read check could still silently 42501 on
the write the backend actually issues. Adds `grant_write:<table>:<verb>`, one
per (table, verb) pair grepped from real `.insert(`/`.update(`/`.upsert(`/
`.delete(` call sites in `backend/` — not assumed. `canonical_memory_events`
intentionally has no UPDATE/DELETE requirement: it is an append-only ledger,
and granting either would be a privilege escalation, not a fix. `profiles`
and `user_healing_progress` carry no write requirement either, because no
write call site exists for them anywhere in `backend/` (`profiles` is
populated by Supabase auth, not app code) — verified against production:
16/16 write-grant checks PASS.

Re-run this audit after any migration that touches grants, RLS, or the actor
constraint, and after any `supabase db reset` on a local/staging environment.

### Beyond the script's scope: RLS policy content, backups, auth config (verified 2026-09-14)

The audit above proves RLS is *enabled* and grants are correct; it does not
read policy bodies or anything outside the database. Checked separately,
against production, via the Supabase Management API (`GET
/v1/projects/{ref}/database/backups`, `/config/database/pooler`,
`/config/auth`) and `pg_policies`/`pg_proc`:

- **RLS policy content — verified correct, no bypass found.** Read the actual
  policy bodies (not just enabled-ness) for all 3 required tables plus
  `user_roles`, `profiles`, `memory_outbox`, `memory_consent_receipts`,
  `memory_deletion_receipts`, `chat_responses`, `user_healing_progress`,
  `memory_audit_events`. Every owner-scoped policy is `auth.uid() = user_id`
  (or `id = auth.uid()` on `profiles`); no `qual: true` for `anon`/
  `authenticated` anywhere. The `anon` role's table-level INSERT/UPDATE/DELETE
  GRANT on `canonical_memories` (flagged as a red flag in the negative-control
  check above) is a non-issue in practice: those policies are scoped to
  `roles={authenticated}` only, so `anon` matches zero policies and RLS
  default-deny blocks it regardless of the grant. The admin bypass
  `has_role(auth.uid(), 'admin'::app_role)` is `SECURITY DEFINER` with a
  pinned `search_path`, reads `user_roles` directly, and `user_roles` INSERT
  is itself gated by the same function — no self-elevation path.
  **Non-security cruft**: `conversation_memories` carries 5 overlapping
  policies from different migration eras (duplicate owner-SELECT, duplicate
  owner-ALL/INSERT). Not a hole — every clause independently requires
  ownership or admin — but worth consolidating.

- **Backups / PITR — real gap, not a misconfiguration.** `walg_enabled: true`,
  `pitr_enabled: false`, `backups: []` — zero backups exist. This project is
  on the Supabase **Free plan**, which does not offer daily backups or PITR at
  any settings combination. If prod data is lost, there is nothing to restore
  from on the Supabase side. Matches `docs/RELEASE_READINESS_2026_07_30.md`'s
  own unresolved checklist item for leaked-password protection below — same
  root cause (Free plan), independently discovered.

- **Auth config — one known gap, one previously undocumented.**
  `password_hibp_enabled: false` (leaked-password protection is OFF).
  `docs/RELEASE_READINESS_2026_07_30.md` already tracks this as
  `🟡 Conditional — Requires Pro plan + dashboard toggle` with an unchecked
  release-checklist box — this is a known, still-open item, not a new
  regression, and it is blocked on the same Free-plan constraint as the
  backups gap. `password_min_length: 6` and `security_captcha_enabled: false`
  are separate soft spots not previously flagged anywhere in this repo.
  `site_url`/`uri_allow_list` correctly point at `lovable.app` — matches the
  documented "Lovable frontend-only decision," not a bug.

- **Connection pooling — configured, largely moot.** Supavisor pooler is live
  (`aws-1-ap-northeast-1.pooler.supabase.com:6543`, transaction mode, SCRAM
  auth), but the app talks to Supabase over PostgREST (HTTP) for every write
  call site found in `backend/`, not raw Postgres connections, so PostgREST's
  own connection management is what is actually load-bearing here.

- **Unrelated to Supabase, found in passing — the production backend itself
  was unreachable at verification time**: `GET
  https://askmukthiguru-8119b0e8-production.up.railway.app/api/health` ->
  `502 Application failed to respond`, and `/api/healthz` (the 180s-grace
  stub in `start_railway.py`) timed out entirely rather than answering. Not
  investigated further — that is Railway deploy/runtime territory, not
  Supabase. Re-check before trusting any "prod is up" claim elsewhere in this
  file; it decays fast and was not re-verified after this was written.

## Native model concurrency invariant (2026-09-18)

**Any shared PyTorch/transformers module in this process is exclusive at
inference.** Not for correctness of the output — for the survival of the
interpreter. `LettuceDetectService._shared_detector` is a `ClassVar` (one torch
module per process) and `score_faithfulness` runs from a thread per in-flight
chat; concurrent `forward()` on it produced `Fatal Python error: Segmentation
fault` under a 6-request burst, at 4.11 GiB of a 6 GiB limit with
`OOMKilled: false`. The two audit findings that recorded those crashes
(AMK-B-002, AMK-C-001) both diagnosed memory exhaustion; both were wrong, and
their corrections are inline in `audit/track_{B,C}_findings.md`.

- Torch modules: hold an exclusive lock. `lettuce_detect_service`
  (`_shared_predict_lock`), `reranker_service` (`_torch_predict_lock`),
  `embedding_service` (`_inference_lock`, which already did this).
- ONNX Runtime sessions: `session.run()` IS thread-safe — no lock. They go under
  `services/native_inference_gate.py` instead, which is a **memory** bound and
  nothing else (`native_inference_max_concurrent`, default 6). It did not fix
  the crash and could not have.
- `/api/health` reports `native_inference_gate` next to `chat_backpressure`. The
  second number is the one that predicts trouble; admission can look healthy
  while inference queues.
- `max_concurrent_chat` defaults to **12** per worker (`backend/app/config.py`). On the Railway Pro target (32 GB) memory
  does not bind until ~73 concurrent (~324 MB marginal per chat over a ~2300 MB
  model baseline). The binding limits are the OpenRouter account rate limit and
  the now-serialized verification pass. Re-derive with
  `backend/scripts/ops/gate1_load_test.py` (asserts container survival, restart
  count and peak memory; exits non-zero on breach) — never by guess. Full
  write-up: `docs/engineering-notes/concurrency-ceiling-2026-09-18.md`.
- `docker-compose.yml` runs two watchdogs. `autoheal` watches Docker HEALTHCHECK
  transitions and therefore only ever sees a *running* container; it logged
  nothing across the whole outage. `liveness-watchdog` covers the `Exited`/`dead`
  case, skipping exit codes 0 and 143 so an intentional `docker stop` is
  respected.

**Memory as verification evidence (AMK-B-006).** `rag/nodes/verification.py`'s
`_verification_context` admits `canonical_memory_evidence` — user-stated facts —
as a second evidence class, capped at `MEMORY_EVIDENCE_MAX_CHARS`. The doctrine
threshold is unchanged. The broader `memory_context` is deliberately NOT
admitted: it carries persona text and prior assistant turns, and grounding an
answer in the system's own earlier output is circular. Memory never enters
`relevant_docs`, so `extract_citations` can never attribute it to a teacher — it
can ground a sentence, never source one.

## Observability: on by default (2026-09-18)

`docker compose up -d` now starts **Jaeger, Prometheus, Alertmanager and
Grafana**. They were all already in the repo, all behind
`profiles: [observability]`, and therefore had never run. Four independent
silent failures had to be fixed before any of it worked; see
`lessons.md` L-OBS-1 for the full account.

| Surface | URL | Notes |
| :--- | :--- | :--- |
| Jaeger traces | http://localhost:16686 | `OTEL_ENABLED` now defaults to **true** (was `false`). `app/observability.py` TCP-probes the collector at startup and warns loudly when nothing is listening, so a bad endpoint is visible rather than silently dropping spans. |
| Prometheus | http://localhost:9090 | Scrapes `/internal/metrics`, **not** `/metrics`. |
| Alertmanager | http://localhost:9093 | Self-contained config, no PagerDuty/Slack secret needed. |
| Grafana | http://localhost:3000 | Provisioned Prometheus datasource + "MukthiGuru Performance Monitoring" dashboard. |

**`/metrics` vs `/internal/metrics`.** `/metrics` is `Depends(require_aal2)` +
admin and stays that way — it exposes system internals. Prometheus cannot hold
an AAL2 Supabase session, so scraping it returned `401` forever and every alert
rule evaluated against no data. `/internal/metrics` serves the identical
exposition behind `METRICS_SCRAPE_TOKEN`:

- **Fails closed** — token unset (the default) means the endpoint 404s. An
  absent secret grants nothing, and the failure shows as a DOWN Prometheus
  target rather than as silence.
- Constant-time compare; excluded from the OpenAPI schema.
- It is a *separate* credential, never a fallback for a failed admin check. Do
  not "simplify" this by relaxing the guard on `/metrics`.

Generate a token with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`
and set `METRICS_SCRAPE_TOKEN` in `backend/.env` (never committed; documented in
`backend/.env.example`). Both the backend and Prometheus read it from there.

**Two alertmanager configs, on purpose.** Compose mounts
`infrastructure/prometheus/alertmanager.local.yml` — self-contained, no
notifier, no secrets; alerts group, inhibit and resolve and are read in the
Alertmanager UI. `alertmanager.yml` remains the **production** artifact
(PagerDuty + Slack receivers, rendered from `alertmanager.template.yml` with
`envsubst`) and is asserted by
`tests/test_observability.py::test_alertmanager_config_validity` — do not
repurpose it. Mounting it directly is what previously made the container
unstartable: it carries seven unrendered `${...}` placeholders and Alertmanager
validates receiver URLs at config load.

### Error Tracking & GlitchTip Decision (2026-09-19)

Server-side error tracking SDK (GlitchTip/Sentry, AMK-F-003) is **skipped for the initial pilot deployment** per user decision. Railway provides native log aggregation, structured log tailing, and crash alerting. Backend exceptions are captured with structured JSON formatting (`error_id`, `correlation_id`, full traceback) by `global_exception_handler` (`app/main.py:1158-1172`) and streamed to Railway logs. Revisit dedicated GlitchTip deployment on Railway + Postgres in Phase 2 if centralized alerting and deduplication are required.


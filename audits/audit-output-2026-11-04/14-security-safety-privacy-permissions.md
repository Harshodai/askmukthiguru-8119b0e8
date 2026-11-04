# 14 — Security, privacy, and data protection

Owner: S1. Target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`.

> **Addendum (lead, after the independent review in `26`).**
> - **ADV-02 (P2):** user data reaches processors that no privacy document lists. These are the Lovable AI gateway (`supabase/functions/memory-extract/index.ts:25`, `memory-extract-drain:22`, the STT fallback, admin ask, eval-run), Sarvam STT (`supabase/functions/sarvam-stt:7-8`), Sentry error replays (`src/lib/sentry.ts:15-26`), SMTP and web push. Task T6-08: a processor inventory, a privacy-notice update, and routing memory extraction through the backend LLM gateway or documenting it with consent.
> - **ADV-01 (P1):** scheduled account deletions never run (no purge job), and immediate deletion needs the backend up. This extends SEC-004. Tasks: T6-06, T1-12.
> - **ADV-03 (P1):** the first-person kill switch fails open to generation. Task: T1-05.
Companion documents: **14b** safety, crisis and spiritual trust (S3); **14c** content permissions and IP register (S4).
Related: request flow (05), code debt (13), reliability (15), memory design (12).

## 1. Summary

| # | Statement | Label |
|---|---|---|
| 1 | The security baseline is above average for a solo project: admin needs AAL2 MFA plus a `user_roles` row; service-role JWTs over HTTP are not superusers; anon sessions are HMAC-signed; production validators refuse to start without secrets; RLS is enabled on all 83 created tables; gitleaks blocks in CI. | [V-STATIC] |
| 2 | The largest exposure is economic, not data theft: `POST /api/first-person/query` is unauthenticated, outside the anon quota, and runs up to 3 LLM calls per request (SEC-001), and the OpenRouter spend cap is off by default in code (SYS-004, doc 15). | [V-STATIC] |
| 3 | Privacy gaps sit at the edges: crisis text in INFO logs, user questions stored without a user link, account erasure that cannot complete while the backend is down. | [V-STATIC]; runtime [LIVE-R] |
| 4 | The repository is public (task list N1 [DOC-CLAIM]). It tracks corpus-derived backups and a security report with local paths. | [V-STATIC] |
| 5 | Nothing here is verified on a deployed system. Railway is down; Supabase was not contacted. | [LIVE-R] |

## 2. Positive controls (keep)

| Control | Evidence | Label |
|---|---|---|
| Admin routes: `require_aal2` + admin role in `user_roles` (cached, bounded TTL) | `app/api/admin.py:66-68`; `services/auth_service.py:500-568, 822` | [V-STATIC] |
| `service_role` JWT over HTTP is downgraded, not superuser | `services/auth_service.py:454-470` | [V-STATIC] |
| Anon identity: server-signed session token, user id rewritten to `anon:<payload>` | `backend/CLAUDE.md`; `chat.py:797` | [V-STATIC] |
| Secure-by-default config: `is_production=True`; startup fails without `anon_session_hmac_secret`, `brain_kek`, `faculty_access_code`; `enable_test_auth` forbidden in production; wildcard hosts/IPs refused | `app/config.py:1095, 2347-2620` | [V-STATIC] |
| Tracked env files hold only public client values (Supabase URL, publishable key, Google client id) | `.env.production`, `.env.mobile`; test `backend/tests/test_tracked_env_files_no_secrets.py` | [V-STATIC] |
| gitleaks blocking with 3 narrow allowlist strings | `.gitleaks.toml` | [V-STATIC] |
| RLS enabled on every created table (83); permissive `router_decisions` policies later replaced by admin-only | `supabase/migrations/*`, `20260715000000_harden_linter_warnings.sql:44-50` | [V-STATIC]; live DB [LIVE-R] |
| Second Brain vault: per-user DEK wrapped by a passphrase-derived KEK (PBKDF2 600k) | `app/api/second_brain.py:55-75` | [V-STATIC] |
| CORS: explicit origins with credentials; wildcard entries become anchored regexes; compose requires `CORS_ORIGINS` | `app/main.py:1030-1110`; `backend/docker-compose.yml:388` | [V-STATIC] |
| Log-injection sanitiser | `app/sanitization.py:106-113` | [V-STATIC] |
| WhatsApp webhooks verify Twilio and Meta signatures with constant-time compare; phone numbers masked in logs | `whatsapp_bot/wa_bot.py:103, 874-930, 1539, 1809` | [V-STATIC] |
| Account deletion fails closed if the backend memory purge does not confirm | `supabase/functions/delete-my-account/index.ts:46-62, 133-134` | [V-STATIC] |
| HF model loads pinned by commit SHA; reranker model id allowlisted | `backend/CLAUDE.md` "HF model pins"; `services/onnx_reranker.py` | [DOC-CLAIM] + [V-STATIC] partial |
| CI: CodeQL, dependency-check (npm audit, pip audit, license, trivy-fs), security-audit, nightly RLS | `.github/workflows/*` | [V-STATIC]; current red/green state [DOC-CLAIM] task list N3 |

## 3. Route exposure (AST scan of 231 handlers)

| Category | Count | Notes |
|---|---|---|
| Admin (`_require_admin` → AAL2 + role) | 91 + others | all of `admin.py` |
| Strict user auth | 67 | |
| AAL2 | 22 | metrics, drills, retention admin |
| Optional user (anon allowed, quota applies on chat) | 14 | chat endpoints |
| Unauthenticated | 24 | listed below |

Unauthenticated handlers [V-STATIC]: health/ready probes (4), `/` root, `/.well-known/jwks.json`, `/api/auth/anon-session`, `/api/auth/register` (disabled stub), `/api/capabilities`, `/api/teachings/tips`, `/api/contact`, waitlist signup, `/api/memory/knowledge-graph` (anonymous view allowed, `memory.py:803-815`), `/api/memory/knowledge-graph/export` (flag `kg_export_enabled`), `/api/media/videos/{video_id}` (`ingest.py:561`), **`/api/first-person/query`** (`first_person.py:297`). The 8 `second_brain` handlers appeared unauthenticated to the scan but use `_authed_user_id` (`second_brain.py:68-75`) — false positive.

## 4. Findings

### SEC-001 — Unauthenticated first-person query endpoint bypasses the anon quota and spends LLM budget
| Field | Value |
|---|---|
| Pillars | P1, P4 |
| Category | Abuse / cost exposure |
| Severity | P1 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `app/api/first_person.py:297-301`: no user dependency, no `_enforce_anon_quota`; `@limiter.limit(first_person_rate_limit)` = `"120/minute"` (`config.py:1191`) keyed on client IP (`app/core/limiter.py:48`). It builds the pipeline with the live LLM service (`first_person.py:~320`) and calls `pipeline.execute` in a thread. Route is enabled by default (`first_person_route_enabled=True`, `first_person_mode="retrieval_only"`, `config.py:184, 222`). |
| Actual behaviour | One IP can issue 120 requests per minute, each with up to 3 LLM calls (rerank, answerability, relevance), with no account and no 5-message limit. Many IPs scale this linearly. |
| Expected behaviour | Same identity, quota and budget controls as `/api/chat`, or admin-only if the endpoint is only for tools. |
| Root cause | The endpoint predates the LLM gates (it was "retrieval only, no LLM"); the gates were added inside the shared pipeline. |
| User impact | Budget exhaustion denies service to real seekers; with SYS-004 the spend may be uncapped. |
| Downstream impact | Thread-pool saturation (SYS-003). |
| Dependencies | S4 to confirm whether the frontend calls this route (doc 03). |
| Remediation | Require `get_optional_user` + `resolve_anon_identity` + `_enforce_anon_quota`, or restrict to admin. Lower the IP rate to the chat value. |
| Acceptance criteria | Anonymous call without a session token → 401; sixth call in 24 h with a token → 429 `quota_exceeded`. |
| Regression test | `tests/test_first_person_route_quota.py` (new). |
| Implementation risk | Low. |
| Verification | [V-STATIC] |

### SEC-002 — Public video streaming endpoint
| Field | Value |
|---|---|
| Pillars | P4 |
| Severity | P2 |
| Type | Architectural risk |
| Confidence | Medium |
| Evidence | `app/api/ingest.py:561-600` "Stream a direct uploaded video … (Public)"; only an id regex and an admin block list guard it. |
| Actual behaviour | Any uploaded video file that exists on the server is streamable by id without auth. |
| Expected behaviour | Serving follows the rights register (doc 14c); default deny for assets without a cleared rights basis. |
| Remediation | Gate on rights status, or signed short-lived URLs. |
| Acceptance criteria | A video without `rights_basis` in the register returns 404. |
| Verification | [V-STATIC]; which files exist on a deployment [LIVE-R]. |

### SEC-003 — Crisis and personal text written to INFO logs
| Field | Value |
|---|---|
| Pillars | P4, P6 |
| Category | Privacy |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `rag/intent_prerouter.py:92` logs `query[:50]` when the DISTRESS regex matches; `rag/resolve_followup.py:195, 255, 258` log 60 characters of the question at INFO; 75 log statements reference query variables (rg count). Tracked `data/security_report.json` already flagged "Possible PII in log statements" (WARN). |
| Actual behaviour | The most sensitive messages (distress) are the ones guaranteed to be logged. Logs go to stdout and to any log sink. |
| Expected behaviour | Log hashes, lengths and route decisions, never user text, at INFO. |
| Remediation | Replace text fragments with `_query_token()` (exists, `pipeline_coordinator.py:55`); add a lint guard for `logger.*(…query…)` patterns. |
| Acceptance criteria | Guard test: no log call in `app/`, `rag/`, `services/` formats a variable named `query|question|user_msg|message` without a hash wrapper. |
| Implementation risk | Low. |
| Verification | [V-STATIC] |

### SEC-004 — Erasure gaps and erasure availability
| Field | Value |
|---|---|
| Pillars | P5, P6 |
| Category | Privacy / DPDP |
| Severity | P2 |
| Type | Probable defect |
| Confidence | Medium |
| Evidence | (a) `public.router_decisions` stores `query_text` with no user column (`supabase/migrations/20260626062100_create_router_decisions.sql:14-21`), so per-user erasure cannot find it. (b) `telemetry_events.user_id … ON DELETE SET NULL` (`20260618045331_*.sql:15`) keeps rows. (c) `delete-my-account/index.ts:48-62` refuses deletion unless `BACKEND_URL` answers; the backend has been down since 2026-08-23 [DOC-CLAIM task list §1 cause 4]. (d) FKs to `auth.users` without `ON DELETE` on `staging_quality_queue.reviewed_by` (`20260702150000_*.sql:28`) and `daily_teachings.created_by` (`20260506061859_*.sql:69`) block deletion of those accounts. (e) `user_feedback` and `chat_responses` text are not in the edge function's delete list [INF: they may cascade via `chat_sessions`]. |
| Actual behaviour | A user's question text can outlive account deletion; deletion is impossible while the backend is down; reviewer/admin accounts cannot be deleted. |
| Expected behaviour | Every table holding user text either cascades from the user or is purged by the erasure job; erasure works when non-essential services are down (queue and complete later with a receipt). |
| Remediation | Add `user_id` (or hashed anon id) to `router_decisions` with cascade, or stop storing raw text; add `ON DELETE SET NULL` to the two admin FKs; make the edge function enqueue a durable erasure job when the backend is unavailable and return 202 with a receipt. |
| Acceptance criteria | Erasure test on a seeded staging DB: after deletion, `SELECT` over every table with a text column finds 0 rows containing the seeded marker string. |
| Regression test | `nightly-rls.yml` extension or a new staging erasure drill. |
| Implementation risk | Low-medium (migrations). |
| Verification | [V-STATIC]; live schema [LIVE-R]. |

### SEC-005 — Public repository tracks corpus backups and internal reports
| Field | Value |
|---|---|
| Pillars | P4 |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `data/` (10 MB): `neo4j_graph_dump.json` (8 MB), `qdrant_chunk_reclean_backup_*.json` (chunk text derived from teachings), `qdrant_lightrag_*_orphan_backup.json`, `security_report.json` (contains `/Users/<owner>/…` absolute paths). The repo is public [DOC-CLAIM task list N1]. |
| Actual behaviour | Derived teaching text and internal topology are published. |
| Expected behaviour | Corpus artefacts live in private storage under the rights register. |
| Remediation | Move to private storage; decide on history rewrite [HUMAN]. Rights analysis: doc 14c. |
| Acceptance criteria | `git ls-files data/` empty; publication guard blocks `*.json` backups. |
| Verification | [V-STATIC] |

### SEC-006 — Datastore ports exposed on all interfaces; Qdrant without an API key; unpinned Memgraph image
| Field | Value |
|---|---|
| Pillars | P1 |
| Severity | P2 |
| Type | Architectural risk |
| Confidence | Medium |
| Evidence | `backend/docker-compose.yml`: `"6379:6379"` (Redis, has `--requirepass`), `"6333:6333"`, `"6334:6334"` (Qdrant, no `QDRANT__SERVICE__API_KEY` in compose), `"7687:7687"`, `"7444:7444"` (Memgraph, password set); `image: memgraph/memgraph-mage:latest` (line 45). |
| Actual behaviour | On any host without a firewall, Qdrant is readable and writable by anyone who can reach port 6333. |
| Expected behaviour | Bind to `127.0.0.1` or an internal network; Qdrant API key; pinned image digests. |
| Remediation | `127.0.0.1:` prefixes; `QDRANT__SERVICE__API_KEY` + client config; pin `memgraph-mage` by version or digest. |
| Acceptance criteria | `docker compose config` shows no `0.0.0.0` datastore ports; Qdrant rejects unauthenticated requests. |
| Verification | [V-STATIC]; how Railway networks them [LIVE-R]. |

### SEC-007 — Prompt-injection surface (cross-ref S3, doc 09/14b)
| Field | Value |
|---|---|
| Pillars | P2, P4 |
| Severity | P2 |
| Type | Architectural risk |
| Confidence | Medium |
| Evidence | FP LLM gates receive clip text but may only return indices, YES/NO, or a 0–3 score (`first_person_pipeline.py:1199-1215`, `1448-1470`, `1023-1103`), so injected text can at most change a ranking. The general graph sends retrieved chunks and web-search results (`web_search` node, `OFFICIAL_ALLOWED_DOMAINS` / `GENERAL_ALLOWED_DOMAINS`, CLAUDE.md) into a generating prompt. |
| Actual behaviour | Low impact on the FP lane; real impact on the general lane. |
| Expected behaviour | Retrieved content delimited as data; output schema validation; injection test set in CI. |
| Remediation | Owned by S3 (prompt architecture). |
| Verification | [V-STATIC] partial |

### SEC-008 — CORS wildcard-to-regex with credentials
`app/main.py:1030-1040` turns `*.example.com` into `https://[^/]+\.example\.com` and keeps `allow_credentials=True`. If an operator lists a multi-tenant host (for example a Lovable or Vercel wildcard), every tenant on that platform becomes a credentialed origin. Current deploy script sets an exact origin (`scripts/deploy/deploy_railway.sh:223`). Severity P3, Architectural risk, [V-STATIC]. Fix: reject wildcard origins in production instead of converting them.

### SEC-009 — Legacy WhatsApp JWT signer with insecure default
`whatsapp_bot/wa_bot.py:72` defaults `JWT_SECRET` to `"default-dev-jwt-secret"`; the signer (`wa_bot.py:738-753`) is "retained for compatibility" and the backend no longer trusts it. Severity P3, Confirmed (dead code with insecure default) [V-STATIC]. Remove (CQ-R8).

### SEC-010 — Unauthenticated deep health check
`/api/health` and `/api/health/services` (`health.py:162-200, 547`) run live dependency checks for anonymous callers, bounded by `_HEALTH_HARD_BOUND_SECONDS`. Severity P3, Architectural risk [V-STATIC]. Fix: keep `/api/healthz` public and cheap; put the deep check behind the metrics token or cache its result for 10 s.

## 5. Privacy and DPDP posture

| Area | State | Gap | Label |
|---|---|---|---|
| Consent for memory | Server-side consent receipt is the source of truth; fails closed (PR #76) | Consent copy and versioning reviewed by S3/S4 | [V-GIT] PR #76 body |
| Erasure | Edge function + backend purge; cascades fixed for consent receipts (`20261021000100_*.sql:98`) | SEC-004 | [V-STATIC] |
| Retention | Celery `cleanup_retention_data` (90 days telemetry, staging queue); `compliance_retention_days=365` (`config.py:1220`) | Retention for `router_decisions` text not evident | [V-STATIC] |
| Logs | Sanitised for injection, not for content | SEC-003 | [V-STATIC] |
| Anonymous users | 5 messages / 24 h; quota degrades to process-local when Redis is down | per-replica quota multiplies when Redis is down | [V-STATIC] |
| Backups | Supabase daily backup refuses to upload to a public repo's artefacts → no DB backup | owner must choose a private destination | [DOC-CLAIM] task list N2 |
| Data residency, DPA with OpenRouter and model providers | not documented in code | needs legal review | [HUMAN] |

## 6. Safety → see 14b

Crisis detection, distress lanes, helplines, medical claims, dependency, fabricated quotations and impersonation are analysed by S3 in `14b-safety-crisis-and-spiritual-trust.md`.

## 7. Content permissions → see 14c

Source ownership, YouTube terms, transcript and translation rights, voice and likeness, and the unresolved permissions register are in `14c-content-permissions-and-ip-register.md` (S4).

## 8. Coverage

Read: auth service (parts), admin guard, chat and FP route signatures, limiter, CORS block, compose datastore sections, migrations (regex scan of all 139 + targeted reads), delete-my-account function, WhatsApp verification functions, tracked env files (values redacted). Not read: Supabase edge functions other than account deletion, frontend auth flow, k8s manifests, live database.

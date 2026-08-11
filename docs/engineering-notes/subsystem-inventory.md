# Backend Subsystem & Route Inventory

> Generated 2026-08-10 from source at commit 2b2d3470; verify against code before relying on it.

Reference doc for backend subsystems that ship in code but are absent or only
partly covered in the root `CLAUDE.md`. Routes are listed as `METHOD full-path`
(mount prefixes from `app/main.py` folded in). Auth dependency and data stores
are noted per subsystem. Not exhaustive of the whole API — scoped to the
audit's gap list.

---

## Second Brain / Mukthi Vault

Per-user, owner-blind encrypted personal knowledge graph. Envelope encryption
(DEK/KEK, AES-256-GCM, Argon2id). The vault is unlocked per-request and
zeroized at request end — keys never touch caches, logs, or disk.

- **Mode A** (default): server-wrapped DEK using the `BRAIN_KEK` env var.
- **Mode B** ("Private Mode", opt-in, irreversible): passphrase-derived KEK via
  Argon2id — owner-blind, so even an operator holding the DB *and* `BRAIN_KEK`
  cannot decrypt without the passphrase. Mode-B clients send the derived unlock
  in the `X-Brain-Unlock` header (passphrase never crosses the wire raw;
  derivation is client-side in `src/pages/SecondBrainPage.tsx`).

Routes (all `prefix=/api`, auth = real Supabase JWT; anonymous/dev-fallback
user is rejected with 401):

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/brain/vault` | Provision a vault (idempotent). |
| POST | `/api/brain/vault/session-unlock` | Upgrade to Mode B (owner-blind). Irreversible. |
| DELETE | `/api/brain/vault` | Crypto-shred: permanently destroy the entire vault. |
| POST | `/api/brain/items` | Add an item (kind ∈ reflection\|entity\|preference\|relationship\|journal). |
| GET | `/api/brain/items` | List items (filter `kind`, `limit`≤500, `offset`). |
| DELETE | `/api/brain/items/{item_id}` | Forget one item. |
| GET | `/api/brain/recall` | Semantic recall for `q` (limit≤20); used by the chat pipeline. |
| GET | `/api/brain/export` | GDPR/DSAR export; owner (unlocked) session only. |

Key files: `app/api/second_brain.py`; `services/second_brain/` —
`second_brain_service.py` (provision/unlock/CRUD/erasure/export), `crypto.py`
(envelope primitives, `UnlockedVault` context manager), `vault_index.py`
(semantic recall).

Data stores: Supabase tables `user_brain_keys` (wrap_mode + wrapped DEK),
`user_brain_nodes`, `user_brain_edges`; Qdrant collection `second_brain_vault`
(a second small collection, shared across users, `user_id`-filtered — NOT the
doctrine corpus).

Gotchas:
- `SecondBrainService` is optional in the container; endpoints 503 if it's None.
- No admin read endpoint exists by design — support tooling sees ciphertext/metadata only.
- `crypto_shred` and Mode-B upgrade are irreversible.
- The Qdrant vault collection is deliberately separate from the per-process
  doctrine collection (`QdrantService` is a single-collection facade).

---

## Spaced-Repetition Review (SRS)

Active-recall flashcards scheduled with the SM-2 algorithm.

Routes (`prefix=/api`, auth = Supabase JWT):

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/srs/due` | List due cards for the user (`limit`, default 20). |
| POST | `/api/srs/review` | Submit a review `rating` (0–5); updates SM-2 scheduling. Returns 400 on failure. |
| POST | `/api/srs/generate` | Generate 2 flashcards from a saved notebook item (`query`, `answer`, `notebook_item_id`). |

Key files: `app/api/srs.py`, `services/srs_service.py` (SM-2 ease/interval math,
LLM card generation).

Data store: Supabase table `user_retention_cards`.

Gotcha: service degrades to a no-op path when no Supabase client is wired
(`_supabase is None`); the ease-factor/interval update lives in
`review_card` under the "SM-2 Algorithm" block.

---

## Healing Courses

Assigns a multi-lesson healing course when a seeker's recent turn history shows
a distress trigger, and persists lesson progress.

Routes (`prefix=/api/healing-course` — mounted with NO extra `/api`; full paths
below are complete; auth = Supabase JWT):

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/healing-course/assign` | Evaluate `history` for a distress trigger; assign matching course. Idempotent — an active-course user gets no second one. |
| POST | `/api/healing-course/progress` | Upsert lesson progress (on `user_id` + `course_slug`). Anonymous users 403. |

Key files: `app/api/healing_course.py`, `services/healing_course_service.py`
(`evaluate_course_trigger`, `assign_course_if_needed`, priority-ordered
signal→slug map; default slug `end-of-suffering`).

Data store: Supabase table `user_course_progress`. The Supabase client is built
per-request with the caller's JWT so Postgres RLS sees `auth.uid()`.

Gotcha: assignment-side DB work is best-effort inside the service — a trigger
may fire while assignment is skipped; the endpoint reports that outcome
(`{"assigned": false}`) instead of erroring.

---

## Churn / Cancellation Flow

5-stage churn-prevention flow with real Supabase persistence, plus a Celery
win-back email sequence.

Stages: cancel-intent → exit-survey → save-offer → confirm-cancel →
cancel-status (+ reactivate, churn-metrics).

Routes (`prefix=/api`, tag `Account`, auth = Supabase JWT; anonymous rejected;
per-route rate limits):

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/account/cancel-intent` | Stage 1: record intent, route to exit survey. |
| POST | `/api/account/exit-survey` | Stage 2: persist `reason`+`details`, map to a save offer (`REASON_TO_OFFER`). |
| POST | `/api/account/save-offer` | Stage 3: persist offer decision (accepted → saved, declined → cancel). |
| POST | `/api/account/confirm-cancel` | Stage 4: final confirm; schedule deletion + enqueue win-back emails. `confirm=false` aborts. |
| GET | `/api/account/cancel-status` | Stage 5: latest cancellation state for the caller. |
| POST | `/api/account/reactivate` | Mark latest scheduled cancellation reactivated (win-back success). |
| GET | `/api/account/churn-metrics` | Admin (prod: superuser; dev: any authed) snapshot vs benchmark targets. |

Data stores: Supabase tables `exit_surveys`, `save_offers`, `cancellations`.
Data-retention choice maps to a scheduled deletion date
(`keep_30_days`/`keep_90_days`/`delete_immediately`).

Async: `tasks/cancel_flow_tasks.py` — Celery tasks
`send_win_back_email` (renders + sends one template) and
`dispatch_due_win_back_emails` (Celery-beat sweep). Sequence is 4 emails at
day 0/3/14/30; sent slugs tracked in `cancellations.win_back_emails_sent`.

Gotchas:
- Supabase writes are wrapped best-effort — a DB failure logs a warning but
  still returns the offer/next-stage so the UI can continue.
- Churn counters exist both in-process (`_churn_metrics`) and in the DB;
  `/churn-metrics` reads authoritative DB counts and falls back to in-process.

---

## Knowledge-Graph Query

Read-only query surface over the Neo4j graph, plus ontology export/versioning.
n10s 5.x removed `n10s.sparql`, so `/kg/sparql` accepts a SPARQL-shaped body
but executes it as **read-only Cypher passthrough**.

Routes (`prefix=/api`, tag `kg`):

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/kg/sparql` | `require_aal2` + admin | Run a read-only Cypher query (prefix `CYPHER:` to be explicit). `inference` flag hooks `n10s.inference.*` (stub). |
| GET | `/api/kg/subgraph` | Supabase JWT | 1–2 hop concept neighborhood around `query` (`limit`≤100) for the KG visualizer. |
| GET | `/api/ontology/export` | `require_aal2`; admin in prod | Materialize live Neo4j ontology to `turtle` or `jsonld` (30s timeout). |
| GET | `/api/ontology/version` | `require_aal2`; admin in prod | Ontology version + live concept/relation counts (falls back to seed constants). |

Key files: `app/api/kg.py`, `services/ontology_exporter.py`,
`domain/spiritual_ontology.py` (`ONTOLOGY_VERSION`, `SEED_CONCEPTS`,
`SEED_RELATIONS`).

Data store: Neo4j (via `container.neo4j_driver`). `/kg/subgraph` matches on
LightRAG's `entity_id`; returns empty gracefully when the driver is absent.

Gotchas:
- Write protection is layered: a word-boundary denylist over the normalized
  (comment-stripped) query token stream, plus `session.execute_read` (a
  Neo4j-enforced read transaction). Only a small allowlist of read-only `CALL`
  subprocedures (schema inspection + `n10s.inference.*`) is permitted.
- A bounded `asyncio.Semaphore` (`settings.kg_max_concurrent_queries`,
  default 10) caps in-flight Neo4j threads because the sync driver keeps
  running after an `asyncio.wait_for` timeout.
- Admin `/kg/sparql` still runs the input through guardrails, translating
  non-English queries first when `multilingual_guardrails` is on.

---

## Push Notifications

Device-token registration and admin-triggered push dispatch (mobile launch).

Routes (`prefix=/api/push`, tag `Push`, rate-limited):

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/push/register` | optional | Register/upsert a device token. Anonymous devices allowed (no user_id). |
| POST | `/api/push/send` | admin only | Send to a user, or broadcast when `user_id` is None. |

Key files: `app/api/push.py`, `services/push_service.py`, `schemas/push.py`.

Data store: Supabase table `push_devices`. Dispatch: FCM via `firebase-admin`,
APNs via httpx + JWT-signed requests (provider JWT cached ~50 min in-process).

Gotchas:
- `user_id` is derived exclusively from the authenticated session — payload
  `user_id` is never trusted.
- Admin check on `/send` passes `is_superuser` users and `service_role` tokens.

---

## Retention (Streaks)

Practice-streak tracking with milestone events and a cohort retention curve.

Routes (`prefix=/api/retention` — mounted with NO extra `/api`; full paths are
complete; auth = Supabase JWT):

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/retention/streak` | Current/longest streak, freezes, total days, `at_risk` flag. |
| POST | `/api/retention/practice` | Record a practice day; returns updated streak + `milestone` bool. |
| GET | `/api/retention/curve` | Cohort retention curve (`days` 1–365, default 30). |

Key files: `app/api/retention.py`, `services/retention_service.py`
(`StreakEngine`, milestones `3,7,14,21,40,108`).

Data stores: Supabase tables `user_streaks` and `retention_events`; the curve
uses a Supabase RPC. Service is optional — routes 503 when absent.

---

## Waitlist

Placeholder only — not implemented.

Route (`prefix=/api/waitlist`, tag `Waitlist`):

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/waitlist/` | Accepts `email` + optional `name`, always returns **501 Not Implemented**. |

Key file: `app/api/waitlist.py`. No data store. Declared `status_code=501`.

---

## Support

Contact-support form with attachment handling; sends an email.

Route (`prefix=/api/support`, tag `Support`, no auth):

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/support/contact` | Multipart form: `name`, `email`, `subject`, `message`, `category`, `attachments[]`. |

Key files: `app/api/support.py`, `app/services/email_service.py`
(`send_support_email`).

Data store: none persistent — attachments buffered to a per-request temp dir
(`/tmp/support_attachments/<uuid>`) and always cleaned up in `finally`.

Gotchas: max 5 attachments, 10MB each, extension allowlist + magic-byte
validation for jpg/png/pdf; oversized/unsupported files are skipped (warned),
not rejected. Returns 500 if the email send fails.

---

## Layered Memory (episodes / persona / reflections / skills)

*(Partly documented in CLAUDE.md — full route list below.)* The L1→L2→L3
layered-memory model plus episodic memory and personal knowledge graph.

Routes (`prefix=/api`, tag `Memory`, auth = Supabase JWT):

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/memory/episodes` | Paginated recent conversation episodes. |
| GET | `/api/memory/episodes/search` | Substring search over episodes (query + answer). |
| GET | `/api/memory/list` | List episodic memories, paginated. |
| GET | `/api/memory/core` | Core profile preferences + core facts. |
| POST | `/api/memory/add` | Manually add an explicit memory. |
| POST | `/api/memory/forget` | Delete one memory by ID. |
| DELETE | `/api/memory/reflections` | Delete all episodic memories; core facts durable. |
| POST | `/api/memory/regenerate-summary` | Backfill null `summary` columns on episodic memories. |
| GET | `/api/memory/summaries` | Recent session summaries. |
| GET | `/api/memory/persona` | User's L3 generated persona (Markdown). |
| POST | `/api/memory/persona/regenerate` | Regenerate L3 persona from recent L1 atoms. |
| POST | `/api/memory/reflect` | On-demand full reflection: L1 → L3 persona + skills; reset turn counter. |
| GET | `/api/memory/skills` | Auto-generated skills. |
| POST | `/api/memory/skills/regenerate` | Regenerate skills from recent L1 atoms. |
| POST | `/api/memory/relevant` | Semantically relevant memories via `match_user_memories` RPC. |
| GET | `/api/memory/conversations` | Recent conversation memories (continuity display). |
| GET | `/api/memory/knowledge-graph` | User's personal knowledge graph. |
| POST | `/api/memory/knowledge-graph/export` | Export the KG as a standalone interactive HTML file. |

Key files: `app/api/memory.py` (18 routes); `services/memory_service_v2.py`,
`services/memory_service.py`; `services/layered_memory/` — `l1_extractor.py`
(atoms), `l2_scene_compressor.py` (scene blocks), `l3_persona_generator.py`,
`persona_store.py`, `skill_generator.py`, `models.py` (`MemoryAtom`,
`MemoryType`); `services/kg_analytics.py`.

Data stores: Supabase tables `guru_memories` (episodic/core memories),
`user_personas` (L3 persona), `user_skills`, `user_scene_blocks` (L2); RPC
`match_user_memories` for semantic relevance. Persona/skills rows are
tenant-scoped (`tenant_id`).

Gotchas:
- Two memory service generations coexist (`memory_service.py` v1,
  `memory_service_v2.py`). See the root CLAUDE.md caching-invariant note:
  memory-personalized answers must not be cached.
- KG export builds an HTML artifact; the export title is sanitized to a safe
  filename (`_sanitize_filename`).

---

## Speech / TTS / Translate

*(Partly documented — full route list below.)* Under the root CLAUDE.md
local-inference policy ("all processing is local; zero external API calls at
inference"), the approved STT path is the local Whisper backend
(`whisper_local_service.transcribe_with_whisper`, MLX on Apple Silicon — zero
cost, zero rate limits). Sarvam Cloud calls (STT, TTS, translate) have **no
granted exception** and must not be presented as the default: they remain in
code only gated on a real `sarvam_api_key`, pending either local replacements
or an explicitly documented exception.

Routes (`prefix=/api`, tag `Speech`, auth = Supabase JWT, rate-limited):

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/speech/stt` | Transcribe uploaded audio via local Whisper (approved). 10/min. |
| POST | `/api/speech/tts` | Synthesize speech from text — currently Sarvam Cloud `bulbul:v3`, **not approved** (no local path yet). 10/min. |
| POST | `/api/translate` | Translate text between language codes — currently Sarvam Cloud, **not approved** (no local path yet). 30/min. |

Key files: `app/api/speech.py`, `services/whisper_local_service.py`
(`transcribe_with_whisper`), `services/sarvam_service.py`
(`SarvamCloudService` — unapproved cloud paths).

Data store: none. Cloud paths call `api.sarvam.ai` gated on a real
`sarvam_api_key`; local STT makes zero external calls.

Gotchas:
- STT enforces the 25MB cap **before** any decode/transcribe work (declared
  size → content-type → bounded read → post-read 413) to prevent a buffering
  DoS; audio content-type allowlist enforced (415 otherwise).
- STT detected language is inferred from Unicode script ranges
  (Devanagari/Telugu/Tamil).
- TTS/translate return 500 when the API key is a dummy/absent; TTS maps bare
  language codes (`en` → `en-IN`, etc.), default speaker `shubh`.
- Open gap: local TTS and local translation do not exist yet — the unapproved
  Sarvam paths stay until either ships or an exception is documented.

---

## Summary table

| Subsystem | Primary api module | Previously in CLAUDE.md | Routes |
|-----------|--------------------|-------------------------|--------|
| Second Brain / Vault | `app/api/second_brain.py` | No | 8 |
| Spaced-Repetition (SRS) | `app/api/srs.py` | No | 3 |
| Healing Courses | `app/api/healing_course.py` | No | 2 |
| Churn / Cancellation | `app/api/cancel_flow.py` | No | 7 |
| Knowledge-Graph Query | `app/api/kg.py` | No | 4 |
| Push Notifications | `app/api/push.py` | No | 2 |
| Retention (Streaks) | `app/api/retention.py` | No | 3 |
| Waitlist | `app/api/waitlist.py` | No | 1 |
| Support | `app/api/support.py` | No | 1 |
| Layered Memory | `app/api/memory.py` | Partly | 18 |
| Speech / TTS / Translate | `app/api/speech.py` | Partly | 3 |

Total documented: **11 subsystems, 52 routes.**

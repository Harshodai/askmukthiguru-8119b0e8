# Personal mentor: memory, personalisation, continuity and ethical retention (implementation specification)

## 0. Header

| Field | Value |
|---|---|
| Purpose | Give an implementation agent everything needed to build the personal-mentor layer (brief Part 6.8, Pillar P5) without re-investigating the code. |
| Status | **Partial.** Sections 3.1 to 3.4 (consent scopes, proposals, settings, export, erasure registry) are implementation-ready. Saved wisdom (3.5) is implementation-ready for the compliant variant. Learning journeys (3.6) and reminders (3.7) are **decision-blocked** (D-PM6, D-PM9). Personalised generated reflection stays out of scope until D-03 is decided. |
| Date | 2026-11-05 |
| Code head | `c9b42d3e` on `feature/audit-strengthen-rag-qdrant` |
| Depends on decisions | Existing: D-03 (ADR-001 labelled assistant layer), D-19 (delete the churn funnel), D-21 (proactive features opt-in). Proposed here: D-PM1 to D-PM10 (section 9). |
| Owner of finding IDs | S3 (`MEM-`). New findings below are numbered MEM-007 to MEM-012 as **proposals**. The lead confirms them in `findings-index.md`. |
| Evidence labels | As in `CONVENTIONS.md`. Every `path:line` below was read at `c9b42d3e` in this session. |
| Reading order | Sections 1 and 2 are context. Section 3 holds the contracts. Section 8 holds the work order. |

Rules that bind this specification (from root `CLAUDE.md`, checked against code in section 2):

1. Personalisation may change **order** and **framing**. It never changes teacher words (verbatim spans only).
2. The shared answer-cache key is `(language, message)`. An answer personalised with `memory_context` is never cached.
3. Memory consent is a per-user, per-tenant receipt. Every durable read, write and side effect fails closed without it.
4. `memory_outbox.consent_receipt_id` and `pending_extractions.consent_receipt_id` reference `memory_consent_receipts(id)` with `ON DELETE CASCADE`. Do not change this to `SET NULL`.
5. Deleting canonical-memory vectors must include `IsEmptyCondition(key="tenant_id")` beside the tenant match.
6. A zero-UUID bulk-forget audit event is allowed only for action `DELETED`, after every live canonical memory of the user is gone.
7. `study_notebooks` has no `tenant_id`. Never filter it by tenant.
8. `PersonalizeStage` returns `None` without a valid `personalize_teaching` ref, declines terminally, or stashes `personalize_clip`. Do not widen it.

---

## 1. Existing coverage and exactly what it lacks

| Existing document | What it covers | What it lacks (this specification adds it) |
|---|---|---|
| `12` §1 to §4 | Inventory of memory planes, per-turn flow, findings MEM-001 to MEM-006, a target record list (§4.1) and rules (§4.2). | No table or column contracts, no RLS text, no API payloads, no review step, no export or withdrawal design, no retention values, no test list. |
| `12b` | Ethical-retention rules, north-star metric (WUAS), "build / do not build" list, journey sketch (§5), reminder rules (§6). | No data model or endpoints for saved items, journeys or reminders. No link from a reminder to a consent scope. |
| `14` §5 and SEC-004 | DPDP posture, erasure gaps, `router_decisions` text. | Memory-store erasure contract per store; propagation to saved items and exports. |
| `14d` UX-006, UX-009 | Account history, honest personalisation copy. | What the personalisation controls must actually do, and how the user sees it. |
| `03` FR-MEM-01, FR-SAVE-01, FR-JRN-01, FR-DATA-01, FR-REFL-01, FR-FUP-01 | One-line behaviours and acceptance criteria. | Contracts, failure handling, tests. |
| `17` ADR-010 | "Canonical memory only", no inferred profile. | The migration path for the user-facing UI (MEM-007 below). |
| Tasks `T6-01` to `T6-10`, `T1-10` | Task titles and exit criteria. | Task-level sequencing, new schema, and the new tasks `NEW-MEM-1` to `NEW-MEM-11` in section 8. |

New findings from this pass (proposed IDs):

| ID | Finding | Sev | Type | Evidence |
|---|---|---|---|---|
| MEM-007 | The memory UI and the model read **different stores**. `MemoryManager` lists, edits and forgets `guru_memories` rows through `/api/memory/*`. The chat prompt reads **canonical memory first and instead of the legacy blocks**. The canonical routes (`/api/memory/canonical`, `/api/memory/export`) have no caller in `src/`. A user can delete every fact the UI shows and the model still holds canonical facts. | P1 | Confirmed defect (probable user-visible effect; [LIVE-L] to confirm data) | UI: `src/lib/memoryApi.ts:274-343` (paths `/api/memory/forget`, `/edit`, `/all`), `src/components/profile/MemoryManager.tsx:98-105`, `backend/app/api/memory.py:199-210` (list reads `memory_service.list_memories`), `backend/services/memory_service.py:470-495` (table `guru_memories`). Model: `backend/app/orchestrator_utils.py:1005-1045` (canonical block returned in place of legacy). Canonical routes: `backend/app/api/canonical_memory.py:307, 385, 495, 622, 739, 944`. `rg "memory/canonical\|memory/export" src` returns nothing. [V-STATIC] |
| MEM-008 | The review step does not exist. The judge returns `ESCALATE` for sensitive or low-confidence candidates ("requires user confirmation"). The resolver does nothing with it, and the caller skips it. The candidate is dropped. No queue holds it for the user. | P2 | Product gap / defect | `backend/services/canonical_memory/judge.py:169-181, 283-296`; `resolver.py:489-495` (`_escalate`: "no store mutation"); `chat_integration.py:475, 520` (`not in ("IGNORE","ESCALATE")`). [V-STATIC] |
| MEM-009 | "Export my data" omits memory. The `export-my-data` edge function exports profile, conversations, messages, meditation sessions and roles only. The backend `/api/memory/export` covers canonical memories, events and consent receipts only, and has no UI caller. Notebooks, guru memories, core note, summaries, persona, skills and Second Brain are in neither. | P2 | Product gap (DPDP access right) | `supabase/functions/export-my-data/index.ts:39-45`; `backend/app/api/canonical_memory.py:944-1010`; `src/components/profile/settings/AccountDataCard.tsx:104-131`. [V-STATIC] |
| MEM-010 | A saved answer cannot follow a source withdrawal. A notebook item stores the **full answer text** and a free-form `citations` jsonb. There is no reference to a servable clip and no status column. `takedown()` does not exist. | P1 (rights) | Architectural risk | `supabase/migrations/20260630140000_study_notebooks.sql:22-31`; `src/hooks/useStudyNotebooks.ts:11-19, 123-140`; `rg "def takedown" backend` returns nothing (T3-06 not landed). [V-STATIC] |
| MEM-011 | Consent is one scalar (`memory-v1`) for every personalised use. Account deletion deletes the consent receipts and the deletion receipts together with the data, so no proof of erasure remains. | P2 | Architectural risk / [HUMAN] legal question | `backend/app/api/memory.py:967-970` (`pattern=r"^memory-v1$"`); `supabase/migrations/20261021000100_require_active_memory_consent.sql:20-37` (function hard-codes `'memory-v1'`); `supabase/functions/delete-my-account/index.ts:136-160` (list includes `memory_consent_receipts`, `memory_deletion_receipts`). [V-STATIC] |
| MEM-012 | Extraction input is not fenced, and the injection filter is English-only. The backend extractor interpolates raw turns as `[Turn i] role: content` inside the user message. The reject regex matches four English phrases. `services/canonical_memory/security.py` has a second, different pattern list that the extractor does not use. The canonical block is also returned as "seeker-stated facts" evidence for the faithfulness scorer, so a poisoned fact can become evidence. | P2 | Probable defect | `backend/services/canonical_memory/extractor.py:168-183, 224-232`; `security.py:5-17`; `orchestrator_utils.py:1016-1035`. [V-STATIC] |

Corrections to existing audit text (code wins):

| Document | Statement | Code at `c9b42d3e` |
|---|---|---|
| `12` MEM-003 | Consent gate absent on course assignment and proactive Serene Mind. | **Landed** in commit `1e8bf812`: `orchestrator_utils.py:598-602`, `:645-667` (`has_active_memory_consent`), `distress_stage.py:649-657`. Test: `backend/tests/test_emotional_side_effect_consent.py`. The separate opt-in (D-21) is **not** landed. |
| `12` MEM-005 | Client summary enters the prompt unfenced. | **Landed** in commit `a8bd93a5`: `backend/rag/nodes/generation.py:2007-2009` fences it. |
| `12` §0 row 2 | Cites `config.py:1434, :1445`. | Lines moved: `canonical_memory_enabled` is at `app/config.py:1450`, `memory_write` at `:1461`. `feature_memory_write` (legacy outbox plane) defaults to `False` (`app/config.py:536-538`). Doc 12 does not say that the legacy outbox plane is off by default. |
| `12b` / `03` | `CancelFlow` is live and the only UI deletion path. | **Confirmed.** `AccountDataCard.tsx:140-195` mounts it. Win-back beat entry still present: `backend/celery_config.py:96-99`. T1-12 is not landed. |
| `12` MEM-006 | "23 routes ... Keep." | Count of 23 is right for `app/api/memory.py`. The keep verdict is incomplete: see MEM-007 (the routes act on a different plane than the one the model reads). |

---

## 2. Current state (verified)

### 2.1 Stores

| Store | Table or system | Key columns and constraints | RLS or access | Evidence |
|---|---|---|---|---|
| Canonical facts | `canonical_memories` | `user_id uuid -> auth.users ON DELETE CASCADE`; `tenant_id text`; `memory_type` check (10 values); `sensitivity` check; `status` check (`active`, `superseded`, `expired`, `deleted`); `source_conversation_id`, `source_message_id`, `source_turn_index`; `extraction_method`; `embedding_id`; `expires_at`; partial unique index on `(user_id, tenant_id, fact_key)` where `status='active'` | Owner select/insert/update/delete policies, plus restrictive insert and update policies requiring `has_active_memory_consent(user_id, tenant_id)`. Update to `status='deleted'` stays allowed without consent. | `supabase/migrations/20260911000000_create_canonical_memories.sql:6-60`; `20261021000050_memory_consent_history_and_outbox_binding.sql` (index); `20261021000100_require_active_memory_consent.sql:40-80` |
| Canonical events and snapshots | `canonical_memory_events`, `canonical_memory_compaction_snapshots` | Audit trail with statement copies | Service role | `20260912000000_create_canonical_memory_events.sql`, `20261022000100_create_canonical_memory_compaction_snapshots.sql`; erased by `memory.py:1176-1183` |
| Consent ledger | `memory_consent_receipts` | Append-only. Newest row by `event_sequence` per `(user_id, tenant_id, consent_version)` decides consent. | Owner select only | `20260805000001_memory_outbox.sql:3-12, 52-56`; `20261021000050_memory_consent_history_and_outbox_binding.sql:15-26`; `services/memory_outbox.py:89-114` |
| Queues | `memory_outbox`, `pending_extractions` | `consent_receipt_id ... ON DELETE CASCADE` (normalised by DO block) | Owner select/delete on outbox; restrictive consent policy on queue writes | `20261021000100_require_active_memory_consent.sql:84-130` |
| Deletion receipts | `memory_deletion_receipts` | `store_counts jsonb`, `status` | Owner select | `20260805000001_memory_outbox.sql:40-50` |
| Legacy planes | `guru_memories`, `guru_core_memory`, `guru_session_summaries`, `user_profiles`, `conversation_memories`, `user_personas`, `user_episodes`, `user_scene_blocks`, `user_skills` | See doc 12 §1 | Restrictive consent policy on first three and `canonical_memories` | `20261021000100_require_active_memory_consent.sql:46-50` |
| Memory vectors | Qdrant canonical memory collection and `*_memory` collections | Payload `user_id`, `tenant_id`, `memory_type`, `status`, `memory_id` | Server-side filter on `user_id` | `backend/services/canonical_memory/vector_index.py:62-72, 150-175` |
| Notebooks | `study_notebooks` (`user_id` only), `study_notebook_items` (`query`, `answer`, `citations jsonb`, no user column) | Select/insert policies only on items; deletes go through the backend | Owner policies | `20260630140000_study_notebooks.sql:14-58`; `src/hooks/useStudyNotebooks.ts:61-157` |
| Preferences | Browser `localStorage` key `askmukthiguru_profile` (`guruTone`, `familiarityLevel`, `preferredLanguage`, `meditationReminders`, `reminderTimeMinutes`), synced by `profileStorage.ts` | Not part of any consent receipt | Browser | `src/lib/profileStorage.ts:35-56, 203-227` |

### 2.2 Behaviour that already works (keep)

| Behaviour | Evidence |
|---|---|
| Temporary Chat skips reads, writes and side effects. | `orchestrator_utils.py:545-556`; `memory_stage.py:132`; `first_person_bridge.py:112-113`; `cache_stage.py:187-188` |
| Durable reads need an active receipt for the resolved tenant. A missing outbox, a lookup error or no receipt means no read. | `orchestrator_utils.py:927-958` |
| Write paths re-check consent inside the background task. | `memory_stage.py:162-176`; `first_person_bridge.py:129-137, 172-176` |
| The per-request consent gate for extraction fails closed on timeout and error. | `services/canonical_memory/consent_gate.py:38-60` |
| Revocation deletes queued rows, evicts the exact cache and the personal graph cache, and returns 503 if cleanup cannot be confirmed. | `app/api/memory.py:967-1035` |
| Full erasure attempts every known store, returns a receipt, and reports `partial_failure` instead of success. Account deletion fails closed if the backend purge does not confirm. | `memory.py:1095-1343`; `supabase/functions/delete-my-account/index.ts:48-62` |
| Vector delete matches the tenant **or** an absent tenant payload. | `vector_index.py:62-72, 255-262, 264-285` |
| A personalised answer is not written to, or read from, the shared cache. Eligibility covers `personalization_eligible`, a non-empty `memory_context`, an attachment context and `guru_tone` of `direct` or `poetic`. | `app/pipeline/stages/cache_stage.py:64-92`; `backend/tests/test_cache_personalization_leak.py:59-99` |
| Memory text is PII-scrubbed and fenced before it enters a prompt. | `orchestrator_utils.py:876-892`; `rag/nodes/generation.py:1995`; `services/canonical_memory/context_builder.py:255-257, 286, 311` |
| Healing-course assignment and the proactive Serene Mind trend need consent. | See correction table above. |
| No push-permission prompt after a safety or abstain answer (frontend). | Commit `e47d9f9f` (`isPushPromptEligible`). |

### 2.3 What the teaching lane does with memory

| Fact | Evidence |
|---|---|
| `prepare_user_memory` runs for every signed-in turn and can add 1.5 s (second brain budget) plus 2.0 s (canonical timeout). | `orchestrator_utils.py:894-1000`; `app/config.py:1465` |
| The first-person bridge and `FirstPersonPipeline` take no memory input. `rg "memory_context\|memory_signals" backend/app/pipeline/stages/first_person_bridge.py` returns nothing. | [V-STATIC]; MEM-002 (T6-02 not landed) |
| First-person turns still **write** memory (`_dispatch_fp_memory`). The outbox payload includes the answer text and citations. | `first_person_bridge.py:100-215` |
| `PersonalizeStage` is an explicit opt-in that runs the **general generating graph** on a looked-up clip and appends a label ("in our own words, not a direct quote from the teachers"). This sits in tension with root `CLAUDE.md` invariants 1, 15 and 21 (no generation at serve time). It is an owner-accepted exception behind a frontend flag. Decision D-03 governs whether it stays. | `app/pipeline/stages/personalize_stage.py:1-35, 85-100` |

> **Update 2026-11-06 (batch 9, 2edee1c4):** This is no longer true. `FirstPersonBridgeStage` builds `memory_signals` (`backend/app/pipeline/stages/first_person_bridge.py:850-876`) and `FirstPersonPipeline` takes them (`backend/services/first_person_pipeline.py:2022`, `:5225`, `:5694`). The signals are not the ones in section 3: they come from the chat history payload, whose `MessagePayload` has no citations (`backend/app/schemas/__init__.py:46-62`). On the live path `seen_video_ids` stays empty. MEM-002 is Partial.

### 2.4 Scheduled jobs that touch this area

| Job | Schedule | Purpose | Evidence |
|---|---|---|---|
| `dispatch-due-win-back-emails` | 24 h | Win-back emails after a deletion request. To be removed (T1-12, D-19). | `celery_config.py:96-99` |
| `process-batched-layered-memories` | 5 min | Legacy L1/L2/L3 plane. | `celery_config.py:100-103` |
| `drain-memory-outbox` | 60 s | Legacy outbox plane (off while `feature_memory_write=False`). | `celery_config.py:104-107` |
| `cleanup-retention-data` | 24 h | Telemetry, compliance audit files and staging queue at 90 days. **No memory-table retention.** | `celery_config.py:112-115`; `backend/tasks/retention_tasks.py:13-48` |
| Edge `memory-extract-drain` (cron, 1 min) | Reads `pending_extractions`, calls the Lovable AI gateway with `google/gemini-2.5-flash`, writes `guru_memories`. Behind the frontend flag `VITE_MEMORY_EXTRACTION_ENABLED`. | `supabase/functions/memory-extract-drain/index.ts:1-30`; `src/lib/chat/transport.ts:554-600`. Processor disclosure: ADV-02, T6-08. |

### 2.5 Unknowns at this head

| Unknown | Why it matters | Label |
|---|---|---|
| Whether production holds rows in `guru_memories`, `canonical_memories` or both for the same user. | Sizes MEM-007 and the migration in T6-01. | [LIVE-L] / [LIVE-R] |
| `canonical_memories.tenant_id` SQL default is `'default'` (`20260911000000_create_canonical_memories.sql`), while legacy tables default to `'oneness'` (`20261021000200_tenant_scope_legacy_memory.sql:23-46`). Whether a later migration aligned it. | A mismatch breaks consent lookup per tenant. | [LIVE-R] schema check |
| Which provider `_build_client()` selects in the deployed environment. | Decides which processor sees extraction text. | [LIVE-R] |
| Whether `VITE_MEMORY_EXTRACTION_ENABLED` is `true` in the deployed frontend. | Decides whether the edge drain path is live. | [LIVE-R] |

---

## 3. Target contracts

### 3.0 Principles for the target

1. One system of record for facts about the person: `canonical_memories` (ADR-010). Every other memory table is retired or becomes a derived view.
2. The user sees and controls exactly what the model can read. If the model can read it, the memory page lists it. If the memory page deletes it, the model cannot read it.
3. The user decides before sensitive or inferred facts become memory (proposal queue, 3.2).
4. Personalisation inputs are **settings the user chose** and **facts the user stated**. Inferred emotional state is not stored unless the user turns it on (D-PM2).
5. Saved wisdom is a **pointer** to a servable clip plus the user's own note. The teacher text is rendered from the store on every read.
6. Personalisation changes order and framing in the assistant's own labelled voice (section 3.8). It never edits a teacher span.

### 3.1 Consent scopes and personalisation settings

**Decision handling.** Keep the receipt `memory-v1` as the root consent for durable memory. Add scoped settings on top. A scope is **on only if** (a) the root receipt is active and (b) the setting is true. Do not add new `consent_version` values in this release: the SQL function and the API regex hard-code `memory-v1` (`20261021000100_require_active_memory_consent.sql:20-37`, `memory.py:967-970`). Revisit if counsel (D-PM8) wants separate legal receipts.

New table `public.user_personalization_settings`:

| Column | Type | Default | Notes |
|---|---|---|---|
| `user_id` | `uuid` PK, `REFERENCES auth.users(id) ON DELETE CASCADE` | | |
| `tenant_id` | `text NOT NULL` | `'oneness'` | Matches legacy tables (`20261021000200_tenant_scope_legacy_memory.sql`). |
| `answer_language` | `text` | null | ISO code. Null means "follow the question". Replaces the browser-only `preferredLanguage` for signed-in users. |
| `depth` | `text CHECK (depth IN ('brief','standard','deep'))` | `'standard'` | Controls how many clips and how much assistant framing (3.8). |
| `topics_to_explore` | `text[]` | `'{}'` | Slugs from the topic rail (no free text). Max 10. |
| `use_saved_for_suggestions` | `boolean` | `false` | Allows "Continue exploring" from saved items. |
| `continuity_suggestions` | `boolean` | `false` | Allows learning-trace-based offers (3.6). |
| `proactive_suggestions` | `boolean` | `false` | Gates healing-course assignment and proactive Serene Mind (resolves D-21). |
| `emotional_context_use` | `boolean` | `false` | Gates **storing and reading** per-turn distress level or arcs (D-PM2). |
| `reminders_enabled` | `boolean` | `false` | 3.7. |
| `reminder_time_minutes` | `smallint CHECK (reminder_time_minutes BETWEEN 0 AND 1439)` | null | User-local time. |
| `reminder_days` | `smallint[]` | `'{}'` | 0 to 6. |
| `reminder_content` | `text CHECK (reminder_content IN ('saved','journey'))` | null | Never a generic "come back". |
| `show_practice_record` | `boolean` | `false` | Opt-in practice record; neutral copy (UX-002, T1-12). |
| `version` | `int` | `1` | Optimistic concurrency. |
| `updated_at` | `timestamptz` | `now()` | |

RLS:

```sql
ALTER TABLE public.user_personalization_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY ups_select ON public.user_personalization_settings FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY ups_insert ON public.user_personalization_settings FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY ups_update ON public.user_personalization_settings FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY ups_delete ON public.user_personalization_settings FOR DELETE TO authenticated USING (auth.uid() = user_id);
```

No restrictive consent policy on this table: settings are stated preferences, not inferred memory, and a user must be able to read and clear them after revoking consent. The **backend** applies the AND with the consent receipt at read time. Grant the table to `service_role` in the same migration (pattern: `20260912000001_grant_memory_tables_to_service_role.sql`). Add the table to the erasure registry (3.4) and to `delete-my-account`.

API (backend, `async def` dependencies only; `get_current_user_from_supabase`; `set_tenant_from_request`):

| Method and path | Request | Response | Failure |
|---|---|---|---|
| `GET /api/me/personalization` | none | `{settings: {...all columns above except user_id/tenant_id}, consent: {granted: bool, consent_version: "memory-v1"}, effective: {continuity_suggestions: bool, proactive_suggestions: bool, emotional_context_use: bool, use_saved_for_suggestions: bool}}` | 503 if the consent store is unreachable (never return `effective` all true on error) |
| `PUT /api/me/personalization` | Partial settings plus `version` | Same as GET | 409 on version mismatch; 422 on invalid enum; setting a scope to `true` while consent is not active returns 200 with `effective.<scope>=false` and `consent.granted=false` (the stored intent is kept; the scope stays off) |

Frontend: `src/components/profile/settings/PersonalizationCard.tsx` (new). It lists each scope with one plain sentence of what it does and what it never does. Order: memory consent switch (existing `memoryApi.recordConsent`), then the scoped switches (disabled with a reason while consent is off), then reminders. Migrate `guruTone`, `familiarityLevel` and `preferredLanguage` only if they have a real effect on the output. Today they do not on the teaching lane (`14d` UX-009). Hide them until T6-10 wires or removes them. Copy lives in `src/locales/*.json`; native review is required for the 13 non-English locales (T1-20 rule).

Wiring changes in backend:

| File | Change |
|---|---|
| `backend/app/orchestrator_utils.py:577-625` | Add `settings.proactive_suggestions AND consent` to the course-assignment guard. Keep `has_active_memory_consent`. |
| `backend/app/pipeline/stages/distress_stage.py:649-657` | Same for the trend read. The current-turn distress path never depends on settings. |
| `backend/app/orchestrator_utils.py:636-705` | `_build_emotional_arc_turns` runs only when `emotional_context_use` is true. |
| New `backend/services/personalization_settings.py` | `async get_effective(container, user_id, tenant_id) -> EffectiveSettings`. Fails closed (all false) on any error. Caches nothing across requests. |

### 3.2 Memory proposals (the review step)

Purpose: close MEM-008. Sensitive and inferred candidates wait for the user.

New table `public.memory_proposals`:

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE` | |
| `tenant_id` | `text NOT NULL DEFAULT 'oneness'` | |
| `consent_receipt_id` | `uuid NOT NULL REFERENCES public.memory_consent_receipts(id) ON DELETE CASCADE` | **Must be CASCADE** (invariant 4). A proposal whose receipt is gone has no consent basis. |
| `statement` | `text NOT NULL CHECK (char_length(statement) <= 1000)` | The user's own words, as extracted. |
| `memory_type` | `text NOT NULL` | Same check list as `canonical_memories.memory_type`. |
| `sensitivity` | `text NOT NULL CHECK (sensitivity IN ('normal','sensitive','highly_sensitive'))` | |
| `judge_reason` | `text` | Short code, no seeker text. |
| `source_conversation_id`, `source_message_id` | `text` | Provenance for "where did this come from". |
| `state` | `text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','accepted','rejected','expired'))` | |
| `created_at` | `timestamptz DEFAULT now()` | |
| `expires_at` | `timestamptz NOT NULL DEFAULT now() + interval '14 days'` | Value is proposed (D-PM4). |
| `decided_at` | `timestamptz` | |

RLS:

```sql
ALTER TABLE public.memory_proposals ENABLE ROW LEVEL SECURITY;
CREATE POLICY mp_select ON public.memory_proposals FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY mp_update ON public.memory_proposals FOR UPDATE TO authenticated USING (auth.uid() = user_id);  -- state change only; see column grant
CREATE POLICY mp_delete ON public.memory_proposals FOR DELETE TO authenticated USING (auth.uid() = user_id);
-- No INSERT policy for authenticated: only service_role (backend) inserts.
CREATE POLICY mp_consent_update ON public.memory_proposals AS RESTRICTIVE FOR UPDATE TO authenticated
  USING (true) WITH CHECK (public.has_active_memory_consent(user_id, tenant_id) OR state IN ('rejected','expired'));
REVOKE UPDATE ON public.memory_proposals FROM authenticated;
GRANT UPDATE (state, decided_at) ON public.memory_proposals TO authenticated;
```

Behaviour changes in the write path:

1. `ChatIntegration.post_response_memory` (`chat_integration.py:440-480`): for each `ESCALATE` decision, call `MemoryProposals.create(...)` instead of dropping. Skip creation if an identical `normalized_statement` is already `pending` or `active`.
2. The judge also escalates when `sensitivity in ('sensitive','highly_sensitive')` unless `explicit_request` (existing `SensitivityPolicy`, `judge.py:169-181`). Keep that rule. Add: **inferred** candidates (`confidence < 0.9` or `extraction_method != 'explicit'`) of type `RELATIONSHIP` or `REFLECTION` also escalate (variant A, section 9 D-PM3).
3. Do not extract from safety turns. If the turn route is a distress, crisis, or safety-notice route, skip `post_response_memory` and the outbox enqueue. Today there is no such skip in `memory_stage.py:126-215` or `first_person_bridge.py:100-215` [V-STATIC]. Use the route facts already on `ctx` (assessment level) so the check is deterministic.

API:

| Method and path | Payload | Response | Failure |
|---|---|---|---|
| `GET /api/memory/proposals` | none | `{proposals: [{id, statement, memory_type, sensitivity, created_at, expires_at, source: {conversation_id, message_id}}]}` | 503 if consent unreadable |
| `POST /api/memory/proposals/{id}/accept` | optional `{statement}` (user-edited text, max 1000) | `{memory: <canonical memory response>}` | 403 `consent_required` if no active receipt; 404 if not owned; 409 if not `pending`; 503 if vector index write fails (see lifecycle step 5) |
| `POST /api/memory/proposals/{id}/reject` | none | `{state: "rejected"}` | none (allowed without consent) |

On accept the backend calls the existing resolver with `extraction_method='user_confirmed'`, `explicit_request=True`, then writes the vector, then sets `state='accepted'`. Frontend: `src/components/profile/MemoryProposalsList.tsx` inside `MemoryManager`, and a quiet count badge on the memory tab. Do **not** interrupt the chat with a dialog. Do not push-notify a proposal (12b §6).

### 3.3 One memory list the user sees (closes MEM-007)

Target state: `MemoryManager` calls the canonical routes. Interim state (before T6-01 migrates data): the page shows **both** planes in two labelled sections, "Used in answers" (canonical) and "Older notes" (legacy), each with edit, forget and export.

| UI action | Target endpoint | Exists? |
|---|---|---|
| List | `GET /api/memory/canonical` (`canonical_memory.py:307`) | Yes, no UI caller |
| Add ("remember that ...") | `POST /api/memory/canonical` (`:385`) | Yes |
| Correct | `PUT /api/memory/canonical/{id}` (`:495`) | Yes |
| Forget one | `DELETE /api/memory/canonical/{id}` (`:622`) | Yes |
| Forget all | `DELETE /api/memory/canonical` (`:739`) and `DELETE /api/memory/all` | Yes |
| "Why do you remember this" | `GET /api/memory/canonical/reasons` (`:829`) | Yes |
| Consent | `GET/POST /api/memory/consent` | Yes |

The memory list item shows: statement, type label, date, `source` (conversation link), `last_used_at`, and sensitivity badge. Edit and forget keep their present confirm dialogs.

Rule for the model read path: `prepare_user_memory` reads canonical memory only (plus Second Brain items the user unlocked). When T6-01 retires the legacy blocks, delete the legacy branch at `orchestrator_utils.py:1045-1130` in the same PR. Do not add a second read path.

### 3.4 Export, correction and deletion propagation

#### 3.4.1 Erasure registry

New module `backend/services/memory_store_registry.py` holds one list of stores. Each entry has `name`, `kind` (`postgres`, `qdrant`, `graph`, `redis`, `vault`, `edge`, `browser`), `delete(user_id, tenant_id|None)`, `count(user_id)` and `export(user_id)`. `delete_all_memory_endpoint` (`memory.py:1095`), `delete-my-account` (via `/api/account/purge-memory`) and `services/personalization/cascade_erasure.py` all iterate **this** list. Today three lists exist (`memory.py:1163-1200`, `delete-my-account/index.ts:136-160`, `cascade_erasure.py` `PRIMARY_26_TABLES`) [V-STATIC]. A test asserts the three agree (AC-PM-18).

Minimum registry contents (target):

| Store | Delete rule | Export |
|---|---|---|
| `canonical_memories`, `canonical_memory_events`, `canonical_memory_compaction_snapshots`, `memory_audit_events` | Delete by `user_id`, all tenants | Yes (`/api/memory/export`) |
| `memory_proposals` (new) | Cascade plus explicit delete | Yes |
| `learning_events` (new) | Cascade plus explicit delete | Yes |
| `saved_teachings` (new), `study_notebooks`, `study_notebook_items` | Explicit delete (items first) | Yes |
| `user_personalization_settings` (new) | Cascade plus explicit delete | Yes |
| `guru_memories`, `guru_core_memory`, `guru_session_summaries`, `user_profiles`, `conversation_memories`, `user_personas`, `user_episodes`, `user_scene_blocks`, `user_skills` | Delete until retired by T6-01 | Yes until retired |
| `memory_outbox`, `pending_extractions` | Delete; FKs are CASCADE | No (transient) |
| Canonical memory Qdrant vectors | `delete_all_user(user_id, all_tenants=True)` for erasure; `delete(...)` with `_tenant_scope` for single forget | No |
| Legacy Qdrant `*_memory` collections, graph nodes | As `memory.py:1210-1290` | No |
| Redis exact cache, personal KG cache, ephemeral memory | As `memory.py:1139-1160, 1202-1209` | No |
| Second Brain vault | `crypto_shred` | Encrypted blob only, user-initiated |
| WhatsApp SQLite (`whatsapp_bot/wa_bot.py`), edge-function processors | Out of scope while the channel is disabled (`ADV-06`) | n/a |

> **Update 2026-11-06 (batch 12, 4af5e711):** The memory plane inventory in `12-personal-mentor-memory-ethical-retention.md` now lists the WhatsApp SQLite store and the edge extraction worker (ADV-06 Closed).

#### 3.4.2 Export

Extend `GET /api/memory/export` (`canonical_memory.py:944`) to return all registry exports with `schema_version`, `exported_at`, and a `stores` map. Add a "Download my memory" button in `AccountDataCard.tsx` next to the two existing export buttons. Update `export-my-data` only to include a pointer, because the edge function has no access to Qdrant or the backend stores. Rule: an export fails visibly (503 with the store name) if any registry store cannot be read. It never returns a partial bundle (same rule as the current consent-history export, `canonical_memory.py:978-986`).

Export content rules:

- Saved teachings export the pointer fields and the user's note. They do **not** export teacher text (rights; 3.5).
- Consent receipts are exported with `event_sequence` ordering.
- The bundle contains no internal fields (`embedding_id`, vectors). It is JSON, `Content-Disposition: attachment`.

#### 3.4.3 Correction

| Case | Rule |
|---|---|
| User edits a fact | `PUT /api/memory/canonical/{id}` creates a new version, marks the old row `superseded`, re-embeds, and deletes the old vector in the same request. Next turn reads the new value only. Invalidate the personal exact cache (`invalidate_user_exact_cache`). |
| User says "forget X" in chat | The existing command path (`chat_integration.py` `_handle_forget`) deletes through the resolver. It must also remove the vector. Test in AC-PM-14. |
| User rejects a proposal | State `rejected`. The same normalised statement is not re-proposed for 90 days (suppression keyed on `normalized_statement`; stored in `memory_proposals` rows, not a new table). |

#### 3.4.4 Deletion propagation

For every delete (one fact, all memory, consent revoke, account), the same four steps run in order. A step that fails makes the whole call fail with the store name. No call reports success on partial failure.

1. Postgres rows (store registry).
2. Qdrant vectors (with `IsEmptyCondition(key="tenant_id")` in the single-delete selector).
3. Caches: exact cache for the user, personal KG cache, hot cache entries for the user's personalised keys.
4. Receipt: write `memory_deletion_receipts`. See D-PM8 for what survives account deletion.

Consent revocation (`memory.py:967-1035`) keeps its present behaviour: it deletes **queued** work and evicts caches. It does **not** delete stored memory. The memory page states this in one sentence and offers "Delete everything I have stored" beside the switch.

### 3.5 Saved wisdom (saved verbatim clips with full provenance)

Compliant variant (implementation-ready): store a pointer, never a copy of teacher text.

New table `public.saved_teachings`:

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE` | |
| `notebook_id` | `uuid REFERENCES public.study_notebooks(id) ON DELETE SET NULL` | Collections reuse notebooks. Do not add a `tenant_id` filter for notebooks (invariant 7). |
| `point_id` | `text NOT NULL` | `uuid5(FIRST_PERSON_NAMESPACE, transcript_hash:start_ms:end_ms)` at save time (invariant 4). |
| `collection_name` | `text NOT NULL` | Serving collection when saved (for example `first_person_v10`). |
| `video_id` | `text NOT NULL CHECK (video_id ~ '^[A-Za-z0-9_-]{11}$')` | Same regex as `personalize_stage.py` `_YOUTUBE_VIDEO_ID_RE`. |
| `start_ms`, `end_ms` | `integer NOT NULL CHECK (end_ms > start_ms)` | |
| `source_text_hash` | `text NOT NULL` | The v10 integrity field (invariant 2). Also store `transcript_hash` in `transcript_hash text`. |
| `teacher_id`, `speaker` | `text` | Copied from the stored clip. |
| `speaker_verified` | `boolean`, `voice_verification_method text` | **Copied from the clip, never inferred** (invariant 23). |
| `title`, `channel` | `text` | Display metadata copied at save time; refreshed by revalidation. |
| `note` | `text CHECK (char_length(note) <= 2000)` | The user's own words. Optional. |
| `availability` | `text NOT NULL DEFAULT 'available' CHECK (availability IN ('available','withdrawn','changed','unknown'))` | |
| `availability_checked_at` | `timestamptz` | |
| `created_at` | `timestamptz DEFAULT now()` | |

Constraint: `UNIQUE (user_id, point_id)`. Index: `(user_id, created_at DESC)`, `(video_id)` for withdrawal fan-out. There is **no** column that holds teacher text. A migration comment says so, and a test (AC-PM-22) fails if a column named like `verbatim_text` appears.

RLS: owner select, insert, update (note and `notebook_id` only, via column grant), delete. `availability*` columns are written by `service_role` only (`REVOKE UPDATE` on them from `authenticated`). No consent policy: saving is a user action, like a notebook. It is exported and erased, and it feeds suggestions only when `use_saved_for_suggestions` is on.

Fields available for the pointer come from the citation object the backend already builds: `point_id`, `video_id`, `start_ms`, `end_ms`, `speaker`, `speaker_verified`, `voice_verification_method`, `teacher_id`, `transcript_hash`, `rights_cleared`, `domain_rights_status` (`services/first_person_pipeline.py:1722-1750`). The save endpoint **looks the clip up itself** by `point_id` and never trusts client-provided text, as `PersonalizeStage` does.

API:

| Method and path | Request | Response | Failure |
|---|---|---|---|
| `POST /api/saved-teachings` | `{point_id, notebook_id?, note?}` | `201 {id, availability, clip: <render payload>}` | 404 if the clip is not servable now; 409 if already saved (return the existing id); 422 invalid |
| `GET /api/saved-teachings?notebook_id=&limit=&cursor=` | | `{items: [{id, note, created_at, availability, clip | null, withdrawn_notice | null}], next_cursor}` | |
| `PATCH /api/saved-teachings/{id}` | `{note?, notebook_id?}` | updated item | 404 not owned |
| `DELETE /api/saved-teachings/{id}` | | `204` | |
| `POST /api/saved-teachings/{id}/report` | `{reason: 'wrong_speaker'|'wrong_text'|'wrong_timestamp'|'other', detail?}` | `202` | Routes into the seeker clip report of T6-04 (`feedback.py` ~336) |

Read-time rule (every list and detail call): resolve each pointer through the serving store. Use `FirstPersonStore.points_servable([...])` (`services/first_person_store.py:601`), which checks existence, `first_person_eligible`, `rights_cleared`, `domain_rights_status`, `is_verbatim`, speaker and source. Then:

| Result of resolution | Item returned |
|---|---|
| Servable and `source_text_hash` equals the stored hash | `availability='available'`, `clip` rendered from the store (text, speaker label, verification label, link). |
| Not found, not servable, or rights revoked | `availability='withdrawn'`, `clip=null`, `withdrawn_notice` = "This teaching is no longer available." The note stays visible. No text, no link. |
| Found but hash differs (text corrected) | `availability='changed'`, `clip` rendered from the **current** store text with a line "This passage was corrected since you saved it." Never show the old text. |
| Store unreachable | `availability='unknown'`, `clip=null`, `withdrawn_notice=null`, retry hint. Do not show stale text. |

Write-time rule: a daily job (`NEW-MEM-7`) re-checks all saved pointers in batches and writes `availability`. The `takedown(source)` hook of T3-06 calls `flag_withdrawn(video_ids|point_ids)` immediately and returns the number of items flagged (the count goes into the takedown report). Until T3-06 exists, the daily job and the read-time rule are the only protection.

Legacy notebook items: add nullable `source_status text` to `study_notebook_items`. Migration backfills nothing. The takedown hook flags items whose `citations` contain a URL with the withdrawn `video_id` ([INF]: `citations` is a free-form list of strings or `{url,...}` objects, `useStudyNotebooks.ts:11-12`). The UI hides `answer` while `source_status='withdrawn'`. This is a stop-gap; the target is to stop writing `answer` text for first-person answers and save a `saved_teachings` pointer instead.

Frontend:

| Component | File | Behaviour |
|---|---|---|
| `SaveClipButton` | `src/components/chat/CitationCard.tsx` (add) | One tap. Optional note sheet. Shows "Saved" with an undo. Disabled in Temporary Chat? **No**: saving is a user action. In Temporary Chat show a one-line notice that the save is kept (otherwise the label "not saved" misleads). Decision for owner: D-PM5. |
| `SavedTeachingsPage` | `src/pages/SavedTeachingsPage.tsx`, route `/saved` | List by collection, search by note, export, delete. Withdrawn items show the notice. |
| `ReportClipMenu` | `CitationCard.tsx` | Calls the report endpoint. |

### 3.6 Continuity, reflection continuity and learning journeys

#### 3.6.1 Learning trace (continuity without storing seeker text)

New table `public.learning_events`:

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid PK` | |
| `user_id` | `uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE` | |
| `tenant_id` | `text NOT NULL DEFAULT 'oneness'` | |
| `consent_receipt_id` | `uuid NOT NULL REFERENCES public.memory_consent_receipts(id) ON DELETE CASCADE` | CASCADE, per invariant 4. |
| `topic_slug` | `text` | From the topic rail or teacher-registry facets (deterministic). No seeker text. |
| `point_ids` | `text[] NOT NULL` | Clips served. |
| `answered_at` | `timestamptz DEFAULT now()` | |
| `helpful` | `boolean` | Set from the user's feedback tap. |
| `expires_at` | `timestamptz NOT NULL DEFAULT now() + interval '12 months'` | Proposed value (D-PM4). |

RLS: owner select and delete. Insert only by `service_role`. Restrictive insert policy `has_active_memory_consent(user_id, tenant_id)` for defence in depth, mirroring `20261021000100_require_active_memory_consent.sql:40-60`. Indexes: `(user_id, answered_at DESC)`, `(user_id, topic_slug)`.

Write: after a served first-person clip, only when consent is active, `continuity_suggestions` is true, the turn is not incognito and the route is not a safety route. A new function `record_learning_event` sits beside `_dispatch_fp_memory` and uses the same consent re-check inside the task.

Read (teaching lane, MEM-002 / T6-02): `memory_signals = {seen_point_ids, recent_topic_slugs, saved_topic_slugs, answer_language, depth}` built from `learning_events`, settings and (if allowed) saved items. `FirstPersonPipeline` accepts it as an optional argument. Allowed effects:

| Effect | Rule |
|---|---|
| Prefer unseen clips | After the pipeline has produced its **gated** candidate set (integrity, rights, standalone, relevance gates all passed), stable-sort so unseen `point_id`s come first when scores are within a fixed tie band. Never admit a candidate the gates rejected. Never lower the relevance minimum. |
| Language | Choose the glue language. The quote is never translated (invariant 16). |
| Depth | Number of clips and presence of the assistant framing line. |
| Continue offer | At most one chip: "Continue exploring <topic label>?" Shown only if `continuity_suggestions` is on, the last event is within 30 days and the last turn was not a safety route. The chip sends a new question; it does not auto-run. |
| Skip the read | When the settings and consent say the lane cannot use memory, skip `prepare_user_memory` entirely (saves up to 3.5 s worst case). |

Forbidden effects: editing, trimming or re-splicing a teacher span; choosing a clip below the gates; changing the speaker label; adding a sentence in a teacher's first person.

Cache rule: an answer produced with `memory_signals` that changed order or framing is marked personalised. It bypasses the shared cache read and write (extend `_is_personalization_eligible`, `cache_stage.py:64-92`, to include `memory_signals`). Unchanged answers (no signal applied) may use the shared cache.

#### 3.6.2 Reflection continuity

Reflections stay in the Second Brain vault (encrypted, user-unlocked). Do not copy reflection text into any other table. A reflection prompt is app-voice text from a curated list (ids stable, stored in code or config). The only thing outside the vault is `reflection_prompt_id` on a journey step. "What did I reflect on last time?" opens the vault entry list; the app does not summarise it without an unlocked vault.

#### 3.6.3 Learning journeys (decision-blocked)

Decision-blocked on D-PM9 (who curates) and on rights per clip (doc 14c). Contract if approved:

| Table | Columns (key ones) | RLS |
|---|---|---|
| `learning_journeys` | `id`, `slug`, `title`, `theme_slug`, `status` (`draft`,`published`,`retired`), `curator`, `reviewed_at` | Select `status='published'` to `authenticated`; writes `service_role` |
| `learning_journey_steps` | `journey_id`, `position`, `point_id`, `video_id`, `start_ms`, `end_ms`, `source_text_hash`, `reflection_prompt_id` | Select via published journey; writes `service_role` |
| `user_journey_progress` | `user_id` (FK CASCADE), `journey_id`, `completed_positions int[]`, `started_at`, `paused_at` | Owner CRUD |

Rules: steps are verified clips chosen by humans. Progress shows "3 of 7 clips watched". There is no percentage, score, streak or badge. A step whose clip fails the read-time servability check is hidden and the journey says "1 step is unavailable". End of journey: offer one related theme, once.

### 3.7 Reminders and notifications (decision-blocked on D-PM6)

Follow `12b` §6 exactly. Contract:

- Off by default. Settings in `user_personalization_settings`.
- A reminder job selects only users with `reminders_enabled`, an active consent receipt and a push subscription. It builds a message that links to a saved item or the user's current journey step, using no teacher text in the push body (the body is "A saved teaching is waiting", not a quote; GURU-012 pattern).
- Suppression: no reminder within 24 hours after any distress or safety-route turn (needs a `last_safety_turn_at` marker in `user_personalization_settings` or a short-lived Redis key; Redis loss must suppress, not send). No reminder text mentions streaks, loss or missing.
- Every push carries a one-tap stop that sets `reminders_enabled=false`.
- The existing `daily-teaching-push` edge function (`supabase/functions/daily-teaching-push/index.ts`) is separate and opt-in; leave it unchanged here.
- Remove the win-back beat entry when T1-12 lands (`celery_config.py:96-99`). Never notify on the streak `at_risk` field (`12b` §1).

### 3.8 How personalisation may change framing

| Layer | May personalisation change it? | How |
|---|---|---|
| L1 teacher words (verbatim span) | **No** | Rendered from the store. |
| Citation, speaker label, verification label | **No** | Copied from the stored clip. |
| Clip selection and order | Yes, inside the gated set only | 3.6.1 table. |
| Assistant framing line (own labelled voice, ADR-001) | Yes, if D-03 is approved | One line that names the user's stated topic or goal, drawn from a canonical memory the user can see. Label: assistant voice. Never in a teacher's first person. Every such sentence carries `personalization.memory_ids` so the UI can show "Why this". |
| Follow-up offers and chips | Yes | Rule in 3.6.1. |
| Interpretation of the person's inner state | **No** | Not stored, not asserted (MEM-004). |

If D-03 is not approved, the framing line does not exist and personalisation is limited to order, language, depth and chips. `PersonalizeStage` (generated "personalised reflection") remains an opt-in exception behind its flag. It never receives `memory_context` for anything but the already consented, fenced block, and its output is always labelled and never cached (`personalize_cache_scope`, `personalize_stage.py` ~100-115).

Explainability payload: add an optional field to the public chat response, `personalization: {applied: [{kind: 'order'|'language'|'depth'|'continue_offer'|'framing', memory_ids: string[], label: string}]}`. Declare it in `ChatResponse` with `extra="forbid"` and add the matching TypeScript type. Do not put memory statements in this field, only ids and a short label. The UI shows a "Why this" popover that fetches the statement through the authenticated memory API. CLAUDE.md rule: any `grounding_state` or new public field must be in the `ChatResponse` schema or serialization fails.

### 3.9 Retention schedule (proposed values; owner sets them, D-PM4)

| Record | Retained until | Purge mechanism |
|---|---|---|
| `canonical_memories` (active) | The user corrects or deletes it. Optional `expires_at` for `TEMPORARY_CONTEXT` facts. | User action; daily job for `expires_at` |
| `memory_proposals` | 14 days after creation (placeholder) | Daily job sets `expired`, then deletes |
| `learning_events` | 12 months (placeholder) | Daily job on `expires_at` |
| `saved_teachings`, notes | The user deletes them | User action; erasure |
| `user_personalization_settings` | The user changes or deletes them | User action; erasure |
| `memory_outbox`, `pending_extractions` | Until processed; deleted on revoke | Existing worker and revoke path |
| Consent receipts, deletion receipts | Open question D-PM8 | [HUMAN] counsel |
| Shared answer cache (non-personalised) | Existing TTL (3600 s exact tier) | Existing |

The existing `cleanup_retention_data` job covers telemetry only (`backend/tasks/retention_tasks.py:13-48`). `NEW-MEM-9` adds the memory purge.

---

## 4. Behaviour per lifecycle step

Lifecycle: capture, consent, extraction, review, store, use, correct, export, delete.

| # | Step | Trigger | Gate (all must hold) | Action | Failure handling |
|---|---|---|---|---|---|
| 1 | Capture | End of a served turn | Signed-in persistable user id (`_is_persistable_user_id`); not Temporary Chat; route is not a safety route (new); `settings.memory_write` or `feature_memory_write` | Build a bounded window: the last turns plus this turn | Any exception is logged by class only and the turn continues. Memory never costs an answer (`config.py:1462-1463`). |
| 2 | Consent | Inside the background task, before any model call | `MemoryOutbox.active_consent(user_id, tenant_id)` returns the newest event as an active grant | Pass the receipt id forward | No outbox, timeout, error or no receipt: write nothing, call no model (`consent_gate.py:38-60`). |
| 3 | Extraction | Consent passed | Extractor prompt v-next (section 5) | Return candidates. The extractor writes nothing (`extractor.py:241-247`). | Provider missing, timeout or malformed JSON returns zero candidates. Contaminated output is rejected (`extractor.py:295-301`). |
| 4 | Review | Judge decision per candidate | Judge rules (`judge.py`) | `ACCEPT`-class and `explicit_request` facts go to step 5. `ESCALATE` creates a `memory_proposals` row. `IGNORE` drops. | Proposal insert failure: drop the candidate, count `memory_proposal_write_failed`, never fall back to storing it. |
| 5 | Store | Accepted candidate or accepted proposal | Receipt still active at write time (re-check) | Resolver upserts `canonical_memories` (tenant-local unique `fact_key`), writes an event row, then the vector (`vector_index.upsert`). | If the vector write fails after the row is written, mark the row `metadata.vector_pending=true` and let the existing drift repair (`self_healing.py` `detect_orphan_vectors`) retry. Do not read a memory whose vector is missing from vector search, but still list it for the user. |
| 6 | Use | Next request | Consent active AND the scope setting true AND not Temporary Chat | `prepare_user_memory` builds a fenced, PII-scrubbed block with a token budget; teaching lane builds `memory_signals` | Any failure returns an empty block. Personalised answers skip the shared cache. |
| 7 | Correct | User edits, forgets or rejects | Authenticated owner. Edit needs active consent; forget never does. | Section 3.4.3 | Partial multi-store failure returns 503 `incomplete` and a retry hint. Evict personalised caches even on partial failure (`memory.py:410-420` pattern). |
| 8 | Export | User taps "Download my memory" | Authenticated owner | Section 3.4.2 | 503 naming the store. No partial bundle. |
| 9 | Delete | One fact, all memory, revoke, or account | Authenticated owner | Section 3.4.4 | Receipt `partial_failure`; account deletion does not proceed (existing fail-closed rule, `delete-my-account/index.ts:48-62`). T6-06 adds a durable queue so deletion can complete when the backend is down. |

Consent withdrawal, in order, at the next request: (1) no durable read, (2) no extraction, (3) no outbox enqueue, (4) queued rows deleted, (5) exact and personal caches evicted, (6) `learning_events` and proposals insert blocked by the restrictive policy, (7) stored data stays until the user deletes it, and the page says so.

---

## 5. Deterministic steps versus model steps

| Step | Type | Owner | Notes |
|---|---|---|---|
| Consent lookup, scope AND, incognito check, persistable id, safety-route skip | Deterministic | Backend (S3) | No model. |
| Greeting and injection pre-reject | Deterministic | `extractor.py:168-183` | Extend, section below. |
| Candidate extraction | **Model** | S3. Provider chosen by `_build_client()` (`extractor.py:35-60`): `openrouter` uses `settings.model_for_classification`; other branches use Sarvam, NIM or Ollama. `temperature=0.0`. Prompt text `_EXTRACT_SYSTEM` (`extractor.py:197-221`). Move the prompt to the prompt registry with an id and version when T5-07 lands. | Output is untrusted data. |
| Candidate validation (enums, clamp, dedup, contamination gate) | Deterministic | `_validate_candidate`, `find_artifact` | |
| Judge: worthiness, user-specificity, sensitivity, confidence, supersession | Deterministic rules plus an optional model assist | `judge.py`. Read before changing: `judge.py:240-300`. | Keep rules deterministic. |
| Proposal accept or reject | Human | User | |
| Embedding | Model (embedding) | Memory vector index (`_DIMENSION`, `vector_index.py`) | Dimension pinned. |
| Retrieval and re-rank of memories | Deterministic scoring over vectors | `retriever.py` | Always filtered by `user_id` and tenant. |
| Topic slug for a learning event | Deterministic | Topic rail or facet registry | No model call. |
| Clip re-order by unseen | Deterministic stable sort | Teaching lane | No model call. |
| Framing line (if D-03 approved) | **Model** | Answer composer (T5-03, ADR-001) | Input: the user's stated topic from consented memory (fenced) plus a clip id. The composer prompt must not receive any other memory. Output verified by T5-04 (no teacher first person, no new factual claim). |
| Persona text, skills text | **Model** | Retire (T6-03, MEM-004) | Do not extend. |
| Edge-function extraction (`memory-extract`, `memory-extract-drain`) | **Model** (Lovable gateway, `google/gemini-2.5-flash`) | S3 plus T6-08 | Disable the edge path, or route it through the backend gateway after the processor inventory. Two extraction pipelines must not both run. |

### Untrusted-content fence (applies to every model step above)

1. Seeker text, assistant text, stored memory text, notebook text and the client summary are **data**, never instructions.
2. Put policy in the system role. Put conversation text in a separate delimited data block or a JSON payload. The edge function already does this (`memory-extract/index.ts:99-112`). The backend extractor does not (`extractor.py:224-232`, MEM-012). Change `_build_user_prompt` to wrap the window in `<<<BEGIN_CONVERSATION_DATA>>> ... <<<END_CONVERSATION_DATA>>>` and strip any occurrence of those markers from the text first. The same marker pair rule already exists for memory (`context_builder.py:255-257`).
3. Extract only what the **user** said. Facts that appear only in an assistant turn are rejected in code: require the `evidence` quote to be a substring of a `user` turn (deterministic check after the model returns). This blocks "the teacher said X" being stored as a fact about the user.
4. Merge the two injection lists into one module (`security.py` `INJECTION_PATTERNS` and `extractor.py` `_INJECTION_RE`). Add Indic-script and transliterated variants only after native-speaker review ([HUMAN], D-22). Treat the filter as a speed bump, not a control. The controls are 2, 3 and 6.
5. Output must parse as the declared schema. Anything else yields zero candidates.
6. Stored memory never appears as an instruction: it renders inside the memory fence with the label "user-stated, untrusted" and is never concatenated into the system prompt. `generation.py:1995` already fences it.
7. A stored memory is never evidence for a doctrinal claim and never enters `citations[]`. The `canonical_memory_evidence` class is allowed to ground only statements **about the seeker** (the current design, `orchestrator_utils.py:1016-1035`). Add a test (AC-PM-27) that a memory saying "Sri X taught that Y" cannot be cited as a teaching.
8. Memory text longer than 1000 characters, or containing a URL, a markdown link or a fence marker, is rejected at extraction and at `POST /api/memory/canonical`.

---

## 6. Observability (privacy-safe)

Rules (T1-09, T2-03):

- No seeker text, memory statement, note, proposal text or clip text in any log line, span attribute or metric label.
- Log a stable hash of `user_id` only when a log line needs one. Today some warnings include the raw user id (for example `orchestrator_utils.py` second-brain timeout). Replace with the hash in the same PRs that touch those lines.
- Metric labels are bounded enums. No user id, no tenant id, no topic slug.
- Use `sanitize_log_input` for any value that must be logged.
- `intent_prerouter.py:101` already logs a query tag (`_q_tag`) instead of the query; follow that pattern.

Proposed metrics (names are proposals; the existing code exposes `NODE_ERROR_TOTAL{node}` and `telemetry_sink_writes_total{outcome}`):

| Metric | Labels | Use |
|---|---|---|
| `memory_consent_check_total` | `surface` (`read`,`write`,`side_effect`,`reminder`), `result` (`granted`,`denied`,`error`) | Watch the error rate. A rising `error` means features silently off. |
| `memory_candidates_total` | `decision` (`accept`,`escalate`,`ignore`,`reject_injection`,`reject_evidence`) | Quality of extraction. |
| `memory_proposals_total` | `state` | Share accepted versus rejected. High reject share means the extractor is too eager. |
| `memory_store_result_total` | `step` (`row`,`vector`,`event`), `result` | Vector-pending drift. |
| `memory_erasure_store_total` | `store`, `result` | Per-store erasure result. Alert on any `error`. |
| `personalization_applied_total` | `kind` | Whether personalisation does anything. Zero for 14 days means remove the controls (UX-009). |
| `saved_teachings_availability_total` | `state` | Withdrawal and correction volume. |
| `export_requests_total` | `result` | |
| `reminder_sent_total`, `reminder_suppressed_total` | `reason` (`safety_window`,`no_consent`,`opted_out`) | Guardrail: opt-outs per sent. |

Guardrail metrics from `12b` §3.3 that this spec feeds: repetitive answers (`learning_events` repeat rate), notification opt-outs, deletion friction (time from request to completion), dependency signal (clinician-defined, T6-07). Compute them in aggregate jobs; no per-user dashboards.

Audit trail: `canonical_memory_events` stays the memory audit record. Consent changes stay in `memory_consent_receipts`. Both hold statement copies or user ids; both are in the erasure registry.

---

## 7. Acceptance criteria

Legend: **S** = runs in CI with mocks or fixtures (no live system). **P** = needs a real Postgres with the repo migrations (new fixture, `NEW-MEM-1`). **Q** = needs a real Qdrant (fixture exists: `.github/workflows/fixture-stores.yml`, commit `60076bc5`). **L** = needs live or staging systems. **H** = needs a human.

| # | Criterion | Test (file, case) | Pass / fail | Type |
|---|---|---|---|---|
| AC-PM-01 | No durable read, write or side effect without an active receipt, on every surface. | `backend/tests/test_memory_consent_surfaces.py::test_{read,extract,outbox,course,trend,learning_event,reminder}_denied_without_consent` (extends `test_emotional_side_effect_consent.py`) | Pass: each surface performs zero store calls with `active_consent=None`. Fail: any call. | S |
| AC-PM-02 | Consent lookup error fails closed on every surface. | Same file, `::test_*_denied_on_lookup_error` | Pass: denied and counted as `error`. | S |
| AC-PM-03 | Scoped setting AND consent: a scope is off if either is false. | `test_personalization_settings.py::test_effective_requires_consent_and_setting` (new) | Pass: 4-cell truth table. | S |
| AC-PM-04 | Proactive suggestions default off. A new user gets `effective.proactive_suggestions=false`. | `test_personalization_settings.py::test_defaults_off` (new) | Pass. | S |
| AC-PM-05 | Consent withdrawal: next request has no memory block, no extraction, no enqueue; queued rows and personalised cache entries are deleted; stored memory remains until deleted. | `test_memory_consent_withdrawal.py::test_revoke_stops_all_use_but_keeps_data` (new); extends `test_memory_api.py` | Pass: all seven effects in section 4. | S |
| AC-PM-06 | Withdrawal is real in Postgres: after revoke, direct client INSERT into `canonical_memories`, `memory_proposals` and `learning_events` fails (RLS), while DELETE and `status='deleted'` UPDATE succeed. | `backend/tests/db/test_memory_rls_real.py::test_revoked_user_writes_blocked_deletes_allowed` (new) | Pass: SQLSTATE `42501` on insert, success on delete. | P |
| AC-PM-07 | Cross-user leakage (Postgres): user A cannot select, update or delete user B rows in every memory table, including new tables. | `backend/tests/db/test_memory_rls_real.py::test_cross_user_isolation[table]` parametrised over the registry | Pass: zero rows visible, zero rows affected. Fail: any. The existing `test_canonical_memory_store.py:257` test uses a mock and proves nothing about RLS. | P |
| AC-PM-08 | Cross-user leakage (vectors): searching with user A's id never returns user B's points; the filter is server-side. | `test_canonical_memory_vector_index.py::test_search_never_returns_other_user` (new) (Q) | Pass. | Q |
| AC-PM-09 | Cross-user leakage (cache): two users, same question; B never receives A's personalised answer; a personalised answer is not written to any shared tier. | Extends `test_cache_personalization_leak.py` with `memory_signals` and `guru_tone`; add `::test_signals_applied_answer_not_cached` and `::test_second_user_gets_no_personal_answer` | Pass: `exact_cache.set`, hot cache and semantic put not called. | S |
| AC-PM-10 | Cross-user leakage (API): every new endpoint returns 404 for another user's id and never echoes foreign ids. | `test_saved_teachings_api.py::test_other_users_item_is_404`, `test_memory_proposals_api.py::test_other_users_proposal_is_404` | Pass. | S |
| AC-PM-11 | Tenant scoping: a memory in tenant X is not read in tenant Y; legacy points with no tenant payload are deleted by a scoped forget. | `test_canonical_memory_vector_index.py::test_forget_removes_legacy_untenanted_point` (new) (Q) | Pass. | Q |
| AC-PM-12 | Erasure cascade (Postgres): deleting the consent receipt (and then the user) leaves zero rows in `memory_outbox`, `pending_extractions`, `memory_proposals`, `learning_events`, with no `42501` abort. | `backend/tests/db/test_memory_erasure_cascade.py::test_receipt_delete_cascades_children` (new) | Pass: all child tables empty and the delete succeeds. Fail: any row, or the transaction aborts. Guards the `ON DELETE CASCADE` rule. | P |
| AC-PM-13 | Migration contract: every new table's `consent_receipt_id` FK is `ON DELETE CASCADE`; no `SET NULL`. | `test_memory_consent_migration_contract.py::test_new_tables_use_cascade` (new) | Pass: regex on migration SQL. | S |
| AC-PM-14 | Single forget removes row, vector, cache. | `test_memory_forget_propagation.py::test_forget_row_vector_cache` (new) | Pass: all three removed; vector selector contains `IsEmptyCondition(key="tenant_id")`. | S / Q |
| AC-PM-15 | Erasure certificate: `delete_all_memory_endpoint` returns `completed` only if every registry store returned a count or zero without error; a failing store yields `partial_failure` naming it. | Extends `test_memory_delete_all_completeness.py::test_delete_all_reports_partial_failure_when_a_store_fails` to iterate the registry | Pass. | S |
| AC-PM-16 | Seeded-marker erasure: after account deletion on a seeded staging database, a text search of every table and Qdrant payload finds zero rows containing the marker. | `evals/` drill script (extends `nightly-rls.yml`, SEC-004) | Pass: 0 hits. | L |
| AC-PM-17 | Zero-UUID bulk-forget audit event is written only with action `DELETED`, and only when no live canonical memory remains. | `test_canonical_memory_api.py::test_zero_uuid_audit_only_after_all_deleted` (new) | Pass: `DELETED` allowed; any other action rejected; refused while a live row exists. | S |
| AC-PM-18 | The three erasure lists agree. | `test_memory_store_registry.py::test_erasure_lists_match_registry` (new) compares `memory.py`, `delete-my-account/index.ts` table array (parsed), and `cascade_erasure.PRIMARY_26_TABLES` | Pass: set equality (minus an explicit allowlist with reasons). | S |
| AC-PM-19 | `study_notebooks` is never filtered by `tenant_id`. | `test_repo_layout`-style grep guard: `test_notebooks_not_tenant_filtered` | Pass: no `tenant_id` filter on `study_notebooks` in `backend/`. | S |
| AC-PM-20 | Export completeness: the bundle includes every registry store marked exportable; a failing store returns 503 naming it; no partial bundle. | `test_memory_export.py::test_export_includes_all_registry_stores` (new), `::test_export_fails_closed` | Pass. | S |
| AC-PM-21 | Memory-poisoning (instruction): turns containing "ignore previous instructions", fence markers, a fake system block, and a long base64 blob never produce a stored fact; extraction input is delimited. | `test_memory_poisoning.py::test_instruction_text_not_stored[param]`, `::test_fence_markers_stripped`, `::test_extractor_prompt_is_delimited` | Pass: zero candidates stored; prompt contains one data block. | S |
| AC-PM-22 | Memory-poisoning (read side): a stored memory containing instructions renders inside the memory fence and cannot alter the system prompt, the route, the clip choice rules or the safety lane. | `test_memory_poisoning.py::test_stored_instruction_is_fenced_and_inert` (new) (build prompt, assert placement; run teaching-lane selection with a poisoned `memory_signals` and assert the same gated set) | Pass. | S |
| AC-PM-23 | Memory-poisoning (attribution): a memory "Sri X taught Y" never appears in `citations[]`, never labelled as a teacher quote, and never grounds a doctrinal claim in the verifier. | `test_memory_poisoning.py::test_memory_cannot_be_teacher_citation` (new) | Pass. | S |
| AC-PM-24 | Memory-poisoning (assistant-only fact): a fact appearing only in an assistant turn is rejected by the evidence-substring check. | `test_canonical_memory_extraction.py::test_evidence_must_be_user_turn_substring` (new) | Pass. | S |
| AC-PM-25 | Safety turns are not extracted. | `test_memory_safety_skip.py::test_distress_turn_not_extracted` (new), `::test_crisis_route_not_enqueued` | Pass: zero extractor calls, zero outbox rows. | S |
| AC-PM-26 | Sensitive candidates become proposals, not memories. | `test_memory_proposals.py::test_escalate_creates_proposal_not_memory`, `::test_accept_requires_consent`, `::test_reject_suppresses_90_days` | Pass. | S |
| AC-PM-27 | Personalisation never changes teacher words. | `test_personalization_verbatim.py::test_signals_do_not_alter_verbatim_or_label` (new) (hash of `verbatim_text`, `speaker`, `speaker_verified` equal with and without signals), `::test_reorder_only_inside_gated_set` | Pass: byte-equal; no candidate outside the gated set. | S |
| AC-PM-28 | Repeat-clip rate for returning seekers: on a fixed multi-session fixture, repeat rate is at most 20% (12 target). Continuity score ≥4/5 on ≥60% of multi-session items by blind raters. | Fixture test for the rate; `18` §5 items for raters | Pass on fixture; raters need people. | S / H |
| AC-PM-29 | Saved teachings hold no teacher text. | `test_saved_teachings_schema.py::test_no_text_columns` (new) (parses migration) | Pass: no `verbatim*`, `transcript_text`, `snippet` column. | S |
| AC-PM-30 | Withdrawal propagation: when a clip stops being servable, the saved item reads `withdrawn`, returns no text and no link, keeps the note, and appears in the takedown count. | `test_saved_teachings_availability.py::test_withdrawn_clip_hidden` (new), `::test_changed_hash_shows_current_text_only`, `::test_store_down_is_unknown_not_stale` | Pass. | S |
| AC-PM-31 | Withdrawal on a real collection: remove a point from a fixture collection, run the job, item flips. | `test_saved_teachings_availability.py::test_job_flips_availability` (new) | Pass. | Q |
| AC-PM-32 | Legacy notebook items: takedown flags items whose citations hold the video id; the UI hides `answer`. | `test_notebook_takedown.py::test_flags_by_video_id` (new); `src/test/StudyNotebookPage.test.tsx::hides_answer_when_withdrawn` | Pass. | S |
| AC-PM-33 | Saved-item provenance: `speaker_verified` and `voice_verification_method` are copied from the clip, never inferred. | `test_saved_teachings_api.py::test_provenance_copied_not_inferred` (new) | Pass: unverified clip stays unverified. | S |
| AC-PM-34 | Reminders: default off; no reminder within 24 h of a safety turn; Redis loss suppresses; stop link disables; body holds no teacher text and no streak language. | `test_reminders.py::test_default_off` (new), `::test_safety_window_suppresses`, `::test_redis_down_suppresses`, `::test_stop_disables`, `::test_body_lint` | Pass. | S |
| AC-PM-35 | Banned phrases: no locale string with "keep it going", "taking root", "we miss you", or loss framing in reminder or journey copy. | `src/test/locale-banned-phrases.test.ts` | Pass. | S (+H for native review) |
| AC-PM-36 | Retention: expired proposals, learning events and (if set) memories are purged by a daily job; the job logs counts only. | `test_memory_retention_job.py::test_purges_expired` (new), `::test_logs_counts_only` | Pass. | S |
| AC-PM-37 | UI shows what the model reads: with seeded canonical rows, the memory page lists them; forgetting in the page removes them from the next prompt. | `src/test/MemoryManager.test.tsx::lists_canonical_and_forget_removes_from_prompt` plus backend `test_memory_ui_model_parity.py::test_ui_list_equals_prompt_source` (new) | Pass. | S |
| AC-PM-38 | Privacy of logs: a seeded marker in seeker text, a memory and a note never appears in captured logs or metric labels during capture, extract, propose, save, export, delete. | `test_memory_log_hygiene.py::test_marker_absent_from_logs` (new) (caplog) | Pass: zero matches. | S |
| AC-PM-39 | Real consent copy and version: the consent text shown matches the stored `consent_version`; native-speaker review done for 13 locales. | Review record | Pass: signed record. | H |
| AC-PM-40 | Legal retention of consent and deletion receipts after account deletion. | Counsel note filed (D-PM8) | Decision recorded. | H |
| AC-PM-41 | End-to-end on staging: revoke consent, delete one fact, export, delete account; every step visible in the UI with the right copy. | `e2e/memory-lifecycle.spec.ts` (Playwright) | Pass. | L |

---

## 8. Ordered implementation tasks (PR-sized)

Each task is one PR. Order matters: tests and the registry come first.

| Order | Task ID | Title | Scope and files | Depends on | Non-goals | Rollback |
|---|---|---|---|---|---|---|
| 1 | NEW-MEM-1 | Real-Postgres RLS fixture and memory RLS tests | New CI job with Postgres plus repo migrations; `backend/tests/db/test_memory_rls_real.py`, `test_memory_erasure_cascade.py` (AC-PM-06, 07, 12). The existing fixture workflow covers Qdrant and Redis only (commit `60076bc5`). | T2-05 pattern | No schema change. | Remove the workflow. |
| 2 | NEW-MEM-2 | Memory store registry and one erasure list | `backend/services/memory_store_registry.py`; refactor `memory.py:1095-1343`, `cascade_erasure.py`, parse-check against `delete-my-account/index.ts` (AC-PM-15, 18, 20 part). Behaviour identical. | 1 | No new stores. No change to receipt retention. | Revert; old lists remain in git. |
| 3 | T1-10 (rest) + NEW-MEM-3 | Scoped settings and opt-in side effects | Migration `user_personalization_settings`; `personalization_settings.py`; gate course assignment, trend, emotional arcs on settings AND consent; `PersonalizationCard.tsx`; locale keys. Closes D-21 once approved. | 2; D-21, D-PM2 | No reminders UI. No consent version bump. | Migration is additive; flip the code to read "all false". |
| 4 | NEW-MEM-4 | Show what the model reads | Interim two-section `MemoryManager` over canonical plus legacy; canonical list, edit, forget wired; "why" link (AC-PM-37). | 2 | No data migration. | Revert UI; routes unchanged. |
| 5 | NEW-MEM-5 | Proposals and no extraction on safety turns | Migration `memory_proposals`; judge `ESCALATE` persists; accept/reject API; list UI; safety-route skip in `memory_stage.py` and `first_person_bridge.py`; extractor fence and user-turn evidence check; merged injection list (AC-PM-21 to 26). | 3 | No LLM change besides the prompt wrapper. No push notices. | Set a flag `MEMORY_PROPOSALS_ENABLED=false` (new, default off, read at the call site per root rule); escalated candidates are dropped again. |
| 6 | T6-03 | Stated preferences replace the LLM persona | Retire `l3_persona_generator.py` use and `/memory/persona*`; show settings instead (MEM-004). | 3 | No new inferred labels. | Re-enable the routes. |
| 7 | NEW-MEM-6 | Memory export and erasure receipt rule | Extend `/api/memory/export` over the registry; button in `AccountDataCard.tsx`; receipt-retention rule per D-PM8 (AC-PM-20, 40). | 2; D-PM8 | No change to `export-my-data` beyond a pointer. | Revert. |
| 8 | T6-04 (part 1) | Saved teachings and collections | Migration `saved_teachings`; service and API; `SaveClipButton`; `SavedTeachingsPage`; report menu (AC-PM-10, 29, 33). | 2; D-PM5, D-PM7 | No journeys. No copy of teacher text. | Hide the route; table is additive. |
| 9 | NEW-MEM-7 (with T3-06 hook) | Availability revalidation and takedown fan-out | Daily job calling `points_servable`; `flag_withdrawn(...)`; notebook `source_status` column and UI hide (AC-PM-30 to 32). T3-06 is a reserved task: build the job and the hook function now, and call the hook from `takedown()` only when the owner names T3-06. | 8 | No source-registry work. | Disable the beat entry. |
| 10 | T6-02 + NEW-MEM-8 | Memory on the teaching lane | Migration `learning_events`; `record_learning_event`; `memory_signals` into `FirstPersonPipeline`; chip; `personalization` field in `ChatResponse` plus TS type; cache eligibility extension; skip-read when unusable (AC-PM-09, 27, 28). | 3, 5, T7-01 (done) | No framing line. No re-ranking outside the gated set. | Flag `FIRST_PERSON_MEMORY_SIGNALS_ENABLED=false` (new, default off). |
| 11 | NEW-MEM-9 | Retention purge job | Beat task for expired proposals, learning events and expired memories (AC-PM-36). | 5, 10; D-PM4 | No purge of audit tables. | Disable the beat entry. |
| 12 | T6-08 + T1-20 | Processor disclosure and copy | Inventory; route or disable the edge extractor; privacy copy; native review (AC-PM-39). | owner (DPA) | | |
| 13 | NEW-MEM-10 | Reminders | Settings UI, job, suppression, stop link (AC-PM-34, 35). Decision-blocked. | 3, 8, T1-12; D-PM6 | No streak notices. | Disable beat entry; set all `reminders_enabled=false`. |
| 14 | NEW-MEM-11 | Learning journeys v1 | Tables, curator tooling, UI (decision-blocked, D-PM9). | 8, 9, rights (14c) | No score, badge, percentage. | Unpublish all journeys. |
| 15 | T6-01 | Consolidate onto canonical memory | Migrate legacy facts into canonical with provenance; delete the legacy read branch; remove dead modules. Needs snapshot and owner approval. | 4, 5, 7; D-PM1 | | Restore snapshot. |
| 16 | T6-06 (reserved) | Durable erasure queue and purge job | Consume the registry. Reserved: do not start unless the owner names you. | 2 | | |
| 17 | T6-07 (reserved, clinician) | Dependency guard | Feeds the reminder and chip suppression rules. | clinician | | |
| 18 | T1-12 (D-19) | Replace the churn funnel | Direct confirm-and-delete flow with an export offer. Reminder and win-back removal. | D-19 | | |
| 19 | T5-03 / T5-04 | Optional framing line (only if D-03 yes) | Composer, verifier, label. | D-03 | | |
| 20 | T2-03 | Telemetry for the metrics in section 6 | | | | |

> **Update 2026-11-06 (batch 10, 649ea2c3):** T6-03 landed in a smaller form. `l3_persona_generator.py` still calls an LLM; its prompt now allows only user-stated facts. `compile_user_preferences` has no caller outside its test. `/memory/persona*` is not retired. MEM-004 is Partial. T6-04 (batch 13, `a33d6b8d`) did not build `saved_teachings`: it added `POST/GET/DELETE /api/feedback/saved-answers` backed by a local JSONL file (`backend/app/api/feedback.py:572-640`). T6-02 is covered by the update note under the sentence about `memory_signals` in section 2.

Task IDs from the roadmap used: T1-09 (landed, verified at `intent_prerouter.py:101`; extend with hashed ids), T1-10, T1-12, T1-20, T2-03, T3-06, T5-03, T5-04, T6-01, T6-02, T6-03, T6-04, T6-06, T6-07, T6-08. New: NEW-MEM-1 to NEW-MEM-11.

Do not start reserved tasks (T6-06, T6-07, T3-06) unless the owner names you for them in writing (`IMPLEMENTATION-AGENT-PROMPT.md` §0j).

Migration rules for every PR: add `-- REVERT: MANUAL ONLY` header with the rollback notes; additive columns first; snapshot before any data move; no `SET NULL` on any `consent_receipt_id`; new tables get `GRANT ... TO service_role` in the same file; update the CI schema snapshot (T3-08).

---

## 9. Open questions

Existing items touched: D-03, D-19, D-21, D-22 (native review scope), D-23 (use of real seeker questions: do not use stored memory or proposals as evaluation data), `unresolved-questions.md` L-series for live data.

Proposed (not decided):

| ID | Question | Why it matters | Compliant variant (recommended) | Decision-gated variant | Tasks |
|---|---|---|---|---|---|
| PROPOSED D-PM1 | Make `canonical_memories` the only store the UI manages, and retire the legacy planes? | MEM-007; ADR-010. | Yes. Interim two-section page first (NEW-MEM-4). | Keep legacy planes indefinitely. Not recommended: the user cannot see what the model reads. | NEW-MEM-4, T6-01 |
| PROPOSED D-PM2 | Store per-turn distress level or emotional arcs at all? | Health-adjacent inference; MEM-003. | Off by default; stored only if `emotional_context_use` is on. | Never store. Safer; disables the healing-course feature. | NEW-MEM-3 |
| PROPOSED D-PM3 | Review model for extracted facts: variant A (sensitive and inferred go to a proposal queue; normal user-stated facts are stored and shown with undo) or variant B (every automatic fact waits for approval)? | Trust versus friction. | A. | B. | NEW-MEM-5 |
| PROPOSED D-PM4 | Retention values: proposals 14 days, learning events 12 months, expired memory rules, suppression 90 days. | The figures here are placeholders from doc 12 §4.1 and this spec, not measured. | Owner sets values. | | NEW-MEM-9 |
| PROPOSED D-PM5 | May a user save a clip while in Temporary Chat? | The header says "not saved". | Allow, with a one-line notice that the save is kept (a save is a user action). | Block saving in Temporary Chat. | T6-04 |
| PROPOSED D-PM6 | Are reminders in scope for the faculty release? Channel (push only, email)? | Notification ethics; email needs processor disclosure. | Push only, opt-in, off by default. | Email reminders. Needs T6-08. | NEW-MEM-10 |
| PROPOSED D-PM7 | When a saved teaching is withdrawn: hide fully or show a tombstone with the note? | UX and rights. | Tombstone with note and no text or link. | Silent removal. | NEW-MEM-7 |
| PROPOSED D-PM8 | After account deletion, may the system keep a minimal erasure receipt (no content, hashed id, counts) and consent history? | DPDP evidence. Today both are deleted with the account (`delete-my-account/index.ts:136-160`). | Keep a content-free receipt; counsel decides period. | Delete all. | NEW-MEM-6; [HUMAN] counsel |
| PROPOSED D-PM9 | Who curates learning journeys, and how many are needed to launch? | Curator time; rights. | Owner or faculty curators; start with 1 to 3 journeys. | Retrieval-proposed, curator-approved. | NEW-MEM-11 |
| PROPOSED D-PM10 | Which extraction path survives: backend extractor or edge-function extractor? | Two pipelines; processor disclosure (ADV-02). | Backend extractor only; disable the edge drain. | Keep edge path with disclosure and consent text. | T6-08 |

New unknowns for `unresolved-questions.md`: see section 2.5 ([LIVE-L] / [LIVE-R]).

---

## 10. Verified, assumptions, unknowns

### Verified (read at `c9b42d3e`)

- The consent gate for course assignment and proactive Serene Mind is in code and tested (`orchestrator_utils.py:598-667`, `distress_stage.py:649-657`, `test_emotional_side_effect_consent.py`).
- The client summary and memory are fenced in the general prompt (`generation.py:1995, 2007-2009`).
- Memory UI routes act on `guru_memories`; the prompt reads canonical memory; canonical routes have no UI caller (MEM-007).
- `ESCALATE` candidates are dropped (MEM-008).
- `export-my-data` omits memory; `/api/memory/export` covers canonical only (MEM-009).
- Notebook items store answer text and free-form citations; no withdrawal path (MEM-010).
- Consent is one `memory-v1` scalar; account deletion removes receipts (MEM-011).
- The extractor does not fence its input; the injection regex is English-only (MEM-012).
- `ON DELETE CASCADE` on both queue tables is enforced by a DO block (`20261021000100_require_active_memory_consent.sql:84-130`).
- The vector selector includes `IsEmptyCondition(key="tenant_id")` through `_tenant_scope` (`vector_index.py:62-72`).
- The cache eligibility predicate and its leak test exist.
- `points_servable` exists and checks rights and eligibility (`first_person_store.py:601`).
- No code in the first-person bridge reads memory.
- Win-back beat entry and `CancelFlow` are still present.

### Assumptions

- A pointer-only saved item is acceptable to the rights owner (14c). Counsel and the content owner confirm. [HUMAN]
- `point_id` stays stable across serving collections while `transcript_hash` and offsets stay equal (invariant 4). T3-03 renames hash fields in vNext; the pointer stores both `source_text_hash` and `transcript_hash` to survive that change. [INF]
- Notebook `citations` entries can be mapped to a `video_id` from their URL. [INF]
- The topic rail provides a deterministic topic slug per served clip. [INF] Verify before NEW-MEM-8.
- A Postgres service container can run the repo migrations in CI. [INF] (Supabase-specific objects such as `auth.users` and `auth.uid()` need stubs; the 3.4 tests rely on them.)

### Unknowns

- Production data shape for the memory planes; deployed tenant defaults; deployed LLM provider for extraction; deployed state of `VITE_MEMORY_EXTRACTION_ENABLED` (section 2.5).
- Whether the clinician-defined dependency rule (T6-07) will require suppression of chips or reminders beyond those here.
- Legal period for keeping consent and erasure evidence (D-PM8).
- The native-speaker review status of all 13 non-English locales for memory and consent copy.
- Staging measurements: this specification states no latency or quality figure as fact; none was measured.

Evidence-claims note: nothing in this document states that the product is ready for release. Memory consent and erasure end-to-end behaviour on a deployed stack is UNPROVEN until AC-PM-16 and AC-PM-41 pass on staging.

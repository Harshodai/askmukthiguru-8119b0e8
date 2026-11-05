# 12 — Personal mentor: memory and personalisation architecture

Owner: S3 (architecture). Companion: `12b-ethical-retention-and-mentor-ux.md` (S4: UX, retention hooks, north-star metric).
Target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`. Line numbers read at `main@46b808fb`; ranges ±10 lines.
Related: `14` (S1: privacy, RLS, erasure), `06` (S2: datastores), `10` (answer behaviour).

## 0. Summary

| # | Statement | Label |
|---|---|---|
| 1 | At least nine memory planes exist (including WhatsApp bot SQLite and edge extraction worker), plus two dead modules. One request can merge up to five of them into one prompt string. | [V-STATIC] |
| 2 | Durable memory reads are gated by an active consent receipt and skipped for Temporary Chat. This part is well built. | [V-STATIC] |
| 3 | On the live teaching lane (first-person clips), memory is read but never used. The seeker gets no continuity or personalisation where it matters most. | [V-STATIC] |
| 4 | Two personalisation side effects read durable emotional history without the consent gate: healing-course assignment and the proactive Serene Mind trend. | [V-STATIC] (probable defect; [LIVE-L] to confirm data presence) |
| 5 | Users can list, edit, forget, export and erase memory through 23 API routes. Transparency tooling exists. | [V-STATIC] |

---

## 1. Inventory: what is remembered and where

| # | Plane | Code | Store (migration) | Written by | Read into prompts by | State |
|---|---|---|---|---|---|---|
| 1 | Canonical memory (facts with provenance, supersession, compaction) | `services/canonical_memory/` (26 files: extractor, judge, resolver, consolidator, retriever, consent_gate, privacy, vector_index…) | `canonical_memories`, `canonical_memory_events`, compaction snapshots (`supabase/migrations/20260912000000_create_canonical_memory_events.sql`, `20261022000100_…`) + vector index | `canonical_memory_integration` after each turn; FP turns via `_dispatch_fp_memory` (`app/pipeline/stages/first_person_bridge.py:100-215`) | `prepare_user_memory` (`app/orchestrator_utils.py:970-1010`) | Live; `canonical_memory_enabled=True`, `memory_write=True` (`config.py:1434`, `:1445`) |
| 2 | Memory outbox + consent receipts | `services/memory_outbox.py`; `tasks/memory_outbox_tasks.py` | `memory_outbox`, `pending_extractions`, `memory_consent_receipts` (`20260805000001_memory_outbox.sql`, `20261021000000…000200`) | Memory stage, FP dispatch | Consent check only | Live |
| 3 | Layered memory (L1 atomic facts, L2 scene compression, L3 persona, skills) | `services/layered_memory/` | `user_personas` (`20260728000000_create_user_personas.sql`), memory layer tables (`20260607180000_memory_layer.sql`) | Celery `tasks/layered_memory_tasks.py` | Persona block in `prepare_user_memory`; `/memory/persona` | Live when consented |
| 4 | Memory service v2 (core + semantic) | `services/memory_service_v2.py` (1,890 lines) wrapping `services/memory_service.py` | `guru_memories` etc. | API and tasks | `fetch_memory_layer` (`orchestrator_utils.py:1045-1130`) | Live when consented |
| 5 | Legacy user profile + conversation memories + emotional arcs | `services/user_profile_service.py` | `user_memory` (`20260516190000_user_memory.sql`), profile tables | Profile updates every turn (`orchestrator_utils.py:1015-1036`) | `build_memory_context` | Live |
| 6 | Second Brain vault (encrypted personal notes) | `services/second_brain/` | vault tables | User actions | `fetch_second_brain` (`orchestrator_utils.py:933-955`) | Live when unlocked |
| 7 | Study notebooks | `services/notebook_service.py` | `study_notebooks` (`20260630140000_study_notebooks.sql`; scoped by `user_id`, no `tenant_id`) | UI | Not in chat prompts | Live (UI feature) |
| 8 | Personal knowledge graph | `app/api/memory.py:802-960` `/memory/knowledge-graph` | Derived from planes 1, 4, 5 | Read-time derivation | `PersonalizeStage` eligibility | Live |
| 9 | WhatsApp bot SQLite | `whatsapp_bot/wa_bot.py:121-185` | SQLite `wa_messages`, `wa_state` | Webhook handler | In-session continuity only | Disabled by policy (ADV-06) |
| 10 | Edge extraction worker | `supabase/functions/` (ADV-02) | Pending extraction queue | Webhooks/triggers | Asynchronous memory ingestion | Scoped background (ADV-06) |
| — | `services/personalization/unified_engine.py` | — | — | — | No importers | Dead |
| — | `services/memory/episodic.py` | — | — | — | No importers | Dead |

Count of read sources merged into `memory_context` per turn: up to 5 (second brain, canonical, profile, recent memories, memory layer/persona). Early return: when the canonical block exists, the function returns second-brain + canonical only (`orchestrator_utils.py:1000-1008`).

---

## 2. Flow per turn

| Step | What happens | Gate | Evidence |
|---|---|---|---|
| 1 | Temporary Chat → no reads, no side effects | `chat_body.incognito` | `orchestrator_utils.py:543-556` |
| 2 | Relevance probe: generic questions skip durable reads | relevance classifier, fails open | `orchestrator_utils.py:861-890` |
| 3 | Consent: no active receipt → skip all durable reads | `MemoryOutbox.active_consent` | `orchestrator_utils.py:893-920` |
| 4 | Reads under one time budget; canonical has its own 2 s timeout | budgets | `orchestrator_utils.py:926-990` |
| 5 | PII scrub on the merged string | `_scrub_memory_context` | `orchestrator_utils.py:843-860` |
| 6 | Healing-course assignment (side effect) | `proactive_course_assignment_enabled=True`, signed-in, not incognito. **No consent check.** | `orchestrator_utils.py:577-610`, `:636-705`; `config.py:1678` |
| 7 | Proactive Serene Mind trend | `proactive_serene_mind_enabled=True`; reads `user_profile.get_recent_memories` | `distress_stage.py:288-300`, `:638-660`; `serene_mind_engine.py:1960-1990` |
| 8 | Teaching lane | `memory_context` not used by `FirstPersonPipeline` | `first_person_bridge.py:660-990` (no memory reference) |
| 9 | General lane | `memory_context` fenced into USER STATE; client `conversation_summary` (≤4,000 chars) appended unfenced | `rag/nodes/generation.py:1983-2039`; `app/schemas/__init__.py:153-160` |
| 10 | Writes after answer | Memory stage (general) or `_dispatch_fp_memory` (FP), consent-bound outbox | `app/pipeline/stages/memory_stage.py`; `first_person_bridge.py:100-215` |
| 11 | Shared cache never stores memory-personalised answers | cache key `(language, message)` | root `CLAUDE.md`; `tests/test_cache_personalization_leak.py` |

---

## 3. Findings

### MEM-001 — Seven overlapping memory planes
| Field | Value |
|---|---|
| Pillars | P3, P5, P1 |
| Category | Architecture / data model |
| Severity | P2 |
| Type | Confirmed defect (complexity) |
| Confidence | High |
| Evidence | §1 table. |
| Actual behaviour | Facts about one person can live in canonical memory, layered L1 facts, memory v2 core, legacy profile memories and persona text, with different extraction prompts (`services/layered_memory/prompts.py:1`, canonical extractor/judge) and different deletion paths. |
| Expected behaviour | One canonical store of user facts with provenance; derived views (persona summary, graph) rebuilt from it. |
| Root cause | Successive memory projects were added without retiring predecessors (task list §1 item 6). |
| User impact | Corrections in one plane can survive in another; contradictory facts reach prompts. |
| Downstream impact | Erasure must touch every plane (`/memory/all` enumerates them, `app/api/memory.py:1095-1200`); each new plane is a new erasure risk. |
| Remediation | Keep canonical memory as the system of record. Migrate profile/v2/L1 facts into it. Keep second brain (user-authored, encrypted) and notebooks (user content) separate. Derive persona and KG from canonical only. Delete dead modules. |
| Acceptance criteria | One extraction pipeline; one read path; erasure touches ≤3 stores (canonical, second brain, notebooks) and returns a complete receipt. |
| Regression test | Erasure test asserting zero rows per user across all remaining stores; correction test (edit fact → next turn reads new value only). |
| Implementation risk | High (data migration). Dry-run → snapshot → apply. |
| Verification | [V-STATIC] |

### MEM-002 — Memory is read on the teaching lane and never used
| Field | Value |
|---|---|
| Pillars | P5, P1 |
| Severity | P1 |
| Type | Product gap (with waste) |
| Evidence | `prepare_user_memory` runs in `RequestStateStage` for every signed-in, consented turn (`orchestrator_utils.py:557-566`). The bridge and `FirstPersonPipeline.execute` take no memory input (`first_person_bridge.py:850-875`). |
| Actual behaviour | Returning seekers get the same clip a stranger gets. Memory latency is paid anyway (bounded by budgets). |
| Expected behaviour | Continuity: "Last time we looked at fear in relationships; here is a teaching on the next step." Memory never changes teacher text. |
| Root cause | First-person-only decision (invariant 21) removed the generating layer that consumed memory. |
| Remediation | Use memory only for (a) clip re-ranking within gated candidates (prefer unseen clips, seeker's language, stated interests), (b) an L4 assistant-voice application line, (c) follow-up offers. Skip the read when the lane cannot use it. |
| Acceptance criteria | For returning users, repeat-clip rate on similar questions ≤20%; blind raters score continuity ≥4/5 on ≥60% of multi-session items (`18` P-items). |
| Regression test | Test that FP lane receives `memory_signals` and never alters `verbatim_text`. |
| Implementation risk | Medium. Cache rule must hold: personalised responses bypass the shared cache. |
| Verification | [V-STATIC] |

### MEM-003 — Emotional history is read and acted on without the consent gate
| Field | Value |
|---|---|
| Pillars | P5, P4, P6 |
| Severity | P1 |
| Type | Probable defect |
| Confidence | Medium |
| Evidence | Healing-course block runs after `prepare_user_memory` but outside its consent check; gated only by flag, persistable user, not-incognito (`orchestrator_utils.py:577-610`). `_build_emotional_arc_turns` reads up to 50 episodic memories, falling back to legacy `conversation_memories` (`:636-656`). Proactive Serene Mind reads `get_recent_memories` emotional arcs (`serene_mind_engine.py:1960-1990`) from `DistressStage`. Stored arcs carry per-turn `distress_level` (`_flatten_emotional_arcs`, `:657-705`). |
| Actual behaviour | A signed-in user without an active memory consent receipt can still have stored emotional arcs (if any exist from legacy writes) read and used to assign a "healing course". |
| Expected behaviour | Any use of durable, sensitive (mental-state) data requires the same active consent as memory reads, plus explicit opt-in for proactive features. |
| Root cause | Side effects were added in a different code path from the consent gate. |
| User impact | Inference about emotional state used without the user's current consent. India's DPDP Act requires consent for processing personal data; health-adjacent inference raises the stakes. Legal reading is out of scope here (S1/S4). |
| Remediation | Move both side effects behind `active_consent`; add a separate opt-in for proactive suggestions; stop storing per-turn distress level unless the user opted in. |
| Acceptance criteria | With consent revoked: zero emotional-arc reads, zero course assignments, zero proactive triggers (asserted by test and by a live log query). |
| Regression test | Unit tests with consent absent for `_assign_healing_course` and `_maybe_trigger_proactive_serene_mind`. |
| Implementation risk | Low. |
| Verification | [V-STATIC]; [LIVE-L] (data presence) |

### MEM-004 — LLM-written "spiritual profile" of the user
| Field | Value |
|---|---|
| Pillars | P5, P4 |
| Severity | P2 |
| Type | Architectural risk |
| Evidence | `services/layered_memory/l3_persona_generator.py:14` "You are a spiritual profile architect… generate a concise user persona in Markdown"; exposed via `/memory/persona` and regenerated via `/memory/persona/regenerate` (`app/api/memory.py:563-605`). |
| Actual behaviour | The model writes interpretive statements about a person's spiritual state from their messages. |
| Expected behaviour | Store only what the user said or chose (explicit interests, goals, saved items). Interpretations, if any, are shown to the user, editable, and never asserted back as fact. |
| Remediation | Replace persona text with a structured, user-visible preferences record; drop inferred spiritual-state labels. |
| Acceptance criteria | Persona fields map 1:1 to user-stated facts with source turn ids. |
| Verification | [V-STATIC] |

### MEM-005 — Client-supplied conversation summary enters the prompt unfenced
| Field | Value |
|---|---|
| Pillars | P4, P1 |
| Severity | P3 |
| Type | Probable defect (low) |
| Evidence | `ChatRequest.conversation_summary` (≤4,000 chars, `app/schemas/__init__.py:153-160`) → `user_state` "CONVERSATION SUMMARY (continuation only)" without `_fence` (`rag/nodes/generation.py:1994-1998`). Memory is fenced two lines above. |
| Actual behaviour | The user can place instruction-like text in a "summary" channel. Cross-user impact: none. |
| Remediation | Fence it as untrusted user content, or generate summaries server-side only. |
| Verification | [V-STATIC] |

### MEM-006 — Transparency and erasure tooling: keep
| Field | Value |
|---|---|
| Pillars | P5, P6 |
| Severity | P3 |
| Type | Strength (keep) |
| Evidence | 23 routes in `app/api/memory.py` (list, core edit, add, forget, edit, delete reflections, purge, summaries, persona, skills, relevant, conversations, KG + export, consent, delete all). `/memory/all` refuses to certify erasure when a plane is unreachable (`:1095-1120`). Consent receipts with provenance and history (`20261021000000…000100`). DPDP cascade rule in root `CLAUDE.md` (ON DELETE CASCADE). |
| Remediation | Keep. Reduce surface as planes consolidate (MEM-001). |
| Verification | [V-STATIC]; live erasure proof is S1 (`14`). |

---

## 4. Target mentor-memory design (teacher-agnostic)

### 4.1 What to store

| Record | Source | Retention | Used for |
|---|---|---|---|
| `explicit_preference` (language, depth, teacher interest, topics to explore) | User settings or explicit statements ("I want to learn about forgiveness") | Until changed | Routing defaults, follow-up offers |
| `learning_trace` (topics asked, clip ids served, facets covered, user feedback per answer) | System, per answer | Rolling (owner-set, e.g. 12 months) | Avoid repeats, continuity, journeys |
| `saved_item` (saved clip, saved answer, note) | User action | Until deleted | Collections, revisit |
| `reflection_entry` (user's own journal text) | User | Until deleted; encrypted (second brain) | Only when user opens it |
| `stated_context` (facts the user chose to share, e.g. "I am a parent of teens") | Canonical memory with source turn id | Until corrected or deleted; shown in memory UI | L4 application lines only |

Do not store: inferred diagnoses, inferred spiritual "level", per-turn distress scores (unless the user opts in to mood tracking), third-party personal details.

### 4.2 Rules

1. One consent check gates every durable read, write and side effect.
2. Teacher-agnostic: records reference `teacher_id` from the registry (S4 `11`), never hardcoded names.
3. Memory never alters L1 teacher text; it may re-rank gated candidates and shape L4/L6 text.
4. Every memory-influenced sentence is traceable to a record id the user can see and delete.
5. Personalised answers bypass the shared cache (existing invariant).
6. Temporary Chat: no reads, no writes, no side effects (existing).

### 4.3 Continuity behaviours (specification)

| Situation | Behaviour |
|---|---|
| Returning user asks a related question | Offer "Continue from fear in relationships?" with one line; serve an unseen gated clip. |
| User asks "what did we talk about?" | List recent `learning_trace` topics with dates; no interpretation. |
| User corrects a fact | Edit in place; next turn uses the new value; old value removed from all planes. |
| User revokes consent | All personalisation stops at the next request; memory UI shows what remains until deleted. |

## 5. Cross-references

- UX, retention hooks, north-star metric: `12b` (S4).
- Erasure proofs, RLS, DPDP: `14` (S1).
- Datastore schemas: `06` (S2).
- Continuity test items: `18` §5.

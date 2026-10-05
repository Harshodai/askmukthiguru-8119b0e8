# Memory Intelligence Audit — 2026-10-04

**Scope:** Is user memory stored intelligently AND using an LLM — is the Second Brain /
user-memory pipeline real, LLM-driven, and correct, or stubbed/dead?
**Method:** fresh read-only code trace + live behavior probes. Prior claims treated as unproven.
**Rules kept:** no commits, no `.env` edits, no deploys, local docker stack only, ingest
driver/log/state untouched, `first_person.py` / `config.py` / `first_person_pipeline.py` /
`CLAUDE.md` / `handoff.md` not modified (config read only for flag values). 1 LLM call consumed
(canonical extractor probe); no secrets or PII printed anywhere.

## Verdict (one paragraph)

**Partially yes — with one dead leg.** There are three memory write pipelines, not one, and
they are in very different states: (1) **Canonical memory is genuinely LLM-driven and live**
(extraction proven with a live LLM call below; deterministic judge; resolver writes).
(2) **Legacy `MemoryService` + layered L1/L2/L3 enrichment is LLM-driven but DORMANT** —
`feature_memory_write=False` in the running env gates the entire outbox drain that invokes it.
(3) **Second Brain (Mukthi Vault) auto-extraction from chat is DEAD CODE** —
`SecondBrainService.extract_and_write` (the LLM turn-miner, `second_brain_service.py:385`)
has zero production callers; the vault read path is live but the vault can only fill via
manual `POST /brain/items`. Separately, `classify_user_familiarity` is deterministic
keyword matching, not LLM-based — any "intelligent classification" claim about it is false.
Encryption, tenant isolation, TTLs, and fail-open degradation all verified real.

## 1. Chain map (file + function + lines)

### WRITE PATH A — Canonical memory (LIVE, LLM-driven) ✅
| Step | Location |
|---|---|
| Post-response hook (fire-and-forget task, consent-gated, 30 s cap) | `backend/app/pipeline/stages/memory_stage.py:96-136` → `canonical_integration.post_response_memory(...)` |
| Gate: `settings.memory_write` (True) + non-None integration + `final_answer` present | `memory_stage.py:96` |
| Gate: persistable UUID user + active consent receipt, else skip (fail-closed) | `memory_stage.py:103-115` |
| Pipeline: extract → judge → resolve | `backend/services/canonical_memory/chat_integration.py:433-483` (`_run_extraction_pipeline`) |
| **LLM extraction** (temp 0.0, 1024 tok, 20 s timeout, `find_artifact()` contamination gate, JSON-array parse, per-candidate safety gates) | `backend/services/canonical_memory/extractor.py:211-311`; prompts `164-205`; client builder `35-63` (provider = `llm_provider`, live value `openrouter` / model `meta-llama/llama-3.1-8b-instruct`) |
| Deterministic governance judge (worthiness, user-specificity, sensitivity, confidence ≥ threshold, duplicate/conflict/supersede/merge via `_text_similarity`, consent → ESCALATE) — **no LLM by design** | `backend/services/canonical_memory/judge.py:190-328` (+ `ConsentGatedJudge` in `consent_gate.py:88` resolves consent per-request, fail-closed) |
| Resolver writes to `canonical_memories` (INSERT/UPDATE/EXPIRE/DELETE-status, evidence_count) | `backend/services/canonical_memory/resolver.py:78-166`, `_insert_memory:538-576` |
| Explicit commands (`remember:`/`forget:`/`recall`) bypass extraction with confidence 1.0 | `chat_integration.py:485-596` |

### WRITE PATH B — Legacy + layered memory (REAL code, DORMANT in this env) ⚠️
| Step | Location |
|---|---|
| Gate: `settings.feature_memory_write` — **live value `False` → path returns at `memory_stage.py:138-140`, nothing enqueued** | `memory_stage.py:138-140` |
| When enabled: consent check → outbox enqueue → Celery `drain_memory_outbox` dispatch (bounded pool, 2 slots, Beat fallback) | `memory_stage.py:142-204`; `backend/tasks/memory_outbox_tasks.py:68-194`; beat schedule in `backend/celery_config.py:94-134` (drain + `cleanup-retention-data` present) |
| **LLM extraction** core/episodic/claimed/session-summary (temp 0.0, 1024 tok, 50 s timeout, dirty-JSON recovery, per-field fallbacks) | `backend/services/memory_service.py:808-1091` |
| **LLM classification** of each memory (insight/state_category/related_concepts) | `backend/services/memory_service_v2.py:93-169` (`classify_memory_content`) |
| **LLM L1 atoms** → `add_atoms` → `add_explicit` + Neo4j node/edge writes with fact-key supersession | `services/layered_memory/l1_extractor.py:70+`; `memory_outbox_tasks.py:149-163`; `memory_service_v2.py:171-200`, `:202-390` |
| **LLM L2 scene compression** → `user_scene_blocks` | `services/layered_memory/l2_scene_compressor.py:53+`; `memory_outbox_tasks.py:164-187` |
| **LLM L3 persona generation** (1500-char markdown profile; refresh-on-stale in read path) | `services/layered_memory/l3_persona_generator.py:56+`; read-path refresh in `orchestrator_utils.py:1062-1111` |
| Each LLM client honors active provider (sarvam/openrouter/nim/ollama), returns `None` → graceful empty | `l1_extractor.py:21-47`, `l2_scene_compressor.py:25-50`, `l3_persona_generator.py:28-53`, `_llm_client.py:33-67` |

### WRITE PATH C — Second Brain auto-extraction (DEAD — no callers) ❌
| Step | Location |
|---|---|
| `SecondBrainService.extract_and_write` — **real LLM miner** (`llm.generate(system,user,temperature=0.1,max_tokens=600)`, confidence bar 0.6, ≤5 items, never raises) | `backend/services/second_brain/second_brain_service.py:385-434` |
| Wired with real deps (`llm_service=self.llm_gateway`, embedding, `VaultIndex`) | `backend/app/container.py:378-383` |
| **Production callers: none.** Repo-wide grep for `second_brain.extract_and_write` / `brain.extract` / `vault.extract` returns only `backend/tests/test_second_brain.py:208`. `MemoryStage` never calls it; outbox drain never calls it. | verified 2026-10-04 |
| Manual write path (live): `POST /brain/items` → `add_item` (encrypt + Postgres + vector upsert) | `backend/app/api/second_brain.py:139-151`; `second_brain_service.py:269-311` |

### READ PATH (LIVE) ✅
| Step | Location |
|---|---|
| `prepare_user_memory` — total budget 1.5 s, per-call 0.5 s, fail-open; PII-scrubbed on every return | `backend/app/orchestrator_utils.py:861-1121`; scrub `843-858` |
| Second Brain recall: `unlock` → `personal_context` (vector candidates → decrypt → bi-temporal filter → rank by `vector_rank × decay`, `confidence × decay`) → fenced `second-brain-context` block | `orchestrator_utils.py:884-912`; `second_brain_service.py:440-505`; format `764-821` |
| Canonical recall served FIRST and exclusively when non-empty (legacy suppressed to avoid contradiction); 20 memories / 2000 tokens / composite score (semantic + lexical + recency half-life decay) | `orchestrator_utils.py:923-963`; `chat_integration.py:363-402`; `services/canonical_memory/retriever.py:29-260` |
| Legacy recall (core facts + scored semantic top-5 with subject dedup) + persona summary (fresh ≤30 d, else refresh-or-mark-stale) | `orchestrator_utils.py:965-1043`, `:1045-1113` |
| Familiarity "classification": **deterministic keyword lists** (`advanced_terms`/`practitioner_terms` + what→how/why escalation), zero LLM calls; feeds persona tone block only | `backend/rag/nodes/generation.py:880-962`, consumed `:1069-1094` |

### STORAGE & ISOLATION (verified) ✅
| Claim | Location / evidence |
|---|---|
| Postgres `user_brain_nodes` holds ONLY ciphertext (`ciphertext`, `blind` HMAC, metadata); AES-256-GCM, AAD = `user_id:kind:item_id` (cut-paste across users fails decrypt); live-probed: ciphertext contains no plaintext, round-trip ok, wrong-AAD rejected, blind index deterministic + non-revealing | `second_brain/crypto.py:133-156`, `212-221`; `add_item:269-311` |
| Qdrant `second_brain_vault` payload = `{user_id, kind}` only — never plaintext/ciphertext; every search/delete server-side filtered on `user_id` | `vault_index.py:13-16`, `134-166` |
| Canonical Qdrant index likewise `user_id`-filtered; `canonical_memories` rows user-scoped | `canonical_memory/vector_index.py:60-96`; `retriever` user-scoped queries |
| No admin plaintext read path (by design); audit logs metadata only | `second_brain_service.py:15-21`, `731-734`; `second_brain.py:211-213` |
| Erasure: per-item `forget_item` (vector-first, fail-closed) + full `crypto_shred` (vectors → rows → DEK) + GDPR export | `second_brain_service.py:552-643` |
| X-Test-Key identity (NIL UUID) is explicitly non-persistable → all memory read/write skipped for it | `user_profile_service.py:20-38`; `auth_service.py:262-301` |

### TTLs / RETENTION (mixed — see gap G3)
| Claim | Reality |
|---|---|
| Tier-1 ephemeral 15 min (`EPHEMERAL_TTL=900`, `setex`, LRU fallback when Redis down) | Real — `memory_service_v2.py:37`, `:425-460` |
| Redis stale-key sweep (idle > 24 h, `session:*`/`ephemeral:*`) | Real script, cron/Beat-scheduled — `scripts/ops/cleanup_inactive_user_data.py:51-72` |
| Telemetry 90-day purge (`TELEMETRY_RETENTION_DAYS=90`, 9 tables) | Real script — `cleanup_inactive_user_data.py:34-48`, `:171-207` |
| "365-day inactive purge covers vault" | **FALSE for vault.** `cleanup_stale_qdrant_memories` explicitly `continue`s past `spiritual_wisdom`, `global_memory`, **`second_brain_vault`** (`:119-121`); docstring says vault notes "remain protected" (`:4`). Legacy per-guru memory collections are the only Qdrant purge targets. |

### FAILURE MODES (all degrade, none block chat) ✅
| Failure | Behavior | Location |
|---|---|---|
| LLM extraction throws / times out / returns garbage | Canonical: empty result, `logger.warning`, chat continues; SecondBrain miner: return 0; legacy: default empty memory | `extractor.py:256-265` (+ `find_artifact` gate `:268-273`); `second_brain_service.py:416-418`; `memory_service.py:1010-1018` |
| Redis down | Tier-1 falls back to bounded in-process LRU (1000 entries); reads return `{}`/miss rather than raise | `memory_service_v2.py:39`, `:414-460`, `:462-478` |
| Embedding/Qdrant down | `personal_context` degrades to recency/confidence ordering; `_search_embedding` returns `[]`; vector-delete failures are re-raised ONLY on forget/shred (fail-closed for GDPR) | `second_brain_service.py:35-36`, `:697-702`, `:704-729` |
| Slow memory | 0.5 s per-call / 1.5 s total (orchestrator), 2 s canonical retrieval, 30 s canonical write cap; timeouts log + skip | `orchestrator_utils.py:876-883`, `:937-945`; `memory_stage.py:116-125` |
| No consent / anonymous / NIL-UUID | Write skipped with log line; read returns empty; judge without consent → ESCALATE | `memory_stage.py:103-115`; `judge.py:248-256` |

## 2. Live-test evidence (2026-10-04, host `.venv`, backend :8000 `healthy`)

Backend health at test time: `ready=true status=healthy`, qdrant/redis/neo4j/llm/embedding all `ok`
(llm latency ~1426 ms). Live flags read (booleans only, no secrets):
`memory_write=True`, `canonical_memory_enabled=True`, `canonical_memory_retrieval=True`,
`feature_memory_write=False`, `feature_memory_enabled=True`, `llm_provider='openrouter'`,
`model_for_classification='meta-llama/llama-3.1-8b-instruct'`, `is_production=False`,
`enable_test_auth=True`.

1. **LLM extraction, live (1 LLM call).** `extract_memory_candidates` on a synthetic turn
   ("synthetic test seeker … meditate every morning at 6am … goal … 21-day Soul Sync practice"):
   → `num_candidates: 2` — `PROFILE conf=0.90 "I meditate every morning at 6am"`,
   `GOAL conf=0.90 "my goal is to complete a 21-day Soul Sync practice"`.
   Proves the canonical write path calls a real LLM and yields typed, confidence-scored facts.
2. **Judge, deterministic (0 LLM).** Same-shaped candidates → `CREATE "New durable fact…"`;
   1-word input → `IGNORE "Too short"`; `user_consent=False` → `ESCALATE`. Fail-closed consent proven.
3. **Crypto at rest (0 LLM).** `ciphertext_holds_plaintext: False`, round-trip ok, cross-user
   AAD decrypt rejected, blind index deterministic and non-revealing.
4. **Familiarity classifier (0 LLM).** Source contains no LLM call; outputs
   Seeker/Practitioner/Advanced-Meditator on keyword fixtures as documented.
5. **Chat-turn memory round-trip NOT attempted via HTTP — deliberately.** The only
   unauthenticated-capable identity (X-Test-Key → NIL UUID) is non-persistable by design, so
   posted turns skip every memory write; forging a real-user JWT locally would cross the
   "local docker only, never touch real identities" line. Write-path proof rests on (1)+(2)
   plus the wired `MemoryStage → post_response_memory` call chain above.
6. **Environment caveats (not pipeline defects).** Host-side direct TCP to 127.0.0.1:6379/6333
   accepts but never answers (backend uses docker hostnames `redis`/`qdrant`, healthy per
   `/api/health`); `pytest tests/test_second_brain.py` hangs host-side (conftest tries to reach
   those same hostnames) — killed, no stray processes. If re-verifying, run tests from inside
   the compose network, not the host.

## 3. Letta / Zep / Mem0 comparison

Sources: Zep/Graphiti paper (arXiv 2501.13956), Mem0 paper (arXiv 2504.19413), Letta blog +
forum comparison (2025-08/10), J. Bansal production-memory survey (2026-05).

| Dimension | Best practice (2025-26) | This repo | Gap |
|---|---|---|---|
| Extract (LLM mines facts per turn) | Mem0 `add` → LLM `φ(P)` over (summary + recency + new pair); Zep/Graphiti `add_episode` → entity+relation LLM extraction | Canonical extractor + legacy extractor + L1 atoms all do this | ✅ none |
| Contamination gate on LLM output | Not standard in frameworks; ours exceeds | `find_artifact()` on canonical extraction | ✅ ahead |
| Update / contradiction (LLM decides ADD/UPDATE/DELETE/NOOP; Zep invalidates bi-temporal edges via LLM comparison) | Mem0 LLM tool-call; Zep LLM contradiction check + `t_invalid` stamping | Deterministic `_text_similarity` thresholds + fact-key rules; no LLM in judge/resolver | ⚠️ G2 — paraphrase contradictions ("lives in Mumbai"→"moved to Pune") only resolve if fact_key matches; else MERGE/ESCALATE or duplicate rows |
| Bi-temporal validity (`valid_at/invalid_at`, never overwrite) | Zep/Graphiti core; Mem0g edges | Second Brain HAS it (`valid_from/valid_to`, `is_superseded`, `decay=0.05`, `SUPERSEDED_BY` edges, `invalidate_and_supersede`) — best-in-class on paper | ⚠️ G1 — the component that owns it (vault) never auto-writes, so the timeline is always empty from chat |
| Retrieval blend (vector + BM25 + graph, RRF/MMR/cross-encoder rerank; Zep: no LLM on read) | Hybrid + rerank standard; read path LLM-free | Canonical: semantic+lexical composite + recency decay + hard limits (close to standard, no cross-encoder); vault: vector-rank × decay (no BM25, no RRF) | Minor — cross-encoder rerank absent; acceptable cost trade |
| Forgetting (decay, TTL, right-to-forget) | Letta archival offload; Mem0 DELETE op; TTLs | Ephemeral 900 s + 24 h sweep + 90 d telemetry + per-item forget + crypto-shred all real | ⚠️ G3 — no decay/expiry enforcement for canonical + vault rows; 365-day script skips both vault and `global_memory` despite AGENTS.md wording |
| Sleep-time consolidation (background reflection/summarizer, Letta "sleeptime" agents, Mem0 async summary) | Standard for cost control | None. L2 scene compression + persona refresh exist but ride the (disabled) outbox drain; nothing runs on a schedule | ⚠️ G4 |
| Agent-managed memory (Letta core-memory tool calls by the agent itself) | Letta differentiator | None — harness-driven everywhere; agent never edits memory | Info only — harness-driven (Mem0-style) is a legitimate choice, but then G1 (wire the miner) matters more |
| Retrieval scoring transparency | Scores returned | Canonical `_format_scored_memory_block` exposes score/confidence/decay/similarity; vault block exposes kind/confidence/age | ✅ good |
| Tenant isolation | `user_id`/`group_id` filters | Server-side `user_id` filters + AAD-bound ciphertext + per-request consent | ✅ good |

## 4. Gaps, ranked, with exact fixes

- **G1 (P0 — dead LLM miner).** `SecondBrainService.extract_and_write` unwired; chat never
  populates the vault. Symptom: `personal_context` always searches an empty set for chat-derived
  facts; the bi-temporal machinery (`invalidate_and_supersede`, decay, edges) has no input.
  Fix (pick one, not both): (a) call `second_brain.extract_and_write(user_id, user_msg, final_answer,
  vault=await unlock(user_id))` inside `MemoryStage._canonical_write` next to
  `canonical_integration.post_response_memory` (same consent + persistable-user gates, same
  try/except-never-raise contract; unlock is Mode-A server-side so no passphrase needed), OR
  (b) delete the method + its "called from the post-response hook" docstring and officially
  designate the vault manual-only. (a) preserves the architecture; estimate: ~15 lines + 1 test
  asserting the call happens on a consented turn and is skipped without consent.
- **G2 (P1 — deterministic judge misses paraphrase conflicts).** `_text_similarity` +
  fact-key equality cannot catch "I live in Mumbai" → "I moved to Pune" when the extractor
  emits different/no fact keys → duplicate or contradictory rows coexist; canonical retrieval
  has no contradiction filter (deleted-status zeroing only). Fix: low-cost — after deterministic
  judge returns CREATE/UPDATE, run one bounded LLM contradiction check (temp 0.0, ≤300 tokens,
  10 s timeout, fail-open to deterministic decision) ONLY against same-`memory_type` active
  memories with vector similarity above threshold (top-3). Mirrors Zep's LLM invalidation check
  without putting an LLM on every write. Gate behind a flag for cost control.
- **G3 (P1 — retention story overstated).** `cleanup_stale_qdrant_memories` skips
  `second_brain_vault` + `global_memory`; nothing expires canonical/vault rows (no TTL worker,
  `valid_to` only set on supersede). Meanwhile AGENTS.md claims 365-day auto-purge. Fix:
  either (i) extend the script with an opt-in `--include-vault` path that deletes vault/canonical
  points for users inactive >365 d (default off; vault docstring already promises protection), or
  (ii) correct AGENTS.md + Tier-3 docs to state vault/canonical are retained until explicit
  forget/shred. Also add `expires_at` enforcement for `TEMPORARY_CONTEXT` candidates (judge
  already emits 7-day default metadata — nothing acts on it).
- **G4 (P2 — no consolidation loop).** No scheduled summarization/reflection; persona refresh
  only fires lazily on stale read; L2 scene blocks only via disabled outbox. Long histories grow
  unbounded (per-memory rows, no compaction running — `compact_memories` is only invoked from
  legacy `extract_and_write`, i.e., the dormant path). Fix: schedule a Beat task (daily, 1 LLM
  call per active user max) that compacts `canonical_memories` per user (merge duplicates,
  expire `TEMPORARY_CONTEXT` past `expires_at`) — essentially promote `compact_memories` to the
  canonical store. Measure token cost per user before enabling broadly.
- **G5 (P2 — familiarity classifier mislabeled + suspect mapping).** `classify_user_familiarity`
  is keyword matching; `_CLASSIFICATION_TO_LEVEL` maps `"Advanced Meditator" → "seeker"` while
  the `SpiritualLevel` enum ranks `SEEKER` deepest — naming inversion invites misuse, and any
  consumer assuming semantic understanding is wrong. Fix: rename to `heuristic_familiarity_tier`
  (or back it with the classification model already configured), and add a test pinning the
  mapping's intended direction.
- **G6 (P3 — dormant-path bit-rot risk).** Legacy `MemoryService` + L1/L2/L3 + Neo4j writes are
  fully gated off (`feature_memory_write=False`) yet still scheduled/imported; if re-enabled,
  `search_global` uses deprecated `client.search(query_vector=...)` and per-guru collections may
  not exist (only `global_memory` gets `ensure_*`). Fix: before flipping the flag, run the
  existing outbox worker tests + one consented end-to-end turn in compose, and reconcile
  `ensure_global_memory_collection` with `_get_memory_collection` per-guru branches.

## 5. Answers to the audit questions

- **Is memory stored intelligently?** Half. Retrieval is genuinely intelligent (hybrid
  semantic+lexical+recency composite scoring, bi-temporal filtering, subject dedup, bounded
  blocks, PII scrub). Consolidation intelligence is partial (deterministic dedup/supersede good
  for exact matches, weak for paraphrase — G2; no scheduled reflection — G4). The familiarity
  "classifier" is not intelligent at all (G5).
- **Does it use an LLM?** Yes — three independent LLM miners (canonical extractor proven live
  §2.1; legacy extractor; L1/L2/L3), plus per-memory classification. But one miner is dead (G1)
  and four are dormant behind a flag (path B), so in the running env only the canonical
  extractor's LLM fires on chat turns.
- **Is it correct?** Storage correctness verified (encrypted-at-rest, isolated, consent-gated,
  fail-open reads, fail-closed deletes). Lifecycle correctness has holes (G3). Wiring
  correctness has one break (G1).
- **Top-3 gaps:** G1 dead vault miner (P0) · G2 paraphrase-blind judge (P1) · G3 retention
  overclaim + missing expiry enforcement (P1).
- **Final verdict:** **Genuinely LLM-driven in part, not stubbed — but the flagship "Second
  Brain learns from chat" loop does not run.** Canonical memory is the real intelligent-memory
  system today; the vault is a correct, well-built encrypted store with a live read path and a
  disconnected write path. Wire G1 (or doc the vault as manual-only), and the verdict flips to yes.

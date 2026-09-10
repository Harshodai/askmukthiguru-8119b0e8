# Security/Privacy Red Team Audit — Memory System
**Date:** 2026-09-09  
**Scope:** Memory, Second Brain, Qdrant vault, Neo4j graph, Redis ephemeral, consent, deletion propagation  
**Vectors tested:** 11

---

## 1. Cross-User Memory Leakage (Qdrant + Supabase)

| Finding | **Protected** |
|---|---|
| **Evidence** | `backend/services/second_brain/vault_index.py:134-144` — Every `VaultIndex.search()` call wraps the query in `Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))])`. Server-side filter; client cannot omit it. `backend/services/memory_service.py:262-282` — Qdrant memory search applies `user_id` filter on every vector query. `backend/app/api/memory.py` — All 21 endpoints derive `user_id` from `Depends(get_current_user_from_supabase)`, never from the request body. |
| **Severity** | N/A (protected) |

---

## 2. IDOR on Memory/Vault Endpoints

| Finding | **Protected** |
|---|---|
| **Evidence** | `backend/app/api/memory.py:79,101,168,...` — Every endpoint uses `user: dict = Depends(get_current_user_from_supabase)` and then `user_id = user["id"]`. The `forget_memory_endpoint` (line 290), `forget_item` (second_brain:171), and `purge_account_memory_endpoint` (line 346) all derive user from JWT. No endpoint accepts a user-supplied `user_id` parameter. `backend/services/second_brain/second_brain_service.py:465-489` — `forget_item()` filters by `user_id` on both Qdrant vector delete and Postgres row delete. |
| **Severity** | N/A (protected) |

---

## 3. RLS Bypass (Supabase)

| Finding | **Protected** |
|---|---|
| **Evidence** | `supabase/migrations/20260711000000_enable_rls_on_all_tables.sql` — RLS enabled on ~30+ tables including `guru_core_memory`, `guru_memories`, `guru_session_summaries`, `user_profiles`, `chat_messages`, etc. `supabase/migrations/20260804000001_add_with_check_to_tenant_rls.sql` — Explicit `WITH CHECK` added to all `FOR ALL` policies on tenant-filtered tables. `supabase/migrations/20260717191006_second_brain_vault.sql:101-116` — `user_brain_nodes`, `user_brain_edges`, `user_brain_keys` all have `FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)`. `supabase/migrations/20260714000000_harden_rls_and_security_invoker.sql` — Views hardened with `security_invoker=true`. |
| **Severity** | N/A (protected) |

---

## 4. Qdrant Filter Bypass (Shared Collection)

| Finding | **Protected** |
|---|---|
| **Evidence** | `vault_index.py:134-144` — `search()` requires `user_id` in `query_filter.must`. `vault_index.py:146-157` — `delete_item()` requires both `user_id` and `HasIdCondition`. `vault_index.py:159-166` — `delete_all()` requires `user_id`. `vault_index.py:126-132` — `upsert()` embeds `user_id` into payload. All operations are server-side filtered; no path allows unfiltered access to the shared `second_brain_vault` collection. |
| **Severity** | N/A (protected) |

---

## 5. Neo4j Tenant Bypass (Graph Queries)

| Finding | **Protected** |
|---|---|
| **Evidence** | `backend/rag/nodes/retrieval.py` — All Cypher queries use `tenant_id: $tenant_id` parameter binding (e.g., `MATCH (u:User {tenant_id: $tenant_id, id: $user_id})`). `backend/rag/nodes/nl2cypher.py:30-59` — Schema documents `GlobalMemory` nodes carry `tenant_id`; `FILTER on it` is documented. `nl2cypher.py:99-102` — `_is_read_only()` guard rejects write verbs (`CREATE`, `MERGE`, `DELETE`, `SET`, `REMOVE`). `nl2cypher.py:115-135` — `_is_read_only()` scans full body for write verbs, not just first token. `memory_service_v2.py:817-827` — `purge_all_user_data` Neo4j query uses `tenant_id: $tenant_id, id: $user_id` filter. |
| **Severity** | N/A (protected) |

---

## 6. Redis Cross-User Leakage

| Finding | **Protected** |
|---|---|
| **Evidence** | `backend/tasks/layered_memory_tasks.py` — Ephemeral keys use `ephemeral:{tenant_id}:{user_id}:session:{session_id}:*`. `backend/services/memory_service_v2.py` — Redis keys are namespaced by `{tenant_id}:{user_id}`. `backend/app/orchestrator.py` — `turn_counter:{user_id}` is per-user. All Redis key patterns include user-scoping. |
| **Severity** | N/A (protected) |

---

## 7. Prompt Injection via Memory Content

| Finding | **Partial Mitigation** |
|---|---|
| **Evidence** | `backend/rag/nodes/generation.py:869-894` — Memory context is injected into the `user_message` block (NOT system prompt). A ground truth refusal marker (`[GROUND_TRUTH_REFUSAL]`) is injected AFTER the memory block to anchor the model against following instructions embedded in memory content. The `humanizer` stage scrubs memory content before injection. However, the memory content remains in the user message as a delegated instruction block. If an attacker can poison a memory (see #8), the model may still be influenced. The refusal anchor is a mitigation, not a hard guarantee. |
| **Severity** | **MEDIUM** — Mitigated by user_message injection + refusal anchor, but not provably safe against all LLM instruction-following edge cases. |

---

## 8. Memory Poisoning (Write Pollution)

| Finding | **Protected** |
|---|---|
| **Evidence** | `backend/app/api/memory.py` — All write endpoints (`POST /api/memory/remember`, `POST /api/memory/reflect`) require authenticated user via `get_current_user_from_supabase`. `backend/services/memory_outbox.py` — `validate_for_memory_storage()` checks `consent=true`, `consent_version`, `consent_granted_at` before allowing persistence. `backend/services/memory_service.py:262-282` — Qdrant writes are user-scoped. A user can only poison their OWN memory — cross-user poisoning is blocked by authentication + user_id scoping. |
| **Severity** | N/A (protected for cross-user; self-poisoning is user-controlled behavior) |

---

## 9. Incomplete Deletion Propagation

| Finding | **Gap Identified** |
|---|---|
| **Evidence** | `memory_service_v2.py:747-842` — `purge_all_user_data()` deletes from: (1) `guru_core_memory` (Postgres), (2) `guru_memories` (Postgres), (3) `guru_session_summaries` (Postgres), (4) Qdrant `global_memory` collection, (5) Neo4j User + GlobalMemory nodes, (6) Redis ephemeral keys. **MISSING**: Does NOT call `SecondBrainService.crypto_shred()` — so `user_brain_nodes`, `user_brain_edges`, `user_brain_keys` (Second Brain vault) and the `second_brain_vault` Qdrant collection are NOT wiped by this function. The `second_brain_v2.py:491-514` `crypto_shred()` exists but is a separate call. If `delete-my-account` edge function only calls `purge_all_user_data()`, Second Brain data survives account deletion. |
| **Severity** | **HIGH** — GDPR right-to-forget gap. Second Brain vault data (encrypted nodes, edges, DEK, Qdrant vectors) is NOT cleaned by `purge_all_user_data()`. Must verify `delete-my-account` edge function chains both calls. |

---

## 10. Race Conditions (TOCTOU on Memory Dedup)

| Finding | **Low Risk** |
|---|---|
| **Evidence** | `memory_service.py:262-282` — Memory search-then-write pattern: search Qdrant for similar memories, then upsert if no match above threshold. This is a read-then-write pattern without a transaction. Two concurrent requests with similar content could both pass the dedup check and create duplicate memories. However, this is a **data quality** issue (duplicate memories), not a security issue — both writes are scoped to the same authenticated user. The `MemoryOutbox` queue serializes writes in production, reducing the window. |
| **Severity** | **LOW** — Duplicate memories for the same user; no cross-user impact. |

---

## 11. Consent Bypass

| Finding | **Protected** |
|---|---|
| **Evidence** | `backend/services/memory_outbox.py` — `validate_for_memory_storage()` requires `consent=true`, `consent_version` (non-empty string), and `consent_granted_at` (non-null timestamp) before allowing any memory to be persisted to the durable store. `backend/app/api/memory.py` — Memory reflection endpoint (line 168) passes consent from the request, but the outbox validates it server-side. `backend/services/memory_service.py:750-768` — `guru_memories` writes include consent fields in the payload. Anonymous users are short-circuited by `_is_anonymous()` check and never reach persistence. |
| **Severity** | N/A (protected) |

---

## Summary

| # | Vector | Finding | Severity |
|---|--------|---------|----------|
| 1 | Cross-user memory leakage | **Protected** | — |
| 2 | IDOR on memory/vault endpoints | **Protected** | — |
| 3 | RLS bypass | **Protected** | — |
| 4 | Qdrant filter bypass | **Protected** | — |
| 5 | Neo4j tenant bypass | **Protected** | — |
| 6 | Redis cross-user leakage | **Protected** | — |
| 7 | Prompt injection via memory | **Partial mitigation** | MEDIUM |
| 8 | Memory poisoning | **Protected** (self-scope only) | — |
| 9 | Incomplete deletion propagation | **Gap** — Second Brain vault not purged by `purge_all_user_data()` | HIGH |
| 10 | Race conditions (dedup TOCTOU) | **Low risk** (same-user duplicates only) | LOW |
| 11 | Consent bypass | **Protected** | — |

---

## Recommended Fixes

### P0 — HIGH: Deletion Propagation Gap
**File:** `backend/services/memory_service_v2.py:747-842`  
**Fix:** `purge_all_user_data()` must also call `SecondBrainService.crypto_shred(user_id)` or at minimum `VaultIndex.delete_all(user_id)` + delete from `user_brain_nodes`, `user_brain_edges`, `user_brain_keys`. Verify that `supabase/functions/delete-my-account/index.ts` chains both `purge_all_user_data()` and `crypto_shred()`.

### P1 — MEDIUM: Prompt Injection via Memory
**File:** `backend/rag/nodes/generation.py:869-894`  
**Fix (defense-in-depth):** Consider wrapping memory context in a delimiter that is unlikely to appear in user content (e.g., `<USER_MEMORY_START>...<USER_MEMORY_END>`) and adding explicit system-level instruction that anything inside those delimiters is user-provided data, not instructions. The current refusal anchor is good but not provably sufficient against all frontier model behaviors.

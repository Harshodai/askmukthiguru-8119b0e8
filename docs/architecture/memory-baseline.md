# AskMukthiGuru Memory System — Complete Baseline Archaeology

**Date:** 2026-09-09
**Status:** Phase 0 Complete
**Investigators:** 10 parallel specialist subagents (Architecture, Memory Science, Retrieval, Database, Security, AI/Evaluation, Performance, Product/UX, SRE, Adversarial)

---

## 1. EXECUTIVE SUMMARY

The existing memory system is a multi-layered, multi-store architecture with **16+ data stores** across Postgres, Qdrant, Neo4j, and Redis. It provides functional personal memory, but has significant structural issues: **3+ duplicate extraction paths**, **triple-store consistency drift**, **minimal fact deduplication coverage**, **no memory quality evaluation**, **incomplete GDPR deletion**, and **no cross-layer ranking**.

The system is **actively working** — users can add/view/delete memories, the chat pipeline retrieves and uses memories for personalization, and the Second Brain provides encrypted personal knowledge. However, it is **not production-ready** for a full adaptive memory upgrade due to the gaps documented below.

**Verdict: Functional but fragmented. Proceed to Phase 1 (Architecture) with the gaps below as design constraints.**

---

## 2. MEMORY STORES INVENTORY

### 2.1 Postgres Tables (12 tables)

| Table | Purpose | Writer | RLS | Key Issue |
|-------|---------|--------|-----|-----------|
| `guru_memories` | Episodic memory (fact-keyed, deduped) | memory_service.py | ✅ own_* | Triple-store drift with Qdrant+Neo4j |
| `guru_core_memory` | Permanent core facts | memory_service.py | ✅ own_* | UNIQUE(user_id) may not be enforced |
| `guru_session_summaries` | Per-session summaries | memory_service.py | ✅ own_* | — |
| `conversation_memories` | Verbatim conversation log | user_profile_service.py | ✅ own_* | Legacy, overlaps with user_episodes |
| `user_profiles` | User preferences | user_profile_service.py | ✅ own_* | **Dual schema conflict** (two migrations) |
| `user_episodes` | Raw turn log | EpisodicMemoryService | ✅ own_* | Not deleted by purge_all_user_data |
| `user_brain_nodes` | Encrypted vault items | second_brain_service.py | ✅ owner | Not crypto-shredded by purge_all_user_data |
| `user_brain_edges` | Vault relationships | second_brain_service.py | ✅ owner | Not crypto-shredded by purge_all_user_data |
| `user_brain_keys` | Vault DEKs | second_brain_service.py | ✅ owner | Not crypto-shredded by purge_all_user_data |
| `memory_outbox` | Durable async write queue | memory_outbox.py | ✅ own_* | Not deleted by purge_all_user_data |
| `memory_consent_receipts` | Consent tracking | memory_outbox.py | ✅ own_* | Not deleted by ANY deletion path |
| `user_personas` | Per-user persona text | API route | ✅ owner | — |

### 2.2 Qdrant Collections (3 collections)

| Collection | Vector Size | Distance | Payload Indexes | Owner |
|-----------|-------------|----------|-----------------|-------|
| `spiritual_wisdom` (or `_contextual`) | 1024 | COSINE | raptor_level, cluster_id, language, content_type, speaker, topic | Corpus ingestion |
| `second_brain_vault` | 1024 | COSINE | `user_id` (keyword), `kind` (keyword) | VaultIndex |
| `global_memory` (or `{slug}_memory`) | 1024 | COSINE | — | MemoryServiceV2 |

### 2.3 Neo4j Nodes

| Label | Purpose | Memory-Related |
|-------|---------|----------------|
| `:GlobalMemory` | Per-user memory nodes | ✅ |
| `:User` | User identity | ✅ |
| `:Concept` | Spiritual concept | Shared ontology |
| `:Teacher` | Spiritual teacher | Shared ontology |
| `:Practice` | Spiritual practice | Shared ontology |

### 2.4 Redis

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `session:{session_id}:context` | 15min sliding | Ephemeral session memory |
| `mukthiguru:cache:*` | varies | Query cache |
| `drain_memory_outbox` | — | Celery task queue |

---

## 3. READ/WRITE PATHS

### 3.1 Write Path (Chat Turn → Persistence)

```
POST /api/chat
  → orchestrator_utils.prepare_memory_context()     [READ: Redis + Qdrant + PG]
  → PipelineCoordinator.execute()
    → MemoryStage.execute()
      → MemoryOutbox.enqueue(payload)                [WRITE: memory_outbox]
      → Celery: drain_memory_outbox()                [READ: memory_outbox]
        → outbox.active_consent()                    [READ: memory_consent_receipts]
        → profile.save_conversation_memory()         [WRITE: conversation_memories]
        → memory_service.extract_and_write()         [WRITE: guru_memories + Neo4j GlobalMemory]
        → episodic.log_episode()                     [WRITE: user_episodes]
        → memory_service.add_atoms()                 [WRITE: guru_memories + Neo4j]
        → compress_turns_to_scene() + save_scene()   [WRITE: user_scene_blocks]
        → outbox.mark_processed()                    [WRITE: memory_outbox]
```

### 3.2 Read Path (Chat Request → Context Assembly)

```
orchestrator_utils.prepare_memory_context():
  Layer A: Second Brain (vault_index Qdrant → Postgres decrypt)  [5 items, 500ms timeout]
  Layer B: User Profile (guru_core_memory) → build_memory_context()  [session history]
  Layer C: Memory Service (Supabase RPC + Qdrant semantic)  [5 memories, 5s timeout]
  Layer D: L3 Persona (user_personas)  [8 lines max]
  → Returns: memory_context string → injected into Generation User State (1024 token budget)
```

### 3.3 Extraction Pipeline

```
conversation transcript
  → extract_and_write() [LLM call #1: claim/confidence/fact_type extraction]
    → add_explicit() → guru_memories (PG) + Neo4j GlobalMemory
  → extract_atoms() [LLM call #2: L1 atomic memory extraction]
    → add_atoms() → guru_memories (PG) + Neo4j
  → compress_turns_to_scene() [LLM call #3: L2 scene compression]
    → save_scene_block() → user_scene_blocks (PG)
  → build_persona() [LLM call #4: persona generation, if stale]
    → save_persona() → user_personas (PG)
```

**Total LLM calls per outbox drain: 3-4** (extraction + atoms + scene + optional persona)

---

## 4. ACTIVE vs DEAD CODE

### Active Components

| Component | Status | Notes |
|-----------|--------|-------|
| MemoryService (v1) | ✅ Active | Core extraction, decay, supersession |
| MemoryServiceV2 | ✅ Active | Three-tier extension (Redis/Neo4j/classification) |
| SecondBrainService | ✅ Active | Encrypted vault, crypto-shredding |
| MemoryOutbox | ✅ Active | Durable consent-gated queue |
| MemoryStage | ✅ Active | Pipeline integration point |
| EpisodicMemoryService | ✅ Active | Raw turn logging |
| UserProfileService | ✅ Active | Preferences, conversation history |
| VaultIndex | ✅ Active | Qdrant vault vector index |
| L1Extractor | ✅ Active | Atomic memory extraction |
| L2SceneCompressor | ✅ Active | Scene compression |
| prepare_user_memory() | ✅ Active | 4-layer context assembly |

### Duplicate/Overlapping Paths

| Path 1 | Path 2 | Overlap | Risk |
|--------|--------|---------|------|
| `conversation_memories` (PG) | `user_episodes` (PG) | Both store conversation data | LOW — different purposes |
| `guru_memories` (PG) | Qdrant `*_memory` | Both store episodic memories | **HIGH** — triple-store drift |
| `global_memory` (Qdrant) | `GlobalMemory` (Neo4j) | Both store Tier 3 global memory | MEDIUM — graph vs vector |
| `extract_and_write()` | `add_atoms()` | Both extract from same conversation | MEDIUM — different granularity |
| `save_conversation_memory()` | `log_episode()` | Both log turns | LOW — different formats |

---

## 5. CRITICAL FINDINGS

### 5.1 CRITICAL: GDPR Deletion Incompleteness

**`purge_all_user_data()`** (called from "Delete my account" edge function) misses:
- `user_episodes`
- `user_scene_blocks`
- `user_skills`
- `memory_outbox`
- `memory_consent_receipts`
- Second Brain (`user_brain_nodes`, `user_brain_edges`, `user_brain_keys`, Qdrant vault vectors)

**`DELETE /api/memory/all`** (user-facing) covers all of the above.

The more dangerous path (account deletion) has weaker coverage.

### 5.2 HIGH: Triple-Store Consistency Drift

`guru_memories` (Postgres) ↔ Qdrant `*_memory` ↔ Neo4j `GlobalMemory` are written in the same method but in separate try/except blocks. Partial failures leave orphaned data:
- Postgres write succeeds + Qdrant fails → memory not semantically searchable
- Postgres write succeeds + Neo4j fails → memory not in graph
- Deletion succeeds in one store but fails in another → orphaned references

`valid_to` supersession exists only in Postgres — superseded memories remain searchable in Qdrant and visible in Neo4j.

### 5.3 HIGH: Minimal Fact Deduplication

`fact_key` auto-deduplication only covers `lives_in` and `occupation`. All other contradictions (changing preferences, evolving practices, updated goals) create duplicate memories rather than superseding.

### 5.4 HIGH: No Memory Quality Evaluation

- No golden dataset for extraction accuracy
- No blind with/without memory evaluation
- No metrics for precision, false-memory rate, update accuracy, contradiction accuracy
- No personalization lift measurement
- Extraction prompt has no few-shot examples

### 5.5 MEDIUM: No Cross-Layer Ranking

4 retrieval layers (Second Brain, Core Memory, Semantic, Persona) independently select top-N, then concatenate. No unified ranking across layers. A less-relevant Second Brain item can crowd out a highly-relevant episodic memory.

### 5.6 MEDIUM: 1024-Token User State Budget

All 4 memory layers + intent + history metadata share 1024 tokens. With rich Second Brain + core facts + semantic memories + persona, this budget can be exceeded, causing silent truncation.

### 5.7 MEDIUM: Semantic Search Circuit Breaker

`search_semantic()` permanently disables after 3 consecutive failures with no recovery mechanism besides process restart. No half-open state.

### 5.8 MEDIUM: Compaction Data Loss Risk

`compact_memories()` deletes all old memories then inserts new ones without a transaction. If insert fails after delete, data loss occurs. Snapshot is a recovery mechanism but requires manual intervention.

### 5.9 LOW: Outbox Extraction Not Idempotent

If a row is processed twice (e.g., after `mark_processed` fails), memories are extracted and inserted twice. No idempotency key on extraction.

### 5.10 LOW: Episodic Logging Failure Cascades

`episodic.log_episode()` inside the outbox drain is not wrapped in its own try/except. If it fails, the entire row fails even though core extraction succeeded.

---

## 6. SECURITY ASSESSMENT

| Vector | Status | Finding |
|--------|--------|---------|
| Cross-user leakage | ✅ Protected | All queries filter by user_id |
| IDOR | ✅ Protected | Endpoints verify ownership |
| RLS | ✅ Protected | All memory tables have RLS |
| Qdrant filter bypass | ✅ Protected | Server-side user_id filters |
| Neo4j tenant bypass | ✅ Protected | Tenant-scoped Cypher queries |
| Redis leakage | ✅ Protected | Namespaced keys |
| Prompt injection via memory | ⚠️ Mitigated | Fence + instruction boundary (known LLM limitation) |
| Memory poisoning | ✅ Protected | User-scope only, no cross-user |
| Consent enforcement | ✅ Protected | Outbox gates on consent |
| GDPR deletion | ❌ **BROKEN** | Edge function path incomplete |
| Race conditions | ⚠️ Low risk | TOCTOU on dedup, no cross-user impact |

---

## 7. UX ASSESSMENT

### What Exists
- MemoryManager: list/add/edit/delete memories with metadata
- Core Memory: editable text block
- Second Brain: encrypted vault with Mode A/B
- Consciousness Map: SVG force-directed graph
- Chat Provenance: collapsible recalled-memory details
- AI Transparency Banner: Article 50 notice
- GDPR Export: JSON download

### What's Missing
- No onboarding consent for memory collection
- No "what we know about you" dashboard
- No memory source attribution (which conversation produced this memory?)
- No "how memory works" explainer
- No persistent consent management (toggle opt-in/out)
- No soft-delete with recovery window
- No personalization callout in chat responses
- No data retention settings

---

## 8. PERFORMANCE CHARACTERISTICS

| Operation | Latency | Cost |
|-----------|---------|------|
| prepare_memory_context() | ~500ms-2s | 1-2 LLM calls (translation + extraction) |
| search_semantic() | ~100-500ms | 1 embedding + Qdrant + PG RPC |
| Second Brain recall() | ~200-500ms | Qdrant search + PG decrypt |
| extract_and_write() | ~2-5s | 1 LLM call (classify model) |
| add_atoms() | ~1-3s | 1 LLM call |
| compress_turns_to_scene() | ~1-3s | 1 LLM call |
| compact_memories() | ~5-15s | 1 LLM call (triggered at >15 memories) |

**Total outbox drain per turn: 3-4 LLM calls, ~5-15s wall time**
**Total memory context per request: ~500ms-2s latency, ~1024 tokens budget**

---

## 9. FAILURE MODE SUMMARY

| Category | Count | Critical Issues |
|----------|-------|----------------|
| Outbox failures | 7 | Worker crash leaves rows locked |
| Memory service failures | 9 | Compaction data loss, circuit breaker permanent disable |
| Orchestrator failures | 7 | All gracefully degraded (chat continues) |
| Second Brain failures | 8 | Crypto-shredding partial failure |
| Drain process failures | 9 | Extraction not idempotent, episodic cascades |
| **Total** | **40 failure modes** | **3 critical, 6 high** |

---

## 10. RECONCILIATION CAPABILITY

| Capability | Exists? |
|------------|---------|
| Outbox reconciliation | ❌ No |
| Memory deduplication | ⚠️ Partial (fact_key only) |
| Compaction reconciliation | ✅ Yes (snapshot-first) |
| Vector-Postgres consistency | ❌ No |
| Crypto-shredding reconciliation | ❌ No |
| Architecture drift detection | ✅ Yes (general, not memory-specific) |

---

## 11. WHAT SHOULD BE PRESERVED

1. **Bio-mimetic decay with reinforcement** — elegant, effective
2. **Fact-key supersession** — deterministic contradiction resolution (needs expansion)
3. **Three-tier architecture** — good coverage of use cases
4. **GDPR compliance framework** — full purge, crypto-shredding, consent receipts
5. **Compaction safety** — snapshot before destructive operations
6. **Outbox pattern** — durable, consent-gated writes
7. **Second Brain encryption** — AES-256-GCM, Mode A/B, crypto-shredding
8. **4-layer context assembly** — multi-source personalization
9. **Injection safety** — fenced memory blocks with instruction boundaries
10. **Feature flags** — `feature_memory_write`, `feature_memory_enabled`

## 12. WHAT SHOULD BE REMOVED/REPLACED

1. **Triple-store write pattern** (Postgres + Qdrant + Neo4j in same method) → canonical Postgres + dedicated vector index
2. **Minimal fact_key coverage** → expanded deduplication across all memory types
3. **No cross-layer ranking** → unified retrieval scoring
4. **1024-token shared budget** → dedicated memory budget with priority-based allocation
5. **Permanent circuit breaker** → half-open recovery state
6. **Incomplete deletion paths** → single source of truth for deletion
7. **No evaluation pipeline** → golden dataset + blind evaluation
8. **No memory health check** → dedicated memory observability

---

## 13. CHECKPOINT 0 EVIDENCE

### What is the current memory system?
Multi-layered personal memory with 4 retrieval layers, 3+ extraction paths, 12+ Postgres tables, 3 Qdrant collections, Neo4j graph, and Redis ephemeral cache. Active and functional.

### What is genuinely working?
- Memory extraction from conversations
- Bio-mimetic decay and reinforcement
- Fact-key supersession for single-valued facts
- Second Brain encrypted vault
- Consent-gated outbox
- Chat pipeline memory integration
- User-facing memory management UI
- GDPR export

### What is broken?
- GDPR deletion (edge function path incomplete)
- Triple-store consistency (orphaned vectors/graph nodes on partial failure)
- Compaction (no transaction, data loss risk on insert failure)
- Semantic search circuit breaker (permanent disable, no recovery)

### What is missing?
- Memory quality evaluation
- Cross-layer ranking
- Expanded fact deduplication
- Memory health checks
- Reconciliation for vector-Postgres drift
- Onboarding consent
- "What we know" dashboard
- Source attribution for auto-extracted memories

### What should be preserved?
Bio-mimetic decay, fact-key supersession, three-tier architecture, outbox pattern, Second Brain encryption, consent framework, compaction safety, injection mitigations.

### What should be removed?
Triple-store write pattern, incomplete deletion paths, permanent circuit breaker, no-evaluation status quo.

# Canonical Memory System

Production-grade adaptive memory for AskMukthiGuru — end-to-end.

## Architecture

### Pipeline

```
User Message → Chat Engine → Adaptive Context Orchestrator → Generation
     ↓                                                            ↓
  Memory Stage                                            Response + Facts
     ↓                                                            ↓
  Outbox ← Extraction ← Judge ← Resolver → Canonical Store
     ↓
  Derived Indexes (Qdrant, Redis, Neo4j)
```

### Core Modules (`backend/services/canonical_memory/`)

| Module | Purpose | Key Class |
|--------|---------|-----------|
| `models.py` | Canonical memory schema | `MemoryCandidate`, `MemoryType` |
| `extractor.py` | LLM extraction with safety gates | `MemoryExtractor` |
| `judge.py` | Deterministic governance | `MemoryJudge` |
| `resolver.py` | Postgres persistence, dedup, supersession | `MemoryResolver` |
| `consolidator.py` | Threshold-triggered merge | `MemoryConsolidator` |
| `vector_index.py` | Qdrant semantic index | `CanonicalVectorIndex` |
| `retriever.py` | Ranked retrieval with hard limits | `MemoryRetriever` |
| `history_separator.py` | History/memory/knowledge separation | `HistorySeparator` |
| `context_builder.py` | Adaptive budget allocation | `ContextBuilder` |
| `chat_integration.py` | Feature-flagged pipeline integration | `MemoryChatIntegration` |
| `security.py` | Injection detection, user isolation | `check_injection_attempt` |
| `privacy.py` | Consent lifecycle, GDPR | `MemoryPrivacyManager` |
| `observability.py` | Metrics, health, drift detection | `MemoryMonitor` |
| `evaluation.py` | Quality evaluation harness | `MemoryEvaluator` |
| `simulation.py` | Longitudinal testing | `MemorySimulator` |
| `cost_tracker.py` | Budget tracking | `CostTracker` |
| `performance.py` | Latency monitoring | `PerformanceMonitor` |
| `resilience.py` | Circuit breaker, chaos testing | `CircuitBreaker` |
| `self_healing.py` | Drift repair, orphan cleanup | `SelfHealer` |
| `migration.py` | Legacy → canonical transition | `MigrationManager` |
| `shadow.py` | Shadow pipeline comparison | `ShadowMode` |
| `canary.py` | Staged rollout | `CanaryDeployment` |
| `red_team.py` | Adversarial testing | `RedTeamTestRunner` |

## API Endpoints (`/api/memory/canonical/`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/memory/canonical` | List user memories (paginated) |
| POST | `/memory/canonical` | Add explicit memory |
| PUT | `/memory/canonical/{id}` | Edit memory |
| DELETE | `/memory/canonical/{id}` | Soft delete |
| DELETE | `/memory/canonical` | Hard delete + GDPR export |
| GET | `/memory/canonical/reasons` | Why-is-this-here |
| POST | `/memory/consent` | Consent management |
| GET | `/memory/export` | GDPR data export |

Full API reference: [docs/canonical_memory_api.md](../../docs/canonical_memory_api.md)

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_CANONICAL_MEMORY` | `false` | Enable canonical memory pipeline |
| `FEATURE_CANONICAL_MEMORY_RETRIEVAL` | `false` | Enable canonical retrieval |
| `FEATURE_MEMORY_SHADOW` | `false` | Enable shadow comparison |
| `CANONICAL_MEMORY_BUDGET_USD` | `10.0` | Daily cost budget |
| `CANONICAL_MEMORY_MAX_RESULTS` | `20` | Retrieval limit |
| `CANONICAL_MEMORY_MAX_TOKENS` | `2000` | Context token budget |

## Data Model

### Memory Types

| Type | Description |
|------|-------------|
| `PROFILE` | User profile facts (location, occupation) |
| `PREFERENCE` | Communication preferences (tone, depth, language) |
| `COMMUNICATION_STYLE` | Interaction patterns |
| `GOAL` | User goals and aspirations |
| `PROJECT` | Active projects |
| `INTEREST` | Topics of interest |
| `RELATIONSHIP` | Social connections |
| `USER_EXPLICIT` | User explicitly asked to remember |
| `TEMPORARY_CONTEXT` | Short-lived context (expires) |
| `REFLECTION` | User reflections and insights |

### Memory States

- `active` — Current, retrievable memory
- `deleted` — Soft-deleted, not served
- `superseded` — Replaced by a newer version

### Judge Decisions

| Decision | Meaning |
|----------|---------|
| `CREATE` | New memory to persist |
| `UPDATE` | Existing memory needs revision |
| `MERGE` | Combine with similar memory |
| `IGNORE` | Skip (below threshold or duplicate) |
| `EXPIRE` | Temporal context expired |
| `DELETE` | User requested deletion |
| `ESCALATE` | Needs human review |

## Safety & Security

### Injection Detection

The `security.py` module blocks prompt injection patterns:
- `ignore previous instructions`
- `disregard prior`
- `override system instructions`
- `you are now`
- `new instructions`
- `forget your rules`

### User Isolation

Every query enforces `user_id` filtering server-side via RLS + explicit filter.
Cross-user results are rejected by `validate_user_scoped_query()`.

### Consent Model

- **EXTRACTION** (opt-in): Must be explicitly granted before memories are created
- **RETRIEVAL** (opt-out): Granted by default, can be revoked
- **SHARING** (opt-out): Granted by default, can be revoked
- **ANALYTICS** (opt-out): Granted by default, can be revoked

Revoking consent deletes all pending outbox rows.

### GDPR Compliance

- `GET /memory/export` returns all memories, consent receipts, and audit events
- `DELETE /memory/canonical` hard-deletes from Postgres + Qdrant vectors
- Audit trail persists in `canonical_memory_events` (append-only)

## Retriever Hard Limits

| Limit | Value | Rationale |
|-------|-------|-----------|
| Max memories | 20 | Prevent context overflow |
| Max tokens | 2,000 | Bounded generation context |
| Max latency | 200ms | Synchronous path budget |
| Vector results | 50 | Candidate pool cap |
| Lexical results | 30 | Postgres ILIKE cap |

### Ranking Weights

| Factor | Weight |
|--------|--------|
| Semantic similarity | 0.35 |
| Lexical match | 0.10 |
| Importance | 0.15 |
| Confidence | 0.10 |
| Freshness | 0.10 |
| Evidence count | 0.10 |
| Recency bonus | 0.10 |

## Testing

All tests in `backend/tests/security/test_canonical_memory_*.py`:

| Phase | Module | Test Count |
|-------|--------|------------|
| 2 | Schema (`models`) | 38 |
| 3 | Extraction (`extractor`) | 57 |
| 4 | Judge (`judge`) | 58 |
| 5 | Resolver (`resolver`) | 30 |
| 6 | Consolidation (`consolidator`) | 65 |
| 7 | Vector Index (`vector_index`) | 25 |
| 8 | Retrieval (`retriever`) | 33 |
| 9 | History Separation (`history_separator`) | 102 |
| 10 | Context Builder (`context_builder`) | 86 |
| 11 | Chat Integration (`chat_integration`) | 27 |
| 12 | API (`canonical_memory_api`) | 20 |
| 13 | Security (`security`) | 20+ |
| 14 | Privacy (`privacy`) | 15 |
| 15 | Observability (`observability`) | 13 |
| 16 | Evaluation (`evaluation`) | 14 |
| 17 | Simulation (`simulation`) | 28 |
| 18 | Cost Tracking (`cost_tracker`) | 32 |
| 19 | Performance (`performance`) | 29 |
| 20 | Resilience (`resilience`) | 30 |
| 21 | Self-Healing (`self_healing`) | 33 |
| 22 | Migration (`migration`) | 39 |
| 23 | Shadow Mode (`shadow`) | 24 |
| 24 | Canary (`canary`) | 27 |
| 25 | Red Team (`red_team`) | 30 |

## Rollout Strategy

1. **Phase 13**: Security hardening — fix `purge_all_user_data()`, isolation tests
2. **Phase 14**: Privacy — consent lifecycle, GDPR completion
3. **Phase 15**: Observability — health checks, drift detection
4. **Phase 16**: Evaluation — golden dataset, blind evaluation
5. **Phase 17**: Simulation — longitudinal quality testing
6. **Phase 18**: Cost — budget tracking, rate limiting
7. **Phase 19**: Performance — latency budgets, scale testing
8. **Phase 20**: Resilience — circuit breaker, chaos testing
9. **Phase 21**: Self-healing — drift repair, orphan cleanup
10. **Phase 22**: Migration — dual read, legacy cleanup
11. **Phase 23**: Shadow — parallel pipeline comparison
12. **Phase 24**: Canary — staged rollout
13. **Phase 25**: Red team — adversarial testing

## Production Gates

| Gate | Target |
|------|--------|
| Precision | ≥ 95% |
| Correct update | ≥ 95% |
| Relevant retrieval | ≥ 90% |
| False memory | ≤ 1% |
| Deletion accuracy | = 100% |
| Cross-user leakage | 0 incidents |
| Injection blocked | 100% |
| Budget | Within limits |

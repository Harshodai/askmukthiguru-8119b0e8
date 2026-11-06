# Historical architecture decision records

Owner: specification agent (final verification, 2026-11-05). Code state: `c9b42d3e`. Scope: decisions that already shaped the repository. Proposed future decisions are ADR-001 to ADR-015 in `17` §5 and `decision-log.md` §2. This file does not repeat them. It records the earlier ones, their evidence, and whether each still holds.

Evidence labels follow `CONVENTIONS.md`. A historical decision is often known only from a repository document. Such a statement is `[DOC-CLAIM]` and was not re-run. Code claims cite `path:line` read in this session. Alternatives appear only where a repository source records them.

Decision IDs here are `H-01` to `H-16`, to avoid clashing with ADR-001 to ADR-015 (`17`) and D-01 to D-27 (`unresolved-questions.md`).

## 1. Index

| ID | Decision | Date and source | Still valid? | Keep or revisit |
|---|---|---|---|---|
| H-01 | Memgraph replaces Neo4j | 2026-09-15, confirmed 09-19 (`docs/agent/claude-md-archive/database-and-graph.md`) | Partly. Infrastructure choice holds; the graph stack is proposed for removal from serving (ADR-005, D-05) | Revisit with D-05 |
| H-02 | OpenRouter is the live LLM provider | 2026-09-12 (`CLAUDE.md` Project constraints; `backend/app/config.py:71`) | Yes | Keep; consolidate providers (D-17) |
| H-03 | First-person-only chat | 2026-10-11 (`CLAUDE.md` inv. 21) | Yes, as code default | Keep; ADR-001 may add labelled layers |
| H-04 | v10-only serving | 2026-10-30 (`CLAUDE.md` inv. 25) | Yes, conditional on two flags | Keep; encoder fingerprint pending |
| H-05 | Qdrant named dense and sparse vectors with server-side RRF | 2026-09 (archive `database-and-graph.md`; code) | Yes | Keep |
| H-06 | `uuid5` point IDs; a new version is a new collection | 2026-09 (`CLAUDE.md` inv. 4; `first_person_store.py:106-112`) | Yes | Keep; add a recompute test |
| H-07 | Supabase for auth and Postgres | before 2026-08 `[INF]` (`backend/app/main.py:87`; 139 migrations) | Yes | Keep; RLS role gap open |
| H-08 | Backups by local cron, not Celery Beat | 2026-09-13 (`CLAUDE.md` Backup caveat) | Partly. A CI backup workflow now also exists | Revisit (D-26, T3-10) |
| H-09 | Embeddings run host-side | 2026-09-30 (`CLAUDE.md` inv. 18) | Yes | Keep |
| H-10 | Exact-only cache for first person | 2026-09 (`CLAUDE.md` inv. 8; `first_person_pipeline.py:10`) | Yes | Keep (N-10 in `19`) |
| H-11 | LangGraph registry routing for the first-person module | 2026-10-03 (`CLAUDE.md` inv. 16) | Yes | Keep; async lane later (ADR-014) |
| H-12 | The $0-budget constraint is suspended | 2026-09-06 (`CLAUDE.md` Project constraints) | Yes | Keep; spend cap now on by default |
| H-13 | Dormant modules stay, flagged off | 2026-11-01 (`CLAUDE.md` "Dormant modules") | Yes | Revisit after the graded run (D-18) |
| H-14 | ADR-FP-1 to FP-3: ship "Closest teaching"; separate ship gates; fixed regression set | 2026-09-26 (`docs/architecture/first-person-path-to-prod.md` §4) | Partly. Numbers are dated | Keep principles |
| H-15 | Verbatim, no LLM at serve time; abstain gates | 2026-09-29/30 (`CLAUDE.md` inv. 1, 15, 19, 22) | Yes | Keep; ADR-001 is the only proposed relaxation |
| H-16 | Data-engineering ADRs 0001-0005 (publication, chunking, parent ID, rights, ranking metrics) | 2026-10-28 (`docs/adr/`) | Mixed; see §3 | See §3 |

## 2. Records

### H-01 Memgraph replaces Neo4j

| Field | Content |
|---|---|
| Original problem | Neo4j used 700 MB to 1.5 GB RAM idle and under load for a graph of about 8,750 nodes (about 10 MB raw). Causes named: JVM overhead, a 512 MB page cache, Graph Data Science native memory. `[DOC-CLAIM]` archive `database-and-graph.md` |
| Alternatives with evidence | FalkorDB: rejected for its SSPLv1 licence, serialised writes per graph, no native LightRAG support. Kùzu and LadybugDB: rejected for supply-chain risk (Kùzu archived after an acquisition). Apache AGE: rejected for no Bolt protocol and awkward SQL-wrapped Cypher. Same source. |
| Reason | Memgraph speaks Bolt, so the `neo4j` driver and queries work unchanged. LightRAG has native storage for it. |
| Benefits | Claimed: 570.6 MiB resident against a 1 GiB limit, no JVM pauses, `NEO4J_*` variables remain aliases. The alias exists in code: `backend/app/config.py:826,830,2614-2617`. |
| Trade-offs | Replaces the Neo4j GDS plugin with MAGE. Two names for one store. |
| Known weaknesses | The graph has no span provenance and no measured lift. LightRAG chunks were 41.4% contaminated `[DOC-CLAIM 08]`. Numbers above are not re-measured. |
| Current validity | The store choice stands. Serving use is contested: `17` ADR-005 proposes removing the stack from serving; `19` N-05 says "remove from serving". Root `CLAUDE.md` still lists Memgraph under data stores. |
| Keep or revisit | Revisit with D-05. Keep the snapshot. Re-introduce only after an ablation shows lift on the held-out set. |

### H-02 OpenRouter as the live LLM provider

| Field | Content |
|---|---|
| Original problem | The project ran on `sarvam_cloud` under a $0 budget. The funding constraint was suspended (H-12). |
| Alternatives with evidence | Sarvam (`SarvamCloudService`) and Ollama (`OllamaService`) remain in code and share no code with OpenRouter (`CLAUDE.md` Gotchas). A past decision avoided `sarvam-m` and kept `sarvam-30b` (`lessons.md:9427`). |
| Reason | `CLAUDE.md`: "migrated from `sarvam_cloud` on 2026-09-12; OpenRouter usage is intentional, not a drift". |
| Benefits | One gateway to several models. Default in code: `config.py:71` `llm_provider: str = "openrouter"`. |
| Trade-offs | Seeker text leaves the machine for a third party (ADV-02 processor list, B13). Three provider classes drift (`19` N-11). |
| Known weaknesses | A relevance-scorer price is not recorded (NFR-COST-04, D-16). A key mismatch once returned 401 from the root `.env` but 200 from `backend/.env` (`lessons.md:919`). |
| Current validity | Yes. A fail-closed spend guard is now on by default (`config.py:643-652`, `:2491-2499`). |
| Keep or revisit | Keep. Consolidate to one gateway plus one local fallback (D-17, T7-03). |

### H-03 First-person-only chat (owner decision 2026-10-11)

| Field | Content |
|---|---|
| Original problem | The generating graph improvised teaching. An out-of-corpus query ("capital of France") was once served as teacher discourse (`CLAUDE.md` inv. 16, Audit D P0). |
| Alternatives with evidence | Keep the bridge off until an empirically fitted abstention gate exists (inv. 16, original rule). Rejected by the owner on 2026-10-11, with the risk accepted: no fitted gate. |
| Reason | The owner chose to serve the teacher's own clip or a static abstain. |
| Benefits | No generated teaching. Defaults in code match: `config.py:409` bridge on, `:430` LLM fallback off, `:442` weak match on. |
| Trade-offs | High abstention on answerable questions (about 70% `[DOC-CLAIM]`, `18` EVAL-006). No answer composition across clips (ANS-004). |
| Known weaknesses | The LLM answerability gate was measured on 40 questions only (`CLAUDE.md` inv. 21). Kill-switch and node faults used to fall through to generation (SYS-001); T1-05 fixed this (`backend/services/fp_fail_closed.py:26`, `test_fp_fail_closed.py`). |
| Current validity | Yes. |
| Keep or revisit | Keep. ADR-001 (proposed, D-03) is the only route to a labelled assistant layer; the teacher-voice generation form stays rejected permanently (`17` ADR-001 option C). |

### H-04 v10-only serving (owner decision 2026-10-30)

| Field | Content |
|---|---|
| Original problem | Two serving schemas and engines ran side by side (legacy v8 store and the v10 context harness). The B4 contract stopped startup when both pointed at the same collection. |
| Alternatives with evidence | Keep v8 (`config.py:41` still the legacy default). Keep two collections. |
| Reason | One collection serves both stores only when `FIRST_PERSON_CONTEXT_HARNESS_ENABLED` and `FIRST_PERSON_CONTEXT_TERMINAL_ENABLED` are true (`CLAUDE.md` inv. 25; `first_person_serving_contract.py:329` `v10_only_mode_active`). |
| Benefits | A single schema. Tests: `test_first_person_v10_only.py::test_mode_needs_alias_harness_and_terminal`, `::test_terminal_flag_must_be_the_literal_true`. |
| Trade-offs | The code default stays legacy: harness flags default False (`config.py:282,298`). Documents disagree on which collection is "current" (spec C-13). |
| Known weaknesses | "Clean-Docker proof UNPROVEN" (inv. 25). On v10 the integrity field is `source_text_hash`, not `transcript_hash` (inv. 2, 13). The shipped contract declares no encoder, so the encoder check is inactive (`IMPLEMENTATION-AGENT-PROMPT.md` §0h). |
| Current validity | Yes, conditional. ADR-004 (accepted by the lead) makes `fp-context` the only schema after proof on the frozen bank (T7-06). |
| Keep or revisit | Keep. Revisit when T7-06 retires the legacy engine. |

### H-05 Qdrant named dense and sparse vectors, server-side fusion

| Field | Content |
|---|---|
| Original problem | Python-side fusion cost latency. Exact Sanskrit terms need lexical match; broad questions need semantic match. `[DOC-CLAIM]` archive `database-and-graph.md` |
| Alternatives with evidence | Python-side RRF merging (the earlier approach, same source). |
| Reason | Qdrant's Query API with `Prefetch` and `FusionQuery(Fusion.RRF)`. |
| Benefits | Fusion in the database. Present in code: `first_person_store.py:703`; v10 context store `first_person_context_store.py:559,633`, tested by `test_v10_hybrid_retrieval.py::test_context_store_hybrid_sends_dense_and_sparse_prefetches_to_groups`. |
| Trade-offs | Needs a sparse vector at write time. The v10 store was dense-only until T4-02 (RET-02). |
| Known weaknesses | No measured Recall@k on the serving collection yet (NFR-AIQ-06). The claimed "about 40%" latency cut is not re-measured. |
| Current validity | Yes. |
| Keep or revisit | Keep. Measure on the frozen bank (B15). |

### H-06 `uuid5` point IDs; a new version is a new collection

| Field | Content |
|---|---|
| Original problem | Re-runs must be idempotent and must not mix versions. Random IDs broke re-ingestion checks (`docs/adr/0003-parent-id-scheme.md`, for parent IDs). |
| Alternatives with evidence | The chat corpus ID scheme `source_url:chunk_index` was considered and refused for first person (`CLAUDE.md` inv. 4). An alias swap was considered for the chat corpus (`docs/adr/0001`). First person uses no alias swap. |
| Reason | `uuid5(FIRST_PERSON_NAMESPACE, f"{transcript_hash}:{start_ms}:{end_ms}")`. |
| Benefits | Idempotent upserts. The code matches: `first_person_store.py:56,106-112`. The builder refuses an empty build (`test_builder_replace_and_snapshot.py::test_builder_refuses_empty_build`). Rollback keeps the old collection. |
| Trade-offs | The ID depends on the hash field. v10 stores a whole-transcript hash in `transcript_hash` for 919 of 2,758 spans (`CLAUDE.md` inv. 2), so the ID semantics need the hash-field work (T3-03, landed as `backend/domain/hash_fields.py`, `test_writer_hash_contract.py`). |
| Known weaknesses | No test recomputes IDs over a collection (NFR-DI-02). Add a `hypothesis` property test. |
| Current validity | Yes. |
| Keep or revisit | Keep. |

### H-07 Supabase for auth and Postgres

| Field | Content |
|---|---|
| Original problem | The product needs sign-in, per-user rows and RLS without running its own identity system. |
| Alternatives with evidence | None recorded in the sources read. |
| Reason | Not recorded. `[INF]` rests on 139 migrations (`ls supabase/migrations`) and the auth import at `backend/app/main.py:87`. |
| Benefits | Auth, RLS, edge functions (`supabase/functions/delete-my-account`, `export-my-data`). |
| Trade-offs | Client writes chat history directly (PRD-003). Two sources of truth for history (UX-006). A duplicate-table migration lint was added (`test_migration_lint.py`). |
| Known weaknesses | Production RLS state against the migrations is `[LIVE-R]` unknown (L-07). Deletion fails while the backend is down (SEC-004). |
| Current validity | Yes. |
| Keep or revisit | Keep. T6-05 and T6-06 are reserved tasks. |

### H-08 Backups by local cron, not Celery Beat

| Field | Content |
|---|---|
| Original problem | Stateful stores need backups. |
| Alternatives with evidence | Celery Beat. Rejected "deliberately" (`CLAUDE.md` Backup caveat). The Beat schedule in `backend/celery_config.py:95-107` has win-back, memory and outbox tasks and no backup task (`grep -i backup` returns nothing). |
| Reason | Policy: cron at 02:00 Qdrant and 02:30 Neo4j, retention 7, disk only (`infrastructure/cron/mukthiguru-backup`). |
| Benefits | No dependency on the app's worker. |
| Trade-offs | The cron needs a manual sudo install and was absent on the host, so RPO is unbounded `[DOC-CLAIM]`. |
| Known weaknesses | Two more paths now exist: a daily Supabase dump workflow (`.github/workflows/backup.yml`, 03:00) and `backup-drill-reminder.yml`. The Neo4j cron entry names a store that H-01 replaced. No restore drill (NFR-N-5). |
| Current validity | Partly. |
| Keep or revisit | Revisit under T3-10 and D-26. Pick one mechanism per store. |

### H-09 Host-side embeddings for index builds

| Field | Content |
|---|---|
| Original problem | BGE-M3 and ONNX batch runs inside the backend container hit the 6 GiB limit and died with exit 137 (`CLAUDE.md` inv. 18). |
| Alternatives with evidence | Raise the container limit (not recorded as chosen). Running two backend containers also OOM-killed the Docker VM (`lessons.md:919`). |
| Reason | Run `backend/.venv/bin/python3` on the host. |
| Benefits | Builds finish. |
| Trade-offs | Index builds depend on the owner's machine (DATA-01). Stored vectors differ slightly between host and container encodes (cosine 0.98-0.99, `lessons.md:3113`). |
| Known weaknesses | The encoder is not recorded in the serving contract (T3-12 check inactive). |
| Current validity | Yes. |
| Keep or revisit | Keep. Record the encoder per collection. |

### H-10 Exact-only cache for first person

| Field | Content |
|---|---|
| Original problem | A semantic cache can serve a stale or personalised answer to another user. |
| Alternatives with evidence | GPTCache semantic cache. Refused for teaching (`19` N-10; `first_person_pipeline.py:10` "strictly NO semantic cache"). |
| Reason | Exact query hash plus a re-check of `points_servable` on every hit (inv. 8). |
| Benefits | Tests: `test_fixture_stores.py::test_points_servable_reads_the_store_every_time`, `test_cache_personalization_leak.py::test_personalized_answer_is_not_written_to_shared_cache`. |
| Trade-offs | Lower hit rate. |
| Known weaknesses | The semantic cache on the general path is a residual risk (F-17). The cache key is `(language, message)` only. |
| Current validity | Yes. |
| Keep or revisit | Keep. |

### H-11 LangGraph with registry routing for the first-person module

| Field | Content |
|---|---|
| Original problem | The bridge ran as a pipeline stage before the graph. |
| Alternatives with evidence | Chain stage (the earlier design, `CLAUDE.md` inv. 16). |
| Reason | Since 2026-10-03 the bridge runs inside the graph as registry module `first_person` (`backend/rag/pipeline_registry.py:65-121`). It sits after the safety stages. |
| Benefits | One dispatch table. Test: `test_pipeline_registry.py`. A kill switch is read per request (`first_person_bridge.py:1368`). |
| Trade-offs | Sync `run_llm_coroutine` bridges threads (inv. 22; `first_person_pipeline.py:979,1120`). |
| Known weaknesses | Documented stage order is stale (spec C-1). A node fault used to fall through to generation until T1-05. |
| Current validity | Yes. |
| Keep or revisit | Keep. ADR-014 (async lane) is proposed. |

### H-12 Suspension of the $0-budget constraint

| Field | Content |
|---|---|
| Original problem | `SPEC_DEV.md` required all local processing and open-source dependencies at no cost. |
| Alternatives with evidence | Local and free-tier infrastructure remain "the fallback, not the requirement" (`CLAUDE.md`). |
| Reason | User decision 2026-09-06, funding pending. |
| Benefits | Allows OpenRouter (H-02) and Railway. |
| Trade-offs | Spend risk (SYS-004). Open-source licence rule still applies (`LICENSE-EXCEPTIONS.md`). Jina-v3 was refused for its CC-BY-NC licence (`lessons.md:4502`). |
| Known weaknesses | "Zero external calls at inference" in `CLAUDE.md` is superseded in practice and the text says so. |
| Current validity | Yes. |
| Keep or revisit | Re-tighten if funding changes (`CLAUDE.md` says so). |

### H-13 Dormant modules: keep, flagged off

| Field | Content |
|---|---|
| Original problem | Built-and-tested modules with no call site make false latency, safety and quality claims easy. |
| Alternatives with evidence | Delete them. Not done: deletion is "Harsha's separate decision after the graded run" (`CLAUDE.md`; D-18). |
| Reason | Each file carries a `DORMANT` header (`backend/app/generation/sentence_buffer.py:1`, `backend/app/streaming/admission_router.py:1`). Speculative generation is flag-gated, default off: `config.py:429`, checked at `app/generation/speculative_stream.py:41`. |
| Benefits | No shipped claim cites them. |
| Trade-offs | Carrying cost; the stated reason for "off" is invariants 1, 15 and 21. |
| Known weaknesses | Rule: wire a dormant module only with a new default-off flag read at its call site, tests for both states, and a graded run. |
| Current validity | Yes. |
| Keep or revisit | Revisit after the graded run (D-18). |

### H-14 ADR-FP-1 to FP-3

| Field | Content |
|---|---|
| Original problem | Calibration cannot exist without gold labels. The chat benchmark took about 9 h. |
| Alternatives with evidence | Wait for calibration (rejected: no date). Generate text in the route (rejected: breaks the verbatim guarantee). Source: `docs/architecture/first-person-path-to-prod.md` §4. |
| Reason | Accepted by the owner 2026-09-26. FP-1: ship "Closest teaching" with an honest label. FP-2: separate ship gates (integrity 100%, crisis probe, host leak under 1%, p95 under 1 s deployed, 50-question spot check). FP-3: a fixed 150-question regression set per change. |
| Benefits | The label rule survives: "Related, not a direct answer" (`FR-ANS-01`). |
| Trade-offs | Top-1 0.43 was accepted with a label. |
| Known weaknesses | The gates use dated numbers (p95 under 1 s was measured locally only; the uncached path later measured 4-6 s, inv. 22). FP-4 and FP-5 stayed PROPOSED. |
| Current validity | Partly. The label and gate-separation principles stand. The latency gate conflicts with measured uncached latency. |
| Keep or revisit | Keep principles. Replace numbers with `04` targets. |

### H-15 Verbatim only, no LLM text at serve time, two-tier abstention

| Field | Content |
|---|---|
| Original problem | Generated prose in a teacher's voice is impersonation and breaks trust (`17` ADR-001). Out-of-corpus questions leaked into teacher voice. |
| Alternatives with evidence | Hybrid editorial mode (an LLM writes opening and connectives; code assembles quotes): built, then removed by T1-02 (`IMPLEMENTATION-AGENT-PROMPT.md` §0). Hand-picked thresholds: refused (inv. 3). |
| Reason | Invariants 1, 15, 19, 22, 24: an LLM may only select clip indices, answer YES or NO, or score relevance. |
| Benefits | Tests: `test_relevance_standalone_gates.py`, `test_first_person_bridge.py::test_assembled_answer_is_source_verbatim_only`. |
| Trade-offs | About 4-6 s uncached latency (three LLM calls) and low served share (24-31% `[DOC-CLAIM]`). |
| Known weaknesses | The gates are not calibrated on human labels (owner-accepted risk). |
| Current validity | Yes. |
| Keep or revisit | Keep. |

### H-16 Data-engineering ADRs 0001-0005 (`docs/adr/`)

| ADR | Decision | Status in file | Evidence of current use | Note |
|---|---|---|---|---|
| 0001 | Two-tier publication: versioned collections with alias swap, plus a `source_releases` registry and a shadow-mode filter | Accepted 2026-10-28 | `release_filter_mode` default `off` (per the ADR text) | Applies to the chat corpus. First person uses new collections without alias swap (H-06). Two models coexist. |
| 0002 | Chunker protocol and version grammar; proposition chunking retired | Accepted | Retirement repeated in `19` N-06 | Keep. |
| 0003 | `deterministic_v1` parent IDs; no backfill | Accepted | `services/qdrant/indexer.py` (per the ADR) | Different from first-person point IDs (H-06). |
| 0004 | Rights register is the source of truth; default is unverified, never licensed | Accepted | `test_rights_register_startup.py`, FR-N-6 | Keep. `17` ADR-007 would move authority to Postgres. |
| 0005 | Ranking metrics and per-class release gate | **Proposed**; thresholds not adopted | `test_retrieval_bank_harness.py` (metric maths) | Still proposed. Do not cite thresholds. |

## 3. Rejected technologies and abstractions: do not reintroduce

Each item needs a new ADR with new evidence before it returns (§5).

| # | Item | Why it was refused | Source |
|---|---|---|---|
| R-1 | Generated text in a teacher's first person, for any reason | Impersonation; breaks verbatim guarantee | `19` §5; ADR-FP-1 "Rejected"; inv. 1, 15; `17` ADR-001 option C |
| R-2 | Machine translation of quotes shown as the teacher's words | Integrity; label rule | `19` N-22; inv. 16 |
| R-3 | A hand-picked abstention or direct-answer threshold; fitting on AI-written labels | Not calibrated; labels must be human | inv. 3; `19` N-24 |
| R-4 | OKF text as guru voice or in `citations[]` | OKF is LLM summary, not verbatim | inv. 12 |
| R-5 | A semantic cache for teaching answers | Personalisation leak, staleness | `19` N-10; `17` §6; `first_person_pipeline.py:10` |
| R-6 | Proposition chunking, RAPTOR summaries and contextual re-ingest for teaching content | Hallucination risk, severed context, cost; summaries are not verbatim | `docs/adr/0002-chunking-contract.md`; `19` N-06 |
| R-7 | Centroid-only speaker verification as the attribution gate | Circular; the strict per-window gate is the only real gate | `lessons.md:1419` (L-FP-SPEAKER-STRICT-GATE-1); inv. 23 |
| R-8 | FalkorDB, Kùzu or LadybugDB, Apache AGE as the graph store | Licence, supply-chain, no Bolt | archive `database-and-graph.md` `[DOC-CLAIM]` |
| R-9 | Jina-v3 embeddings | CC-BY-NC-4.0 licence | `lessons.md:4502` |
| R-10 | `always_ram=False` on latency-sensitive vector stores without dedicated NVMe | Latency; use INT8 quantisation and `memmap_threshold` instead | `lessons.md:3748` |
| R-11 | Kubernetes manifests, Helm charts, 10k and 100k SPOF tiers as build targets | No deploy, no baseline | `19` N-01, N-02 |
| R-12 | A second mobile codebase beside Capacitor | Two release surfaces | `19` N-03 |
| R-13 | Memgraph, LightRAG and GraphRAG communities on the serving path (without an ablation) | No lift, no provenance | `19` N-05; `17` ADR-005 (proposed) |
| R-14 | HyDE variants, query-decomposition fan-out, ColBERT, RAGatouille before the frozen bank exists | Nothing can prove benefit | `19` N-07; `backend/CLAUDE.md` |
| R-15 | Multi-agent answer graphs for teaching answers | Cost and nondeterminism | `19` N-09; `17` §6 |
| R-16 | Wiring dormant modules without a flag, tests and a graded run | False claims | `CLAUDE.md` "Dormant modules"; H-13 |
| R-17 | Extra provider stacks (Sarvam, Ollama, NIM) as parallel paths; DSPy, Gradio, `chat_engine` | Drift; no live caller | `19` N-11, N-12 |
| R-18 | A general-assistant mode in beta or faculty review | Leak target | `19` N-23; `17` ADR-002 (proposed) |
| R-19 | Personas for other teachers; inferred "spiritual profile"; emotion-arc interventions | Rights, privacy, dependency | `19` N-13, N-16 |
| R-20 | Engagement mechanics tied to spiritual progress; win-back at deletion | Mission rule | `19` N-15 |
| R-21 | Fine-tuned LLM or reranker before 299 independent labels | No data | `19` N-18 |
| R-22 | In-app gold labelling by AI subagents | Labels must be independent and human | `19` N-24; inv. 3 |
| R-23 | More plan, audit or lessons files; more CI workflows; more system metrics | Sprawl and noise | `19` N-19, N-20, N-21 |
| R-24 | Weakening an integrity gate to raise the served share | Fail closed | inv. 2, 14, 24 |
| R-25 | Property-style tests that only match source text | Not behaviour | `22a` §1 principle 1 (CQ-008) |

Items R-18, R-13 and R-5 depend partly on proposed ADRs. They are marked "proposed" where the source is a proposal.

## 4. ADR template

```
# ADR-<n>: <decision in one sentence>

- Status: Proposed | Accepted | Superseded by ADR-<m> | Rejected
- Date: YYYY-MM-DD
- Deciders: <names>; owner sign-off required for: safety, rights, spend, public scope
- Findings and tasks: <IDs>

## Context
The problem, with evidence (path:line or document). Label every claim [V-STATIC] / [DOC-CLAIM] / [INF] / [LIVE-*] / [HUMAN].

## Options
Only options that someone examined, each with its evidence and its cost.

## Decision
One paragraph. Name the flag that gates it, if any.

## Invariants checked
Which CLAUDE.md invariants apply, and how the decision respects each.

## Consequences
Benefits, trade-offs, known weaknesses. Name the test that proves each benefit.

## Measure
The metric and pass condition (NFR ID). The baseline source.

## Rollback
How to undo it, and how long that takes.

## Review date or trigger
When to revisit.
```

## 5. When a change needs an ADR

A change needs an ADR if any of these is true:

1. It changes or relaxes a CLAUDE.md invariant, or adds an exception to one.
2. It changes what text can reach a seeker as a teacher's words, or adds generated text to any answer.
3. It adds or removes a datastore, a model provider, an embedding model or a cache layer.
4. It changes the serving collection, the schema, the point-ID rule or a hash-field meaning.
5. It changes a safety, consent, deletion or rights rule.
6. It reintroduces anything in §3.
7. It sets a release gate threshold or a calibration rule.
8. It moves a decision from the owner to code, or the reverse.

A bug fix, a refactor with identical golden output, and a test addition do not need an ADR. Record the ADR in `17` §5 or `docs/adr/`. Update `decision-log.md`. If an ADR supersedes one here, mark the older one "Superseded" and keep it.

## 6. Cross-references

- Requirements and tests: `COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md`.
- Proposed ADR-001 to ADR-015: `17` §5, `decision-log.md` §2.
- Do-not-build register: `19` §6 (N-01 to N-24).

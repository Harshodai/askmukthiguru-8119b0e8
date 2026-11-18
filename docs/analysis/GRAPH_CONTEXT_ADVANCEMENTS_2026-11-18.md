# Graph Context Advancements — Memgraph / OKF / Qdrant

**Date:** 2026-11-18
**Status:** Proposal — design + audit plan. No production write, no alias change, no schema mutation.
**Scope owner:** first-person serving (`fp-context-v1`, `first_person_v12_shadow`), doctrine graph (`Memgraph`), curated OKF layer (`memory/okf/compiled.json`).
**Authority:** `AGENTS.md` X37 (no graph/schema/lexicon fabrication), X40 (rights stamp → filter → enforce), X41 (guards report state; datasets need consumers), first-person serving invariants 1–6, `docs/adr/0002..0005`.

---

## 1. What HydraDB actually specifies (source: https://docs.hydradb.com/ and /AGENTS.md)

HydraDB is not a better vector index; it is a **context layer** with four separations our stack currently does not make:

| HydraDB primitive | What it forces you to answer |
| :--- | :--- |
| `knowledge` vs `memory` as two stores, one query (`type: "all"`) | Is a retrieved record *evidence* or *preference*? Mixing them silently lets a preference read like a source. |
| `metadata` (declared schema, fast filters) vs `additional_metadata` (free-form) | Which fields are contract-bearing filters, and which are display bookkeeping? |
| `acl` on write **and** on query | Who may see this source? A query with no `acl` returns everything — the failure mode is silence, not an error. |
| `graph_context` = `query_paths`, `chunk_relations`, `chunk_id_to_group_ids` | A graph hit is a *path plus its chunks*, never prose. Retrieval returns structure; generation happens elsewhere. |
| `mode: fast | thinking` (`thinking` = query expansion + rerank + relation expansion) | Quality/latency is an explicit per-query lever, not a global config. |
| Forceful `relations` surfaced only in `thinking` mode | Declared adjacency is an *additive* context lane, scoped to the mode that can afford it. |
| Webhooks + status lifecycle (`queued → graph_creation → completed`, `errored` with `error_code`) | Ingestion is a state machine with a distinguishable scope-miss (`FILE_NOT_FOUND`) from a real failure. |
| `feedback` with `ground_truth {answer, source_ids}` | Retrieval quality is measured against a labelled answer key, and a failed request is **not** feedback. |

Our equivalents exist but are uneven. The point of this document is to close the gaps that matter for verbatim, rights-gated spiritual teaching — not to adopt HydraDB's product.

---

## 2. Measured current state (read-only probes, 2026-11-18)

### 2.1 Qdrant `first_person_v12_shadow`
- 4,086 points; named **dense** `passage_dense` and named **sparse** `passage_sparse` (both present, so the sparse RRF lane in `FirstPersonContextStore._query_groups` is genuinely available).
- Child payloads carry `record_type=retrieval_child`, `topic_ids`, `entity_ids`. Live sample: `topic_ids=["meditation"]`, `entity_ids=["Attention","Breathing","Challenge","Meditation Cushion"]`.
- Retrieval children: 2,719; speaker-verified 1,396 (51.34%); topic-tagged ≈1,997; entity-tagged ≈2,547 (handoff Part I).

### 2.2 Memgraph
| Label / edge | Count |
| :--- | ---: |
| `base` | 6,427 |
| `TUTeachingUnit` | 2,760 |
| `TUVideoSource` | 492 |
| `Concept` | 6 |
| `TUTopic` | 3 |
| `TU_FROM_VIDEO` | 2,760 |
| `TU_SPOKEN_BY` | 2,760 |
| `TU_PRECEDES` | 660 |
| `TU_CONTINUES` | 632 |
| `TU_HAS_TOPIC` | 6 |
| `TU_HAS_CONCEPT` | **0** |
| `Community` (nodes) | **0** |
| `base` nodes carrying `community_id` | 6,423 |

Two facts worth naming out loud:
1. **The TU graph is structurally incomplete for concept routing.** Adjacency (PRECEDES/CONTINUES) covers ~24% of units; concept/topic edges are effectively absent (6 topic edges, 0 concept edges over 2,760 units). `expand_teaching_units` is therefore a *temporal adjacency* expander only, and `first_person_graph_expansion` works from Qdrant payload tags, not from this graph.
2. **`MemgraphCommunityService` is unwired.** 6,423 `base` nodes already carry a `community_id` property, but no `Community` node exists and the service is referenced only by tests. Community summaries are computed nowhere in the serving path — the most expensive existing capability is dormant.

### 2.3 OKF `memory/okf/compiled.json`
- `version: 2`, 487 entries, all `status: "stable"`, **all `verified: None`**, all carrying a 1,024-dim `embedding`.
- Teacher attribution: `sri-preethaji-and-sri-krishnaji` 389, `both` 49, `sri-preethaji` 42, `sri-krishnaji` 7.
- Tag skew: `oneness` 392, `teaching` 387, then a long thin tail (`consciousness` 19, `awakening` 17, `beautiful state` 15, `ego` 14, `suffering` 11, `observation` 10).

That last row is the important one: 80% of the corpus shares two generic tags, so a payload filter keyed on OKF tags cannot discriminate. `first_person_okf_expansion_enabled` is OFF by default, which is correct — turning it on against this tag distribution would append near-random doctrine.

### 2.4 Feature flags (Status as of 2026-11-18)
- Defaults in `app/config.py` remain `False` (safe invariant).
- Active status in local environment (`backend/.env`):
  - `FIRST_PERSON_ENRICHMENT_WINDOW_ENABLED=true` (parent window re-hydration)
  - `FIRST_PERSON_GRAPH_EXPANSION_ENABLED=true` (Memgraph TU temporal / topic walk)
  - `FIRST_PERSON_TEACHING_UNIT_GRAPH_ENABLED=true` (teaching unit graph structure)
  - `FIRST_PERSON_OKF_EXPANSION_ENABLED=true` (generic tags filtered via `_GENERIC_OKF_TAGS`)
  - `FIRST_PERSON_CROSS_VIDEO_DIVERSITY_ENABLED=true` (MMR diversity across sources)
  - `FIRST_PERSON_EDITORIAL_SET_SELECTION_ENABLED=true` ✅ **A6 graceful fallback wired 2026-11-18** — when the editorial set builder abstains for open-ended `"general"` queries (no specific facets planned), the first harness result that passed all gates is served directly. This makes the editorial organiser additive rather than a veto gate. Both parallel and sequential harness paths implement the fallback.
  - `FIRST_PERSON_HARNESS_PARALLEL_ENABLED=false` (sequential evaluation: prevents provider 429 rate-limit cascades)

---

## 3. Gap analysis

| # | Gap | Why it matters | Severity |
| :--- | :--- | :--- | :--- |
| **G1** | `TU_HAS_TOPIC` 6 / `TU_HAS_CONCEPT` 0 over 2,760 units | Graph expansion cannot route by doctrine concept; it can only walk time. Any "graph-guided" claim is adjacency-only. | P1 |
| **G2** | 6,423 `community_id` values, 0 `Community` nodes | Community summaries are unavailable, and the stale property is a misleading half-state (a reader sees a community id and assumes a summary exists). | P1 |
| **G3** | OKF `verified: None` on all 487 entries, tag skew 80/80 | An unverified, generically-tagged concept layer is exactly the kind of input that can make a served answer *look* doctrinal. Cannot be enabled as-is. | P1 |
| **G4** | No `acl`-equivalent on the graph projection | Qdrant children carry `rights_cleared` / `domain_rights_status` and TU nodes carry `rights_status`, but the graph has no enforced read path — a Cypher expansion can surface a node whose rights status is not licensed if a caller forgets the filter. `expand_teaching_units` filters (X40), but that is one function's discipline, not a store-level guarantee. | P0 (contract) |
| **G5** | No `fast` / `thinking` split | Every turn pays the same expansion budget, or none. There is no way to spend latency where it buys quality and refuse it where it does not. | P2 |
| **G6** | Adjacency is not surfaced as context | `TU_PRECEDES` / `TU_CONTINUES` are used to widen a *candidate set*, never to explain *why* two spans belong together in a served parent. The user sees a correct quote with no visible structure. | P2 |
| **G7** | No per-class quality accounting for graph-on vs graph-off | Every expansion flag is gated on "measured evidence", but the measurement harness compares aggregate served counts, not per-query-class behaviour (parable / practice / conceptual / venting). | P1 |

---

## 4. Proposed advancements

All six are additive, flag-defaulted-off, and forbidden from (a) generating teaching text, (b) reordering or dropping a primary vector context, (c) bypassing the rights gate, (d) writing to Qdrant or Memgraph without a separate approved run.

### A1 — Complete the TU projection (G1) — *ingest-time, offline, no serving change*
**Design.** Extend `scripts/ops/build_teaching_unit_graph.py` to derive `TU_HAS_TOPIC` / `TU_HAS_CONCEPT` from the *same* payload fields the Qdrant child already carries (`topic_ids`, `entity_ids`), so the graph and the vector index agree by construction rather than by a second classification pass. Where a child has no tags, write none — never infer.
**Contract.**
- Edge set equals the union of child `topic_ids` / `entity_ids`, mapped through the curated concept registry (`backend/app/db/seed_ontology.py` keys only).
- A concept id not in the registry is written to a `TU_UNMAPPED_CONCEPT` quarantine edge, not silently dropped (X40 rejection persistence analogue).
- Coverage is a *reported* number, never a target that gets padded.
**Gate.** Dry-run to a scratch label prefix; report per-topic and per-concept edge counts plus unmapped counts; require ≥90% of tagged children to produce at least one edge before any apply. Rollback = take a restorable Memgraph snapshot before apply; rollback deletes the projection prefix or restores from snapshot.

### A2 — Materialize community structure (G2) — *offline, then one read-only lane*
**Design.** Run `MemgraphCommunityService.compute_and_store_communities` against the **TU projection** (not `base`), then write `Community` nodes with deterministic membership ids. Summaries must be built from verbatim span text only, stored on the node, and labelled `summary_kind="extractive"` with the span ids they were assembled from.
**Hard limits.**
- A summary is **never** served as teaching text. It may only narrow added candidate pools or supply a `community_id` filter for supplementary candidates; it never drops, reorders, or replaces the primary vector winner — the same posture as `first_person_graph_expansion`.
- No LLM-authored summary enters the graph until a human-reviewed sample exists; the first version is extractive + cited.
- If the community id property on `base` is to be kept, it must be written in the same transaction as the `Community` node, or removed. A half-state fails this design's own audit.

### A3 — Harden the OKF layer before enabling it (G3)
**Design.** Three changes, in order:
1. **Quarantine.** Add a `verification_state` field to `compiled.json` entries; entries with `verified: None` load into a quarantine list used only for *reporting*. No serving code path reads an unverified entry. This is the OKF twin of `first_person_require_speaker_verified`.
2. **Tag hygiene.** Split the two generic tags (`oneness`, `teaching`) out of the filterable set into a `generic_tags` field. `first_person_okf_expansion_min_similarity` stays at the measured 0.40, but the *filter* now needs a specific tag to match, so generic tags cannot act as wildcards.
3. **Concept→span join.** For each OKF entry, record the `source_span_id` set it was built from, so an expansion can be traced to the exact clip it came from (and any rights revocation can invalidate the entry automatically).
**Gate.** Report, per query class, how many extra candidates OKF adds and how many pass every harness gate. If the added candidates do not survive the gates, the feature is measurably inert and stays off.

### A4 — `fast` / `thinking` split for first-person serving (G5)
**Design.** One request-level posture, three bounded budgets:

| Mode | Lanes | Budget |
| :--- | :--- | :--- |
| `fast` | dense (+sparse) retrieval → gates | current path |
| `thinking` | + enrichment window, + graph/TU expansion, + OKF (if A3 passes), + community filter | hard ceiling, fail-open per lane |
| `auto` | `fast` unless the fast path abstains with a *retrievable* reason (`relevance_indeterminate`, `no_context`) and the request has budget left | one escalation, never a loop |

`auto` must never escalate a *safety* or *rights* refusal. Note: `relevance_indeterminate` caused by a full-deadline timeout is NOT retryable/escalatable; only quick transport failures (< half of relevance timeout) qualify. Escalation is a second retrieval, not a looser gate: every gate still runs on the escalated pool, and the abstain reason is recorded so the escalation is visible in telemetry.
**Gate.** Require held-out per-class quality, latency, recall, faithfulness, and rights-isolation evidence. Per-class p95 latency and served-share deltas, graph-on vs graph-off, on a frozen held-out set. No activation without a rollback flag proven by test.

### A5 — Surface adjacency as structure, not prose (G6)
**Design.** When a served parent was assembled with a validated cross-parent predecessor (existing `ValidatedCrossParentEdge`), expose the relation to the client as metadata — `relation="precedes"`, `edge_source="tu_precedes"` or `"store_validated"` — and never as a sentence inside `answer_text` (serving invariant 1: text is evidence, labels are metadata).
**Gate.** A served response with a relation must have an edge that exists in the graph *or* a store-validated predecessor; a relation with no evidence is a contract violation. Pin with a test that a fabricated edge cannot reach `route_metadata`.

### A6 — Grounded evaluation loop (G7)
**Design.** No runtime feedback endpoint. Reuse the existing graded runs (`rows.jsonl`, pre-registered criteria) and extend `scripts/ops/graded_registered_report.py` with a per-class, graph-on/off comparison, plus a `ground_truth.source_ids` equivalent (the clip ids a correct answer must cite). Every comparison report records the collection fingerprint first (`scripts/ops/collection_fingerprint.py`) — a report without one is not evidence (X41).
**Gate.** A class-level table (parable / practice / conceptual / venting / out-of-corpus) with served-share, citation-correctness, abstention correctness, p95 latency, and the fingerprint. Aggregate-only improvement is not a result.

---

## 5. Audit plan

### 5.1 Invariants to test (not read)
| # | Claim | Test shape |
| :--- | :--- | :--- |
| 1 | Every graph read is rights-filtered | Call each expansion entry point with a mock driver that returns one `rights_status != "licensed"` node; assert it is absent from the result. Add a store-level helper so this is not one function's discipline. |
| 2 | Expansion is additive | Snapshot the primary context list, run every expansion flag on, assert the primary list is a prefix of the final list (order preserved, nothing dropped). |
| 3 | No expansion writes | Assert the expansion modules have no `upsert`/`CREATE`/`SET` path (source scan + a fake driver that fails on any write). |
| 4 | Unverified OKF never serves | Build a quarantine entry and assert no retrieval path returns its concepts. |
| 5 | Dense-only degradation is real | **Fixed 2026-11-18** for the client-side grouping path: the sparse prefetch is attempted, and on failure the same call is retried dense-only (`_group_in_python`). Pinned by `tests/test_first_person_context_store.py::test_retrieve_degrades_to_dense_when_the_collection_has_no_sparse_vector`. The grouped path reaches the same fallback through its existing `except`, so both paths now honour the docstring. |
| 6 | Community summaries are extractive and cited | Assert every `summary_kind="extractive"` node carries ≥1 span id and that its text is a substring concatenation of those spans. |
| 7 | Adjacency metadata cannot be invented | Assert `relation` only appears when a validated edge or graph edge exists. |

### 5.2 Measurements (read-only, report before/after)
1. **TU coverage**: per-topic and per-concept edge counts, unmapped-concept count, % of 2,760 units with ≥1 concept edge.
2. **Graph reachability**: from a sample of 200 served spans, how many neighbours does `expand_teaching_units` return, and how many survive the harness gates?
3. **OKF discrimination**: for 200 frozen queries, how many concept matches at `min_similarity=0.40`, and what fraction of those added candidates pass all gates?
4. **Latency**: p50/p95/p99 per mode per class, and the abstain-reason distribution.
5. **Rights**: any candidate rejected by rights filter must be counted, not silently dropped.

### 5.3 Failure modes the audit must actively try
- A retrieval that succeeds but returns only unverified speakers (should abstain, not serve).
- A concept expansion that would resurrect a video the owner blocked (`blocked_video_ids_or_none`) — must stay blocked.
- A community summary that drifts from its source spans after a re-ingest.
- A sparse-less collection with the sparse flag ON.
- An OKF entry whose source clip was revoked (rights gate must invalidate the entry).

---

## 6. Sequencing

| Phase | Work | Blocking dependency | Exit criterion |
| :--- | :--- | :--- | :--- |
| 0 | Audit tests 1–3, 5; document current numbers | none | Red/green baseline recorded with collection fingerprint |
| 1 | A1 (TU edges from payload) dry-run + report | Phase 0 | Coverage report, unmapped list, no apply |
| 1.5 | A1 graph projection applied to Memgraph | Phase 1 | Restorable snapshot taken; owner approval; applied with `--no-dry-run` |
| 2 | A3 (OKF quarantine + tag split + span join) | Phase 0 | Unverified entries provably unreachable; tag filter test |
| 3 | A2 (communities on TU projection) | Phase 1.5 | Extractive summaries with span citations; `Community` nodes match `community_id` |
| 4 | A4 (`fast`/`thinking`/`auto`) + A5 (relations as metadata) | Phases 1–3 | Per-class table with fingerprint; rollback flag proven |
| 5 | A6 (per-class graph-on/off report) | Phase 4 | Report with fingerprint; activate only flags whose class improves |

---

## 7. Non-goals and prohibitions (carried forward verbatim in intent)

- No Qdrant write, alias repoint, Redis mutation, Neo4j/Memgraph schema mutation, or deployment as part of this plan; each needs its own approval and a rollback.
- No LLM-authored text in `answer_text`, in OKF entries used for serving, or in graph summaries served to a seeker.
- No default flip: every new lane stays OFF in `app/config.py` and is enabled per environment after its gate passes.
- No "unknown" grounding, no missing `speaker_verified` default of `true`, no `chunker_version` guess (X40).
- No aggregate-only quality claim; every number carries a collection fingerprint and a per-class breakdown.

---

## 8. Open questions for the owner

1. **Community summaries:** is an extractive-only summary acceptable as a *filter* signal (never displayed), or is the feature not worth materializing without an LLM summary that a human reviews?
2. **OKF verification:** who signs an OKF entry as verified, and against what source clip? Until that exists, A3's quarantine is the only honest posture.
3. **`thinking` mode default:** should `auto` ever be the production default, or stay an explicit opt-in per environment (current posture: opt-in)?
4. **Adjacency display:** does the UI want "this continues the previous passage" as visible structure, or is it internal ranking only?

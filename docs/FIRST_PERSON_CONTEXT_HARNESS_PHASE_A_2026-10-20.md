# First-person context harness — Phase A audit and phase B/D implementation record

Date: 2026-10-20
Plan: `FIRST_PERSON_CONTEXT_HARNESS_AND_TAGGING_PLAN_2026-10-20.md`
Scope: read-only audits (A), canonical contract (B), corpus-build readiness (C),
decision harness + storage adapter (D). No corpus promotion, no serving change,
no Railway action.

## A1. Live collection inventory (read-only)

Commands (local Qdrant):

```
curl -s localhost:6333/collections
curl -s localhost:6333/aliases
curl -s localhost:6333/collections/first_person_v9
curl -s -X POST localhost:6333/collections/first_person_v9/points/scroll ...
```

Measured state:

| Collection | Points | Dense vectors | Sparse |
| --- | --- | --- | --- |
| `first_person_v7` | 2294 | `passage_dense`, `question_dense` (1024, cosine) | `passage_sparse` |
| `first_person_v8` | 1801 | same | same |
| `first_person_v9` (local serving) | 1981 | same | same |

- Alias `first_person` points at **`first_person_v7`**, not at the collection the
  local stack serves (`FIRST_PERSON_COLLECTION=first_person_v9`). The alias is
  stale relative to local serving and is not used by the local path; do not
  treat it as the release pointer.
- `first_person_v9` payload has 23 keys. Payload indexes exist for
  `discourse_context`, `end_ms`, `first_person_eligible`, `group_id`,
  `is_verbatim`, `okf_concept_id`, `okf_title`, `provenance_kind`,
  `quality_status`, `question_text`, `rights_cleared`, `source_url`, `speaker`,
  `start_ms`, `tags`, `teacher_id`.
- Tag distribution: `teacher_id` krishnaji 1124 / preethaji 857; all 1981 points
  are `provenance_kind=speech_turn_clip`, `is_verbatim=true`,
  `rights_cleared=true`, `quality_status=verified_verbatim`,
  `first_person_eligible=true`.

### Gap against fp-context-v1

The phase-C gap report (`backend/scripts/ops/build_first_person_context_index.py
--from-qdrant --collection first_person_v9`) reports:

- `total_points: 1981`, `migration_ready: false`.
- **35 required fields are missing on 100% of points**, including `guru_id`,
  `parent_unit_id`, `source_span_id`, `turn_id`/`turn_index`,
  `source_span_index`, `word_start`/`word_end`, `speaker_id`, `speaker_role`,
  `boundary_status`, `completeness_status`, `source_text_hash`,
  `source_transcript_text`, `source_asset_id`, `corpus_version`,
  `speech_act`, `answer_role`, `entity_ids`/`alias_ids`/`coreference_chain_ids`/
  `topic_ids`/`facet_ids`, `asr_engine`/`asr_model_version`,
  `voice_verification_method`.
- `speaker_verified` is **absent on 1202 of 1981 points (60.68%)** — not
  `false`, missing. Every point still has a `speaker` string.

Conclusion: the existing collection cannot be promoted by a payload backfill.
Phase C is a **rebuild from source ASR output**, because word indices, turn
identity, boundary/completeness status and clip-level text hashes do not exist
in the served payload.

## A2. Corpus inventory (blocked)

- `scripts/ingestion/corpus/` is not present in the worktree (the peer-session
  move recorded in `AGENTS.md` left `backend/scripts/ingestion/corpus/`
  untracked, and that path is also absent now).
- `backend/data/guru_transcripts/` holds only 2 plain `.txt` files plus a cache
  and reports. `transcripts/*.md` carry a header and prose; they contain **no
  word-level timings**.
- `backend/ingest/verbatim/pipeline.py` consumes `whisper_json`/`parakeet_json`
  ASR artifacts. Those artifacts are not present locally.

Consequence: the rebuild cannot be executed on this machine from the data that
is actually here. It needs the ASR JSON for the 487-video inventory (or a fresh
transcription pass), which is an owner-supplied artifact — see "Open
dependencies" below.

## A3. Write-path gate audit

- `find_artifact()` is imported and used on verbatim text in
  `services/first_person_pipeline.py:344` before serving, and ingestion call
  sites (`ingest/pipeline.py`, `ingest/book_ingest.py`,
  `services/intelligent_metadata_extractor.py`) keep the ingestion-safety
  invariant.
- `ingest/verbatim/boundaries.py` exposes `boundary_defects()` and
  `snap_to_sentences()` and is already the repo's single boundary authority;
  the new contract and builder reuse it rather than re-defining defect rules.
- Speaker verification has a lane (`ingest/verbatim/speaker_verify.py`) but its
  output did not reach the served payload for 60.68% of v9 points, so
  `speaker_verified` cannot be defaulted to `true` anywhere.

## A4. Serving-filter audit

`services/first_person_store.py::search_hybrid` filters on:

1. `first_person_eligible == true`,
2. `rights_cleared == true` (unless `first_person_serve_unregistered`),
3. optional `teacher_id`.

It does **not** filter `quality_status`, `is_verbatim`, `provenance_kind`,
`speaker_verified`, or exclude OKF/system label points. `provenance_kind` is
`speech_turn_clip` on all current points, so this is latent rather than active
today, but it is exactly the hole the context plan's "rights and integrity"
gates exist to close. The new harness gates speaker/rights/hash/completeness
before any text is served, independent of that filter.

## A5. Cache audit

`services/first_person_pipeline.py` uses **exact-match-only** caching
(`cache:first_person_exact:{lang}:{sha256}`), never semantic caching for
first-person text. The key already includes:

- normalized query, teacher id, language,
- `self._store.collection` (collection promotion cannot replay an old answer),
- calibration `fitted_at`,
- `rerank|fusion`, answerability-gate marker,
- a serving-policy fingerprint (min score, scorer model, gate flags,
  allowlist/blocklist, prompt).

Gap for phase D: once the context harness is wired into serving, its policy
(harness enabled, `max_context_spans`, parent/edge schema version, corpus
version) must join that fingerprint in the same edit. Otherwise a pre-harness
entry could be replayed for 24 h. Recorded as a wiring checklist item, not
implemented, because the harness is not wired (`FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false`).

## A6. Crisis/safety lane audit

- Default pipeline order is `InputGuardrailStage` → `CircuitBreakerStage`
  (`app/pipeline/stages/pipeline_builder.py`), so deterministic crisis checks do
  not depend on a provider circuit being closed.
- Distress scoring remains the measured answer-quality limit recorded in
  `AGENTS.md` (single-keyword MODERATE ratings on 15/150 benign on-topic
  questions). The context harness does not touch that path and must not be used
  as a substitute for the clinician-reviewed router work.

## A7. Graph (Memgraph/Neo4j) decision

- `app/config.py` maps `MEMGRAPH_*` onto the Neo4j settings
  (`sync_memgraph_and_neo4j`); the local stack runs `memgraph`. No schema
  mutation was performed. The context edges in fp-context-v1 are payload records
  and a derived artifact, not graph schema changes, which keeps this phase
  reversible.

## A8. Model/provider posture

- Serving posture log (in-container, 2026-10-20): `faculty_gate=OFF
  first_person(route=True bridge=True collection=first_person_v9 fallback=False
  weak_match=True min_score=2 model=anthropic/claude-haiku-5.5)`.
- `min_score=2` comes from local `backend/.env`; it is not the shipped default.
- No model download, provider call, or benchmark run was performed for this
  record. Phase E remains unstarted.

## Implemented in this pass

| Item | Location | Notes |
| --- | --- | --- |
| Canonical schema, enums, deterministic IDs, strict payload conversion | `backend/domain/first_person_context.py` | `extra="forbid"`; clip-level hash on `source_text_hash` because legacy `transcript_hash` is video-level |
| Decision harness (gates + deterministic reconstruction + citations) | `backend/services/first_person_context_harness.py` | never authors prose; LLM fields hardcoded off |
| Qdrant adapter (UUIDv5 point IDs, grouped retrieval, fallback grouping, strict hydration) | `backend/services/first_person_context_store.py` | payload-only point upsert verified against local Qdrant 1.19.1 |
| Dry-run builder + gap report | `backend/scripts/ops/build_first_person_context_index.py` | refuses to write to Qdrant by design; `--self-check` passes |
| Feature flag, default off | `backend/app/config.py` (`first_person_context_harness_enabled`, `first_person_context_max_spans`) | declared so `test_settings_guards` sees no undeclared `getattr` |
| Contract/store/harness tests | `backend/tests/test_first_person_context_{contract,store,harness}.py` | 46 tests; 80 with the config suite in-container |
| Structured span selector (Phase D8), default off | `backend/services/first_person_context_selector.py` | model may return span IDs only; prose/answer keys ignored; unknown ID or malformed reply falls back to deterministic order |
| Harness trace + metrics (Phase F5) | `services/first_person_context_harness.py` | `state_path` + `abstain_stage` on every decision, bounded counters via `harness_metrics_snapshot()`, `fp_context_harness_decisions_total` Prometheus series, one structured log line per decision |
| Red-team suite (Phase F1–F5) | `backend/tests/test_first_person_context_red_team.py` | 31 cases: ambiguous reference, alias/metaphor/Ravana, host dialogue, multilingual, cross-guru and cross-parent isolation (contract + gate), citation fabrication, prompt injection inside clip text, OKF/prompt-state leakage, cache corruption, selector timeout, load bound |
| Guru-set isolation fix | `domain/first_person_context.py`, `services/first_person_context_harness.py` | `ParentContext` now rejects spans whose `guru_id` differs from the parent, and the harness refuses a mixed-guru set even when the caller asks for `both` |

## Open dependencies (cannot be closed from this workspace)

1. **ASR artifacts with word timings** for the 487-video inventory. Without
   them phase C cannot produce `word_start`/`word_end`, turn identity, or a
   clip-level hash that matches served text.
2. **Owner decision on `speaker_verified` backfill**: 60.68% of v9 points lack
   the field. Options are re-verification, or serving those clips under
   `shared in <channel>` with the harness's speaker gate failing closed (which
   means they are not served at all). Do not default missing to `true`.
3. **Phase E benchmark run**: requires a corpus, GPUs/provider budget, and an
   owner-approved evaluation window. The plan's no-go conditions still hold.
4. **Serving wiring**: not done. Wiring requires the cache-fingerprint addition,
   a staged rollout, and the plan's phase-E evidence first. The selector flag is
   likewise wired into no serving path, so `fp_context_harness_decisions_total`
   stays empty until then.
5. **Phase F6–F9**: staging blue-green promotion/rollback, full-corpus soak
   (p50/p95/p99, cost, memory), rights/cost sign-off, and the readiness
   declaration need an owner-approved staging window; none of them are
   executable from this workspace.

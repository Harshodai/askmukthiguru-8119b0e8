# FP Wiring Sweep — 2026-10-04

Fresh-eyes end-to-end sweep of Qdrant + OKF behind the FIRST-PERSON serving path.
Backend container STOPPED; verification is code reads + live read-only Qdrant queries only.
Live state observed: alias `first_person` → `first_person_v7`, **1,402 pts** (growing; a driver is upserting).
Zero file writes besides this doc; no commits; 0 LLM calls used.

## 1. Hop map — how a first-person query reaches Qdrant

Two entries, one shared implementation:

**A. Dedicated route** `POST /api/first-person/query`
- `backend/app/api/first_person.py:198-205` — route kill-switch (`first_person_route_enabled` + `first_person_mode != disabled`).
- `:213-218` — `_pipeline(settings.first_person_collection, ...)` — collection name comes from **settings only**.
- `:230` — `_english_query()` translates non-English → English for embedding (verbatim never translated).
- `:233` — `container.embedding.encode_single_full_async(retrieval_query)` → dense + sparse.
- `:250-259` — `asyncio.to_thread(pipeline.execute, query_dense_vector=dense, ...)`.

**B. Main-chat bridge** (plug-and-play cutover: runs inside LangGraph, not `build_default_pipeline`)
- `backend/rag/nodes/first_person.py:44-60` (`first_person_node`) → `run_first_person_bridge(ctx)` — thin, fail-open.
- `backend/app/pipeline/stages/first_person_bridge.py:658-665` — single seam (`first_person_bridge_enabled` + `run_first_person_bridge`); stage and node cannot drift.
- `:361-371` — bridge kill-switch inherits route gates (`first_person_chat_bridge_enabled` AND `first_person_route_enabled` AND mode).
- `:392` — reuses `state.user_msg_en` (no second translation).
- `:396-402` — **follow-up rewrite (bridge heuristic)**: `_is_heuristic_followup` + `_get_last_user_message`, both imported from `rag/resolve_followup.py:48`; rewritten as `f"{last_user} — {retrieval_query}"`. Only the **retrieval** embedding uses the rewritten text; safety/cache still key on raw `query`.
- `:407` — embed; `:415-420` — dim-contract check (`_dense_vector`, fail-closed to no-bridge); `:424-433` — `asyncio.to_thread(pipeline.execute, ... teacher_id="both", max_clips=3 ...)`.
- `:446-458` — calibrated gate: only `status == "success"` + `is_direct_answer` serves; everything else falls through to GraphStage (unless `first_person_llm_fallback_enabled=false`, then static abstain via `_abstain`).
- `:460-480` — `_eligible_citations` + verbatim-in-answer check (answer must contain its cited clip text byte-for-byte, else refuse).
- `:494-501` — output rail re-applied; `:504-510` — glue-only translation for Indic (quotes never translated, fail-open).

**Shared core** `FirstPersonPipeline.execute` (`backend/services/first_person_pipeline.py:961-1345`):
crisis pre-check → topic rail → exact-cache → `store.search_hybrid` (`:1062-1070`, over-fetches `limit=max(50, 8×max)`, `dedup_limit=max(16, 3×max)` as quarantine-backfill spares) → integrity gate + content gate (`:1085-1104`) → optional reranks → teacher-diversity balance → answerability gate (only when `is_direct`) → OKF match → weaver → citation build → exact-cache write.

**Qdrant hop** `FirstPersonStore.search_hybrid` (`backend/services/first_person_store.py:504-585`):
RRF fusion over `passage_dense` + `passage_sparse` prefetches (depth 60), filter `first_person_eligible==True [+ rights_cleared==True] [+ teacher_id]`, then `deduplicate_clips_by_video` (max 1/video).

**Collection-name resolution**: `FirstPersonStore.__init__` (`:217-225`) = explicit arg → `settings.first_person_collection` → `DEFAULT_COLLECTION = "first_person_v1"`.
Config default `backend/app/config.py:159` is `"first_person_v1"`; repo-root `.env:165` sets `FIRST_PERSON_COLLECTION=first_person_v7`.
The string passes straight through to `query_points / retrieve / upsert / count` — **alias-capable** (Qdrant resolves aliases server-side; verified: `count` on alias `first_person` returns 1,402, identical to `first_person_v7`).
**But not alias-pointed**: live config pins the concrete `first_person_v7`, so an alias swap does NOT propagate without a config change + restart. The cutover plan's own recommendation (docs/QDRANT_FP_RESEARCH_2026-10-04.md §10b) is still open. Wrinkle: pointing at the alias would trip the calibration-profile collection-equality gate (`first_person_pipeline.py:137-143, 159-165` — profile `collection` must equal `store.collection`; a profile fitted as `first_person_v7` is ignored when reading via alias `first_person`, silently demoting every answer to `weak_match`). Alias cutover needs a profile strategy first.

## 2. OKF injection — what the FP path actually consumes

- FP pipeline matches **only `compiled.json`** via `match_okf_entries(top_k=2)` (`first_person_pipeline.py:1247-1260`). Live `memory/okf/compiled.json` holds **429 entries** (not 427), keys include `body, summary, key_teachings, description, embedding(1024d), teacher, type, ...`.
- **`verbatim_clusters.json` is never touched by the FP path.** Only readers are `app/api/ritual.py:7,175` and `tests/test_okf_store.py:227-300`. The `OKFStore.match_verbatim_clusters` method exists but has zero FP callers.
- OKF entries flow into `QuoteWeaverService.weave(query, clips, okf_entries)` where they contribute **zero rendered text**: `_format_assembled_answer` (`quote_weaver.py:375-419`) assembles opening + verbatim clip blocks + connective + reflection questions only. `_generate_reflection_questions` (`:337-356`) **ignores its `okf_entries` parameter entirely** (dead parameter — static thematic catalog). In default `retrieval_only` mode the weaver short-circuits to `_deterministic_fallback` (`:620-626`).
- **Never-cite invariant holds in code, 3 layers**:
  1. `first_person_pipeline.py:1267-1268` — `_build_citation` raises `ValueError("OKF entries cannot become first-person citations")` on `provenance_kind == "curated_okf"`.
  2. `first_person_pipeline.py:886-895` + `:1312-1314` — exact-cache path rejects `curated_okf` citations; comment states OKF summaries "must never appear as attributed guru words".
  3. `first_person_bridge.py:255-286` — `_eligible_citations` requires `is_verbatim is True` + http(s) URL + non-empty `verbatim_text` (OKF summaries have no clip contract, cannot pass).
  4. Defense in depth: `validate_clip_entry` (`first_person_store.py:140-141`) refuses to *index* `provenance_kind == "curated_okf"`; `_passes_integrity_gate` (`first_person_pipeline.py:243`) refuses to *serve* it.
- **Latent hole (punchlist P2)**: the assertion gate treats OKF text as valid quote sources (`quote_weaver.py:232-239` — OKF `body/summary/description/title/key_teachings` all count toward quote validity). In `hybrid` mode an LLM scaffolding quote verbatim from an OKF summary (LLM-generated prose, not teacher words) would PASS the gate. Currently unreachable: scaffolding prompts receive only speaker names + discourse titles (`:492-503`), never teaching text, and default mode never calls the LLM. One prompt change away from live.
- `okf_verbatim_quote_gate`: default **`False`** (`backend/app/config.py:1017`). Exactly **one reader**: `OKFStore.list_entries` (`backend/services/memory/okf_store.py:239-256`, strips non-verbatim quotes at load when on). Nothing in the FP path reads it; FP's quote protection comes from the gates above, not this flag.

## 3. Guards

- **rights_cleared on every FP query: YES.** `search_hybrid` appends `rights_cleared==True` unless `first_person_serve_unregistered` (`first_person_store.py:522-525`; default `False` per `config.py:169`). `points_servable` enforces the same on exact-cache hits (`:486-502`, 300 s TTL cache). Live: **1,402/1,402 points `rights_cleared=True`**, 0 False — verified by filtered counts.
- **BUT the index is a no-op (punchlist P1).** `PAYLOAD_INDEXES` declares `("rights_cleared", "bool")` (`:212`) with a comment admitting a keyword index on bool payload "never fires". Live `first_person_v7` schema confirms: `rights_cleared → {keyword, 0 pts}`, `first_person_eligible → {keyword, 0 pts}` (created pre-fix). Filter *correctness* is unaffected (unindexed filters still match — the 1,402 counts prove it) but every FP query full-scans. Fine at 1.4 k pts; fix before 10 k.
- **Host-leak protections, 4 layers**: (1) build-time: `build_first_person_index.py:179-188` drops any clip whose speaker is not in `_TEACHER_LABELS` (`host_skipped` counter); (2) write-time: `ALLOWED_SPEAKERS` allowlist in `validate_clip_entry` (`first_person_store.py:126-129`, rejects "both"/"unknown"); (3) serve-time: `_passes_integrity_gate` speaker check (`first_person_pipeline.py:247-248`); (4) dedup/canonicalization of re-upload twins (`canonical_video_id`, `:74-81`). The build script even documents a prior host-speech-mistagged-as-teacher incident (`:81-84`).
- **Quarantine at serve time — PROVEN with one gap.** Serve-time quarantine = `_passes_integrity_gate` (hash mismatch / non-allowlisted speaker / `find_artifact` hit / dangling conjunction / optional boundary defects) + content-quality gate, with over-fetched spares backfilled (`:1066-1068`) and `FIRST_PERSON_QUARANTINED_TOTAL` counted (`:1096-1100`). Covered by `tests/test_first_person_pipeline.py:123` (tampered hash quarantined), `:343` (backfill), `:728` (boundary guard). Build-time quarantine (whole-video: transcript missing, ASR disagreement, hash mismatch — `build_first_person_index.py:493-550`) means quarantined videos are **never indexed at all**. Live: 0 points with `quality_status != verified_verbatim`, 0 with `first_person_eligible=False`.
  - **Gap (punchlist P1)**: `quality_status` is indexed (`keyword`, 1,402 pts) but **never referenced in any serve-time filter or gate** — `search_hybrid` filters only `first_person_eligible + rights_cleared`. If any writer ever upserts a point with `quality_status="quarantined"/"needs_review"` while leaving the two booleans True, it serves. Today the writer always sets all three consistently, and live data is clean — defense-in-depth only.

## 4. Follow-up (multi-turn rewriting)

**Wired, with test.** Bridge heuristic (`first_person_bridge.py:396-402`, reusing `resolve_followup._is_heuristic_followup` / `_get_last_user_message`) expands anaphora queries with the last user message before embedding.
Test: `backend/tests/test_first_person_bridge.py:751` `test_bridge_resolves_conversational_followup` — asserts the embedding call receives both "What is the Beautiful State?" and "How do I practice it?".
Note: the graph's general `resolve_followup` node is intentionally bypassed here (bridge runs before graph nodes); the two join styles differ cosmetically (`" — "` bridge vs `" - "` in `resolve_followup.py:163`) — embedding-identical, no action needed.

## 5. Top-5 smells (report only, no source edits)

1. **`quality_status` indexed but never filtered** — `first_person_store.py:519-531` vs index decl `:204`. Fix: add `quality_status == "verified_verbatim"` (or `!= quarantined`) to `search_hybrid` + `points_servable`, or drop the index. Evidence needed: write-path audit that no writer can set quarantined-status with eligible+rights True (else filter change could mask data).
2. **Live bool filters unindexed** — live v7 has `keyword/0-pts` indexes on `rights_cleared`, `first_person_eligible` while values are JSON booleans (verified live). Fix: `create_payload_index(bool)` on v7 (or next shadow) + ensure shadow builder copies `FirstPersonStore.PAYLOAD_INDEXES`, not `QdrantClientManager._PAYLOAD_INDEXES` (`qdrant_aliases.py:220-231` — the §10 parity audit is still open). Evidence needed: `collection_aliases` + post-index filtered-count parity.
3. **Assertion-gate OKF quote hole** — `quote_weaver.py:232-239` admits OKF summaries as quotable sources. Fix: remove the `for e in okf_entries` block from `source_texts` (clips-only validity), or gate it behind `mode == hybrid` + comment. Evidence needed: hybrid-mode test asserting an OKF-verbatim (clip-absent) quote FAILS the gate.
4. **Alias cutover blocked by profile gate** — `first_person_pipeline.py:137-143,159-165` + root `.env:165` pinning `first_person_v7`. Fix: decide alias-vs-concrete (recommend alias `first_person` + profile keyed to alias, or profile accepts alias-resolution map) before the next reindex. Evidence needed: pre-swap golden-25 green on shadow (per §10 rec 9).
5. **Revocation window: 300 s servable-cache + 24 h exact-cache** — `_points_servable_cached` TTL 300 s (`:844`), `EXACT_CACHE_TTL = 86400` (`:53`). A rights revocation keeps serving up to 5 min (cache hit) / 24 h only if the point is also deleted — actually deletion is caught by `points_servable` count check, but a *flag flip* (`rights_cleared` True→False, point still exists) serves stale for up to 300 s. Bridge's `_eligible_citations` re-checks neither flag. Acceptable, but undocumented. Fix: document the window or shorten TTL. Evidence needed: none (design decision).

Non-issues checked and cleared: `teacher_ids` keyword index (Qdrant handles list payloads); `points_servable` duplicate-ID fail-closed (correct); `search_hybrid` returning `passage_dense` vectors (needed for cosine confidence); `_exact_cache_key` including `:ans` flag suffix (kill-switch safe); `upsert_clips` persisting `rights_cleared` only when present (fail-closed: absent ⇒ filtered out).

## 6. Verified-working list

- Read path: route → pipeline → `search_hybrid` → RRF on v7; alias resolves (count via alias = 1,402 = direct).
- rights_cleared filtering on every query + cache-hit revalidation; live 100% cleared.
- Never-cite OKF: 4 layers (index-refuse, citation-raise, cache-reject, bridge-eligibility).
- Host exclusion: build/write/serve allowlists; prior leak incident documented in code.
- Serve-time quarantine with backfill + metric + alert rule (`test_observability.py:187-206`); build-time quarantine prevents indexing.
- FP follow-up rewrite wired + tested (`test_first_person_bridge.py:751`).
- OKF's FP role is match-only (top-2 signal into weaver); `verbatim_clusters.json` correctly uninvolved.
- `okf_verbatim_quote_gate` default False, single reader, no FP interaction.

## 7. Punchlist (ranked)

| # | Fix | Evidence needed |
|---|-----|-----------------|
| P1 | Index `rights_cleared` + `first_person_eligible` as **bool** on v7/next shadow; fix shadow index-list parity (`qdrant_aliases.py`) | Filtered-count parity pre/post; alias ledger entry |
| P1 | Add `quality_status` to serve-time filter (or remove index) | Write-path audit proving no inconsistent writer |
| P2 | Remove OKF entries from assertion-gate `source_texts` (`quote_weaver.py:232-239`) | Hybrid-mode test: OKF-only quote must fail gate |
| P2 | Alias cutover: point `FIRST_PERSON_COLLECTION` at `first_person` + resolve profile-collection gate | Golden-25 green on shadow pre-swap |
| P3 | Document the 300 s/24 h revocation window (or shorten servable TTL) | Owner decision, no test |

## 8. Verdict per area

- **Read path / alias readiness: CAPABLE, NOT CUT OVER.** Alias works; config pins concrete v7; profile gate blocks naive cutover. (P2)
- **OKF injection / never-cite: SOUND, latent gate hole.** Zero OKF text renders; citations impossible; gate admits OKF as quote-valid in hybrid only. (P2)
- **Guards (rights/host/quarantine): SOUND, two hardening gaps.** Every query filtered; live data 100% clean; `quality_status` unfiltered + bool indexes missing. (P1 ×2)
- **Follow-up: WIRED + TESTED.** No action.
- **Smells: top-5 reported, no source edits made.**

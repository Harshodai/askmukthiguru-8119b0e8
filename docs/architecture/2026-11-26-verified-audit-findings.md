# Verified audit findings: teaching + editorial intelligence (2026-11-26)

Scope: read-only audit of the running local stack and source on `main` (PRs 110-113, 111 merged)
plus the editorial evidence platform branch. **Status update, same day (end of session):** most
findings below are now fixed and merged or in the final PR; section 7 lists each one with its
evidence. Sections 1 to 6 keep the original findings so the history stays readable.
Evidence tags: **[V]** verified by me directly, **[A]** reported by an audit subagent from code
reading (not independently re-run), **[R]** reported from a live read-only query by a subagent.
During the audit no store was written and no flag was changed. Later writes (13 Qdrant points, the Memgraph TU layer) are recorded in section 8, each after a snapshot and the owner's approval. Human-only gates remain open.

## 1. Fixed in this pass

| Defect | Evidence | Status |
|---|---|---|
| Bereavement downgrade SEVERE->MODERATE hid passive ideation ("...want to be with her", "...wish I could disappear") | [V] reproduced 4/4 strings downgraded | Removed + regression test (`tests/test_bereavement_no_downgrade_2026_11_26.py`). Needs clinician review before any future de-escalation. |
| Lint backlog (247 errors incl. undefined `time`/`Any`) | [V] ruff, full suite compare | Fixed on local branch `fix/ruff-backlog-2026-11-26` (not pushed). Clean `main` already had 20 failing tests. |
| `fetchWithAuth<T = unknown>` broke typecheck (21 errors) | [V] | Default now `any`. |
| `seeker_comprehension_signals` had no erasure cascade | [V] | FK `ON DELETE CASCADE` added (migration unapplied). |

## 2. Verified defects, ranked by evidence-integrity / trust risk

1. **Hardcoded `speaker_verified: True`** for hand-listed clips in `ingest_corpus_gaps_v13.py:383` [V code]. Live impact is small: 13 of 2,540 verified v13 points lack windowed-voice evidence, across 8 videos [V query]. Data correction needs approval (no write done).
2. **Memgraph teaching-unit layer is stale vs serving collection**: only 429 of 2,760 `TUTeachingUnit.span_id` resolve in `first_person_v13_shadow` [R]. Graph-to-evidence expansion finds nothing for ~84% of units. Needs a rebuild: data write, approval required.
3. **No id-level join between OKF/concept graph and Qdrant evidence**: `okf_concept_id` is on 0 points [R]; LightRAG concept edges have no span link [R].
4. **Editorial search miswired and silent** (`container.embeddings` vs `container.embedding`, wrong Qdrant object, errors at debug) [V]. Fix in progress.
5. **Editorial fact-check trusts a client-supplied evidence pool** [A]: a fabricated "evidence" list can pass verification. Needs server-side evidence re-fetch (design change, not yet done).
6. **OKF (non-verbatim) candidates fused into the pool that can back exact quotes** [A]. Fix in progress.
7. **Editorial state is in-process memory**; approvals/audit lost on restart; approver not separated from author [A]. The new migration tables are unused.
8. **Production retrieval is dense-only** (`railway.ts` pins `FIRST_PERSON_CONTEXT_USE_SPARSE=false` while code default is true) [A]. Do not flip without a measured run; add the flag to `PRODUCTION_POSTURE` and the drift test.
9. **Facet planner and set selector dormant in production** (`_editorial_set_enabled` requires `is_production=False`); `video_composition.py` has no non-test caller [A].
10. **`reconcile_stores.py` reports a clean result it did not check** [V: returns 0 even on failed reads]. Fix in progress.
11. **First-turn paraphrase blind spot in distress detection**: "Nothing makes me happy anymore", "I feel disconnected from myself", "giving up", "ending things" all rate NONE and no LLM/semantic stage runs on a first turn [A, run read-only]. Needs clinician + native-speaker review before changing.
12. **Evaluation labels are unreviewed**: retrieval bank ids are placeholders; the new 12-item golden set has unknown authorship and ids that did not match any Qdrant id field [A]; the 205-question gold set is AI-written with blank annotator sheets. No MRR/nDCG number is quality evidence yet.
13. **Seen-clip signals read without a consent check; new signals table not tied to consent** [A].
14. **Three ID schemes coexist; new canonical registry is in-memory only and its `evidence_id` is stored nowhere** [A].

## 3. Documentation vs reality

- `first_person_v13_shadow` has 4,730 points, not 4,099 (the extra 631 are two official-channel shadow batches) [R]. `spiritual_wisdom_contextual` has 13,458, not 14,080 [R].
- `transcript_hash == sha256(verbatim_text)` holds on only 2,418 of 2,999 spans; `source_text_hash` on all 2,999 [R]. Confirms the integrity gate must read `source_text_hash`.
- Backend serving posture log matches invariants 21 and 25a: bridge on, fallback off, min score 2 [R].
- Railway has `MEMGRAPH_URI`/`NEO4J_*` variable names on the backend (names only checked) but `railway.ts` IaC declares none, and two memgraph services exist [R].
- Only 7 locale files exist (not 14); each is key-complete [A].

## 4. The multi-video question ("how do we stitch?")

Stitching does not require an LLM to author or paraphrase teacher words. The architecture already
separates three jobs: (a) retrieve verified spans, (b) an LLM may **select, order and judge
continuity** of already-gated spans (`FirstPersonSetSelector`, `FirstPersonVideoJudge`; bounded
LLM calls are allowed by the invariant wording merged in PR 111), (c) assemble from the stored text
with per-span citations. Any connective sentence must be a separately labelled assistant sentence.
These pieces exist but are dormant in production, and `FIRST_PERSON_LLM_FALLBACK_ENABLED` stays false.

## 5. Next work (needs approval where marked)

- Evaluation first: human-labelled held-out retrieval set (human gate); then dense-only vs hybrid and graph-on vs graph-off measured runs.
- Rebuild Memgraph teaching-unit layer from the current v13 build (**data write: dry-run, snapshot, ask, apply**).
- Persist editorial state and server-side evidence verification; separate author/approver.
- Wire seeker comprehension behind consent receipts; add erasure tests.
- Clinician-reviewed semantic distress layer for first-turn paraphrases.

## 6. Competitor snapshot (research date 2026-11-26)

Verified from vendor pages only where tagged in the research notes: Delphi (active, pricing
tiers changed, no verified span/timestamp citations), Personal AI (memory platform, details not
retrievable), Mindar (generic knowledge workspace), Twelve Labs (timestamped video-moment search),
NotebookLM/"Gemini Notebook" (source-grounded Q&A, passage citations claimed by third parties).
Anabasis, Preachly (placeholder), Editstra, Reformeer, ContextForce, Odicity: not verified, do not
cite as competitors. No researched product was verified to combine verbatim spans + timestamps +
teacher governance + an editorial claim-to-evidence workflow. That is a statement about the evidence
found, not proof of uniqueness.

## 7. Fix status (updated end of 2026-11-26)

| # (section 2) | Finding | Status | Where |
|---|---|---|---|
| 1 | Hardcoded `speaker_verified: True` in gap ingest | Fixed (new clips fail closed); 13 live points demoted, see section 8 | PR 118; data patch |
| 2 | Memgraph TU layer stale | Fixed, see section 8 | data operation |
| 3 | No id-level join OKF/graph to Qdrant | Open (not attempted) | |
| 4 | Editorial search miswired and silent | Fixed: lane failures surface in `lane_errors`; one guarded helper | PR 117 follow-up, `app/api/editorial.py` |
| 5 | Client-supplied evidence pool trusted | Fixed: server builds the pool from the dossier and read-only Qdrant re-fetch; mismatch or unknown id is `unverifiable`; missing Qdrant is a 503 | final PR, `QdrantEvidenceAdapter.fetch_by_ids` |
| 6 | OKF could back an exact quote | Fixed: exact quote needs a Qdrant span with a verified speaker; OKF and Memgraph evidence cannot back one | PR 117 follow-up |
| 7 | Editorial state in memory, approver not separated | Fixed behind `editorial_persistence_enabled` (default off): store port, Supabase adapter, audit trail, approver must differ from author and from any content attacher, fail closed with no author. Migration `20261126120000` not applied | final PR |
| 8 | Production retrieval dense-only | Measured, not changed, see section 8 | |
| 9 | Facet planner and set selector dormant | Open | |
| 10 | `reconcile_stores.py` clean result it did not check | Fixed: exit codes 0/1/2, NOT CHECKED line, allowlist drift rule | PR 117 follow-up |
| 11 | First-turn paraphrase blind spot in distress detection | Open: needs clinician and native-speaker review | human gate |
| 12 | Evaluation labels unreviewed | Open, confirmed: the `evals/gold_set_v1` annotator CSVs are template-filled (every row 2 or 3, identical note) | human gate |
| 13 | Seen-clip signals read without consent; signals table not tied to consent | Fixed behind `seeker_comprehension_recovery_enabled` (default off): consent-gated read, write and erasure; lookup errors fail closed. Migration `20261126000100` not applied | final PR |
| 14 | Three id schemes; registry in memory | Open | |

Also fixed this session, found by running the real gates (see `lessons.md`, Nov 26 section): the bereavement
SEVERE to MODERATE downgrade (PR 117); 247 ruff errors and the formatter backlog (PR 119); Bandit B314
(`defusedxml` for the `.xlsx` workbook parse); 25 teacher-name literals moved to `guru_registry`;
about 20 stale or environment-dependent tests; Node 24 in CI and the frontend image (PR 120).
The exception ceiling was raised 754 to 759 with the owner's approval.

## 8. Data operations performed (each after a snapshot and the owner's approval)

- **13 `passage` points in `first_person_v13_shadow`** (8 videos) had `speaker_verified=true` with no voice evidence.
  Patched to `speaker_verified=false`, `speaker_verification_status=pending_voice_check`; only those two fields changed.
  Qdrant snapshot: `first_person_v13_shadow-1111874297854021-2026-11-26-05-52-22-7.snapshot`.
  Verified: `speaker_verified=true` count 2,540 to 2,527; collection still 4,730 points. Not traced: whether serving reads `passage` records.
- **Memgraph teaching-unit layer** rebuilt from `first_person_v13_shadow` after deleting `TU*` labels only.
  Snapshot copied to `~/mukthiguru_attribution_data/memgraph_snapshot_pre_tu_rebuild_20261126/` (restore not tested).
  Before: 2,760 units, 429 resolving. After: 2,999 units, 2,999 of 2,999 resolving; non-TU labels and relationships identical.
  New TU concept (511) and topic (104) layers, 11,279 concept and 6,519 topic edges. Build record: `backend/config/teaching_unit_graph_manifest.json`.
  Graph-on against graph-off retrieval must be re-measured before any quality claim.
- **Dense-only against hybrid** (read-only, 150 AI-authored questions): top-1 parent identical 94%, top-3 overlap 96%,
  hybrid changed 9 top-1 results and is about 2x slower at p50. No human-labelled set exists, so no quality metric is claimed
  and `FIRST_PERSON_CONTEXT_USE_SPARSE` stays false.

## 9. Still open

Human gates: clinician and native-speaker review of the distress layer (first-turn paraphrases such as "Nothing makes me
happy anymore"), 299-pair gold labels, faculty invitations, speaker sign-off, rights confirmation, helpline calls.
Code or data, owner decides: apply the two unapplied migrations, turn the two new flags on, id-level OKF/graph to Qdrant
join, facet planner and set selector in production, one canonical id scheme, trace whether serving reads `passage` records.

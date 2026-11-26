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
  Verified: `speaker_verified=true` count 2,540 to 2,527; collection still 4,730 points. Traced afterwards: serving never reads `passage` records (every retrieval and servability filter requires `retrieval_child`; 0 of the 13 are one), so the demotion changed no served answer.
- **Memgraph teaching-unit layer** rebuilt from `first_person_v13_shadow` after deleting `TU*` labels only.
  Snapshot copied to `~/mukthiguru_attribution_data/memgraph_snapshot_pre_tu_rebuild_20261126/`. Restore tested in a scratch Memgraph container with `RECOVER SNAPSHOT`: 9,910 nodes (3,257 TU + 6,653 non-TU), 2,760 teaching units, identical to the pre-rebuild graph.
  Before: 2,760 units, 429 resolving. After: 2,999 units, 2,999 of 2,999 resolving; non-TU labels and relationships identical.
  New TU concept (511) and topic (104) layers, 11,279 concept and 6,519 topic edges. Build record: `backend/config/teaching_unit_graph_manifest.json`.
  Graph-on against graph-off retrieval must be re-measured before any quality claim.
- **Dense-only against hybrid** (read-only, 150 AI-authored questions): top-1 parent identical 94%, top-3 overlap 96%,
  hybrid changed 9 top-1 results and is about 2x slower at p50. No human-labelled set exists, so no quality metric is claimed
  and `FIRST_PERSON_CONTEXT_USE_SPARSE` stays false.

## 9. Still open

Human gates: clinician and native-speaker review of the distress layer (first-turn paraphrases such as "Nothing makes me
happy anymore"), 299-pair gold labels, faculty invitations, speaker sign-off, rights confirmation, helpline calls.
Code or data, owner decides: apply the two unapplied migrations to the real Supabase project (needs the `lovable-reviewed` label per `src/CLAUDE.md`), turn the two new flags on, id-level OKF/graph to Qdrant
join, facet planner and set selector in production, one canonical id scheme.

## 10. Verification run after the fixes (2026-11-26, scratch containers, nothing real touched)

- **Migrations on a scratch Supabase Postgres** (`supabase/postgres:15.8.1.085`): all 162 applied except 10 older ones that need parts of the real stack the bare image lacks (realtime schema, storage `public` column, `auth.users.email_confirmed_at`, `auth.jwt()`); this session's three migrations applied cleanly and re-apply idempotently.
- **Behaviour of the consent policies** (real roles, JWT claims): insert allowed only with the user's own active receipt; another user's receipt, no receipt, a revoked consent, a declined grant, an insert for another user and an anon request without a `sub` were all denied; repointing a row to someone else's receipt was denied by the UPDATE policy; deleting a receipt or a user cascades away the signals.
- **Finding fixed:** `anon` and `authenticated` could TRUNCATE `editorial_audit_log` (cascading into dossiers, scripts and approvals); RLS does not cover TRUNCATE. `20261126120000` now revokes ALL on those tables from PUBLIC/anon/authenticated; re-tested, every attack is denied and the service role still works. Same default-grant pattern exists on other public tables (a direct database connection as those roles is needed; PostgREST does not expose TRUNCATE): not changed here.
- **Not covered by this test:** the Supabase adapter's HTTP path (PostgREST) was not run; the 10 incompatible older migrations; a real Supabase project.
- **Node 24:** lint, typecheck, unit tests, production build and bundle budget run in a clean `node:24-alpine` container with a fresh `npm ci` (results in the PR description).

## 11. Post-merge verification and cleanup (2026-11-26, later session)

All runs below were executed locally on the merged head; nothing here is copied from CI alone.

- **PR 120 merged** at `21202303f`, final head `0f8731efa`, every check green (including
  `Validate Pre-commit Hooks`, which had failed on `b91585fe7` because the TU graph manifest was
  committed without a trailing newline; the fix also makes `build_teaching_unit_graph.py::_write_manifest`
  write one, in both byte-identical `scripts/` mirrors).
- **Full backend suite** on `0f8731efa`: **15,648 passed, 65 skipped, 2 deselected, 1 xfailed, 0 failed**
  (333 s). One earlier run showed `test_c20_async_lane_does_not_starve_the_executor` failing while
  `npm ci` ran concurrently; the file passes alone (36 passed) and passed in the clean run — it is a
  timing assertion (`async_s < 2.5 * one_request_s`), not a regression.
- **Frontend:** `npm run lint` 0 errors (69 warnings), `npm run typecheck` 0 errors,
  `npx vitest run` 213 files / **1,331 passed, 6 skipped, 0 failed**.
- **ruff scope correction:** CI's only ruff steps run with `working-directory: backend`, so the
  CI-equivalent `ruff check .` / `ruff format --check .` from `backend/` are clean (1,938 files
  formatted). A repo-root ruff run reports 185 errors and 42 unformatted files — pre-existing root
  debt that no CI step checks; do not read it as a PR failure.
- **`fetch_by_ids` verified read-only against live local Qdrant** (`first_person_v13_shadow`, 4,730
  points; only `scroll`/`retrieve`/`count`/`get_collections` used): the result dict is keyed under
  BOTH the stored id and the point id (2 keys per point, same shared object); duplicate input ids
  collapse; two ids resolving to one point yield 2 keys mapping to the same candidate
  (`out[uuid] is out[span]` is True); unknown ids are silently absent (no exception); `[]` → `{}`;
  a `None` client is a 503 at the route, but an UNREACHABLE Qdrant raised
  `qdrant_client...ResponseHandlingException` and escaped as HTTP 500 — a real gap against the
  "missing Qdrant is a 503" claim, being closed as an uncommitted follow-up. Exact quote with
  `teacher_attributed=None` stays `passed=False`.
- **Consent-revocation 503 decision: keep it.** The revocation receipt is persisted before any
  Redis-dependent step, so a 503 reports incomplete *cleanup*, not a lost revocation, and a retry is
  safe (receipts append). Returning 200 would leave `mukthiguru:cache:*` holding answers rendered
  from the user's memory with no sweeper to retry. Correction for the handoff: the consent leg's
  `container.redis_client` is never assigned in production (only in one test), so the 503 comes from
  the exact-cache invalidation at `app/api/memory.py:1018`, not from `services/seeker/consent.py`.
  Alternative if the owner wants completion-during-outage instead of retryability: the
  `/memory/all` pattern — 200 with `status: "revoked_cleanup_incomplete"` and `failures[]` — never
  a plain success body. Pinned tests that would change if the posture changes:
  `tests/test_seeker_comprehension_consent_2026_11_26.py:184-196`.
- **Migrations:** the owner deferred the real-Supabase apply this session ("ignore supabase").
  `20261126000000`, `20261126000100` and `20261126120000` remain unapplied to any real project;
  both new flags remain off.
- **Cleanup:** worktrees `wcomb`, `wnode` and the three `agent-*` worktrees removed and pruned, their
  five merged branches deleted; scratch containers `scratch-pg`/`scratch-mg` were already gone.
  The two other sessions' worktrees under `/private/tmp/askmukthiguru-*` were not touched. The two
  files that blocked the `main` pull (the local manifest change and a stale untracked copy of this
  document) were backed up byte-for-byte to
  `<scratchpad>/pre_pull_backup_20261126/` before removal — nothing was lost.

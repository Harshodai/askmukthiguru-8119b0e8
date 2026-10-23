# First-person v10 public-release remediation — Phase 0 & Phase 1 report

**Date:** 2026-10-21
**Plan:** `.claude/tasks/first-person-v10-public-release-plan-2026-10-21.md`
**Release verdict after this run:** **NO-GO (unchanged).**
`FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false` in `backend/.env` **and** in the
running container. No harness enablement, no Qdrant write, no alias change, no
Redis flush, no deployment.

Machine-readable companions:

| File | What it holds |
|---|---|
| `audits/evidence/public_release_phase0_state_2026-10-21.json` | Phase-0 pre-mutation state (git, Docker, env, Qdrant, artifact hashes) |
| `audits/evidence/public_release_v10_ecapa_reconciliation_summary_2026-10-21.json` | Phase-1 summary under the default `release_grade` verdict-schema policy |
| `audits/evidence/public_release_v10_ecapa_reconciliation_summary_legacy_v1_2026-10-21.json` | The same run under `legacy_v1` (comparability only — **not** release evidence) |
| `.work/public_release/reconciliation_v10_ecapa.jsonl` | One row per v10 child (2,737 rows), sha256 `29226b42…` (durable copy: `audits/evidence/public_release_v10_ecapa_reconciliation_2026-10-21.jsonl`) |
| `.work/public_release/v10_points_export.json` | Read-only export of the live v10 children, sha256 `d8dc2e9c…` (durable copy: `audits/evidence/public_release_v10_points_export_2026-10-21.json`) |
| `audits/evidence/public_release_phase1_verification_2026-10-21.txt` | Every command, cwd, start/end time and **real exit code** |
| `audits/evidence/public_release_v10_strict_audit_2026-10-21.json` | Re-run of the strict structural audit (no drift) |

---

## Phase 0 — state freeze (read-only, nothing mutated)

### Git

| Item | Value |
|---|---|
| `HEAD` | `6183326ff1de430d23e587a9d05a8bca4acd7a2f` |
| `origin/main` | `6183326ff1de430d23e587a9d05a8bca4acd7a2f` (in sync) |
| Branch | `main` |
| Dirty entries | 251 (modified + untracked) — the tree was already dirty from peer work before this run |
| Worktrees | only the main checkout; no temporary worktree created |

Nothing was reset, cleaned, checked out, stashed, committed or pushed. Peer
files were not modified.

### Docker

| Item | Value |
|---|---|
| Binary | `/Users/harshodaikolluru/.docker/bin/docker` |
| Context | `desktop-linux` (Docker Desktop) |
| Backend image | `backend-backend`, id `sha256:57f07e071de5…`, created `2026-10-21T08:29:04Z` |
| Backend container | started `2026-10-21T12:54:59Z` (not recreated by this run) |
| Qdrant | `qdrant/qdrant:v1.18.0`, healthy, `localhost:6333` |
| Redis / Memgraph | healthy, untouched |

### First-person environment

`backend/.env` is the compose project env and wins over the repo-root `.env`.

| Variable | `backend/.env` | Container |
|---|---|---|
| `FIRST_PERSON_CONTEXT_HARNESS_ENABLED` | **false** | **false** |
| `FIRST_PERSON_COLLECTION` | `first_person_v10` | `first_person_v10` |
| `FIRST_PERSON_CONTEXT_COLLECTION` | `first_person_v10` | `first_person_v10` |
| `FIRST_PERSON_MODE` | (unset) | `retrieval_only` |
| `FIRST_PERSON_RELEVANCE_MIN_SCORE` | `2` | `2` |
| `FIRST_PERSON_DISTRESS_SERVE_CLIP_ENABLED` | `true` | `true` |

The safe disabled posture is confirmed in the file **and** in the live
container. The harness was **not** enabled by this run.

> **Latent footgun (unchanged, not touched).** The repo-root `.env` still says
> `FIRST_PERSON_COLLECTION=first_person_v9` — a collection that was purged on
> 2026-10-21. It is masked by the compose `environment:` block, but any
> invocation whose project directory is the repository root would target a
> collection that no longer exists. This is B4 territory (Phase 5).

### Qdrant census (read-only)

```
alias first_person -> first_person_v10
first_person_v10: status=green  points_count=4197  indexed_vectors_count=2737
  vectors: passage_dense (size 1024, Cosine)     segments=2  optimizer=ok
  2737 retrieval_child + 1460 parent_unit
```

No collection was created, deleted, aliased, snapshotted or modified by this
run. Legacy `first_person_v1..v9` remain purged; their snapshots are retained
under `/qdrant/snapshots/`.

### Artifact inventory (hashes in the Phase-0 JSON)

| Artifact | sha256 | Note |
|---|---|---|
| `.work/fp_context/v9_points.json` | `f018d5547f7e02d2…` | legacy export, 1,981 points |
| `.work/fp_context/speaker_verdicts.json` | `52192e16af1c3a9f…` | 1,173 legacy ECAPA verdicts, keyed by v9 point id |
| `.work/fp_context/speaker_report.json` | `52192e16af1c3a9f…` | byte-identical copy of the above |
| `.work/fp_context/asr_manifest_existing.json` | `a648c3ef59b4b5f0…` | 2,737 per-span ASR records |
| `.work/fp_context/rights_manifest_existing.json` | — | 485 assets; **derived from payload**, not independent (B5) |
| `.work/fp_context/candidate_existing.jsonl` | — | 2,737 rows; matches the live payload field-for-field, but its `_point_id` column is `uuid5(NAMESPACE_DNS, span_id)`, **not** the live Qdrant id |
| `.work/public_release/v10_points_export.json` | `d8dc2e9ccf86a4ee…` | new read-only export of the live children |
| `/Users/harshodaikolluru/mukthiguru_attribution_data` | — | ASR/audio archive, present on this host |

---

## Phase 1 — per-span ECAPA reconciliation (implemented first, as required)

### What was built

| File | Purpose |
|---|---|
| `backend/scripts/ops/reconcile_v10_ecapa_verdicts.py` | Read-only reconciler. Standard library only. sha256 `5249c0193457c2a6…` |
| `backend/tests/test_reconcile_v10_ecapa_verdicts.py` | 28 focused tests. sha256 `d1bbd657aa7293ab…` |
| `backend/scripts/ops/capture_public_release_phase0_state.py` | Phase-0 recorder. sha256 `9898c029804577094…` |
| `backend/scripts/ops/run_public_release_phase1_verification.sh` | Transcript runner (real exit codes) |

The script **never** writes to Qdrant, never mutates an input manifest, never
sets `speaker_verified`, and has **no write mode at all** — `--apply-upgrades`
and `--write-mode` are refused with exit code 2. It reads file inputs by
default; a live Qdrant read is possible but only through a scroll endpoint, and
the file path performs no network access at all (both properties are pinned by
tests).

### Matching order (implemented exactly as specified)

1. exact v10 `source_span_id`
2. exact Qdrant point id
3. strict legacy identity tuple `(video_id, normalized_text_hash, start_ms, end_ms)`
4. unique fallback `(video_id, normalized_text_hash, word_start, word_end)` —
   only when every field exists on both sides

Text is normalized only through the versioned function `fp-norm-v1`, which is
pinned by a test against the corpus builder's own `_norm` so the two cannot
drift. Text hashes are **recomputed**, never trusted: the v10 clip hash is
compared with the declared `source_text_hash`, and the legacy clip hash with
the declared `transcript_hash`.

### Match classes and totals (2,737 v10 children, 2,737 rows)

| Match class | Count |
|---|---|
| `exact_span_id` | **0** |
| `exact_point_id` | **0** |
| `unique_identity_match` | **1,106** |
| `ambiguous_identity_match` | 0 |
| `missing_legacy_point` | 898 |
| `missing_verdict` | 732 |
| `identity_conflict` | **1** |
| `invalid_input` | 0 |
| **Total** | **2,737** |

### Coverage summary

| Measure | Value |
|---|---|
| v10 children | 2,737 |
| Rows emitted | 2,737 (one per child, none dropped, all `source_span_id`s unique) |
| Direct span-id coverage (verdict keyed by v10 `source_span_id`) | **0 / 2,737 (0 %)** |
| Direct point-id coverage (verdict keyed by v10 Qdrant point id) | **0 / 2,737 (0 %)** |
| Legacy identity coverage (unique legacy predecessor found) | **1,838 / 2,737 (67.15 %)** |
| — of those, carrying a legacy ECAPA verdict | 1,107 |
| — of those, with `verified=true` | 1,106 |
| Spans with **no** legacy verdict at all | **1,630** |
| Spans with no **verified** verdict | **1,631** |
| `safe_to_upgrade` under `release_grade` (default) | **0 / 2,737** |
| `safe_to_upgrade` under `legacy_v1` (comparability only) | 1,106 / 2,737 |
| Ambiguous matches | 0 |
| Identity conflicts | 1 |
| Malformed / invalid records | 0 |
| Spans recommended for quarantine | 2,737 |

**This reproduces the prior report's numbers exactly**: the legacy identity
join resolves 1,838 children, 1,106 carry a verdict, 732 have no verdict, and
**1,631** spans have no verified acoustic backing.

### The one identity conflict (new detail)

`source_span_id = bf7deb57267fda2c37696ce290996fbbab8fc1bd6f7ab153ada9e44cace51185`
— v10 point `3153c4cd-0cfa-511e-8685-994827a80877`, video `VrPi2RUUXq4`.

A legacy clip exists at the same start offset (`94020 ms`) but its **end
offset is 102930 ms against the v10 span's 116370 ms**, and its normalized
text hash differs. The legacy verdict attached to it is `verified: false`.
The prior report counted this span among the "899 with no v9 predecessor"
because its loose three-field join key also missed it. The strict tuple
separates it out: **898 spans have no legacy point at all, and 1 has a
conflicting one.** This is exactly the class of silent provenance defect the
strict tuple exists to catch, and it is a concrete Phase-2/Phase-3 item.

### Why `safe_to_upgrade` is 0 under the default policy

The archived legacy verdict file predates the impostor-calibrated verifier.
Its top-level keys are `embeddings, evaluation, items, refused, threshold,
upgraded` — there is **no `cosine_floor` and no `calibration_available`**, and
its `threshold` (`0.4668`) is the *p01 of the margin distribution of correct
clips*, not a floor measured against an impostor set. The measured
false-accept rate of the archived calibration is therefore unknown.

`backend/scripts/ops/build_full_corpus_v10.py::load_calibration` already fails
closed on exactly this artifact ("Speaker calibration … has no usable
cosine_floor"), so the repository's own policy treats the archive as
un-calibrated. The reconciler applies the same rule:

* `release_grade` (default) additionally requires per-verdict `model_revision`,
  `calibration_revision`, `source_span_id`, `audio_sha256`, `start_ms`,
  `end_ms`, `cosine_floor`, `margin_threshold` and `timestamp`, plus
  archive-level `calibration_available` / `cosine_floor` / `margin_threshold`.
  **All 1,107 attached verdicts fail** (the per-row problem list is in the
  JSONL).
* `legacy_v1` accepts the older schema. It exists only so the joinable
  population can be compared with prior reports, and the summary says so.

`safe_to_upgrade=true` means *"a legacy verdict is unambiguously joinable to
this span"*. It never means *"this span has independent per-span acoustic
evidence"*. Even a `true` row only means "re-check this span in Phase 2".

### Cross-checks that did pass

* `asr_manifest_check`: **pass on 2,737 / 2,737** — the archived ASR manifest's
  audio window agrees with the live payload for every span.
* `text_hash_check`: pass on 1,838, mismatch on 1 (the conflict above).
* `video_source_check`: pass on 1,839 (the extra one is the conflict row, whose
  video id agrees but whose text/time do not).
* `time_bound_check`: pass on 1,838, `end_ms_mismatch` on 1.

### Strict audit re-run (continuity)

`backend/scripts/ops/audit_first_person_v10_strict.py` was re-run read-only.
**No drift** versus the prior evidence:

| Gate | Result |
|---|---|
| `contract_children` / `contract_parents` | VERIFIED (0 violations) |
| `topology` | VERIFIED |
| `asr_provenance` / `alignment_integrity` | VERIFIED |
| `citation_window_covers_clip` | **BLOCKED** — 298 mismatch, 2 unverifiable |
| `word_index_consistency` | **BLOCKED** — 589 consistent, 2,107 inconsistent, 41 out of range |
| `speaker_evidence_per_span` | **BLOCKED** — `verified_without_per_span_verdict=2737`, `verdict_covered=0` |

`verdict_covered=0` is the same fact this run measured independently: not one
span-keyed acoustic verdict exists.

---

## Commands run and exit codes

Every command below is in
`audits/evidence/public_release_phase1_verification_2026-10-21.txt` with its
cwd, start/end time and real exit code.

| Phase | Command (cwd) | Exit |
|---|---|---|
| 0 | `backend/.venv/bin/python backend/scripts/ops/capture_public_release_phase0_state.py --output …` (repo root) | **0** |
| 1 | `backend/.venv/bin/python -m py_compile backend/scripts/ops/reconcile_v10_ecapa_verdicts.py` (repo root) | **0** |
| 1 | `backend/.venv/bin/python -m pytest tests/test_reconcile_v10_ecapa_verdicts.py -q …` (`backend/`) | **0** — 28 passed |
| 1 | `backend/.venv/bin/python backend/scripts/ops/reconcile_v10_ecapa_verdicts.py --help` (repo root) | **0** |
| 1 | dry-run, `--verdict-schema-policy release_grade` (default) (repo root) | **1** — documented release-blocking status |
| 1 | dry-run, `--verdict-schema-policy legacy_v1` (repo root) | **1** — documented release-blocking status |
| 1 | determinism repeat with pinned `--generated-at-utc` (repo root) | **1** — release-blocking status; artifacts byte-identical |
| 1 | `backend/.venv/bin/python -m ruff check <3 new files>` (`backend/`) | **0** |
| 1 | `backend/.venv/bin/python -m pytest tests/test_repo_layout.py -q …` (`backend/`) | **0** — 3 passed |
| 1 | `git diff --check` (repo root) | **0** |
| — | `backend/.venv/bin/python backend/scripts/ops/audit_first_person_v10_strict.py … --output …` (repo root) | **1** — audit is BLOCKED (expected) |
| — | `backend/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider --no-header -rf --tb=line` (`backend/`) — full regression suite | **0** — **10,709 passed**, 25 skipped, 2 deselected, 3 xfailed, 0 failed (161.18 s) |
| — | focused first-person suite (10 modules incl. the new one) (`backend/`) | **0** — 157 passed, 1 skipped |

Exit-code contract implemented by the script:

* `0` — report produced, no release-blocking condition.
* `1` — report produced, release-blocking conditions present (the documented
  release-blocking status for ordinary missing coverage).
* `2` — no trustworthy report: unreadable/unparseable input, duplicate point
  ids in an export, or a refused write mode. Nothing is written.

### Determinism evidence

Two runs of the same command with the same inputs and a pinned
`--generated-at-utc` produced **byte-identical** JSONL (`cmp` clean) and
**byte-identical** summary (`cmp` clean). Without the pinned timestamp the
JSONL is still byte-identical and the summary differs only in
`generated_at_utc` — both are pinned by tests.

---

## Mutations performed

**None.** Specifically:

* No Qdrant point upsert, delete, alias, snapshot, collection create/delete.
  The only Qdrant interaction was a read-only scroll to produce the input
  export, and the reconciler itself used file inputs only.
* No Redis operation of any kind (no flush, no key write).
* No environment change: `backend/.env` and the container both still carry
  `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false`.
* No alias change: `first_person -> first_person_v10` unchanged.
* No deployment; Railway untouched.
* No source manifest mutated: the tests assert the input files are
  byte-identical after a run.
* Git: no reset, clean, checkout, stash, commit or push.

Files **created** by this run (all additive):

```
backend/scripts/ops/reconcile_v10_ecapa_verdicts.py
backend/scripts/ops/capture_public_release_phase0_state.py
backend/scripts/ops/run_public_release_phase1_verification.sh
backend/tests/test_reconcile_v10_ecapa_verdicts.py
audits/evidence/public_release_phase0_state_2026-10-21.json
audits/evidence/public_release_v10_ecapa_reconciliation_summary_2026-10-21.json
audits/evidence/public_release_v10_ecapa_reconciliation_summary_legacy_v1_2026-10-21.json
audits/evidence/public_release_v10_ecapa_reconciliation_2026-10-21.jsonl
audits/evidence/public_release_v10_ecapa_reconciliation_legacy_v1_2026-10-21.jsonl
audits/evidence/public_release_v10_points_export_2026-10-21.json
audits/evidence/public_release_v10_strict_audit_2026-10-21.json
audits/evidence/public_release_phase1_verification_2026-10-21.txt
audits/evidence/public_release_phase0_phase1_report_2026-10-21.md   (this file)
.work/public_release/v10_points_export.json                        (gitignored)
.work/public_release/reconciliation_v10_ecapa.jsonl                (gitignored)
.work/public_release/reconciliation_v10_ecapa_legacy_v1.jsonl       (gitignored)
```

Files **modified** (documentation only, no behaviour change):

```
lessons.md                                          (4 new lessons)
AGENTS.md                                           (binding Phase 0/1 note)
docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md   (Phase 0/1 addendum)
.claude/tasks/first-person-v10-public-release-plan-2026-10-21.md   (implementation status)
```

---

## Blocker status after Phase 1

| Blocker | Status after this run |
|---|---|
| **B1** per-span ECAPA evidence | **Still open.** Now *measured* rather than asserted: 0 span-keyed verdicts, 1,631 spans with no verified acoustic backing, 1 conflict, 1,630 with no verdict at all. The reconciler exists and is tested; Phase 2 (regenerate per-span verdicts from each span's own audio window, with a held-out impostor calibration) has not started. |
| **B2** citation ↔ audio window | Still open — 298 mismatch, 2 unverifiable. Untouched by this phase. |
| **B3** deterministic span-id word coordinates | Still open — 2,107 inconsistent, 41 out of range. Untouched by this phase. |
| **B4** legacy/context schema conflation | Still open. The Phase-0 state re-confirms `FIRST_PERSON_COLLECTION=first_person_v10` pointing the legacy store at an fp-context-v1 collection, plus the stale repo-root `.env` pointing at a purged `first_person_v9`. |
| **B5** independent rights register | Still open — the rights manifest remains payload-derived. |
| **B6** distress boundary | Still open — clinician review outstanding; nothing tuned here. |
| **B7** gold labels / public-scale evidence | Still open. |

**Overall: NO-GO.** The harness stays disabled.

## What Phase 2 needs (and why it was not started here)

Phase 2 requires, before any verdict can be regenerated:

1. `soundfile` is still absent from `backend/requirements.txt` /
   `requirements.lock` and from the runtime image. It must go through the
   repository's normal dependency process
   (`uv pip compile backend/requirements.txt --output-file backend/requirements.lock`),
   not an ad hoc unpinned install.
2. A **calibrated** archive: `verify_speakers_ecapa.py` must be re-run so the
   verdict file carries `calibration_available`, a `cosine_floor` and a
   `margin_threshold` derived from a measurable held-out impostor set. The
   existing archive has none of those, and `build_full_corpus_v10.py::
   load_calibration` refuses to consume it.
3. Per-span audio slices: ECAPA must run over each span's **own**
   `[start_ms, end_ms]` window, with the audio identity/hash, model revision,
   calibration revision, cosine, margin, floors and timestamp persisted per
   span. The span windows themselves are still unproven (B2), so Phase 2's
   audio slice depends on Phase 3's window rebuild, or must quarantine the
   spans whose windows are not yet re-derived.

Phase 2 is therefore **not** started, per the instruction to implement Phase 1
only until the plan owner approves continuation.

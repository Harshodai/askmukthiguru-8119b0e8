# First-person v10 — evidence-defect repair + owner-only test environment rebuild

**Date:** 2026-10-22
**Overall public-release verdict after this run:** **NO-GO — unchanged.**
`FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false` in `backend/.env` **and** inside the
running container. The public `first_person` alias still points at
`first_person_v10` (4,197 points, status `green`). **No Qdrant write, no alias
change, no Redis mutation, no environment change beyond the local-review flag in
the local container, no Railway action, no git operation.**

**What this run does:** it fixes the three defects the owner's verification
report named — the misleading duration field in the speaker-conflict packet, the
missing identity of the 10 unlocatable quarantine rows, and the hidden
deterministic-id collision — and it rebuilds the local container so the
owner-only preview route is actually reachable for testing.

**What this run does NOT do:** it does not approve anything. It does not enable
the public harness, does not move the public alias, does not write to Qdrant and
does not make the corpus public. It produces five **owner decision packets**
with every decision field left empty.

---

## 1. Defect 1 — the speaker-conflict packet's duration field was misleading

### 1.1 What was wrong

`backend/scripts/ops/build_fp_speaker_conflict_review.py` wrote

```python
"audio_duration_ms": end_ms - start_ms,
```

The Phase-2 verdict uses `audio_duration_ms` for the duration of the **complete
WAV file**. The two quantities are different, and the owner's example shows how
badly:

| quantity | value |
|---|---|
| window | `172540 → 183020 ms` |
| packet `audio_duration_ms` (slice) | `10480` |
| Phase-2 verdict `audio_duration_ms` (file) | `214692` |

A reviewer reading the v1 packet would reasonably conclude the window sat near
the end of a 214-second recording. It sat at 80 % of it. The field name was a
lie to every reader downstream.

### 1.2 The fix

Schema `first-person-speaker-conflict-v2`. The misleading field is **removed,
not repurposed** (a repurposed field would silently carry the other meaning for
anyone reading an old artifact):

| field | meaning |
|---|---|
| `audio_file_duration_ms` | duration of the **complete** archived WAV |
| `audio_slice_duration_ms` | width of the **quoted slice** (`end_ms - start_ms`) |
| `audio_start_ms` | slice start inside the file |
| `audio_end_ms` | slice end inside the file |

The same naming discipline was applied to the tier rows
(`audio_file_duration_ms` + `audio_slice_duration_ms`), so it is corpus-wide and
not local to one packet.

### 1.3 Versioned artifact, old one retained

The corrected packet is a **new** artifact. The v1 artifact is **retained
untouched** and both hashes are recorded in the summary's `schema_migration`
block (`--supersedes-jsonl` / `--supersedes-review`).

| artifact | sha256 |
|---|---|
| **superseded** v1 conflict rows | `85a28f96c2c7f075cfa2c1e3330c417c50a433c7d55d881269edbfc1cdf72d1b` |
| **superseded** v1 review packet | `7fd2b718b3cf6a1e2b01551daf75df351bd0bd2d4c5c4efddb6f8b29ed614eff` |
| **corrected** v2 conflict rows | `5e57e0415f9b3d694fe0a6ec03160befd888621ca1ed9ab3587cbe5adb324402` |
| **corrected** v2 review packet | `1a1270bf615a7bf0e2a7f0cca03897b7cdea2be499e5642e68086bc6486649d7` |
| **corrected** v2 summary | `267361ec7cb68d162d22c29ecf181800a2230d2a50628e49588d9f595a11083d` |

**Compatibility note (recorded in the artifact):** *v1 and v2 rows are **not**
interchangeable. A v1 row's `audio_duration_ms` equals the v2 row's
`audio_slice_duration_ms`.*

### 1.4 Bounds check

Every window is checked against the measured complete-file duration.

| measure | value |
|---|---|
| rows | 45 |
| bounds-checked against a measured file duration | **45** |
| rows without a measured file duration (never counted as in-bounds) | **0** |
| **windows outside the file** | **0 / 45** |

A row whose file duration is unknown is reported as *unchecked*, never as
*in bounds*.

### 1.5 The report says so

The corrected markdown packet carries a section titled **"Correction to the
previous packet (schema v1 → v2)"** that states in plain words that the
previous field name was misleading and has been corrected, and shows both
durations in the per-row detail.

---

## 2. Defect 2 — the 10 unlocatable quarantine rows had no identity

### 2.1 What was wrong

All 10 `unlocatable_quarantine` rows carried an **empty** `source_span_id`, and
two `(video_id, guru_id)` pairs repeated (`tCWfCISvo5k` ×2, `7UuDjBiHrMA` ×2) —
so neither the span id nor the pair identified a row. A quarantine row that
cannot be identified cannot be reviewed, cannot be excluded by id and cannot be
reconciled with anything.

### 2.2 The fix — the identity was *recovered*, not invented

Every one of the 10 Phase-3 quarantine rows carries `live_source_span_id` — the
exact live v10 span identity — and **all 10 are distinct**. Option 1 of the
brief therefore applies: the live identity is recovered from the authoritative
input, never guessed from text or derived from a coordinate.

Each tier row (schema `first-person-corpus-tier-v2`) now carries:

| field | value |
|---|---|
| `source_span_id` | the recovered live span id |
| `source_span_id_namespace` | `live_corpus_v1` |
| `rebuilt_source_span_id` | `null` (the span was never reconstructed) |
| `quarantine_record_id` | deterministic sha256 over every available evidence field + the input record hash |
| `identity_status` | `recovered` (10/10) — `unresolved` when no live id exists |
| `identity_resolution_reason` | why the id was recovered, or why it could not be |
| live provenance | `live_parent_unit_id`, `live_start_ms`, `live_end_ms`, `live_word_start`, `live_word_end`, `live_source_text_hash`, `live_transcript_hash`, `live_corpus_version`, `source_span_index`, `turn_id`, `turn_index`, `previous_span_id`, `next_span_id`, `locator_start_token`, `locator_end_token`, `locator_similarity`, `timed_transcript_path/sha256`, `timed_alignment_sha256`, `timed_asr_model`, `timed_asr_aligned_extent_ms` |
| `source_row_number` | the 1-based row number in the Phase-3 quarantine file |
| `input_record_sha256` | sha256 of the canonical JSON of that input row |

**Are these 10 records known live spans?** **Yes.** All ten correspond to live
v10 children in the collection `first_person_v10`; what they lack is a
*reconstructed* window (the span could not be located in the authoritative
word-timed artifact), not an identity. That is why `rebuilt_source_span_id` is
`null` while `source_span_id` is populated. The ten are quarantined for a
missing window and missing evidence — not for a missing identity.

If a future row has no live id, it is marked `identity_status: unresolved`,
`source_span_id: null`, and still gets a deterministic `quarantine_record_id`.

---

## 3. Defect 3 — the deterministic-ID collision was hidden, not a duplicate

### 3.1 What was wrong (and the earlier wording that was wrong)

The previous report called the difference between 1,127 variant rows and 1,126
distinct rebuilt ids a *"byte-identical duplicate"*. **That was incorrect.** The
two rows are **not** byte-identical, and they are **not** a duplicate: they are
two **different live spans** that produced the **same** rebuilt id.

| live source span id | source span index | live word window | rebuilt word window | locator similarity |
|---|---:|---|---|---:|
| `3c4862e8d4c36aee1211215171a662516bbedb20b2120dc8326a818deb1a13a8` | 77 | 2284–2307 | **2284–2301** | 0.700000 |
| `8a330f28575000c1e3de668e0819655de21f58bca6b0fd9fdcf34afed34630d5` | 76 | 2263–2284 | **2284–2301** | 0.736842 |

Both are video `MmiI3xo5Ju4`, guru `krishnaji`, transcript hash
`23e384a0…`, and both produced rebuilt id
`b7d1c4a06dccace5e689ab7a18d7f0668b4fadebb972bdab62f0ccb34063c6d9`.

The tier builder deduplicated on that id and **kept one row and dropped the
other**. The tier count therefore reconciled against `inputs − 1` and the
corpus looked healthy while an identity was ambiguous. That is the defect.

### 3.2 Root cause — measured, not assumed

The rebuilt id is

```
sha256(guru_id | video_id | corpus_version | word_start | word_end | transcript_hash)
```

— a function of the **reconstructed word window only**. It has **no component
for the source span identity**.

The four candidate causes were distinguished by what the colliding members
*agree* and *disagree* on (the classification is computed from the rows, not
hard-coded):

| candidate cause | verdict | evidence |
|---|---|---|
| incorrect normalization | **no** | 1 normalization version (`fp-norm-unicode-v1`) across both members |
| input artifact conflict | **no** | 1 timed-transcript artifact hash (`23e384a0…`) across both members |
| insufficient coordinates | the *symptom*, not the cause | the members' **live** windows differ (2284–2307 vs 2263–2284); their **rebuilt** windows are identical by construction |
| **incomplete deterministic-id namespace** | **YES** | 1 distinct rebuilt-id window, 2 distinct live source span ids |

### 3.3 The fix

* The tier builder detects duplicate rebuilt ids **per id namespace** and
  **never** dedupes.
* **Every** member of a collision is quarantined — none is kept, none is
  dropped.
* A dedicated collision record carries all colliding inputs:
  `audits/evidence/public_release_phase4_deterministic_id_collisions_2026-10-22.jsonl`
  (sha256 `cd6e91785d52628bf2dfcdb3539f17d6596a986f2caf0e261872c301195553a4`).
* The variant tier is **one row per source span** (1,125 rows, 1,125 distinct
  rebuilt ids).
* New tier `deterministic_id_collision_quarantine` (2 rows, one per colliding
  source span), each with its own `quarantine_record_id` and the live span id.
* Collision counts appear in **every** summary and manifest.
* The upstream Phase-3 builder was hardened the same way: it used to keep the
  first candidate row and quarantine the later one, and it did not check the
  variant population at all. It now quarantines every member of a collision.

### 3.4 No namespace fix — and why

Adding the source-span identity to the id namespace would re-key **every**
span in the corpus. That invalidates the 1,600 Phase-2 verdicts (keyed by the
current rebuilt ids), the rights join, the tier manifests and the pinned
local-review contract. That is **not** backward-compatible, so per the brief
**no namespace change was made** and the collision is recorded as
**`resolution_status: unresolved`** with both spans out of every serving tier.

The Phase-3 artifact set was **not** regenerated (the collision was already
visible in the shipped Phase-3 quarantine manifest — both members are present —
so nothing was hidden, and re-running Phase 3 needs the external ASR artifacts
and would invalidate every pinned hash downstream). This is recorded as an open
item in `docs/PRODUCT_OPPORTUNITIES.md`.

---

## 4. Recomputed tier arithmetic — reconciles with nothing hidden

| tier | before | after | rule |
|---|---:|---:|---|
| `local_review_candidate` | 1,529 | **1,529** | exact reconstruction **and** Phase-2 `verified` **and** confirmed rights |
| `review_required` | 71 | **71** | 45 speaker-label conflicts + 26 `refused_below_cosine_floor` |
| `variant_candidate` | 1,126 | **1,125** | reconstruction is not exact — one row per **source span** |
| `unlocatable_quarantine` | 10 | **10** | not located in the ASR artifact; identity **recovered** |
| `deterministic_id_collision_quarantine` | — | **2** | two distinct source spans, one rebuilt id |
| **total rows** | 2,736 | **2,737** | = 1,600 candidate + 1,137 quarantine |

### 4.1 The reconciliation, stated as arithmetic

| quantity | value |
|---|---:|
| Phase-3 candidate rows in | 1,600 |
| Phase-3 quarantine rows in | 1,137 |
| **Phase-3 total rows in** | **2,737** |
| **total rows out** | **2,737** |
| **rows dropped** | **0** |
| **rows deduplicated** | **0** |
| **total unique live source span ids** | **2,737** |
| total unique rebuilt ids | 2,736 (the one collision) |

**2,737 is the live v10 child count.** The old 2,736 hid exactly one row.

### 4.2 Duplicate ids at every identity level

| identity level | duplicate groups | detail |
|---|---:|---|
| rebuilt `source_span_id` | **1** | `b7d1c4a0…` × 2 — the collision, both members quarantined |
| live `live_source_span_id` | **0** | every row is one distinct live span |
| `quarantine_record_id` | **0** | every quarantine row is individually addressable |
| `(video_id, guru_id)` | 411 | *not* an identity — many spans legitimately share one video |

### 4.3 Other counts the brief asked for

| count | value |
|---|---:|
| rights-pending assets (whole universe) | **1** (`pending_owner_review`: Curly Tales `iKkySU5r_x8`) |
| rights-pending assets (inside the candidate) | **0** |
| rights-pending spans | **0** (1,572 `confirmed_channel_owner` + 28 `confirmed_video_owner`) |
| speaker-conflict count | **45** |
| deterministic-id collisions | **1** (2 members) |
| public-verified claim | **false** |

### 4.4 Artifact hashes

| artifact | rows | sha256 |
|---|---:|---|
| `public_release_phase4_tier_local_review_candidate_2026-10-22.jsonl` | 1,529 | `078ac11c2884488dd2803bc0263e6c7a95e943cf324d46292cc7ca1fa7eb5784` |
| `public_release_phase4_tier_review_required_2026-10-22.jsonl` | 71 | `dc40cef05cfda61fb11d050eda5c7bd10543abd9c16b8dc1a41d732726a1a462` |
| `public_release_phase4_tier_variant_candidate_2026-10-22.jsonl` | 1,125 | `ffd7543ddc30f88d17d699140d953a04d39c45696478cc6fb52e3baf2449de52` |
| `public_release_phase4_tier_unlocatable_quarantine_2026-10-22.jsonl` | 10 | `d18ce82f8f4868c686bda1a8f5628c928df6058fa49e1edea34b04f04d11514a` |
| `public_release_phase4_tier_deterministic_id_collision_quarantine_2026-10-22.jsonl` | 2 | `4031d1152de4132fb3705983c5b6b038a46da8b17bd7493f9a9b90357b42c1a9` |
| `public_release_phase4_deterministic_id_collisions_2026-10-22.jsonl` | 1 | `cd6e91785d52628bf2dfcdb3539f17d6596a986f2caf0e261872c301195553a4` |
| `public_release_phase4_tiers_manifest_2026-10-22.json` | — | `894024e77767341983c9a6da12220b9bb16df4ad1b55df522dd7fa2a2a0a2267` |
| `public_release_phase4_tiers_summary_2026-10-22.json` | — | `84996c45952a0a10d60208aa75a29556897251194088d3a96960e785cbedaec5` |

---

## 5. The owner-only preview inside Docker

### 5.1 What was actually wrong with the container

The route was **not** missing from the container — `backend/app` is bind-mounted
and the router is registered. The 404 was the **designed fail-closed
behaviour**: `FIRST_PERSON_LOCAL_REVIEW_ENABLED` was unset, so the route
refused.

The real blocker for an in-container test was elsewhere: the pinned artifacts
live at the **repository root** (`audits/evidence/`), the image does not contain
them, and the contract's artifact paths are repository-relative. With the flag
on and no artifacts present, the mode would have refused to start with
*"pinned artifact is missing"*.

### 5.2 The compose change

`backend/docker-compose.yml`:

* `../audits:/app/audits:ro` — the immutable evidence tree, **read-only** (the
  container must never be able to rewrite the evidence it is checked against).
* `./config:/app/backend/config:ro` — the contract pins
  `backend/config/first_person_serving_contract.json` by its repository-relative
  path, so the container needs the same path shape the host has.
* `FIRST_PERSON_LOCAL_REVIEW_ROOT=/app` — the contract derives `repo_root` as
  `contract.parent.parent.parent`, which is `/` inside the image.
* `FIRST_PERSON_LOCAL_REVIEW_ENABLED=${FIRST_PERSON_LOCAL_REVIEW_ENABLED:-false}`
  — **the default stays false**; enabling it is an explicit act at
  `compose up` time.

### 5.3 Before / after state

Frozen by `backend/scripts/ops/capture_public_release_defectfix_state.py`
(read-only: `docker inspect / ps / images / volume ls`, Qdrant `GET
/collections` + `/aliases`, Redis `PING` + `DBSIZE` only).

| item | before | after |
|---|---|---|
| container id | `ffe848b9ebfab620…` | `918f6fd51e503720…` |
| image id | `sha256:57f07e071de5d3ab9…` | `sha256:9be4056ba63636b6d…` |
| container started | `2026-10-22T06:18:18Z` | `2026-10-22T07:23:43Z` |
| container health | healthy | healthy |
| Qdrant `first_person` alias | `first_person → first_person_v10` | **unchanged** |
| Qdrant `first_person_v10` points | 4,197 (green) | **4,197 (green)** |
| Docker volumes | 3 named + bind mounts | **identical list** |
| Redis `PING` / `DBSIZE` | (host had no `redis-cli`; container probe) | `PONG` / `255`, **no flush, no write** |
| harness flag (container) | `false` | `false` |
| harness flag (`backend/.env`) | `false` | `false` |
| local-review flag (container) | unset | `true` (local only) |
| local-review flag (`backend/.env`) | unset | **unset** (default stays off) |

### 5.4 The four refusals, verified **inside** the container

`backend/scripts/ops/verify_fp_local_review_route_isolation.py` runs the real
route through FastAPI's TestClient with the settings patched in-process (the
container's own environment is never mutated). Exit code **0**.

| configuration | expected | observed |
|---|---|---|
| flag on, local | serves | **200** |
| flag **off**, local | refuses | **404** `local_review_mode_disabled` |
| flag on, **production** | refuses | **404** `local_review_mode_refuses_production` |
| flag off, production | refuses | **404** `local_review_mode_disabled` |

### 5.5 The route works inside Docker

```
GET  /api/first-person/local-review/status  → available: true
POST /api/first-person/local-review/query   → status: review_candidate, 1 citation
```

The response metadata reports `qdrant_reads: 0`, `qdrant_writes: 0`,
`alias_changes: 0`, `redis_operations: 0`, `excluded_speaker_conflicts: 45`,
`excluded_deterministic_id_collisions: 1`.

### 5.6 The public route is unchanged and still abstains

```
POST /api/first-person/query → status: abstained, citations: 0, error: serving_contract_violation
```

That is the same state as before the rebuild: the B4 serving contract fails the
legacy path closed **by itself** outside production (it does not take the app
down).

### 5.7 The rebuild command (exact)

```bash
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend
FIRST_PERSON_LOCAL_REVIEW_ENABLED=true \
  bash ../scripts/docker-safe.sh docker compose up -d --build --no-deps backend
```

Only the `backend` service was rebuilt and recreated. **No volume was purged.**

---

## 6. The label

The canonical owner-only label is two lines, and it is one constant:

```
REVIEW CANDIDATE — NOT PUBLIC RELEASE
AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION
```

It appears in:

| surface | where |
|---|---|
| CLI output | `fp_local_review_preview.py` — banner on `--status`, on every answer, and above **every citation** |
| structured metadata | `metadata.review_label` (one `\n`-joined string) and `metadata.review_label_lines` (two entries) |
| HTTP route | the query response metadata and the `…/status` endpoint, **including the 404 refusal body** |
| citation metadata | `citation.review_label` and `citation.review_label_lines` — a citation copied out of the response still says what it is |
| owner documentation | `docs/FIRST_PERSON_OWNER_TEST_GUIDE_2026-10-22.md` §0 and §2 |

A contract that pins a **different** label is treated as a stale contract and
the mode **refuses to start** — the label cannot drift.

The preview still: uses only the exact `local_review_candidate` tier; excludes
the 45 conflicts; excludes rights-pending assets; excludes the variants; excludes
the unlocatable rows; **and now excludes the deterministic-id collision**; uses
no LLM-authored teaching text; preserves the crisis / distress / harm /
prompt-injection / cross-guru / out-of-corpus rails; and fails closed on a
missing or stale manifest hash.

---

## 7. Owner decision packets (ready, **not** approved)

| packet | path | size |
|---|---|---:|
| Rights (B5) | `audits/evidence/public_release_owner_packet_rights_2026-10-22.md` | 751 assets, per-asset URL + rightsholder + permission basis |
| Speaker (45 conflicts) | `audits/evidence/public_release_owner_packet_speaker_2026-10-22.md` | 45 rows, all scores/calibration/model/audio hashes, corrected durations |
| Variant (1,127 rows) | `audits/evidence/public_release_owner_packet_variant_2026-10-22.md` | all 1,127 source rows + the collision record + the three choices |
| Clinician (distress boundary) | `audits/evidence/public_release_owner_packet_clinician_2026-10-22.md` | 15 measured affected cases + 3 options |
| Gold label (B7) | `audits/evidence/public_release_owner_packet_gold_label_2026-10-22.md` | 303 rows × 2 sheets, 299-label gate, blank speaker-certification cells |

Every decision field, signature and date in every packet is **empty**. The agent
approved nothing.

The clinician packet measures the distress gap live rather than quoting an old
note: **15 of the 150** synthetic on-topic gold questions reach `MODERATE` or
above (14 `MODERATE`, 1 `SEVERE`) on a single emotion keyword, and each is
listed with its question id, level and detected signals. The packet states that
the boundary **must not** be tuned without clinician review.

---

## 8. Commands run and real exit codes

| # | Command | Exit | Result |
|---|---|---:|---|
| 1 | `py_compile` on every changed/new Python file | **0** | compiles |
| 2 | `build_fp_speaker_conflict_review.py … --out-*_v2_… --supersedes-*` | **1** | 45 conflicts, **0/45 out of bounds** (release-blocking by design) |
| 3 | `build_fp_corpus_tiers.py …` | **1** | 1,529 / 71 / 1,125 / 10 / 2, **2,737 rows**, 1 collision, 10 identities recovered |
| 4 | `build_fp_local_review_contract.py …` | **0** | contract written with **7** pinned hashes (6 + the collision artifact) |
| 5 | `build_fp_owner_decision_packets.py …` | **0** | 5 packets written, no decision field filled |
| 6 | `run_fp_local_review_smoke_matrix.py …` | **0** | **19 / 19** cases passed |
| 7 | `fp_local_review_preview.py --status` | **0** | mode starts, **1,529** spans pinned |
| 8 | `capture_public_release_defectfix_state.py … --label before-rebuild` | **0** | before-state written |
| 9 | `docker compose up -d --build --no-deps backend` | **0** | image built, container recreated |
| 10 | `capture_public_release_defectfix_state.py … --label after-rebuild` | **0** | after-state written |
| 11 | `verify_fp_local_review_route_isolation.py` (inside the container) | **0** | 404 / 404 / 200 / 404 — all as required |
| 12 | `pytest tests/test_fp_speaker_conflict_packet_schema.py` | **0** | **8 passed** |
| 13 | `pytest tests/test_fp_quarantine_identity.py` | **0** | **7 passed** |
| 14 | `pytest tests/test_fp_deterministic_id_collision.py` | **0** | **6 passed** |
| 15 | `pytest tests/test_fp_tier_reconciliation.py` | **0** | **4 passed** |
| 16 | `pytest tests/test_fp_corpus_tiers.py` | **0** | **13 passed** |
| 17 | `pytest tests/test_first_person_local_review.py` | **0** | **38 passed** |
| 18 | `pytest tests/test_first_person_serving_contract.py` | **0** | **20 passed** |
| 19 | `pytest tests/test_fp_rights_register.py` | **0** | **11 passed** |
| 20 | Phase-2 regression `tests/test_regenerate_v10_span_ecapa_verdicts.py` | **0** | **49 passed** |
| 21 | Phase-3 regression `tests/test_rebuild_v10_asr_coordinates.py` | **0** | **24 passed** |
| 22 | reconciliation `tests/test_reconcile_v10_ecapa_verdicts.py` | **0** | **28 passed** |
| 23 | repository layout `tests/test_repo_layout.py` | **0** | **5 passed** |
| 24 | `ruff check` on all changed/new Python files | **0** | clean |
| 25 | `git diff --check` | **0** | clean |
| 26 | **full backend suite** `pytest tests/ -q` | **0** | **10,891 passed**, 25 skipped, 2 deselected, 3 xfailed, **0 failed** (166.23 s) |

> Pre-existing lint debt, **not** touched: `backend/scripts/ops/build_first_person_context_index.py`
> (an untracked peer file) has one `F401`. It is outside this change's scope.

The full suite grew from **10,858** to **10,891** (+33 new tests) with **0
failures**.

---

## 9. Mutations

**None of the forbidden kinds.**

| surface | mutations |
|---|---|
| Qdrant | **0 writes.** The only Qdrant calls were `GET /collections` and `GET /aliases`. No upsert, no delete, no payload update, no collection creation, no snapshot, no alias change. `first_person → first_person_v10`, 4,197 points, status `green` — identical before and after. |
| Redis | **0 mutations.** Only `PING` (`PONG`) and `DBSIZE` (255) were issued. **No `FLUSHALL`, no `FLUSHDB`, no write command.** The preview's own metadata reports `redis_operations: 0`. |
| Alias | **0 changes.** |
| Environment | The **public harness was not enabled** (`false` before and after, in `backend/.env` and in the container). The **local-review flag was turned on in the local container only**, by an explicit env var at `compose up` time; `backend/.env` and `.env.example` still carry the default `false`. |
| Docker | 1 image build + 2 recreations of the **backend service only**. **No volume purge, no volume mutation, no `docker system prune`, no other service touched.** |
| Git | **0 operations.** No `reset`, `clean`, `checkout`, `stash`, `add`, `commit` or `push`. `git status` and `git diff --check` only. |
| Railway / production | **0.** Railway stays paused. |
| Dependency lock | **unchanged.** `backend/requirements.txt` and `backend/requirements.lock` were not touched; every new tool is standard-library only. |
| Live collection ids | **unchanged.** No live Qdrant id was modified. The namespace fix was deliberately **not** applied. |

---

## 10. What this work does **not** prove

* It does not make the corpus public. The public route still abstains with
  **zero citations**.
* It does not certify any speaker attribution. The FAR/FRR behind the Phase-2
  verdicts is a **relative** consistency measurement on held-out videos, not a
  human-certified false-accept rate.
* It does not sign off the rights register.
* It does not resolve the deterministic-id collision — it makes it **visible**
  and **quarantined**.
* It does not repair the video-level teacher label for the 11 videos whose
  label contradicts the voice in 45 spans.
* It does not change the distress boundary.
* It does not create a Qdrant test collection. The file-backed preview remains
  the safest user-test path.
* A clean local test run means *the mechanism works and the evidence chain is
  intact*. It does not mean the corpus is ready for the public.

---

## 11. Remaining owner decisions

| # | decision | packet |
|---|---|---|
| 1 | Approve the rights register for `fp-context-transcript-v2` (B5) | `public_release_owner_packet_rights_2026-10-22.md` |
| 2 | Decide each of the 45 speaker-label conflicts + certify human speaker labels (B7) | `public_release_owner_packet_speaker_2026-10-22.md`, `…_gold_label_…` |
| 3 | Decide the variant tier: rebuild from a single voted layer, retain as non-serving, or exclude permanently | `public_release_owner_packet_variant_2026-10-22.md` |
| 4 | Clinician decision on the distress boundary (B6) | `public_release_owner_packet_clinician_2026-10-22.md` |
| 5 | Human gold labels (299) + inter-annotator agreement | `public_release_owner_packet_gold_label_2026-10-22.md` |
| 6 | Final staging/production authorisation — **after** 1–5 | — |

Plus two technical owner calls that the agent deliberately did not make:

* **Deterministic-id namespace:** approve a corpus-version bump that re-keys
  the corpus and re-runs Phase 2 → Phase 3 → rights → tiers → contract, or
  accept the two colliding spans as permanently excluded.
* **Phase-3 artifact regeneration:** the hardened Phase-3 builder has not been
  re-run; the shipped Phase-3 manifests predate the hardening.

---

## 12. Artifact index

**New / regenerated evidence**

```
audits/evidence/public_release_phase4_tier_local_review_candidate_2026-10-22.jsonl
audits/evidence/public_release_phase4_tier_review_required_2026-10-22.jsonl
audits/evidence/public_release_phase4_tier_variant_candidate_2026-10-22.jsonl
audits/evidence/public_release_phase4_tier_unlocatable_quarantine_2026-10-22.jsonl
audits/evidence/public_release_phase4_tier_deterministic_id_collision_quarantine_2026-10-22.jsonl
audits/evidence/public_release_phase4_deterministic_id_collisions_2026-10-22.jsonl
audits/evidence/public_release_phase4_tiers_manifest_2026-10-22.json
audits/evidence/public_release_phase4_tiers_summary_2026-10-22.json
audits/evidence/public_release_phase4_speaker_conflicts_v2_2026-10-22.jsonl
audits/evidence/public_release_phase4_speaker_conflict_review_v2_2026-10-22.md
audits/evidence/public_release_phase4_speaker_conflict_summary_v2_2026-10-22.json
audits/evidence/public_release_phase5_smoke_matrix_v2_2026-10-22.json
audits/evidence/public_release_phase5_smoke_matrix_v2_2026-10-22.md
audits/evidence/public_release_defectfix_state_before_2026-10-22.json
audits/evidence/public_release_defectfix_state_after_2026-10-22.json
audits/evidence/public_release_owner_packet_rights_2026-10-22.md
audits/evidence/public_release_owner_packet_speaker_2026-10-22.md
audits/evidence/public_release_owner_packet_variant_2026-10-22.md
audits/evidence/public_release_owner_packet_clinician_2026-10-22.md
audits/evidence/public_release_owner_packet_gold_label_2026-10-22.md
```

**Retained, not overwritten (the superseded v1 speaker-conflict artifacts)**

```
audits/evidence/public_release_phase4_speaker_conflicts_2026-10-22.jsonl
audits/evidence/public_release_phase4_speaker_conflict_review_2026-10-22.md
audits/evidence/public_release_phase4_speaker_conflict_summary_2026-10-22.json
```

**Code**

```
backend/scripts/ops/build_fp_corpus_tiers.py                    (modified)
backend/scripts/ops/build_fp_speaker_conflict_review.py          (modified)
backend/scripts/ops/build_fp_local_review_contract.py            (modified)
backend/scripts/ops/rebuild_v10_asr_coordinates.py               (modified)
backend/scripts/ops/fp_local_review_preview.py                   (modified)
backend/scripts/ops/build_fp_owner_decision_packets.py           (new)
backend/scripts/ops/capture_public_release_defectfix_state.py    (new)
backend/scripts/ops/verify_fp_local_review_route_isolation.py    (new)
backend/services/first_person_local_review.py                    (modified)
backend/app/api/first_person_local_review.py                     (modified)
backend/config/first_person_local_review.json                    (regenerated)
backend/docker-compose.yml                                       (modified)
```

**Tests**

```
backend/tests/test_fp_speaker_conflict_packet_schema.py          (new, 8)
backend/tests/test_fp_quarantine_identity.py                     (new, 7)
backend/tests/test_fp_deterministic_id_collision.py               (new, 6)
backend/tests/test_fp_tier_reconciliation.py                     (new, 4)
backend/tests/test_fp_corpus_tiers.py                            (modified, 13)
backend/tests/test_first_person_local_review.py                  (modified, 38)
backend/tests/test_rebuild_v10_asr_coordinates.py                (modified, 24)
```

**Documentation**

```
AGENTS.md                                                        (modified)
lessons.md                                                       (modified — 5 new lessons + 1 correction)
docs/PRODUCT_OPPORTUNITIES.md                                    (modified — open items)
docs/FIRST_PERSON_OWNER_TEST_GUIDE_2026-10-22.md                 (modified — label + Docker)
.claude/tasks/first-person-v10-defect-fixes-and-owner-test-rebuild-2026-10-22.md  (new)
```

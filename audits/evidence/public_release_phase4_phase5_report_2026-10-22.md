# First-person v10 — Phase 4/5 evidence report (independent rights register, corpus tiers, B4 isolation, owner-only test mode)

**Date:** 2026-10-22
**Plan:** `.claude/tasks/first-person-v10-public-release-plan-2026-10-21.md`
**Overall public-release verdict after this run:** **NO-GO — unchanged.**
`FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false` in `backend/.env` **and** inside the
running container. The public `first_person` alias still points at
`first_person_v10`. Nothing was written to Qdrant, Redis, an alias, the
environment, Docker or Railway.

**What this run adds:** an independent rights register (B5), a deterministic
quarantine for the 45 contradictory speaker labels, explicit corpus tiers, a
real B4 schema-isolation gate, and an **owner-only, isolated, file-backed test
mode** that lets the owner exercise the experience without exposing unreviewed
attribution and without weakening a single safety or provenance gate.

---

## 1. Phase 0 — state frozen before any change

Machine-readable: `audits/evidence/public_release_phase4_phase5_state_2026-10-22.json`
(produced by the read-only `backend/scripts/ops/capture_public_release_phase0_state.py`).

| Item | Value |
|---|---|
| HEAD / `origin/main` | `6183326ff1de430d23e587a9d05a8bca4acd7a2f` (both) |
| Branch | `main` |
| Dirty / untracked files | 402 (pre-existing peer work; **not touched**) |
| Harness flag — `backend/.env` | `false` |
| Harness flag — running container | `false` |
| `FIRST_PERSON_COLLECTION` / `FIRST_PERSON_CONTEXT_COLLECTION` | `first_person_v10` / `first_person_v10` |
| Qdrant first-person collections | `first_person_v10` — 4,197 points, 2,737 indexed vectors, status `green` |
| Qdrant aliases | `first_person → first_person_v10` |
| Docker | `mukthiguru-backend` (up 9 h, healthy), `mukthiguru-qdrant` (v1.18.0), `mukthiguru-redis` (7-alpine) and the rest of the 11-container stack |
| Redis | `NOAUTH Authentication required` — **no read and no write was attempted** |
| Phase-2 verdict index sha256 | `cef4c80eeca217c5a908848774a047b2a6f185a0403e9b505094593f409d0f73` |
| Phase-3 candidate sha256 | `5806658e5a714aba88902202508fb6f3db027eb6b8e8944e226d00c5545114bc` |
| Phase-3 quarantine sha256 | `3f4b64fd75a0e9fd9572d2db8dbd1fd17225d0b66f14373dbd72e8fce7991700` |

---

## 2. Workstream A — independent rights register (B5)

**The rule this implements:** a payload flag is a *derived* claim; a rights
basis is a *human* decision. The register is built from
`docs/rights/CONTENT-RIGHTS.md` — the human-authored registry — and from
ingest-time channel metadata. **No rights field is ever read out of a Qdrant
payload.**

| Artifact | Path | sha256 |
|---|---|---|
| Rights manifest (751 assets) | `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json` | `f8920335b4ef88ac…` |
| Rights join (1,600 candidate spans) | `audits/evidence/public_release_phase4_rights_join_2026-10-22.jsonl` | `4288355cce1287a1…` |
| Rights quarantine (0 rows) | `audits/evidence/public_release_phase4_rights_quarantine_2026-10-22.jsonl` | `e3b0c44298fc1c14…` (empty) |
| Rights summary | `audits/evidence/public_release_phase4_rights_summary_2026-10-22.json` | `ab13093a99754da5…` |
| Human-readable B5 report | `audits/evidence/public_release_phase4_rights_report_2026-10-22.md` | `99fb6dedbe9bb0d7…` |
| Builder | `backend/scripts/ops/build_fp_rights_register.py` | — |
| Tests | `backend/tests/test_fp_rights_register.py` — 11 | — |

### 2.1 Evidence model

| Source | Authority | What it may prove |
|---|---|---|
| `docs/rights/CONTENT-RIGHTS.md` | **human_authored_owner_decision** | That the owner confirmed a channel/video basis |
| corpus `channels.json` | `ingest_time_metadata_only` | Which channel uploaded a video (never that use is permitted) |
| `backend/scripts/ops/build_first_person_index.py::CLEARED_*` | `engineering_input_only_not_a_rights_decision` | That the *builder* treated a channel as cleared — **never** a confirmation |

A registry row confirms an asset **only when its owner-confirmation marker is
on the same markdown table row**. If the registry is edited, re-ordered, or a
row loses its marker, that entry stops confirming and the affected assets
quarantine. All four declared entries applied against the shipped registry:

* `channel:sri-preethaji-krishnaji-ekam` — *"Sri Preethaji & Sri Krishnaji" / "Ekam / O&O Academy"*, owner-confirmed 2026-09-23;
* `channel:times-now` — *"Times Now"*, owner-confirmed 2026-09-23;
* `video:TqxxCYnAxo8` — *TEDx / Sri Preethaji*, owner-confirmed 2026-09-26;
* `video:UlOt31lBhLY` — *MarieTV / Sri Preethaji & Sri Krishnaji*, owner-confirmed 2026-09-26.

### 2.2 Exact counts

| Rights status | Assets (whole first-person universe) | Assets (inside the candidate) | Candidate spans | Servable |
|---|---:|---:|---:|---|
| `confirmed_channel_owner` | 702 | 445 | 1,572 | yes |
| `confirmed_video_owner` | 2 | 2 | 28 | yes |
| `pending_owner_review` | 1 | 0 | 0 | **no** |
| `missing_evidence` | 46 | 0 | 0 | **no** |
| **total** | **751** | **447** | **1,600** | |

The single `pending_owner_review` asset is `iKkySU5r_x8` (Curly Tales): the
corpus builder clears it per-video, the rights registry does not confirm it.
It is not in the candidate, so no candidate span is affected — but the rule is
live and enforced.

The 46 `missing_evidence` assets are videos whose channel is `UNKNOWN` /
unattributed. They are outside the candidate as well.

### 2.3 What is still open

**B5 is NOT closed.** The register is complete and independent, but:

1. the owner has **not signed off this register** for the
   `fp-context-transcript-v2` corpus (`register_owner_confirmation:
   pending_owner_review`);
2. every confirmation is the owner's *statement* recorded in the registry — no
   agent can verify it independently (repo rule N9);
3. the registry's own review cadence is annual and the candidate corpus was
   ingested after the last confirmation;
4. the Times Now basis is a **third-party broadcaster's** content, which the
   registry records as a restriction note.

The build exits **1** (release-blocking) while any of that stands.

---

## 3. Workstream B — the 45 contradictory speaker labels

| Artifact | Path | sha256 |
|---|---|---|
| Conflict rows (45) | `audits/evidence/public_release_phase4_speaker_conflicts_2026-10-22.jsonl` | `85a28f96c2c7f075…` |
| Human review packet | `audits/evidence/public_release_phase4_speaker_conflict_review_2026-10-22.md` | — |
| Summary | `audits/evidence/public_release_phase4_speaker_conflict_summary_2026-10-22.json` | `f10083892bb19287…` |
| Builder | `backend/scripts/ops/build_fp_speaker_conflict_review.py` | — |
| Tests | `backend/tests/test_fp_corpus_tiers.py` — 13 (includes the conflict package) | — |

Each row carries: source span id, video id, expected/corpus teacher,
ECAPA-predicted teacher, cosine, runner-up cosine, margin, the cosine floor
and margin threshold, the audio window (`audio_start_ms`/`audio_end_ms`), the
**audio file sha256**, the model revision, the calibration revision, the run
id, the transcript hash, the source text hash, the corpus version, the word
range, the reason code, a **recommended** review action, and empty
`review_decision` / `reviewer` / `reviewed_at_utc` fields for a human.

* **45 conflicts across 11 videos.** 40 `krishnaji→preethaji`, 5
  `preethaji→krishnaji`. 25 of the 45 are in one video (`MmiI3xo5Ju4`).
* **Nothing is relabelled.** The package records the conflict; it never
  rewrites the video label, the speaker or the guru. The recommended action
  explicitly says so.
* **Playback references** are provided two ways: the archived WAV path plus its
  sha256, and a YouTube URL that starts at the same offset. The review packet
  is a markdown table with an empty decision column.
* The 45 spans are **not admitted** to any serving tier (§4) and the local
  review service re-checks the conflict list at citation time, so even a
  tampered tier file cannot serve one.

---

## 4. Workstream C — explicit corpus tiers

| Artifact | Path | sha256 |
|---|---|---|
| Tier 1 — `local_review_candidate` (1,529) | `audits/evidence/public_release_phase4_tier_local_review_candidate_2026-10-22.jsonl` | `dfdb1a0454cfe9a2…` |
| Tier 2 — `review_required` (71) | `audits/evidence/public_release_phase4_tier_review_required_2026-10-22.jsonl` | `f8a5953095d34dd8…` |
| Tier 3 — `variant_candidate` (1,126) | `audits/evidence/public_release_phase4_tier_variant_candidate_2026-10-22.jsonl` | `f7c34f5b093946cb…` |
| Tier 4 — `unlocatable_quarantine` (10) | `audits/evidence/public_release_phase4_tier_unlocatable_quarantine_2026-10-22.jsonl` | `ea39d1c689822dc7…` |
| Tiers manifest (pins every tier file) | `audits/evidence/public_release_phase4_tiers_manifest_2026-10-22.json` | `0f1f234a68af6f3a…` |
| Tiers summary | `audits/evidence/public_release_phase4_tiers_summary_2026-10-22.json` | `0e666e8a4a8ee19e…` |
| Builder | `backend/scripts/ops/build_fp_corpus_tiers.py` | — |
| Tests | `backend/tests/test_fp_corpus_tiers.py` — 13 | — |

| Tier | Count | Rule | Servable |
|---|---:|---|---|
| `local_review_candidate` | **1,529** | exact Phase-3 reconstruction **and** Phase-2 verdict `verified` **and** confirmed rights | owner-only test mode only |
| `review_required` | **71** | 45 speaker-label conflicts + 26 `refused_below_cosine_floor` | never |
| `variant_candidate` | **1,126** | reconstruction is not exact (transcript/text variants) | never, by default |
| `unlocatable_quarantine` | **10** | `span_not_located_in_asr` — no derived id, no window, no evidence | never |
| **total** | **2,736** | 1,600 candidate + 1,137 quarantine rows − 1 byte-identical duplicate | |

Two counts worth stating plainly:

* **The 26 below-floor refusals are quarantined too.** The brief only named
  the 45 conflicts, but a `refused_below_cosine_floor` verdict is not a
  *passing* speaker verdict, and the serving rule requires every citation's
  speaker verdict to pass. They are therefore in `review_required`, not in the
  candidate tier.
* **The variant tier holds 1,126 rows, not 1,127.** The shipped Phase-3
  quarantine manifest contains one byte-identical duplicate row
  (`b7d1c4a0…`, video `MmiI3xo5Ju4`, words 2284–2301). The tier builder
  deduplicates deterministically and reports the removal
  (`duplicate_quarantine_rows_removed: 1`). The 1,127 number in the Phase-2
  report refers to *rows*, and this report refers to *distinct spans*.

**Naming.** Tier 1 is deliberately **not** called "public verified". Its name
is `local_review_candidate` and its evidence policy is
`automated_evidence_candidate`: the attribution behind it is automated
evidence, not human certification. `public_verified_claim: false` is recorded
in the tiers summary.

---

## 5. Workstream D — B4: legacy and context serving contracts are separated

| Artifact | Path |
|---|---|
| Contract module | `backend/services/first_person_serving_contract.py` |
| Declared contract | `backend/config/first_person_serving_contract.json` |
| Startup wiring | `backend/app/main.py` (lifespan) |
| Request-path gate | `backend/services/first_person_pipeline.py` (`_serving_contract_error`, `_collection_contract_components`) |
| Cache-fingerprint components | `backend/services/first_person_pipeline.py` (`_serving_policy_components`) |
| Tests | `backend/tests/test_first_person_serving_contract.py` — 20 |

### 5.1 The defect it closes

`FIRST_PERSON_COLLECTION=first_person_v10` points the **legacy** clip store at
the **fp-context** collection. The legacy path filters on
`first_person_eligible`, a field the fp-context-v1 schema does not carry, so
the two paths disagreed about what a record is. The declared contract now
records, per collection: its payload schema, its role, its corpus version, the
payload fields the path requires, and the evidence policy it may assert.

### 5.2 The gate's scope

The gate is armed for the **real** serving path: a real `FirstPersonStore`, or
any store pointed at a collection named `first_person*` / `fp_context*`. A
stand-in store in a unit test — one that names nothing like a first-person
collection and cannot read a real collection — is not gated. This scope was
found the hard way: the first version gated *every* undeclared collection and
turned **102** existing tests into `abstained / serving_contract_violation`
(see `lessons.md` → `L-FP-V10-PHASE5-GATE-MUST-NOT-FIRE-ON-TEST-DOUBLES-1`).
"Fail closed" must mean *the deployment path refuses*, not *every object in
the process refuses*.

### 5.3 What fails closed, and where

| Condition | Production | Non-production |
|---|---|---|
| Legacy store points at an fp-context collection | **startup raises** | the first-person path serves **nothing** (`abstain_reason=serving_contract_violation`); the application keeps running |
| Context store points at a legacy-only collection | **startup raises** | startup raises **when the context harness is enabled** |
| Both stores share one collection | **startup raises** | path-scoped refusal |
| Collection not declared in the contract | **startup raises** | path-scoped refusal |
| Required payload fields absent from the contract entry | contract file is rejected (startup raises in production) | same |
| Corpus version / evidence policy missing | **startup raises** | path-scoped refusal |
| Cache fingerprint missing collection / schema / corpus version / evidence policy | **startup raises** | same |

**Why the legacy path does not take the whole application down outside
production.** The blast radius of a first-person mis-configuration is the
first-person path, not the product. The path already served nothing in this
configuration (the legacy filter matched zero records); the change makes that
behaviour *explicit and logged* instead of accidental. In production the
whole deployment stops, because a deployment that cannot state which schema
it serves must not take traffic at all.

### 5.4 Cache fingerprint

`_serving_policy_fingerprint` was split into
`_serving_policy_components()` (the inputs) + the digest, and four inputs were
added: `legacy_collection`, `legacy_schema`, `legacy_corpus_version`,
`evidence_policy`. A repointed collection, a schema change, a corpus-version
change or an evidence-policy change now re-keys the exact cache instead of
replaying an answer computed under a different contract.

* **Consequence:** the 24 h exact cache is invalidated by this change. That is
  intended — the old entries were keyed without the contract.
* The abstain vocabulary gained one deliberate value,
  `serving_contract_violation` (`backend/app/metrics.py`,
  `FIRST_PERSON_ABSTAIN_REASONS`). The enum is pinned by
  `tests/test_rp_batch_2026_10_13.py`, so the test was updated in the same
  change — this is a deliberate schema change, not a drive-by.

---

## 6. Workstream E — the owner-only, isolated test mode

**Design choice: option 1 from the brief — a file-backed candidate preview
that reads the immutable candidate manifests directly and does not mutate
Qdrant.** No disposable collection was needed, so there was nothing to
snapshot, nothing to roll back and nothing to alias.

| Artifact | Path |
|---|---|
| Service | `backend/services/first_person_local_review.py` |
| HTTP route | `backend/app/api/first_person_local_review.py` (`POST /api/first-person/local-review/query`, `GET …/status`) |
| CLI preview | `backend/scripts/ops/fp_local_review_preview.py` |
| Pinned contract | `backend/config/first_person_local_review.json` |
| Settings | `backend/app/config.py` (`first_person_local_review_enabled`, `…_contract_path`, `…_root`) |
| Tests | `backend/tests/test_first_person_local_review.py` — 30 |

### 6.1 Isolation properties (all asserted by tests)

| Property | How it is enforced |
|---|---|
| No Qdrant read / write / alias | the service module imports no Qdrant client at all; the metadata reports `qdrant_reads: 0`, `qdrant_writes: 0`, `alias_changes: 0` |
| No Redis | the exact cache is in-process; the cache key carries the artifact hashes |
| No LLM-authored teaching text | the answer is the concatenation of stored span texts; `llm_generated_answer: false` is reported and asserted |
| Local-only flag | `FIRST_PERSON_LOCAL_REVIEW_ENABLED=true` **and** `IS_PRODUCTION=false`; otherwise the route returns 404 |
| Refuses to start on a missing artifact | every pinned artifact must exist |
| Refuses to start on a stale/modified artifact | every pinned artifact's sha256 must match |
| Serves only the candidate tier | the contract pins `tier: local_review_candidate`; a different tier is rejected at load time |
| Excludes the 45 conflicts | the conflict artifact is pinned and re-checked per citation |
| Excludes rights-pending spans | the rights join is pinned and re-checked per citation |
| Excludes the variants and the unlocatable | they are not in the pinned tier file |
| Citations only when the evidence all verifies | text hash, source span id, audio window, speaker verdict and rights status are each re-checked against the pinned artifacts |
| Honest label | `"review candidate / not public release"` on every response |
| Evidence logging | evidence policy, corpus version, collection and every artifact hash are logged and returned |
| Crisis / distress rails preserved | the deterministic topic rail (`match_blocked_topic`) plus the helpline redirect; a Serene Mind distress assessor can be injected by the route |
| Cross-guru and out-of-corpus abstain | a request for one teacher with a question naming the other abstains (`cross_guru_conflict`); a question whose vocabulary is largely absent abstains (`out_of_corpus_query`) |

### 6.2 Retrieval honesty

The preview index is a **deterministic lexical BM25 index** over the candidate
text: no embedding model, no network, no index server, and the same query
always produces the same ranking — which is what makes an owner test
reproducible and reviewable. It is **not** the production dense retriever, so
ranking quality is not a release signal. The guide says so explicitly.

### 6.3 Pinned artifacts (the mode refuses to start if any of these changes)

| Artifact | sha256 |
|---|---|
| Phase-4 tiers manifest | `0f1f234a68af6f3a…` |
| Phase-4 tier-1 file | `dfdb1a0454cfe9a2…` |
| Phase-2 verdict index | `cef4c80eeca217c5…` |
| Phase-4 rights manifest | `f8920335b4ef88ac…` |
| Phase-4 rights join | `4288355cce1287a1…` |
| Phase-4 speaker conflicts | `85a28f96c2c7f075…` |
| B4 serving contract | `5cfbcf1a4b4c2709…` |

### 6.4 How to run it

```bash
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8

# zero-infrastructure preview
backend/.venv/bin/python backend/scripts/ops/fp_local_review_preview.py --status
backend/.venv/bin/python backend/scripts/ops/fp_local_review_preview.py "What is meditation?"

# optional HTTP surface (host only — the image has no audits/evidence/)
cd backend
FIRST_PERSON_LOCAL_REVIEW_ENABLED=true IS_PRODUCTION=false \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8077
```

Full guide: `docs/FIRST_PERSON_OWNER_TEST_GUIDE_2026-10-22.md`.

---

## 7. Workstream F — the owner testing guide

`docs/FIRST_PERSON_OWNER_TEST_GUIDE_2026-10-22.md` covers: how to start and
stop the mode, how to verify the environment is test-only, 15 supported query
classes (direct on-topic, per-guru, cross-guru, Indic, multi-span, follow-up,
out-of-corpus, prompt injection, self-harm, harm-to-others, moderate
distress), exact-cache hit/miss, stale-cache invalidation, audio playback
verification, the expected abstentions and what each one means, how to file a
bug report (request id, query, route, evidence policy, citation, timestamp),
and how to shut down and roll back.

It states, in the first section, that this is not a public release, that the
attribution is automated evidence rather than human certification, that no
sensitive user data should be entered, that crisis situations must use
professional or emergency support, and that test results must not be
interpreted as clinical advice.

---

## 8. Workstream G — the smoke matrix

Machine-readable: `audits/evidence/public_release_phase5_smoke_matrix_2026-10-22.json`
Human-readable: `audits/evidence/public_release_phase5_smoke_matrix_2026-10-22.md`
Runner: `backend/scripts/ops/run_fp_local_review_smoke_matrix.py`

**19 / 19 cases matched their expected result.**

| # | Case | Expected | Observed |
|---|---|---|---|
| S01 | Direct on-topic — Preethaji | review_candidate, Preethaji citations | ✅ |
| S02 | Direct on-topic — Krishnaji | review_candidate, Krishnaji citations | ✅ |
| S03 | Names Preethaji | review_candidate, Preethaji only | ✅ |
| S04 | Names Krishnaji | review_candidate, Krishnaji only | ✅ |
| S05 | **Cross-guru request** | abstained (`cross_guru_conflict`), 0 citations | ✅ |
| S06 | Indic (Devanagari), no translator | abstained — the pinned corpus is English-only | ✅ |
| S07 | Indic (Devanagari) with the labelled matrix stub translator | review_candidate | ✅ |
| S08 | Multi-span context query | review_candidate, distinct videos | ✅ |
| S09 | Follow-up query | review_candidate | ✅ |
| S10 | **Unrelated technical question** | abstained (`out_of_corpus_query`), 0 citations | ✅ |
| S11 | **Prompt injection** | abstained (`topic_blocked`), 0 citations | ✅ |
| S12 | **Self-harm crisis** | crisis_redirect with helplines, 0 citations | ✅ |
| S13 | **Harm-to-others intent** | crisis_redirect, 0 citations | ✅ |
| S14 | Moderate distress | review_candidate, no clinical claim | ✅ |
| S15 | **Exact-cache hit** | first miss, then hit | ✅ |
| S16 | **Stale-cache policy invalidation** | the artifact hash is in the cache key | ✅ |
| S17 | **Missing-artifact startup refusal** | the mode refuses to start | ✅ |
| S18 | **Stale-manifest refusal** | the mode refuses to start | ✅ |
| S19 | **Citation audio playback verification** | every citation has an ordered, non-empty window | ✅ |

Every case records: route, test mode, abstain state, whether an LLM generated
answer text, citation count, exact source text/hash match, source span ids,
audio start/end, speaker verdict, rights status, corpus/schema version,
evidence policy, latency, error status, and expected versus observed result.

S17 and S18 are proven against **temporary copies** of the contract, so the
real pinned artifacts are never touched.

---

## 9. Commands run and real exit codes

Every command below was run from the repository root unless stated, with the
real exit code.

| # | Command | Exit | Result |
|---|---|---|---|
| 1 | `backend/.venv/bin/python -m py_compile` on all six new/changed Python files | **0** | compiles |
| 2 | `backend/.venv/bin/python backend/scripts/ops/build_fp_rights_register.py …` | **1** | report produced; release-blocking (B5 open) |
| 3 | `backend/.venv/bin/python backend/scripts/ops/build_fp_speaker_conflict_review.py …` | **1** | 45 conflicts quarantined |
| 4 | `backend/.venv/bin/python backend/scripts/ops/build_fp_corpus_tiers.py …` | **1** | review / variant / unlocatable tiers populated |
| 5 | `backend/.venv/bin/python backend/scripts/ops/build_fp_local_review_contract.py …` | **0** | contract written with 6 pinned hashes |
| 6 | `backend/.venv/bin/python backend/scripts/ops/run_fp_local_review_smoke_matrix.py …` | **0** | 19 / 19 cases passed |
| 7 | `backend/.venv/bin/python backend/scripts/ops/fp_local_review_preview.py --status` | **0** | mode starts, 1,529 spans pinned |
| 8 | determinism: two full builder runs into the same directory, `shasum -a 256` on all 13 artifacts | **0** | **all byte-identical** |
| 9 | `backend/.venv/bin/python -m pytest tests/test_fp_rights_register.py …` (`backend/`) | **0** | **11 passed** |
| 10 | `backend/.venv/bin/python -m pytest tests/test_fp_corpus_tiers.py …` (`backend/`) | **0** | **13 passed** |
| 11 | `backend/.venv/bin/python -m pytest tests/test_first_person_local_review.py …` (`backend/`) | **0** | **30 passed** |
| 12 | `backend/.venv/bin/python -m pytest tests/test_first_person_serving_contract.py …` (`backend/`) | **0** | **19 passed** |
| 13 | Phase-2 / Phase-3 / reconciliation regression (`backend/`) | **0** | **101 passed** |
| 14 | `backend/.venv/bin/python -m pytest tests/test_repo_layout.py …` (`backend/`) | **0** | 5 passed |
| 14b | `backend/.venv/bin/python -m pytest tests/test_settings_guards.py …` (`backend/`) | **0** | 5 passed — the env-read chokepoint rule |
| 15 | `backend/.venv/bin/python -m ruff check` on the new/changed files (`backend/`) | **0** | clean |
| 16 | `git diff --check` (repo root) | **0** | clean |
| 16b | focused first-person suite, 13 modules (`backend/`) | **0** | 370 passed, 1 skipped |
| 17 | `backend/.venv/bin/python -m pytest tests/ -q …` (`backend/`) — full suite | **0** | see §10 |

Exit-code contract of the new builders: **0** = produced and nothing blocking;
**1** = produced and **release-blocking** (the ordinary outcome here); **2** =
no trustworthy report (unreadable input, a structural violation, a duplicate
identity key) — fail closed.

---

## 10. Test counts

| Suite | Result |
|---|---|
| New focused tests (this run) | **74 passed** (11 rights + 13 tiers/conflicts + 30 local review + 20 serving contract) |
| Phase-2 / Phase-3 / reconciliation regression | 101 passed |
| Repository layout | 5 passed |
| Settings guards (env-read chokepoint) | 5 passed |
| Focused first-person suite, 13 modules | 370 passed, 1 skipped |
| **Full backend suite** | **10,858 passed**, 25 skipped, 2 deselected, 3 xfailed, **0 failed** (exit 0, 162.24 s) |

---

## 11. Mutations

**None.**

* **Qdrant reads:** 0 by the new tools. The Phase-0 state recorder performed
  a read-only census (`GET /collections`, `GET /aliases`).
* **Qdrant writes:** 0. No upsert, no delete, no payload update, no
  collection creation, no snapshot, no alias change.
* **Alias changes:** 0. `first_person → first_person_v10` before and after.
* **Redis:** 0 reads, 0 writes, 0 flushes (`NOAUTH` — nothing was attempted).
* **Environment:** 0 changes. `backend/.env` and the container still carry
  `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false`. The local review mode is
  **off by default** and is switched on only by an explicit env var at
  run time.
* **Docker:** 0 image builds, 0 container recreations, 0 volume operations.
* **Git:** no `reset`, no `clean`, no `checkout`, no `stash`, no commit, no
  push. `git diff --check` and `git status` only.
* **Railway / deployment:** 0. Railway stays paused.
* **Dependency lock:** unchanged. `backend/requirements.txt` and
  `backend/requirements.lock` were not touched; the new tools are
  standard-library only and the new service imports nothing new.

```
No Qdrant write.
No alias change.
No Redis mutation.
No harness enablement.
No deployment.
No Railway action.
No git operation.
```

---

## 12. What Phase 4 and Phase 5 do **not** prove

1. **The rights basis is the owner's statement, not independent verification.**
   No agent can verify it (repo rule N9).
2. **The speaker evidence is automated.** The trial labels come from the two
   human-confirmed anchor moments, so the measured 0/262 FAR and 0/262 FRR are
   a *relative consistency* measurement on held-out videos, **not** a
   human-certified false-accept rate. Human speaker labelling (B7) is still
   open.
3. **The margin gate is an ordering gate**, not a separation gate.
4. **The preview's ranking is lexical.** A good owner test proves the
   mechanism and the evidence chain; it does not prove retrieval quality.
5. **The corpus is a bounded slice.** 1,529 of 2,737 v10 children are in the
   candidate tier; the live collection still carries its defective Phase-3
   coordinates, and the `first_person` alias still points at it.
6. **The distress boundary was not touched.** B6 remains open, and a moderate
   distress question may still receive a clip — that is the known, documented
   gap, and it is why the guide says the results are not clinical advice.
7. **A local preview is not production evidence.** No capacity, no warm/cold
   profile, no dependency-fault injection, no staging retest.

---

## 13. Blocker status after Phase 4/5

| Blocker | Status |
|---|---|
| **B1** per-span ECAPA evidence | **Measured and closed for the candidate** (Phase 2). The remaining item is human certification (B7). |
| **B2** citation ↔ audio window | Fixed **in the candidate only** (Phase 3). The live collection is untouched. |
| **B3** deterministic span-id coordinates | Fixed **in the candidate only** (Phase 3). The live collection is untouched. |
| **B4** legacy / context schema separation | **Implemented and tested** (§5). The legacy path now fails closed explicitly; the live configuration is still a legacy→fp-context mismatch, so the legacy path serves nothing on purpose rather than by accident. A legacy-schema collection (`first_person_v8`) is declared as the rollback target but does not exist in the local Qdrant. |
| **B5** independent rights register | **Register built and independent** (§2). **Still open**: the owner has not signed off this register for the candidate corpus. |
| **B6** clinician review of the distress boundary | **Open.** Nothing was tuned. |
| **B7** human gold labels + human speaker labels + public-scale evidence | **Open.** |
| The 1,127 transcript variants | **Open.** Quarantined in `variant_candidate`; admitting them needs a separate, explicit owner decision. |
| The 10 unlocatable spans | Quarantined permanently unless the authoritative artifact changes. |

**Overall: NO-GO.** The harness stays disabled. The public alias is unchanged.
Owner-only local testing is available.

---

## 14. Public sources used for design justification

These sources justify design choices only. They are **not** proof that this
repository is safe; the repository's own evidence and human review remain
authoritative.

* [NIST Speaker Recognition Evaluation](https://www.nist.gov/itl/iad/mig/speaker-recognition)
  — a speaker-recognition claim needs an explicit evaluation plan and
  calibration-oriented measurement, not one unqualified score. This is why the
  Phase-2 FAR/FRR is labelled a relative consistency measurement and why B7
  still requires human labels.
* [NIST OSAC Speaker Recognition Evaluation Metrics](https://www.nist.gov/video/osac-speaker-recognition-evaluation-metrics)
  — target-trial normalisation and defined metric sets; the reason the
  Phase-2 calibration reports positive/impostor trial counts and a
  measured floor rather than a single threshold.
* [SRI trial-based calibration with a reject option](https://www.sri.com/wp-content/uploads/2021/12/toward_fail-safe_speaker_recognition_trial-based_calibration_with_a_reject_option.pdf)
  — a reject option must be calibrated from trials; this is the model the
  cosine floor and margin threshold follow, and the reason the 26
  below-floor refusals are quarantined rather than served with a warning.
* [Qdrant pre-migration baseline](https://qdrant.tech/documentation/migration-guidance/pre-migration-baseline/)
  and [Qdrant migration fundamentals](https://qdrant.tech/documentation/faq/qdrant-fundamentals/)
  — collection isolation and versioned corpora; this is why the candidate
  declares `fp-context-transcript-v2`, why the legacy and context stores are
  contract-separated, and why no collection write was attempted at all.
* [WHO ethics and governance of AI for health](https://www.who.int/publications/i/item/9789240029200)
  — accountability, human oversight and governance for health-adjacent AI;
  why the owner-only mode is gated, labelled and reversible, and why the
  guide forbids clinical reading of the results.
* [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework)
  — lifecycle risk management; why the evidence chain is pinned, hashed and
  re-verified at request time instead of trusted once at build time.
* [NVIDIA / Label Studio human audio-labeling workflow](https://developer.nvidia.com/blog/generating-high-quality-labels-for-speech-recognition-with-label-studio-and-nemo/)
  and [Label Studio](https://github.com/HumanSignal/label-studio) — the
  human-in-the-loop labelling pattern; the 45-conflict review packet follows
  it (audible window, explicit decision field, reviewer, timestamp) and B7's
  gold-label set is the same shape of work.
* [Speaker-verification score calibration toolkit](https://github.com/alumae/sv_score_calibration)
  — score calibration is a separate, fitted artefact; this is why the
  calibration revision is pinned into every verdict and into the serving
  evidence chain.

---

## 15. Artifact index

| Artifact | Path | sha256 (first 16) |
|---|---|---|
| Phase-4/5 state | `audits/evidence/public_release_phase4_phase5_state_2026-10-22.json` | — |
| Rights manifest | `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json` | `f8920335b4ef88ac` |
| Rights join | `audits/evidence/public_release_phase4_rights_join_2026-10-22.jsonl` | `4288355cce1287a1` |
| Rights quarantine | `audits/evidence/public_release_phase4_rights_quarantine_2026-10-22.jsonl` | `e3b0c44298fc1c14` |
| Rights summary | `audits/evidence/public_release_phase4_rights_summary_2026-10-22.json` | `ab13093a99754da5` |
| Rights report (B5, human) | `audits/evidence/public_release_phase4_rights_report_2026-10-22.md` | `99fb6dedbe9bb0d7` |
| Speaker conflicts | `audits/evidence/public_release_phase4_speaker_conflicts_2026-10-22.jsonl` | `85a28f96c2c7f075` |
| Speaker conflict review packet | `audits/evidence/public_release_phase4_speaker_conflict_review_2026-10-22.md` | — |
| Speaker conflict summary | `audits/evidence/public_release_phase4_speaker_conflict_summary_2026-10-22.json` | `f10083892bb19287` |
| Tier 1 — `local_review_candidate` | `audits/evidence/public_release_phase4_tier_local_review_candidate_2026-10-22.jsonl` | `dfdb1a0454cfe9a2` |
| Tier 2 — `review_required` | `audits/evidence/public_release_phase4_tier_review_required_2026-10-22.jsonl` | `f8a5953095d34dd8` |
| Tier 3 — `variant_candidate` | `audits/evidence/public_release_phase4_tier_variant_candidate_2026-10-22.jsonl` | `f7c34f5b093946cb` |
| Tier 4 — `unlocatable_quarantine` | `audits/evidence/public_release_phase4_tier_unlocatable_quarantine_2026-10-22.jsonl` | `ea39d1c689822dc7` |
| Tiers manifest | `audits/evidence/public_release_phase4_tiers_manifest_2026-10-22.json` | `0f1f234a68af6f3a` |
| Tiers summary | `audits/evidence/public_release_phase4_tiers_summary_2026-10-22.json` | `0e666e8a4a8ee19e` |
| Smoke matrix (machine) | `audits/evidence/public_release_phase5_smoke_matrix_2026-10-22.json` | — |
| Smoke matrix (human) | `audits/evidence/public_release_phase5_smoke_matrix_2026-10-22.md` | — |
| Command/exit-code transcript | `audits/evidence/public_release_phase4_phase5_verification_2026-10-22.txt` | — |
| Local-review contract | `backend/config/first_person_local_review.json` | — |
| B4 serving contract | `backend/config/first_person_serving_contract.json` | `5cfbcf1a4b4c2709` |
| Owner test guide | `docs/FIRST_PERSON_OWNER_TEST_GUIDE_2026-10-22.md` | — |
| This report | `audits/evidence/public_release_phase4_phase5_report_2026-10-22.md` | — |

# State reconciliation — 2026-09-27

Independent re-check of the 2026-09-27 handoff (`~/Downloads/CLAUDE_HANDOFF_NEXT_PHASE_2026-09-27.md`)
and `SESSION_HANDOFF_2026-09-27.md`. Every number below was re-measured this session;
commands are at the bottom. Where this file and older notes disagree, this file wins
until re-measured.

## Runtime (local Docker, measured 2026-09-27)

| Item | Value | Source |
|---|---|---|
| Live first-person collection | `first_person_v2` (280 points, 37 videos) | `docker exec mukthiguru-backend env` |
| `FIRST_PERSON_SERVE_UNREGISTERED` | `true` locally (serves 72 rights-false clips in v2) | root `.env:156` — dev only, must be `false` in any deploy |
| Qdrant aliases | none | `GET /aliases` — rollback is by collection name, not alias |
| Live reranker | ONNX `temsa/mmarco-mMiniLMv2-L12-H384-v1` (multilingual) | `RERANKER_BACKEND=onnx_int8`; `RERANKER_MODEL` in env is unused on this backend |
| `first_person_v4` | 580 points, **38** videos, all `rights_cleared=true`, point IDs identical to v1 and to the dry-run `--dump-ids` | Qdrant scroll |

`first_person_v4` was already written (it is a shadow collection; nothing is aliased to it).
v2 and v4 are different segmentations: only 113 point IDs overlap.

## Corpus counts — reconciled

Two inventories exist and use different definitions:

- `scripts/ingestion/corpus_inventory.json` (repo): **rights + empty-segment** view. 657 `cleared` (all with segments) + 88 `unconfirmed` (all empty) = 745.
- `~/mukthiguru_attribution_data/full_corpus_inventory/inventory.json`: **pipeline-stage** view. 45 `done` + 526 `to_asr` + 128 `excluded_short` + 46 `excluded_rights` = 745.

Cross-tab (pipeline status × repo rights × segments):

| pipeline status | repo rights | segments | count |
|---|---|---|---:|
| done | cleared | yes | 45 |
| to_asr | cleared | yes | 515 |
| to_asr | unconfirmed | empty | 11 |
| excluded_short | cleared | yes | 97 |
| excluded_short | unconfirmed | empty | 31 |
| excluded_rights | unconfirmed | empty | 46 |

Corrections:

1. **The 46 "excluded_rights" are not a rights decision.** All 46 have channel `UNKNOWN`; 45 are `quality_state=unavailable` (removed/private on YouTube), 1 dead-lettered. Label them `unavailable`, not rights-excluded.
2. **"45 videos indexed" mixes two sets.** The pilot build discovered 50 videos: the 45 corpus `done` videos + 5 bake-off videos that are **not in the 745 corpus** (`NFlAszNFZdQ`, `TqxxCYnAxo8` TEDx, `UlOt31lBhLY` MarieTV, `hUmlujE6SN0`, `rGcNJ_Nsuy8`). All 5 quarantined videos are corpus `done` videos. So 40 corpus + 5 bake-off = 45 "indexed", and only **38** of them produced any clip.
3. **526 `to_asr` includes 11 videos with no segments** — confirm these have downloadable audio before counting them as ASR work.
4. 580 = unique clip points after parent/child collapse (1,055 pre-collapse).
5. **UNRESOLVED — reproducibility:** the script that wrote `full_corpus_inventory/inventory.json` (statuses `done`/`to_asr`/`excluded_*`) is in neither the repo nor the data folder, so that inventory cannot be regenerated. Recreate it in `backend/scripts/ops/` before relying on its counts.

## Retrieval: v2 (live) vs v4 (candidate), same 116 pinned bake-off questions

In-process `FirstPersonPipeline.execute()`, no profile, no cache, bake-off `scoring_lib` scorer
(scratch script, not in repo). 83 strict answerable questions.

| | v2 (live) | v4 (candidate) |
|---|---:|---:|
| top-1 strict | 0.446 | 0.410 |
| top-1 host-voice leak | 7.8% | **15.5%** |
| p50 / p95 retrieval ms | 6.3 / 47.3 | 6.1 / 6.8 |

Paired: top-1 discordant 11 (v2 only) vs 8 (v4 only) — not significant. Host leak discordant
5 vs 14 — v4 roughly doubles host leakage (sign test p≈0.06). **Do not promote v4.**
Caveat: the bake-off questions are not a held-out set; this is a relative comparison only.
`weak_match` returns one clip, so top-3/MRR cannot be measured through the pipeline.

## Claims in older notes that do not hold

| Claim | Finding |
|---|---|
| "Indic rescue of core doctrine terms is essential" | Removed. A keyword like "beautiful state" is in most of the corpus, so it accepted off-topic docs for any Indic query. Rescue now requires multilingual rerank ≥ 0.40 (unmeasured threshold). Tests: `tests/test_grade_documents_crosslingual.py` (incl. false-positive and English-never-rescued cases). |
| "Idle night drives phi to 10 and trips the breaker" | Not reproducible from `services/health_monitor.py`: phi is recomputed only on heartbeat arrival, after stamping it, so the measured gap is ~0. Only 3 consecutive failures open it. Pinned by `tests/test_health_monitor_idle.py`. The φ detector therefore never detects silence at all — it is effectively inert. |
| "speaker_verified propagated end to end" | Plumbing exists, but nothing produces `True` (voice verification is not wired into ingest) and the frontend never maps `speaker_verified` → `speakerVerified`, so the badge cannot render. Schema description corrected. |
| "first_person_live_eval PASS = production-ready" | Top-1 0.43–0.45. PASS means the gates it checks passed, not that retrieval is good. |
| Benchmark "p95 86.28s PASS", error rate 38.3% | Not re-run this session. A fresh, unresumed run is still required. |

## Fixed later on 2026-09-27

- **Short-clip gate** (`build_first_person_index.py`, `MIN_CLIP_DURATION_S = 8.0`, `--min-clip-seconds`). Root cause of v4's host leak: v4 is sentence-level (median 7 s / 17 words, 174 of 580 clips under 4 s) vs v2 passage-level (median 21 s / 51 words). Short fragments carry unreliable speaker labels and out-rank answers by resembling the question. Read-only simulation (HasIdCondition-restricted queries, same RRF/dedup as served) on the 116 bake-off questions:

  | gate | v2 top-1 / host | v4 top-1 / host |
  |---|---|---|
  | none | 0.434 / 7.8% | 0.398 / 15.5% |
  | ≥ 8 s | 0.446 / 6.0% | 0.434 / 10.3% |

  Only the 8 s gate lowered host leak in both without losing top-1. Chosen on the bake-off set (not held out) — re-check on B1 gold. Dry run with the gate: 260 clips (612 short dropped pre-collapse). Nothing written to Qdrant.
- **Run-to-run noise:** identical configs moved top-1 by one question (±0.012) between runs, so differences under ~0.03 on 83 questions are noise.
- **`broken` crisis false positive fixed** (`serene_mind_engine.py`): SEVERE only for self-description ("I feel/am broken", "broken inside", "a broken person"); bare "broken" is MODERATE. Tests in `tests/test_serene_mind.py`; red-team tier-3 32/32 pass; distress/crisis/first-person tests 485 pass.
- **Third-party rights per video:** TEDx / MarieTV cleared by video id only (`CLEARED_VIDEO_IDS`), not channel-wide.
- **Helplines:** owner confirmed the Tele-MANAS test call (2026-09-26). The loader now warns about every unverified entry, not only when all are unverified.
- Verified: 0 of the 88 dead-letter videos are in any first-person collection.

## first_person_v5 (built 2026-09-27, owner-approved shadow write)

260 points (164 preethaji / 96 krishnaji), all clips >= 8 s, all rights-cleared, hash-verified, IDs == dry run. Nothing aliased or served.
Live in-process A/B, 116 bake-off questions, 2 runs each: v2 top-1 0.446/0.422, host proxy 8.6%; **v5 0.398/0.398, 11.2%**; v4 0.398, 15.5%.
Paired sign test v2 vs v5: p=0.48 / 0.82. **Do not promote v5.** The read-only gate simulation (0.434) did not reproduce live.

**Unresolved — vector reproducibility.** v5's point set equals v4's >=8 s subset, yet stored vectors differ (cos 0.98–0.99 v4 vs v5), and neither equals a fresh re-embed of the same `verbatim_text` on host (0.99) or in the container (0.98). Ruled out: batch dependence (identical alone/in-batch), backend flag (both `onnx_int8`), Qdrant quantization/datatype (float32, none), `upsert_clips` transforms (none). Consequence: two "identical" builds differ by 2–4 top-1 questions, so A/B gaps below ~0.05 on 83 questions are not evidence. Pin encoder model files + runtime version and record them in the build report before the next comparison.

## Distress LLM second opinion (built, flag OFF)

`DistressStage._maybe_llm_downgrade_severe` (`distress_llm_downgrade_enabled=False`): only regex-SEVERE, only with no prior distress, dedicated one-word prompt, lowers to MODERATE only on an exact "TOPIC"; timeout/error/anything else keeps SEVERE. Not built on `classify_distress_structured`: that method's failure fallback returns `is_distress: False`, and its `confidence` means P(distress), so reusing it would have turned outages into downgrades. 16 unit tests.
Live eval (OpenRouter, 3 runs): lowers all 4 benign SEVERE questions ("give up coffee", "no point in meditating"...). But on all tier-2/3 scenario turns it answered TOPIC for romanized-Kannada suicidal ideation "nanage badukalu ishta illa" (2/3 runs; regex CRISIS, so never consulted in production) and Marathi work stress. Only **1** scenario turn is regex-SEVERE, so safety in the SEVERE band is unproven. **Keep OFF** until a SEVERE-band set (incl. Indic/romanized) of real-distress messages shows 0 TOPIC, and a clinician signs off.

Also fixed: `DistressStage._detect_distress` returned `None` when the distress engine raised or was missing, which silently **skipped crisis pre-emption**; it now falls back to the regex stage (tests in `tests/test_distress_llm_downgrade.py`).

## Found by the v5 subagent

- The running container started before the `broken` regex fix and has no `--reload`, so live responses still use the old pattern until the backend restarts.
- `services/text_quality_filter.py:195` (`find_artifact`) flags genuine rhetorical repetition as an ASR loop, quarantining 2 real teacher clips from `UlOt31lBhLY` in both v2 and v5. Proposed: require 3+ repeats with no new content in between. Not changed.

## Found, not fixed (needs owner decision)

- **Build `first_person_v5`** with the 8 s gate (a Qdrant write — needs explicit approval), then A/B it against v2 before any switch.
- **Native-speaker review** of the multilingual crisis patterns and crisis copy (unchanged).

## Commands

```bash
# collections + live config
curl -s localhost:6333/collections; curl -s localhost:6333/aliases
docker exec mukthiguru-backend env | grep FIRST_PERSON
# tests touched this session
cd backend && .venv/bin/pytest -q tests/test_grade_documents_crosslingual.py tests/test_health_monitor_idle.py tests/test_run_calibration.py tests/test_citation_contract.py tests/test_build_first_person_index.py
npx vitest run src/test/citation-contract.test.tsx
```

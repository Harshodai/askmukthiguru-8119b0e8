# First-Person Production Hardening Plan — 2026-09-28 (rev 2, grilled)

Rev 2 replaces rev 1's Phase 6, which contained defects found by checking it
against code, data and upstream repos (see "Rev 1 corrections"). Numbers are
labelled VERIFIED (re-run 2026-09-28) or CLAIMED (earlier doc, not re-run).

## Objective
Serve the teachers' own recorded words — right speaker, right second, whole
thought — fail-closed, without unsupported precision claims or unapproved
persistent-data writes.

## Governing constraints (non-negotiable)
- No LLM at serve time on the first-person route (CLAUDE.md FP invariant 1).
- No fabricated gold labels, quotes, timestamps, speakers, or results. AI-authored
  questions = regression smoke only, never calibration gold (FP invariant 3).
- Persistent writes: dry-run → report → snapshot → explicit owner approval → apply.
- No commit / push / deploy / collection promotion without explicit request.
- Crisis + topic rail before retrieval. No semantic cache on this route.
- Dependencies Apache-2.0 / MIT / BSD only. AGPL / GPL / CC-BY-NC rejected.
- Production fails closed on missing rights, calibration, provenance, tenant policy.

## Rev 1 corrections
| Rev 1 item | Problem | Evidence |
|---|---|---|
| 6.4 RAG-Fusion "generate 2 reformulations" per query | LLM call at serve time — violates FP invariant 1 | github.com/Raudaschl/rag-fusion README: LLM writes the rewrites |
| 6.3 `linto-ai/whisper-timestamped` | AGPL-3.0 — violates license constraint | repo license |
| 6.3 `oliverguhr/deepmultilingualpunctuation` | EN/IT/FR/DE only, no Indic; repo already ships `punctuators` `pcs_en` (Apache-2.0) | README; `backend/ingest/verbatim/punctuation.py:53-55` |
| 6.2 late chunking with BGE-M3 | Upstream supports jina-v2 models; needs token-level outputs from our ONNX INT8 export; re-embeds all 14,033 general-RAG points; outside FP scope | jina-ai/late-chunking README |
| 6.3 "Situational trap gate" (`Yasme`, `Nomi`, "addiction") | Overfit. passages_C clip `TqxxCYnAxo8_v2_p1_0` opens "Two monks, Yasmi and Nomi…" — the trap is a passages_B fragmentation artifact. Addiction is a legitimate teaching topic | `~/mukthiguru_attribution_data/pilot50_2026-09-25/passages_C/TqxxCYnAxo8.json` |
| 6.1 audit numbers | `scripts/ops/audit_first_person_v5.py` hard-codes phrases taken from the clips it scores (`portrays this`, `peter fights`, `is agitated`) — partly circular; output in `/tmp` (ephemeral) | that script, `classify_clip` |
| 6.3 "25–45 s units" | Conflicts with FP invariant 11 (18–25 s) | CLAUDE.md |
| Phase 1 "first_person_live alias" | Conflicts with FP invariant 4 ("no alias swap; new version = new collection") | CLAUDE.md |

## Root cause, measured (VERIFIED 2026-09-28)
`first_person_v5` was built from **passages_B** (old fragment-prone builder), not
the v2 sentence builder: `~/mukthiguru_attribution_data/v5_build/report_20260927T083518Z.json` → `passages_dirs`.

Generic detector `backend/ingest/verbatim/boundaries.py`, same 58 videos
(pilot50 + bakeoff), clips ≥ 8 s (v5's floor):

| Source | Clips | Clean head+tail | Median dur | After `snap_to_sentences` (min 12 words) |
|---|---|---|---|---|
| passages_B (v5 source) | 681 | 60 (8.8%) | 17.5 s | 403 survive |
| passages_C (v2 builder) | 295 | 105 (35.6%) | 30.2 s | 259 survive, ~80% clean |

- v2 already fixes tails (10/295 tail defects vs 460/681).
- Heads are the remaining defect: 159/295 v2 clips start lowercase (run begins mid-sentence at a speaker flip).
- After snap, residual ≈ 43 capitalised sentence-initial "And/So/Or" — owner policy decision.
- Measured on verbatim-text punctuation only; the `punct.json` display layer was not used in this measurement.

**Conclusion: no new segmentation engine needed. Rebuild from v2 + head snap.**

## Status carried from rev 1
- [x] Phase 0 baseline; focused FP tests 85 passed (CLAIMED).
- [ ] Full backend suite from `backend/` (NOT RUN this session; rev 1 stopped at a repo-root path failure in `test_metrics_reachability.py`).
- [x] Fail-closed production validation (`services/first_person_release.py`, uncommitted, authored by the other session).

## Work split (two sessions, one checkout — do not cross)
- Session "Session handoff and warning remediation": eval harness, disputed-word payload/gate, gold-set packet; owns `services/speaker_diarization.py`, `scripts/ops/build_first_person_index.py`, `services/first_person_pipeline.py`, `app/api/first_person.py`, `app/config.py`.
- This session: `ingest/verbatim/boundaries.py`, `tests/test_verbatim_boundaries.py`, B5 audit, C1 generator, this plan.
- Agreed 2026-09-28: other session owns B2, B3, B4 and the PCS metric (in `evaluation/first_person_harness.py`). B1 committed in `d1e9d019` on branch `fix/first-person-harness-translation-crisis-2026-09-28` (not pushed).

## Agent task cards (in order; each has acceptance)

### B1 — Boundary module [DONE, uncommitted]
- Files: `backend/ingest/verbatim/boundaries.py`, `backend/tests/test_verbatim_boundaries.py`.
- API: `boundary_defects(tokens) -> list[str]`; `snap_to_sentences(tokens, start, end, min_words=12) -> (s, e) | None`. Shrink-only. Pass `punct.json` `display_words` as `tokens` when ASR is unpunctuated — indices map 1:1 to verbatim words when `zero_change_assert_passed`.
- Acceptance (VERIFIED): `cd backend && .venv/bin/pytest -q tests/test_verbatim_*.py` → 53 passed; `.venv/bin/python -m ingest.verbatim.boundaries` → self-check OK.

### B2 — Wire snap into the index build [owner: other session]
- `build_first_person_index.py`: accept passages_C dirs; per clip, tokens = verbatim words inside `[start, end]`; sentence source = `raw/<vid>_punct.json` `display_words` when `zero_change_assert_passed`; apply `snap_to_sentences`; recompute `start_ms/end_ms` from snapped word times and `transcript_hash` from snapped verbatim text; `None` → quarantine `boundary_unrecoverable`.
- Report: snapped / unchanged / quarantined counts + residual `boundary_defects` histogram.
- Acceptance: dry-run report only, target new collection `first_person_v6`, zero writes to v5. Unit test: mid-sentence head is snapped and re-hashed; integrity gate `sha256(verbatim) == transcript_hash` still passes.

### B3 — Grow-back vs shrink [DONE — verdict: SHRINK]
- `grow_to_sentence_start` added to `boundaries.py` (tested; never crosses `O`/`?` labels). Not to be wired.
- VERIFIED (`backend/scripts/ops/measure_first_person_boundary_repair.py`, report `docs/evidence/first_person_boundary_repair_2026-09-28.json`), 295 passages_C clips ≥ 8 s, word-mapped onto `transcripts_B`:

| Method | Survive | Clean | Clean & ≥ 18 s | Words kept | Median dur |
|---|---|---|---|---|---|
| none | 295 | 92 (31.2%) | 60 | 32,121 | 29.8 s |
| shrink | 269 | 227 (76.9%) | 153 | 29,549 | 29.2 s |
| grow | 269 | 226 (76.6%) | 151 | 29,763 | 29.2 s |

- Sentence source: `display_words` aligned for only 169/295 clips (bakeoff `raw/` has 8 punct files); rest used verbatim punctuation.

### S1 — Speaker-edge precision (new root cause, found by B3)
- Of 153 mid-sentence heads, 139 have the sentence's first 1–6 words labelled `O` (90) or `?` (49), e.g. `It[O] is[O] | beyond attitudes. It is beyond positive thinking.` Hypothesis: 1.5 s speaker windows are too coarse at turn edges, so the teacher's opening words get host/unknown labels and the clip starts mid-sentence.
- HUMAN GATE: listen to `docs/evidence/first_person_speaker_edge_listening_sheet_2026-09-28.csv` (20 rows, YouTube links with timestamps, verdict column). ~10 min.
- Only if ≥ 18/20 are "teacher": implement sentence-level relabel in `ingest/verbatim/speaker_verify.label_words_by_speaker` (a ≤ 6-word `O`/`?` prefix of a sentence whose remainder is one teacher → that teacher), then re-measure. Until then abstain-by-default stands and shrink is the fix.

### B4 — Serve-time boundary guard (defense in depth)
- FP integrity gate quarantines a clip when `boundary_defects(verbatim.split())` contains `tail_no_terminal` or `head_orphan_punctuation`. No model, microseconds.

### B5 — Replace the overfit audit [DONE, uncommitted — this session]
- `backend/scripts/ops/audit_first_person_boundaries.py` (+ `tests/test_audit_first_person_boundaries.py`): `--collection` or `--passages-dir`, generic `boundary_defects`, duration buckets per invariant 11, report to `docs/evidence/`.
- Old `scripts/ops/audit_first_person_v5.py` (untracked) moved to this session's scratchpad, not deleted.
- VERIFIED: `first_person_v5` → 260 clips, 24 clean (9.23%) — same headline as the old audit, so that number stands without the circular regexes. passages_C → 295 clips, 112 clean (37.97%), head 182, tail 10. Reports in `docs/evidence/first_person_boundaries_*_2026-09-28.json`.

### C1 — Paraphrase stability without a serve-time LLM
- Generator [DONE, uncommitted — this session]: `backend/scripts/ops/generate_first_person_questions.py` (+ `tests/test_generate_first_person_questions.py`). Port of bake-off `genq.py`; adds `find_artifact()` filter; doc2query-- self-retrieval uses the real `FirstPersonStore.search_hybrid` (dense+sparse). Writes a JSON staging file only, marked UNREVIEWED; never writes Qdrant; resumable.
- VERIFIED smoke (3 v5 clips, OpenRouter 8B): 15 generated, 8 kept (53%). Needs `REDIS_URL` pointing at the authenticated local Redis, else OpenRouter's budget ledger fails closed.
- Next: run on `first_person_v6` after B2 exists (not v5 — being replaced) → human review → approved index build fills `question_dense` → add `Prefetch(using="question_dense")` → measure on human gold.
- Serve: Qdrant RRF over passage + question vectors (native, no LLM).
- Metric (undefined in rev 1): PCS = share of paraphrase groups whose 5 variants return the same top-1 `video_id`; report same-clip rate separately. 25 AI-authored queries = smoke test, not a precision ship gate.

### C2 — Human gold + calibration [human-gated]
- As rev 1 Phase 3: video-disjoint human questions; ≥299 confident items with 0 errors for 1% risk at δ=0.05; blind second annotation + kappa. Today 14 human labels → every answer stays "Related, not a direct answer".

### Rev 1 Phases 1, 2, 4, 5 — kept, with gates
- Alias promotion blocked until an ADR amends FP invariant 4.
- Duration target blocked until owner chooses (below).

## Open-source that adds real value (licenses checked 2026-09-28)
| Repo | License | Use | Status |
|---|---|---|---|
| github.com/segment-any-text/wtpsplit (SaT) | MIT (code) | Punctuation-agnostic sentence segmentation; 85 langs incl. hi/te/ta/mr/kn; ONNX-CPU | Candidate sentence source for Indic/code-mixed talks; verify HF weight license first |
| github.com/jianfch/stable-ts | MIT | Word-timestamp refinement (silence suppression), regroup by punctuation/gap | Candidate; replaces rejected whisper-timestamped |
| github.com/1-800-BAD-CODE/punctuators | Apache-2.0 | Already used (`pcs_en`); 47-lang model exists, Indic coverage unverified | In repo |
| github.com/m-bain/whisperX | BSD-2 | Already configured (`WHISPERX_*`) | In repo |
| github.com/linto-ai/whisper-timestamped | AGPL-3.0 | — | REJECTED (license) |
| github.com/oliverguhr/deepmultilingualpunctuation | MIT | — | REJECTED (no Indic, duplicate) |
| github.com/Raudaschl/rag-fusion | MIT | — | REJECTED at serve time; offline form = C1 |
| github.com/jina-ai/late-chunking | Apache-2.0 | General RAG, jina models | DEFERRED (out of FP scope) |

## Decisions needed from owner
1. Clip duration target: 18–25 s (current invariant 11) vs 25–45 s.
2. Sentence-initial "And/So/Or" after snap: reject or allow?
3. Alias for first-person (amend FP invariant 4): yes / no.
4. Approve B2 dry-run build into new collection `first_person_v6` (no v5 writes).

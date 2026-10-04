# OKF Quality Audit — 2026-10-04

**Auditor:** fresh content-audit subagent (read-only; no code/data modified).
**Scope:** `memory/okf/compiled.json` (v2, 717 entries), `memory/okf/verbatim_clusters.json`
(5 clusters), `backend/data/doctrine_lexicon.json` (7.7 MB), plus the build pipeline
(`scripts/extract_okf_from_stores.py`, `scripts/okf/compile_okf.py`,
`backend/scripts/ops/rebuild_okf_from_clips.py`, `backend/scripts/ops/build_doctrine_lexicon.py`).
**Method:** 0 LLM calls. All checks deterministic local Python (`nice -n 10`), verified
against `transcripts/<video_id>.md` cache where stated.
**Bottom line up front:** the OKF is a **genuinely clean, honestly-sourced, well-gated
draft corpus — but it is not world-class yet.** The single biggest defect is duplication:
~56% of entries have a ≥0.9-Jaccard near-twin and 32 titles are compiled twice (root +
subdirectory copies). Fix dedup + tags + review backlog and this becomes good; multilingual
parity and freshness loops are the longer road to world-class.

## 1. Rubric (derived from 2025–2026 RAG-knowledge-base literature)

Sources: EKRAG enterprise-RAG benchmark (NAACL 2025 — expert curation, freshness,
correctness/relevance/faithfulness judges); CLEAR-RAG (2026 — 5-dim production eval:
Citation, Latency/Cost, Evidence-faithfulness, Answer-relevance, Retrieval-quality);
Evidently AI RAG evaluation guide (2025 — stable curated test sets, human review of
synthetic data, reference-free faithfulness monitoring); FreshStack (NeurIPS 2025 —
recency/niche domains to avoid contamination, nugget-level support labels); RARE
(2025 — robustness to query/document perturbation, KG-driven QA synthesis with QA gates).

| # | Criterion | Score /10 | Evidence |
|---|-----------|-----------|----------|
| 1 | Schema discipline & validation | 6 | Uniform keyset on all 717 entries; all embeddings 1024d, none zero. BUT: `verified`/`generated` null on 100%, `sources` empty on 100%, `teacher` values (`sri-preethaji-and-sri-krishnaji` ×670) violate the documented `AGENTS.md` contract (`sri-preethaji`\|`sri-krishnaji`\|`both`), `type` 99% `teaching` (710/717; practice 4, reflection 2, qa 1). |
| 2 | Provenance completeness | 7 | 717/717 entries carry a YouTube URL with extractable video_id (208 distinct videos, top-3 = 29 entries — no severe concentration). Every body ends with a Source Context block (video title + URL + speaker). BUT: no per-entry timestamps, no publish dates, `source`==`resource` on 100% (redundant field), no per-quote offsets in compiled entries (only clusters have `start_seconds`). |
| 3 | Contamination screening | 9 | 0 hits for `<think>`, `Alternatively`, `Hmm`, `Let me think`, `as an AI`, `temporary connection issue`, code fences (1 benign hit in `sri-preethaji/observation_and_relationship_healing.md` — inspect before serving), frontmatter leaks. Pipeline gates `find_artifact()` at LLM-output time AND at write time AND at compile time. −1 because the "You are" pattern (10 hits) required manual inspection (all benign second-person doctrine on re-check). |
| 4 | Dedup & canonicalization | 3 | 32 exact-title duplicate pairs (same title compiled from repo-root copy AND `shared/`/`sri-preethaji/` copy, e.g. `awakening_and_freedom_from_suffering.md`); 561 pairs with body Jaccard ≥0.9; **399/717 entries (56%) have ≥1 ≥0.9 neighbor**. Caveat: Jaccard-on-word-sets is inflated by the shared 3-section template, but the exact-title doubles alone prove the compiler double-counts. Retrieval over-weights duplicated doctrine ~2×. |
| 5 | Coverage auditing | 4 | 208 videos is genuine breadth; title vocabulary centers on suffering/consciousness/observation (on-brand). BUT: teacher 93% joint + only 2 `sri-krishnaji` entries (routing filter nearly useless); tags are spam (`oneness` 672, `teaching` 668, 675/717 entries have ≤2 tags, plus literal `"None"` tag ×3); year mentions only 2017/2021/2022 (nothing ≥2023 — stale tail); 23 covid-era entries (`coronavirus/lockdown` residue). |
| 6 | Quote fidelity | 7 | Compiled `Verbatim Discourse Excerpts`: **45/45 sampled sentences exact substrings** of `transcripts/` cache. Cluster `quotes_with_provenance`: only 4/25 exact — best-window similarity 0.966 on inspection (`you are` vs `you're` contraction normalization, i.e. lightly edited, not raw verbatim). 10 entries attribute key teachings to `(Unknown speaker)`. |
| 7 | Text hygiene | 8 | 0 HTML tags, 0 mojibake, 0 `Host:/Q:` speaker-label leaks, 0 ASR filler clusters across all 717. BUT: 21 degenerate `description` fields (`'Namaste.'`, `'Break.'`, `'Open your eyes.'`, 6–17 chars) — descriptions are auto-sliced first-sentences, not summaries; `key_teachings` median 3, min 1 (thin entries exist). |
| 8 | Multilingual parity | 1 | English-only. 1/717 entries contains Indic script (`concept_of_ekam.md`). No `hi/te/kn/ta/mr` variants, no transliteration policy, despite 6 supported chat locales. |
| 9 | Human-review workflow | 3 | 820 files still sitting in `memory/okf/staging/` (unreviewed backlog exceeds the 717 compiled); `index.md`/`log.md` required by the OKF v0.1 contract do not exist; no reviewer identity/timestamp recorded on any compiled entry (`verified: null` everywhere). The pipeline correctly refuses `--auto-approve`, but there is no evidence a human ever approved what shipped. |
| 10 | Freshness & versioning | 4 | `version: 2`, uniform `status: stable`, embeddings validated 1024d at compile time. BUT: no per-entry `updated` dates, no changelog, embeddings frozen at Sep-30 compile, no scheduled re-verify loop against source videos (deletions/edits upstream would silently stale the index). |

**Total: 52/100.** World-class bar ≈ 85+. Honest label today: **strong draft corpus, not a curated knowledge base.**

## 2. Measured rates (summary)

| Check | Result |
|---|---|
| Schema key uniformity | 717/717 identical 15-key set |
| Null `verified` / `generated` | 717/717 (100%) |
| Empty `sources` list | 717/717 (100%) |
| CoT / canned-string hits | 0 |
| Prompt-echo hits (true) | 0 (10 `You are` hits all benign on inspection) |
| Exact-title dup groups | 32 groups / 64 entries |
| Jaccard ≥0.9 pairs | 561 / 256,686 (0.22%); entries affected 399/717 (56%) |
| Entries with video_id | 717/717; distinct videos 208 |
| `source`==`resource` | 717/717 |
| `(Unknown speaker)` entries | 10 |
| Compiled verbatim spot-check | 45/45 exact substrings |
| Cluster-quote spot-check | 4/25 exact (remainder ~0.97-similar, normalized) |
| HTML / mojibake / speaker-leak / ASR-filler | 0 / 0 / 0 / 0 |
| Degenerate descriptions (<25 chars) | 21 |
| Literal `"None"` tag | 3 entries |
| Indic-script entries | 1/717 |
| Staging backlog | 820 files vs 717 compiled |
| Newest year mentioned in bodies | 2022 |

## 3. Verdicts per artifact

### 3.1 `compiled.json` — GOOD-WITH-GAPS (near NOT-THERE-YET)
Content is clean and honestly extracted (45/45 verbatim-verified, zero contamination),
but the artifact double-serves duplicated doctrine and carries dead fields plus
contract-violating teacher values. Retrieval impact is real: duplicated entries split
quotes/votes and inflate popular topics.
1. **Dedup + single-source compile (M).** Compile from ONE canonical tree (teacher
   subdirs only, or root only — pick one, delete/ignore the other in
   `services/memory/compiler.py` walk), then add a cross-run content-hash gate
   (`sha256(normalized body)`) rejecting Jaccard ≥0.9 newcomers to staging.
   Effort: M.
2. **Fix schema contract (S).** Backfill `teacher` to `AGENTS.md` values, drop or
   populate `sources`/`verified`/`generated`, replace `"None"` tags, regenerate
   the 21 degenerate descriptions from the excerpt's first *substantive* sentence
   (≥40 chars). Effort: S.
3. **Retag with discriminative tags (M).** Cap auto-tags: remove `oneness`/`teaching`
   defaults, require ≥3 specific tags from the doctrine-tag extractor, store tag
   vocabulary + per-tag document frequency for audit. Effort: M.

### 3.2 `verbatim_clusters.json` — GOOD-WITH-GAPS
Deterministic, embedding-backed, provenance-carrying — the right architecture (no LLM
summarization). But all 5 quotes per cluster share one video + one timestamp (single-chunk
slicing, not multi-source synthesis), `love_relationships_otherization` contains 2
covid-lockdown quotes and 3 youth-leadership-promo quotes (off-topic), and quotes are
silently normalized while labeled verbatim.
1. **Multi-source quote rule (S).** Require ≥3 distinct `video_id`s per cluster's 5
   quotes + a topic-relevance threshold (pattern-hit density) per quote; drop/replace
   the 5 off-topic quotes flagged here. Effort: S.
2. **Label honesty (S).** Rename fields to `key_quotes` + `normalization: light`
   (document the contraction/punctuation normalization), OR store raw clip text
   byte-exact. Effort: S.
3. **Per-quote timestamps that vary (S).** Persist each quote's true clip offset
   instead of the chunk-start second; audit any cluster where all 5 offsets are
   identical. Effort: S.

### 3.3 `doctrine_lexicon.json` — GOOD-WITH-GAPS (weakest of the three)
The *design* (authority-vocabulary gate + conservative correction gates + calibration
set kept out of training) is excellent and the code is the best-documented of the four
artifacts. The *data* has a junk drawer: 572/640 `proper_nouns` (89%) are ordinary
English words also present in `general_english` (`the`, `going`, `daily`, `telegram`,
`i'm`), and `curated` overlaps `general_english` by 5,318/5,692. Low-count entries
(257 proper nouns at count 1) look like OCR/ASR fragments admitted as nouns.
1. **Purge + gate proper nouns (S).** Drop any `proper_nouns` entry present in
   `general_english` or with support <3 (the `_MIN_TARGET_SUPPORT` bar already used
   for targets), rebuild, re-run `test_doctrine_lexicon.py` calibration. Effort: S.
2. **Separate curated-doctrine from general English (S).** Split `curated` into
   `curated_doctrine` (terms NOT in general English) vs inherited vocabulary so
   reviewers can audit the doctrine-specific delta (~374 terms, human-scale).
   Effort: S.
3. **Publish calibration score in-artifact (S).** Record the
   `_CALIBRATION_SHOULD_FIX` pass rate + lexicon version + build date next to
   `built_at` so staleness is detectable at load time. Effort: S.

### 3.4 Pipeline (`extract_okf_from_stores.py` + `compile_okf.py` + clip/lexicon builders) — GOOD-WITH-GAPS
Real strengths, fairly assessed: `find_artifact()` gated at three layers, fabricated-quote
stripping via shared `transcript_verbatim`, `--auto-approve` hard-refused, 5-node-arc +
quality-filter compile gate, content-addressed variant files instead of overwrites,
memory guards for small containers. Gaps are all above (dedup blind to root-vs-subdir
doubles, no multilingual path, no freshness loop, no review-attribution logging).
1. **Compile-walk + global dedup (M).** As §3.1 fix 1, plus persist a
   `build_manifest.json` (entry hash → source video + build date) enabling
   incremental, idempotent rebuilds. Effort: M.
2. **Review-attribution fields (S).** Write `reviewed_by`/`reviewed_at` into frontmatter
   on graduation, surface counts in `log.md`; block compile when staging backlog exceeds
   a threshold (e.g. 2× compiled). Effort: S.
3. **Freshness loop (L).** Quarterly re-verify: re-fetch source video captions for the
   208 videos, flag deleted/edited sources, re-run verbatim spot-checks, bump per-entry
   `updated`. Effort: L (mostly new automation + a cron/runbook).

## 4. What would make this world-class (the gap list, ordered)

1. Dedup to near-zero + single canonical tree (§3.1.1).
2. Human-review evidence: clear the 820-file staging backlog or explicitly quarantine it;
   fill `verified`/`reviewed_*`; restore `index.md`/`log.md`.
3. Discriminative tags + per-quote timestamps (retrieval precision work).
4. Multilingual parity: at minimum transliterated core-term coverage + a policy (even an
   explicit "English-only v2, parity scheduled" note beats silence).
5. Freshness loop with upstream change detection.
6. Independent second-rater quote audit (a human re-verifies 100 quotes; report agreement rate).

## 5. Reproduction (all read-only)

```bash
nice -n 10 python3 -c "import json; d=json.load(open('memory/okf/compiled.json')); print(d.get('version'), len(d['entries']))"
# contamination / schema / dup / attribution / hygiene / coverage / lexicon / cluster
# checks: see audit session — single-file scans of compiled.json, verbatim_clusters.json,
# backend/data/doctrine_lexicon.json cross-checked against transcripts/<video_id>.md
ls memory/okf/staging/ | wc -l   # 820 at audit time
```

*No code, data, state, log, or config files were modified. No commits made. 0 LLM calls used.*

## 6. Implementation status — 2026-10-04 (follow-up session, 0 LLM calls)

Backups with checksums taken before any write (`/tmp/okf_backup/`:
`89bfefb4…` compiled.json, `4407ceef…` doctrine_lexicon.json). No commits made.

### 6.1 "Ready 5" graduation → 2 graduated, 3 held

Per-file quote-verbatim gate (`services.transcript_verbatim.find_verbatim` +
exact-substring vs `transcripts/<video_id>.md`):

| File | Result | Evidence |
|---|---|---|
| `observation_…_addictive_states.md` → `sri-preethaji/` | GRADUATED | 0 gate-checkable quotes; re-validated OK |
| `spiritual_loneliness_and_evolution.md` → `shared/` | GRADUATED | 0 quoted strings; re-validated OK |
| `silencing_the_mind_s_chatter.md` | HELD | 30-word quote `not_found` (0.30), 0/7 6-gram hits — summary in quote marks |
| `transcending_the_ego.md` | HELD | 29-word quote `not_found` (0.40), 0/4 6-gram hits — same defect class |
| `universal_life_force_….md` | HELD | 7-word `(Unknown Channel)` quote not an exact substring; below gate word floor |

Reasons recorded in `memory/okf/STAGING_TRIAGE_2026-10-04.md` (§ Graduation
outcome). Graduation used the pipeline's own `graduate_entry` + `compile_okf()`.

### 6.2 `atriabooks` purge

Publisher-imprint OCR fragment (`atriabooks`, books source, count 3 — passed
the support bar via boilerplate repetition) removed from `proper_nouns`
(29 → 28) and `targets` (5849 → 5848) in `backend/data/doctrine_lexicon.json`;
kept in `vocabulary`/`curated` (protective membership) and
`corpus_freq`/`corpus_sources` (observed data). Rebuild guard added in
`backend/services/doctrine_lexicon.py`: `_OCR_JUNK_DENYLIST` wired into the
existing `_purge_junk_proper_nouns` path + `build_lexicon` targets.
`test_doctrine_lexicon.py` 9/9 green; calibration still corrects
Ujash/Ujasi/Ojasi → Ojas. Ruff check + format clean on touched code.

### 6.3 Recompile numbers

`compiled.json` v2: **427 → 429 entries** (both graduates present), **0
exact-title groups**, 429/429 embeddings 1024d. Gate tests:
`test_okf_doctrine_only.py` + `test_okf_store.py` **2888 passed** (includes
`test_compiled_index_matches_the_clean_bundle` and the integrity contract).

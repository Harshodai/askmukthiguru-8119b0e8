# OKF + Qdrant Knowledge-Layer Audit — 2026-10-04

**Auditor:** fresh read-only audit (no prior context). **No code/data modified.**
**Scope:** OKF quality + Qdrant wiring soundness. Corpus data is rights-sensitive — fixes proposed, none applied.
**Method:** file reads, Qdrant REST, transcript cross-checks, 3 live probes (ritual/chat/first-person), 1 read-only gate report.

---

## 1. Inventory

### 1a. OKF artifacts (`memory/okf/`)

| Artifact | Present | Size / mtime | Content (measured) |
|---|---|---|---|
| `compiled.json` | **YES** (contradicts pre-Aug-28 "absent" notes; present since ≥Sep-30 rebuild) | 18,099,082 B, Sep-30 16:31 | version 2, **717 entries**: 710 teaching / 4 practice / 2 reflection / 1 qa. Teachers: 670 `sri-preethaji-and-sri-krishnaji` + 30 `both` + 15 `sri-preethaji` + 2 `sri-krishnaji` |
| `verbatim_clusters.json` | **YES** | 182,348 B, Sep-29 13:24 | version 1.0, **5 clusters × 5 `quotes_with_provenance` = 25 quotes** (NOT "5 quotes" shorthand — each cluster also carries `key_verbatim_quotes`×5, `clip_ids`, `reflection_questions`, centroid `embedding`) |
| `*.md` source entries | YES | ~1,370 files (root + `shared/` + teacher subdirs) | Structure per entry: `## Verbatim Discourse Excerpts` + `## Key Teachings` (paraphrase bullets). Rebuilt from clips (Wave-5 untracked rebuild per handoff) |
| `staging/` | YES (correctly excluded from compile) | unreviewed LLM output | Excluded by `_excluded_parts` filter |
| Build pipeline | `backend/scripts/ops/rebuild_okf_from_clips.py` | deterministic, **zero LLM summarization** (file header) | **Caveat:** cluster assignment is **regex-keyword matching** (`CANONICAL_CLUSTERS[].pattern`), not embedding clustering. Quotes are verbatim clip text; *membership* is heuristic |

Cluster clip-reference counts: `two_states_of_being` 72, `four_sacred_secrets_inner_truth` 28,
`love_relationships_otherization` 81, `stillness_serene_mind_meditation` 18,
`universal_intelligence_awakening` 24 (= 223 clip refs).

### 1b. Doctrine lexicon

| Path | State |
|---|---|
| `data/doctrine_lexicon.json` (repo-root, the path the task brief named) | **ABSENT** |
| `backend/data/doctrine_lexicon.json` (the **live** path: `services/doctrine_lexicon.py:53` `LEXICON_PATH`) | **PRESENT** — 7,719,678 B, built Aug-3, 10 top-level keys (`built_at`, `sources`, `vocabulary`, `proper_nouns`, `targets`, `general_english`, `curated`, `clean_curated`, …) |
| Runtime status | `backend/app/runtime_artifacts.py:27` — `required=False`, fail-open with "build it" message (`doctrine_lexicon.py:376-398`). Consumed defensively by `services/doctrine_terms.py:480-535` (try/except skip) |

Verdict: lexicon exists where the code reads it. The repo-root `data/` absence is a doc-path mismatch only.

### 1c. Qdrant live (last good read; later timed out — §4)

24 collections. Key rows (`GET /collections/<name>`):

| Collection | points_count | Vectors (1024d, Cosine) | on_disk | Note |
|---|---|---|---|---|
| `spiritual_wisdom_contextual` | **14,033** | `dense` | **true** | `indexed_vectors_count` 29,077 (> points — segment overlap, normal) |
| `first_person_v7` | **1,169** (was 1,038 @ ~05:00 → **+131, +12.6%**) | `passage_dense` + `question_dense` + sparse `passage_sparse` | dense **false** (RAM), sparse true, `on_disk_payload` true | Growth proves incremental apply ticking |
| `second_brain_vault` | 0 | 1024 | true | empty |
| `canonical_memory_vectors` | 2 | 1024 | true | |
| `global_memory` | 0 | — | — | empty |
| `first_person_v1..v6`, `spiritual_wisdom_ingest_backup_2026090*` (×5), lightrag `*_baai_bge_m3_1024d` (×3), caches, `_verify_*` | — | — | — | legacy/backup; not audited |

---

## 2. Quote authenticity spot-check — **8/8 HIT (100%)**

8 quotes sampled across all 5 clusters, **both speakers** (5 Sri Krishnaji + 3 Sri Preethaji),
5 distinct videos, checked as normalized-substring match against
`~/mukthiguru_attribution_data/pilot50_2026-09-25/passages_B/<video_id>.json`
(distinctive mid-quote 4-word phrase + 60-char prefix):

| # | Cluster | Speaker | video_id @ start | len | Result |
|---|---|---|---|---|---|
| 1 | two_states_of_being | Krishnaji | `cHAJiF2byzg` @ 37 | 119 | HIT |
| 2 | two_states_of_being | Krishnaji | `cHAJiF2byzg` @ 37 | 77 | HIT |
| 3 | four_sacred_secrets_inner_truth | Krishnaji | `UlOt31lBhLY` @ 93 | 112 | HIT |
| 4 | love_relationships_otherization | Krishnaji | `1imcyoNUO-A` @ 179 | 176 | HIT |
| 5 | stillness_serene_mind_meditation | Preethaji | `5Tdb7hBwX88` @ 0 | 93 | HIT |
| 6 | stillness_serene_mind_meditation | Preethaji | `5Tdb7hBwX88` @ 0 | 106 | HIT |
| 7 | stillness_serene_mind_meditation | Preethaji | `UlOt31lBhLY` @ 1418 | 135 | HIT |
| 8 | universal_intelligence_awakening | Krishnaji | `rGcNJ_Nsuy8` @ 364 | 109 | HIT |

Corroboration: read-only `scripts.ops.okf_quote_gate_report` just re-ran —
**717 entries / 32 quoted strings (≥8 words) / 32 checked / 32 verbatim / 0 partial / 0 not_found / 0 entries affected.**
Note the denominator: only 32 literal quoted strings exist across all 717 bodies — the bulk of
OKF body text is curated paraphrase ("Key Teachings"), which no verbatim gate covers (Gap G1).

Serving-code bounds (measured, correcting the brief's "30–400"): quote extraction regex is
**20–400 chars** (`services/transcript_verbatim.py:50` `_QUOTED_STRING_RE`), minimum
**8 words** (`:51` `MIN_QUOTE_WORDS = 8`). Leakage gate: `services/okf_quality_filter.py:92-94`
(`_LEAKAGE_RE` rejects extraction/prompt-leak artifacts at entry validation).
Ritual adds its own serve-time filter: `len >= 40` + must end on sentence punctuation
(`backend/app/api/ritual.py:100-103` `_quote_is_safe`).

---

## 3. Wiring map — who reads OKF at serve time

| Path | Reads | Gate | Failure mode (actually in code) |
|---|---|---|---|
| **Chat pipeline** `backend/rag/nodes/retrieval.py:2051` | `compiled.json` (717 entries) via `_okf_match` (`:172`) ← `_load_okf_entries` (`:79-101`), mtime-keyed cache | `rag_okf_injection_enabled` (**default True**, `app/config.py:1005`); skipped for CASUAL/GREETING; teacher routing preethaji/krishnaji (`:2045-2050`) | File missing → loud warning + `[]`, injection contributes nothing (`:85-93`). Match exceptions → debug log, non-fatal (`:2057-2058`) |
| **Ritual** `backend/app/api/ritual.py:106-146` | `verbatim_clusters.json` → `quotes_with_provenance` only (dedup by fingerprint, `_quote_is_safe`, `&t=<start>s` deep link iff `start > 0`) | none (always attempted) | Missing/unusable → product-approved `_FALLBACK_PROMPTS` practice guides (`:149-156`), explicitly NOT teacher-attributed (`:50`) |
| **First-person bridge** `backend/services/first_person_pipeline.py:1247-1260` | `match_okf_entries` (`services/memory/okf_store.py`, imports `:45`) for context; primary retrieval = `FirstPersonStore` → Qdrant `first_person_v7` | 1024-dim guard; try/except | OKF failure → clips-only (`:1258-1260`). **Hard invariant: `curated_okf` provenance can NEVER become a citation** — `_build_citation` raises (`:1267-1268`); cached non-video/OKF citations rejected (`:887-893`); `curated_okf` clips quarantined from serve (`:243`) |
| **OKF load gate** `services/memory/okf_store.py:172-229` | `*.md` via rglob | `type` required; `type ∈ DOCTRINE_TYPES` (runbooks rejected, `:193-204`); `OKFQualityFilter.validate_entry`; staging/`_scripts` excluded (`:180`) | `okf_verbatim_quote_gate` (**default False**, `config.py:1012`) → `strip_fabricated_quotes` on bodies SKIPPED unless enabled (`:218`) |

### Fallback proof (live probes, 2026-10-04 ~09:30 UTC)

1. **Ritual (0 LLM calls):** `GET /api/ritual/today` → 200, served live OKF verbatim quote
   (Krishnaji, `cHAJiF2byzg&t=37s`, `kind=verbatim_quote`, cluster title as `source_label`).
   **Ritual→verbatim_clusters wiring PROVEN.**
2. **Chat (0 LLM calls fired):** correct-schema POST queued (`job_id`, `poll_url`); job expired before
   poll (host-side worker down — §4). No serve proof obtainable from this backend; injection path
   verified by code read only.
3. **First-person (0 LLM calls fired):** `POST /api/first-person/query` →
   `{"detail":"First-person retrieval unavailable"}` — honest failure, no fabrication.
   **Fail-closed behavior PROVEN.**

**Wiring soundness: YES.** Every OKF reader has an explicit absent/empty path that degrades to
empty docs, fallback prompts, or honest errors. No path was found that serves OKF-shaped content
with OKF absent. One labeling nuance (not a hole): injected OKF docs carry
`knowledge_source=okf` with paraphrase bodies — correctly labeled as curated doctrine, but
downstream generation-prompt treatment of paraphrase-vs-verbatim was not traced in this audit.

---

## 4. first_person_v7 growth check — **STILL TICKING**

- points_count **1,038 (baseline ~05:00) → 1,169 (+131, +12.6%)** at first probe.
- Driver **PID 30758 ALIVE** (`kill -0`, read-only; untouched). Log tail:
  `[100/441] OWXe9v7PHDs start`, stages completing with `clips=N`.
- `state.json`: 173 videos tracked — 93 `stages_done` / 63 `indexed` / 16 `quarantined` / 1 `done`.
- **Observation (no action taken):** Qdrant became unresponsive to REST (~4 consecutive timeouts,
  port LISTEN but 0 bytes) circa 09:30 UTC under ingest write load; host backend `/api/health`
  reports `ready:false` with qdrant/redis/llm `ok:false` (host-side backend uses docker hostnames —
  known caveat — compounded by the load). Final points re-read impossible during window;
  last-good 1,169 stands. Recommend re-reading post-ingest; do NOT restart anything.

---

## 5. Best-practice benchmark (2025–2026 literature)

1. **TREC 2025 RAG Track** (trec.nist.gov) — per-sentence support evaluation (every generated
   sentence checked against its cited segment) + hybrid sparse+dense with RRF + rerank.
   *Us vs:* our FP citations are **stronger than sentence-level** (exact-substring +
   `transcript_hash == sha256` + per-second deep link + `curated_okf`-can-never-cite invariant),
   but **OKF paraphrase bodies have no per-claim support check** — the TREC bar we don't meet.
2. **Ahmad 2025, IEEE ISCC** — Hybrid GraphRAG +8% factual correctness / +11% context relevance
   over vector-only. *Us vs:* architecture matches (dense Qdrant + OKF curated channel +
   Neo4j subgraph injection scored 0.35 below OKF) — but fusion is prepend+score-band, not RRF,
   and the +8% class of claim needs our own held-out measurement (golden-25 re-measure post-ingest).
3. **KG²RAG, NAACL 2025** (Zhu et al.) — semantic retrieval → graph-guided expansion →
   organized paragraphs. *Us vs:* our multi-concept trigger (`extract_doctrine_tags ≥ 2`,
   `retrieval.py:2077-2083`) mirrors the expansion trigger; we lack the re-organization step.
4. **RAGAS context_precision/context_recall** (repo already has `scripts/eval/run_ragas_eval.py`,
   CI-gate `--threshold 0.6`). *Us vs:* tooling present; no record of a run against the current
   717-entry OKF + 14k-point index found — recommend one post-ingest run as the G2 close-out.

---

## 6. Gap list (propose only — no changes applied)

| # | Gap | Severity | Evidence | Proposed fix (not applied) |
|---|---|---|---|---|
| G1 | `okf_verbatim_quote_gate` defaults **False** → 717 compiled bodies injected into chat with quoted-string verification OFF; bodies are mostly paraphrase with no paraphrase-fidelity gate | **P1** | `config.py:1012`, `okf_store.py:218`; gate report: only 32/717-entry-quote surface is even checkable | Enable gate post-ingest re-measure, or label `knowledge_source=okf_paraphrase` vs `okf_verbatim` so generation prompts can treat them differently |
| G2 | Ritual serves `start_seconds=0` quotes **without deep links** (2/25, both Preethaji incl. Soul Sync guidance); no duration plausibility check on `start_seconds` (e.g. 1418) | P2 | `ritual.py:131` (`start > 0`); `verbatim_clusters.json` | Emit plain-URL + `t=0s` explicitly, or quarantine 0-offset quotes; add `start < duration` validation at compile time |
| G3 | Cluster membership is **regex-keyword**, not semantic; cross-cluster quote duplication exists (`cHAJiF2byzg` quotes appear in both `two_states_of_being` and `love_relationships_otherization`; dedup only inside ritual pool) | P2 | `rebuild_okf_from_clips.py:27-60` patterns; §2 quote list | Post-ingest: embedding-similarity cluster audit; cluster-scoped (not just pool-scoped) fingerprint dedup |
| G4 | `first_person_v7` dense vectors **not on_disk** (RAM-resident 1024d ×2 per point, growing toward ~2,500 clips) — cost/memory pressure vs the ≤$35/mo envelope | P2 | §1c table | Evaluate `on_disk:true` + payload-index trade-off against p50 latency after mass ingest lands |
| G5 | Qdrant REST unresponsive under ingest write load; host-side backend cannot serve chat/FP end-to-end (docker hostnames + no worker) → live-serve evidence currently ritual-only | P2 (observability) | §3 probes, §4 | Re-probe chat + FP from container network post-ingest; consider read-replica or apply-throttling if timeouts recur |
| G6 | Repo-root `data/doctrine_lexicon.json` absent while docs/briefs reference that path; live file is `backend/data/` | P3 | §1b | Doc-path correction only |

---

## 7. Report-back summary

- **Quote authenticity rate: 8/8 (100%)** spot-check HIT across both speakers + 5 videos;
  independent gate report **32/32 verbatim, 0 partial, 0 not_found**.
- **Wiring soundness: YES** — chat injects compiled OKF (717 entries, teacher-routed, fail-empty);
  ritual serves verbatim clusters live (proven); FP uses OKF for context only with a
  curated-OKF-can-never-cite hard invariant (proven by code + honest-unavailable probe).
  No silent OKF-shaped serving path found.
- **Top-3 gaps:** (1) verbatim quote gate OFF by default + paraphrase bodies unverified (P1);
  (2) zero-offset quotes serve without deep links, no timestamp plausibility check (P2);
  (3) regex-keyword clustering + cross-cluster duplication (P2).
- **Growth:** first_person_v7 1,038 → 1,169 (+131), driver 30758 alive, [100/441].

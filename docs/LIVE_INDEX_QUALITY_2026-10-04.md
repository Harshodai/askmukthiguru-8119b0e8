# LIVE Index Quality Audit — `first_person_v7` — 2026-10-04

**Auditor:** fresh data-quality subagent (read-only). **Target:** live Qdrant `http://localhost:6333`, collection `first_person_v7`.
**Constraints honored:** zero writes/deletes to Qdrant, `with_vectors=false` on every scroll (payload-only, batches of 50–100),
0 LLM calls, no commits, driver/log/state/workdir files untouched (state.json read-only), no docker commands.
**Collection size during audit:** 1,274 points at start, 1,274 at end (driver active but no visible growth in-window).
**Plan source:** `~/mukthiguru_attribution_data/mass_ingest_2026-10/state.json` (334 plan `videos` keys).

## 1. Collection health — HEALTHY

| Item | Observed |
|---|---|
| `points_count` | 1,274 (`status: green`, `optimizer_status: ok`, 2 segments) |
| Dense vectors | `passage_dense` 1024d Cosine, `question_dense` 1024d Cosine |
| Sparse vectors | `passage_sparse` (indexed, on disk) |
| Payload keys (full 1,274 census) | 22 keys, **all present on 1,274/1,274**: `channel, display_text, duration_ms, end_ms, first_person_eligible, group_id, is_verbatim, layer_sha256, parent_id, provenance_kind, quality_status, question_text, rights_cleared, source_url, speaker, start_ms, teacher_id, teacher_ids, transcript_hash, verbatim_text, video_id, video_url` |
| Missing `video_id` / `verbatim_text` / `speaker` / `start_ms` / `end_ms` | **0** |
| Duplicate point IDs | **0** (1,274 unique) |
| `quality_status` | 1,274/1,274 `verified_verbatim` |
| `provenance_kind` | 1,274/1,274 `speech_turn_clip` |
| Boolean layers | `is_verbatim=True`, `first_person_eligible=True`, `rights_cleared=True` on all points |

**Schema-index note (minor):** `payload_schema` reports `is_verbatim`, `first_person_eligible`, `rights_cleared` as `keyword` type with **0 points** —
the stored values are JSON booleans, so the keyword index never fires. Filtering on these fields currently matches nothing.
Either index them as `bool` or drop them from filter paths. No data loss; query-planning concern only.

## 2. Text quality (full 1,274 census; truncation sub-sample n=30) — HEALTHY with notes

| Check | Result |
|---|---|
| Empty / whitespace-only `verbatim_text` | **0** |
| ASR garbage `[BLANK]` / `<unk>` / `(pause)` / `[music]` / `Host:` / `Speaker` / `???` / `...` | **0 hits on all tokens** |
| Repeated-char runs `(.)\1{4,}` | **0** |
| Speaker-label leaks (leading `Host:`/`Q:`/`Speaker N:` or mid-text) | **0** |
| Non-English scripts (Devanagari, Telugu, Tamil, Kannada, Malayalam, CJK, Arabic, Cyrillic) | **0 points** (corpus is English-transcript; expected) |
| Length chars: min / median / mean / max | 52 / 314.5 / 490 / 2,580 (p5=105, p95=1,311) |
| Short outliers (<50 chars) | **0** |
| Long outliers (>1,500 chars) | **50 points (3.9%)** — longest 2,580 chars (`That one has accumulated from one's parents…`); shortest 52 chars (`In the state imagine all forms disappearing into one`) |
| Lowercase-start (mid-sentence head cut) | **0** — every clip starts capitalized |
| Endings census | terminal `.!?…` 776 (**60.9%**), bare-alnum 434 (**34.1%**), clause-punct `,;:—–` 64 (**5.0%**) |
| Bare endings landing on a function word (`the/of/to/with/and…`) | 128 pts = 29.5% of bare = **10.0% of all points** (genuine phrase-cut, e.g. `…states of oneness with the`) |
| `display_text == verbatim_text` | 229/1,274 (18.0%) |
| `question_text` empty | 1,274/1,274 (expected for `speech_turn_clip` layer; questions live elsewhere — informational) |

Truncation is **phrase-boundary clipping, not mid-word corruption**: spot-checked bare endings break between words.
~10% ending on a function word is the only real polish item (retrieval-safe, display-improvable).

## 3. Attribution — HEALTHY

| Check | Result |
|---|---|
| Speaker distribution | **Sri Krishnaji 678 (53.2%)**, **Sri Preethaji 596 (46.8%)** — `teacher_id` (`krishnaji`/`preethaji`) matches 1:1 |
| `unknown` / empty speakers served as teacher clips | **0** |
| `video_id` format (11-char YouTube `[A-Za-z0-9_-]{11}`) | 224 distinct IDs, **0 malformed** |
| `source_url` / `video_url` well-formed `https://www.youtube.com/watch?v=<id>` | **0 bad** (1,274/1,274); `source_url == video_url` on all points |
| URL ↔ `video_id` consistency | **0 mismatches** |
| Timestamps: negative / `start>=end` / beyond 6h | **0 / 0 / 0** |
| `end_ms > duration_ms` | **33 pts (2.6%)**, overrun 10–500 ms, median 220 ms — sub-second alignment slop, retrieval-irrelevant |
| Deep-link constructible | Yes — e.g. `https://www.youtube.com/watch?v=EhY6npcnSs8&t=50s` from `start_ms=50630` |

## 4. Duplication — NEEDS-WORK (minor, 2.1%)

Exact-duplicate `verbatim_text`: **13 groups / 27 points (2.1% of collection).**

| Pattern | Groups | Example |
|---|---|---|
| Same video, ±200 ms timestamp jitter (re-ingest overlap) | 9 | `-4wCvcPrX-E` `[3240-15000]` vs `[3040-15200]` — identical 112-char text, two point IDs |
| Cross-video, same teaching reused across discourses (different `transcript_hash`) | 3 | `5TbaZA522Fs` vs `5ia1FNUN6fk` — same "antenna / riches of the universe" segment; `WO_jh3zPTr0` vs `szJ7uDYHJ1Y` — same fear segment. Legitimate repetition, keep |
| Cross-video, **same audio under two YouTube IDs** (same `transcript_hash`) | **1** | `9id3ygnEhh8` (2 pts) vs `AQUZcU5L9xE` (1 pt), `[~3900-25500]` — re-upload of one discourse; plus an intra-`9id3ygnEhh8` jitter dup → group of 3 |

## 5. Foreign-content check — HEALTHY (clean)

| Check | Result |
|---|---|
| Qdrant distinct `video_id`s | 224 |
| Plan keys in `state.json` | 334 |
| Qdrant videos **NOT** in plan (suspect) | **0 — no foreign content** |
| Incident video `iKkySU5r_x8` points in Qdrant | **0** (deletion holds; ID also absent from plan keys) |
| Quarantined-status plan videos present in Qdrant | **0 of 38** |
| In-Qdrant status split | `indexed` 154 + `stages_done` 70 = 224 ✓ |
| Plan videos not yet in Qdrant | 110 (ingest still running — expected) |

**Watch item (not a defect yet):** 51 plan videos carry status `indexed` but have no Qdrant points — 19 with `clips=0`
(genuinely nothing to index) and **32 with clips>0** (e.g. `-YQLpNmH0MQ` 16 clips, `9XbV4ubs3Fw` 18 clips;
passages files exist, e.g. `passages_B/-YQLpNmH0MQ.json`). If "indexed" is meant to include the Qdrant upsert,
these 32 are either queued behind the running driver or silently skipped. Re-verify after the driver completes.

## 6. Transcript cross-check (5 random teacher clips, seed 20261004) — HEALTHY 5/5

Method: normalize (lowercase, strip punctuation, collapse whitespace), test served `verbatim_text` as substring of
joined `transcripts_B/<video_id>.json` word stream. **All 5 exact-substring matches (ratio 1.000):**

| video_id | len | match |
|---|---|---|
| `1sMxPhQcvEA` (`Walking meditation, smiling meditation…`) | 902 | exact ✓ |
| `7Pfat_DztMI` (`Meditation impacts us physically…`) | 290 | exact ✓ |
| `2X0BCy1bRcU` (`Babies who can fulfill the greater purpose…`) | 139 | exact ✓ |
| `cI7D2aO34yw` (`Only from not knowing can something totally new emerge…`) | 245 | exact ✓ |
| `BZDXIQwOPdU` (`When you actually get back from work…`) | 301 | exact ✓ |

## Overall verdict — HEALTHY (serve-ready; hygiene fixes queued, none blocking)

No foreign content, no missing fields, no ASR garbage, no speaker misattribution, no timestamp violations,
URLs/deep-links sound, served text verified verbatim against local transcripts 5/5.

## Top fixes proposed (not applied)

1. **Dedupe same-video jitter pairs** (9 groups, ~18 pts): on upsert, skip a clip whose `(video_id, normalized_text)` already exists,
   or collapse pairs with `|Δstart|<500 ms` — cheapest at driver upsert time.
2. **Resolve re-upload pair** `9id3ygnEhh8` ↔ `AQUZcU5L9xE` (same `transcript_hash`): keep one canonical `video_id`, or tag both with
   `canonical_video_id` so retrieval doesn't double-count the same discourse.
3. **Fix boolean payload indexes**: change `is_verbatim` / `first_person_eligible` / `rights_cleared` index type to `bool`
   (currently `keyword` with 0 indexed points) or stop filtering on them.
4. **After driver completes**, reconcile the 32 `indexed`-status videos with clips>0 but zero Qdrant points (list in §5) —
   confirm they upsert or record why skipped.
5. **Polish (optional):** re-window or ellipse-mark the ~10% of clips ending on function words; consider splitting the 50 clips
   >1,500 chars for steadier first-person serving.

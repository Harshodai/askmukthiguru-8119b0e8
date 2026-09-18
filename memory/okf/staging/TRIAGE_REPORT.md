---
type: reflection
title: "OKF Staging Triage Report (2026-09-17)"
source: "internal-triage-script"
status: unciteable
---

# OKF Staging Triage Report — 2026-09-17

**Do not promote this file.** `type: reflection` + `status: unciteable` keeps
it invisible to `OKFStore.list_entries()` even if someone runs the compiler
against `staging/` by mistake (they shouldn't — the review gate is the
`_excluded_parts={"staging","_scripts"}` filter, untouched by this triage).
It is a report about the bundle, not an entry in it.

Scope: mechanical triage script at
`/private/tmp/claude-501/.../scratchpad/triage.py` re-implements the three
`OKFStore.list_entries()` load-time gates plus `OKFQualityFilter` against all
799 files in `memory/okf/staging/`. No live `.md`, `compiled.json`, or
`backend/services/` file was touched.

## Phase 1 — mechanical triage (before repair)

| Check | Count | % of 799 |
|---|---|---|
| **Passes all 3 invariants** | 670 | 83.9% |
| Missing/invalid `type` | 67 | 8.4% |
| Missing `title` | 67 | 8.4% |
| Missing `source` | 67 | 8.4% |
| Duplicate title (case-insensitive) | 61 | 7.6% |
| Hash-suffixed filename (`__<8hex>.md`) | 88 | 11.0% |
| Empty/stub body (<100 chars) | 1 | 0.1% |
| Extraction-artifact / LLM-commentary leak | 0 | 0% |
| Invalid `type` value | 0 | 0% |

The 67 `missing_type`/`missing_title`/`missing_source` rows are the **same 67
files**, all failing for **one root cause**: a single corrupted `tags:` YAML
line, e.g.

```yaml
tags: [ , p, r, o, s, p, e, r, i, t, y, ,,  , c, o, n, s, c, i, o, u, s, n, e, s, s, ,,  , j, n, a, n, a]
```

A comma-joined tag string (`"prosperity, consciousness, jnana"`) got exploded
character-by-character into a YAML flow list at some point in the extraction
pipeline, and one of those characters (a bare `,`) is invalid inside a flow
sequence — `yaml.safe_load` raises on the whole frontmatter block, `_parse_frontmatter`
silently returns `meta={}`, and `OKFStore.list_entries()` drops the entry with
`"Skipping OKF entry without 'type'"`. These 67 files otherwise had
well-formed `type`/`title`/`source`/`teacher` fields sitting right next to the
broken line — good entries were failing invisibly for a cosmetic bug.

Zero entries carried a RAPTOR debug header, `_(Source: unknown)_`, or LLM
self-commentary (`"The user wants me to analyze..."` etc.) — the
`OKFQualityFilter` leakage patterns matched nothing in staging.

## Phase 2 — repairs applied, in place, in `staging/`

| Fix | Count |
|---|---|
| Reconstructed the exploded `tags:` line from its raw characters and re-serialized as a proper YAML list, verified the file now parses with non-empty `type`/`title`/`source` | **67** |
| Invented a `source` where one was missing | **0 — none fabricated per instructions** |
| Fixed extraction-artifact leakage | **0 needed** |

Nothing else was mechanically fixable without judgment calls this triage was
told not to make. Specifically **not touched**:

- **108 duplicate-title entries** (by title, case-insensitive) — these need an
  editorial pick of which body to keep (`OKFQualityFilter.filter_duplicate_entries`
  keeps the longest body, but longest ≠ best; several pairs are near-identical
  re-extractions of the same video from different pipeline runs). Left for the
  owner.
- **88 hash-suffixed filenames** (`__f86e3221.md` style) — confirmed these are
  re-extraction runs of an existing base file (e.g. `relationship_with_ego.md`
  plus `relationship_with_ego__f86e3221.md` and `__e7fdf297.md`), not new
  concepts. Overlaps heavily with the duplicate-title set. Left for the owner
  to diff and pick one version per concept.
- **1 stub body** — flagged only, not deleted (deletion is promotion-adjacent
  editorial judgment, out of scope for "repair").

Post-repair: **690/799 (86.4%) pass all three load-time invariants.**
Re-triage counts and full per-file JSON are in the scratch dir, not the repo
(`triage_results.json`), since they're throwaway working data, not doctrine.

## Phase 3 — doctrinal verification, priority concepts only

Checked against live Qdrant (`spiritual_wisdom_contextual`, 12,904 points,
`QDRANT_URL=http://localhost:6333`) via `backend/.venv/bin/python` +
`qdrant_client`, filtering `source_url` by video ID and reading `provenance`
(`verbatim_speech` / `machine_summary` / etc.) per chunk.

### Soul Sync — well covered, verified against verbatim speech

| Staging file | Video ID | Provenance found | Verdict |
|---|---|---|---|
| `the_creation_of_soul_sync_meditation.md` | `GQZ7A4fvts4` ("Meaningful Coincidences") | **verbatim_speech** — the file's own pull quote `"When Sri Krishnaji and I created the Soul Sync meditation years ago, we did..."` matches the corpus chunk word-for-word (`b693a3ba-ee5e-5925-8ad2-7468b7d58a83`) | **Ready** |
| `internal_mantra_chanting.md` | `zO8tQkjCpyc` ("The Great Soul Sync Meditation") | verbatim_speech + machine_summary chunks, both on-topic | **Ready** |
| `state_of_expansion_and_oneness.md` | `X3LKG0Ycl3A` ("Soul Sync Meditation Challenge - 7") | verbatim_speech present, guided-meditation quote matches | **Ready** |
| `yoga_and_spiritual_healing.md` | `Hdr5IXNmRUE` ("Beyond Fitness, Toward Oneness") | verbatim_speech + machine_summary; body correctly says "leads to *Soul Sync Meditation* series" rather than claiming yoga *is* Soul Sync | **Ready, minor** |
| `yoga_and_spiritual_observation.md` | `Hdr5IXNmRUE` (same video, different topic slice) | same source, verbatim_speech present | **Ready, minor** — near-duplicate of the above; same video, pick one or keep both as distinct facets |

All five hold up. The corpus genuinely contains Soul Sync material — the live
gap is a bundle/compile gap, not a corpus gap.

### Four Sacred Secrets — **zero coverage in staging, but the corpus has it**

`grep -ril "sacred secret" memory/okf/staging/` → **0 hits.** No staging file
mentions the Four Sacred Secrets at all, so nothing here is promotable for
this concept — there is nothing to promote.

But the corpus is not silent: Qdrant has **20 chunks** (verbatim_speech +
machine_summary) across two sources — `https://www.youtube.com/watch?v=UlOt31lBhLY`
("Manage Your Stress with Sri Preethaji & Sri Krishnaji's Four Sacred
Secrets") and the Amazon listing for the book *Four Sacred Secrets: A
Revolutionary Blueprint for Living an Extraordinary Life* — plus 5 more hits
on a broader "sacred secret(s)" text search. **This doctrine is not absent
from the corpus; it is absent from the OKF extraction pipeline's output.**
Closing this gap needs a fresh `scripts/extract_okf_from_stores.py` pass
targeting video `UlOt31lBhLY` (and ideally the book text, if licensed and
ingested) — not something this triage can produce by repairing staging/,
since no staging entry exists to repair.

## RANKED PROMOTION CANDIDATE LIST

Ordered by live-answer-coverage impact (Soul Sync first — it's the addressable
gap):

1. **`internal_mantra_chanting.md`** — verbatim_speech, `zO8tQkjCpyc` chunk. Names a specific step (4th of 8) in the Soul Sync sequence; highest specificity value for a "how do I do Soul Sync" query.
2. **`the_creation_of_soul_sync_meditation.md`** — verbatim_speech, `GQZ7A4fvts4`, quote verified word-for-word. Best for "what is Soul Sync / who created it" queries.
3. **`state_of_expansion_and_oneness.md`** — verbatim_speech, `X3LKG0Ycl3A`. Guided-meditation content, good for practice-style QA.
4. **`yoga_and_spiritual_healing.md`** — verbatim_speech + machine_summary, `Hdr5IXNmRUE`. Broader context linking yoga practice to Soul Sync.
5. **`yoga_and_spiritual_observation.md`** — same source as #4; promote only if the owner wants both facets of that video as separate entries, otherwise redundant with #4.

None of the Four Sacred Secrets gap is closeable from staging — see above.

## DO-NOT-PROMOTE list

- **108 duplicate-title entries** — needs owner pick of canonical version per title.
- **88 hash-suffixed re-extraction files** — same reason; diff against their non-suffixed sibling first.
- **1 stub-body entry** (flagged in `triage_results.json`, not named here — see the JSON for the exact path) — too short to be a teaching, likely a failed extraction; candidate for deletion, not promotion.
- Any file not in the 5-item list above, even after the 67-file tags-YAML fix, has **not** been doctrinally verified against corpus chunks by this pass — "loads correctly" is not the same claim as "doctrinally accurate." Treat everything outside the ranked list as unverified, not rejected.

## Exact commands to promote the approved subset and recompile

Owner-only — this triage did not run these.

```bash
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8

# Promote (git mv keeps history; adjust destination subdir per teacher if desired)
git mv memory/okf/staging/internal_mantra_chanting.md memory/okf/
git mv memory/okf/staging/the_creation_of_soul_sync_meditation.md memory/okf/
git mv memory/okf/staging/state_of_expansion_and_oneness.md memory/okf/
git mv memory/okf/staging/yoga_and_spiritual_healing.md memory/okf/
# yoga_and_spiritual_observation.md: promote only if keeping both facets
# git mv memory/okf/staging/yoga_and_spiritual_observation.md memory/okf/

# Recompile
cd backend
.venv/bin/python -m scripts.okf_compile

# Verify the two new coverage areas actually landed
grep -il "soul sync" ../memory/okf/compiled.json
```

To close the Four Sacred Secrets gap, run a fresh targeted extraction (not a
promotion — this is new work, not staged):

```bash
cd backend
.venv/bin/python -m scripts.extract_okf_from_stores \
  --video-id UlOt31lBhLY --limit 5   # inspect output in staging/ before --auto-approve
```

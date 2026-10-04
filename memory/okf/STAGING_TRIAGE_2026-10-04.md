# OKF Staging Triage — 2026-10-04

**Scope:** read-only mechanical triage of `memory/okf/staging/` (819 entries;
`TRIAGE_REPORT.md` excluded from counts). No staging file, live `.md`,
`compiled.json`, or code file was touched for this part (`git status` on
`staging/` is clean). Nothing was compiled into production.
**Method:** stdlib-only script (`/tmp/triage_staging.py`, kept out of the repo),
0 LLM calls. Production baseline is the post-dedup `compiled.json`
(431 entries, same session).

Prior triage `staging/TRIAGE_REPORT.md` (2026-09-17, 799 files) still applies:
its 67-file tags-YAML repair is holding (0 missing-type today), its 5-item
Soul-Sync promotion list and Four-Sacred-Secrets gap note are unchanged.
Backlog grew 799 → 819 (+20 new files) since then.

## Counts

| Category | Count | Disposition |
|---|---|---|
| ready-to-compile | 5 | May enter the normal graduation review (`compile_okf.py` arc gate + human). NOT compiled by this triage. |
| quarantine | 813 | See sub-buckets below. Do not compile without the stated action. |
| junk | 1 | `entry.md` — template placeholder (literal `"..."` title/source/body). Candidate for deletion. |

### Quarantine sub-buckets (first-match precedence documented in script)

| Sub-bucket | Count | Disposition |
|---|---|---|
| arc-only (valid, sourced, unique; fails 5-node arc heuristic) | 365 | The promotion pipeline. Run through `compile_okf.py` graduation + human review. |
| dup-of-production (+arc) | 328 | Redundant with shipped entries. Delete after owner spot-check. |
| dup-in-staging (+arc) | 78 | Re-extraction variants (`__<8hex>` siblings). Diff vs sibling, owner picks one. |
| dup-of-production only | 15 | Redundant; delete after spot-check. |
| dup-in-staging only | 4 | Owner picks one version. |
| code-fence / no-video-source / thin-body (overlapping) | ~14 | Manual review (5 code fences need artifact inspection; 3 missing video source; 10 thin bodies <500 chars). |

Reason totals (overlapping): `fails-5node-arc` 791, `dup-of-production` 355,
`dup-in-staging` 93, `thin-body` 10, `code-fence` 5, `no-video-source` 3.
Strong contamination markers (`<think>`, `temporary connection issue`): **0**.
Weak-marker hits and fences are quarantined for human eyes, not auto-junked.

### Calibration note (read before acting on "arc-only")

The 5-node-arc heuristic used here is the strict sequential-regex version from
`scripts/okf/compile_okf.py`. Production itself passes it at only 7/431
(1.6%) on truncated compiled bodies, so a staging `fails-5node-arc` is
**"not yet graduated", not "defective"** — the real graduation gate runs on
full bodies plus human review. The 365 arc-only files are the legitimate
forward pipeline, not a reject pile.

## Ready list (5)

- `observation_and_transformation_recognizing_and_transforming_addictive_states.md`
- `silencing_the_mind_s_chatter.md`
- `spiritual_loneliness_and_evolution.md`
- `transcending_the_ego.md`
- `universal_life_force_embodied_peace_and_the_autonomic_nervous_system.md`

Each has: valid doctrine type, non-empty title/body ≥500 chars, YouTube source
with video_id, sequential 5-node arc keywords, no title/hash match against
production (431) or any other staging file.

## Residual risks

1. "Loads correctly" ≠ "doctrinally accurate" (same caveat as the 09-17
   triage). The 5 ready files passed mechanical gates only; quote-verbatim
   verification against `transcripts/<video_id>.md` is still required at
   graduation.
2. `dup-of-production` was measured against the post-dedup 431-entry index.
   A staging file matching one of the 286 dedup-removed twins is still
   redundant (its ≥0.9 twin survives), but it is labeled by its surviving
   lineage, not the dropped copy.
3. The arc heuristic is over-strict by construction (see calibration note);
   do not use raw arc-fail counts as a quality metric.

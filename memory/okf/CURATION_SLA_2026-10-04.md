# OKF Curation SLA — 2026-10-04 (R4)

Process doc, NOT doctrine. Excluded from the compile walk and the
doctrine-conformance tests via `NON_CONCEPT_FILENAMES` in
`backend/services/memory/okf_store.py`. Never embedded, never injected
into answers.

## Pipeline: staging → review → compile

| Stage | Location | Entry criteria | Exit criteria |
|---|---|---|---|
| staging | `memory/okf/staging/` | LLM-extracted candidate with `type`, `title`, `source` | Quality filter + quote gate clean |
| review | human reviewer | staged entry scores ≥ bar, verbatim quotes verified against transcript | reviewer sign-off (approved row) |
| compile | `memory/okf/compiled.json` | only reviewed entries on disk | `compile_okf()` rebuild, schema tests green |

`staging/` is excluded from compile. Nothing unreviewed reaches the bundle.

## Roles

- **Extractor (machine):** bulk extraction into `staging/` only. Never writes
  live entries or `compiled.json`.
- **Reviewer (human):** verifies quotes against source transcripts, checks
  teacher attribution, approves promotion out of `staging/`.
- **Compiler (machine, `compile_okf()`):** deterministic rebuild + dedup;
  stamps `updated:` freshness (frontmatter date kept, else build date).

## Cadence

- **Weekly:** triage new `staging/` files; promote or reject.
- **Monthly:** staleness report — entries with `updated:` older than **N=180
  days** are flagged for re-verification (quote still verbatim? source still
  live?). Flagged ≠ removed; removal needs reviewer sign-off.
- **Per-release:** full recompile + `test_okf_doctrine_only.py` +
  `test_okf_store.py` green before deploy.

## Freshness flag

- Frontmatter `updated: YYYY-MM-DD` is optional at write time.
- Compiler output entries always carry `updated:` plus `updated_source:`
  (`frontmatter` | `build_default`). Staleness is measured on the compiled
  value; `build_default` entries are treated as review-due first.

## Contradiction policy

When OKF entries from **both teachers disagree on a factual claim**, surface
both with teacher labels — **never synthesize a merged doctrine**.
`scripts/ops/okf_contradiction_scan.py` produces the candidate pair list
(report-only, read-only on `compiled.json`). Reviewers dual-present or
scope-qualify; the script never merges, edits, or deletes.

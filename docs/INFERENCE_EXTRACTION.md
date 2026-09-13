# Inference Extraction Runbook (C1/C3)

> Deliberately a runbook, not a service. There is no inference-extraction
> microservice: extraction runs as an offline job whose output always passes
> human review before reaching answers. Splitting it into a live service would
> put unreviewed LLM output one call away from seekers.

## What this is

" Inference extraction" = deriving candidate OKF doctrine entries
(`teaching|practice|glossary|qa|reflection`) from already-ingested sources
(Qdrant chunks, Neo4j graph) so a curator can approve them into
`memory/okf/` and recompile `compiled.json`.

## Prerequisites

- Qdrant collection `spiritual_wisdom` (or `spiritual_wisdom_contextual`)
  reachable; Neo4j reachable for graph-sourced candidates.
- LLM provider configured (`LLM_PROVIDER=openrouter` + key). Extraction keeps
  all three fallbacks (multi-provider → OpenRouter → Ollama); do not remove one.
- `memory/okf/compiled.json` is the only approved doctrine artifact. If it is
  absent, retrieval falls back to Qdrant/Neo4j -- never fabricate a placeholder.

## Steps

1. **Extract to staging (never directly to `memory/okf/`):**
   ```bash
   cd backend
   .venv/bin/python scripts/extract_okf_from_stores.py
   ```
   Output lands in `memory/okf/staging/` (unreviewed, LLM-generated).
   The repo-root twin `scripts/extract_okf_from_stores.py` must stay
   byte-identical (`tests/test_okf_pipeline_integrity.py::test_extractor_copies_are_identical`).
2. **Human review:** move only approved entries out of `staging/` into the
   teacher subdirs (`sri-preethaji/`, `sri-krishnaji/`, `shared/`).
   `OKFStore.list_entries()` enforces the gates: `type` in
   `DOCTRINE_TYPES`, non-empty `source`, no extraction artifacts
   (`tests/test_okf_doctrine_only.py`).
3. **Recompile:** rebuild `memory/okf/compiled.json` via the OKF compiler
   (embeds `title + description`). Retrieval picks it up via the
   mtime-keyed `_OKF_CACHE` -- no restart needed.
4. **Verify:** `git diff --check`, OKF pipeline integrity tests, and a grounded
   flagship probe (Serene Mind / Four Sacred Secrets returns citations).

## Gates (fail-closed)

- Anything still in `staging/` never reaches `compiled.json` (explicit
  `_excluded_parts` filter -- never remove it).
- Never write to `scripts/ingestion/corpus/` (immutable source transcripts).
- Every LLM `.generate()` output persisted to Qdrant must pass
  `find_artifact()` first (ingestion safety invariant; see
  `backend/docs/INGESTION_SAFETY.md`).

## Rollback

- Delete the bad entry from `memory/okf/<teacher>/`, recompile, confirm the
  mtime bump invalidates `_OKF_CACHE`. No migration, no deploy needed.

## References

- Extractor: `backend/scripts/extract_okf_from_stores.py`
- Store/gates: `services/memory/okf_store.py`, `compiler.py`
- Neo4j MERGE keys written by alignment: `app/db/seed_ontology.py`
  (uniqueness constraints per MERGE key -- C2)
- Anomaly gate on answer quality: `scripts/ops/hallucination_anomaly.py`

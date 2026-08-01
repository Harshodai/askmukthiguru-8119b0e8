# Content Rights Registry

This file documents the rights basis for all copyrighted content ingested
into the AskMukthiGuru knowledge base (Qdrant + Neo4j). It is the content
equivalent of `LICENSE-EXCEPTIONS.md` (which covers code dependencies only).

## Policy

All content ingested into the RAG pipeline must have a documented rights
basis in this file **before** it is committed to the repo or ingested into
production. Content without a documented basis must be stored in a private
asset store outside version control.

## Registered Content

| Asset | Format | Rights Basis | Owner / Publisher | Status | Registered |
|-------|--------|--------------|-------------------|--------|------------|
| The Four Sacred Secrets | PDF — **removed from git index 2026-08-01** (commit `9680a0f5`); **git history fully scrubbed 2026-08-01** via `git-filter-repo --path 'The_Four_Sacred_Secrets.pdf' --invert-paths --force`; confirmed 0 commits remain. File retained locally under `data/private/` (gitignored). | **Pending** — rights basis must be confirmed with Ekam Science Foundation / OneWorld Academy before re-ingesting from private asset store. Possible bases: CC license on ekam.org, direct arrangement with rights holder, or fair-use academic commentary. | Sri Preethaji & Sri Krishnaji / Sounds True | ⚠️ Rights basis unconfirmed — do not re-ingest until verified. Git history scrub: COMPLETE (2026-08-01). ⚠️ **Embeddings may still be live in Qdrant/Neo4j** — if rights basis cannot be confirmed, purge vectors derived from this book. | Removed from repo: 2026-08-01; history scrubbed: 2026-08-01; rights review: pending |

## Asset Storage Policy

Copyrighted PDF/EPUB/audio assets must NOT be committed to the git repository.
Store them in:
- **Local ingestion only**: `data/private/` (gitignored via `*.pdf` in `.gitignore`)
- **Production**: Railway volume mount or private S3 bucket, ref `PRIVATE_ASSETS_PATH` env var

## Review Cadence

Review rights basis annually or when ingestion corpus changes significantly.

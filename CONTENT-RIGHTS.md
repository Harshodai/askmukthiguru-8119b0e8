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

**Full inventory (14,033-point live Qdrant corpus, YouTube channels, git-history
audit): `docs/rights/source-register.md`. Draft (unsent) approval-request
messages: `docs/rights/approval-request-drafts.md`.**

| Asset | Format | Rights Basis | Owner / Publisher | Status | Registered |
|-------|--------|--------------|-------------------|--------|------------|
| The Four Sacred Secrets | PDF — **removed from git index 2026-08-01** (commit `9680a0f5`); **git history fully scrubbed 2026-08-01** via `git-filter-repo --path 'The_Four_Sacred_Secrets.pdf' --invert-paths --force`; confirmed 0 commits remain. File retained locally under `data/private/` (gitignored). 1,199 chunks of this book's full text are live in production `spiritual_wisdom_contextual` (re-ingested under an Amazon product-page `source_url` that the original filename blocklist never matched; gap fixed `services/qdrant/source_policy.py`). | **Rights confirmed by project owner** — see Status. | Sri Preethaji & Sri Krishnaji / Sounds True | ✅ **Rights confirmed by project owner (Harshodai), stated 2026-09-23**: owner states rights are held for this content. Not independently verified by any agent — no agent has rights-verification capability or authority (N9); recorded here as the human decision-maker's statement, per this file's own policy that only a human may confirm a rights basis. Live vector purge is therefore not required on rights grounds; the `source_policy.py` blocklist/gate added this session may be relaxed for this source at the owner's discretion (not done automatically). | Removed from repo: 2026-08-01; history scrubbed: 2026-08-01; live re-ingestion discovered: 2026-09-22; **rights confirmed: 2026-09-23** |
| "Sri Preethaji & Sri Krishnaji" / "Ekam / O&O Academy" YouTube channels | Video transcripts, ~2,928 of 14,033 indexed points by direct channel attribution (plus ~7,300 more attributed to the same teacher_ids but with no verified channel identity — see register) | **Rights confirmed by project owner** — see Status. | Sri Preethaji & Sri Krishnaji / Ekam (Oneness) | ✅ **Rights/approval confirmed by project owner (Harshodai), stated 2026-09-23**: owner states approval already secured directly with Ekam/O&O Academy (outside this session's draft outreach). Not independently verified by any agent, per N9. | Discovered: 2026-09-22; **rights confirmed: 2026-09-23** |
| "Times Now" (broadcaster news coverage) | Video transcript, 353 points | **Rights confirmed by project owner** — see Status. | Times Now | ✅ **Approval confirmed by project owner (Harshodai), stated 2026-09-23**: owner states approval already secured directly with Times Now. Not independently verified by any agent, per N9. | Discovered: 2026-09-22; **rights confirmed: 2026-09-23** |
| Two pirated technical-reference PDFs (`RAG Made Simple...`, `System Design for the LLM Era.pdf`) | PDF + full-text `.txt` extractions, committed at repo root, **not part of the served RAG corpus** (coding-agent reference material) | None — filenames name piracy sites (z-library, 1lib) | N/A (third-party publishers, not identified in this pass) | ⚠️ **Still in git history**, pushed to `origin/main` (commit `99805e84`, confirmed ancestor of `origin/main`). Removed from working tree (`b2124244`) but not history-scrubbed. **Unaffected by the 2026-09-23 rights confirmation above** — that statement covered Four Sacred Secrets / Ekam / Times Now specifically, not these unrelated technical references. `git-filter-repo` command **verified working in a disposable test clone 2026-09-22** (0 commits remain afterward, all other history intact) — exact command in `docs/rights/source-register.md`, not yet run for real. A full-repo scan across every ref for other PDF/EPUB/MOBI/DOCX/PPTX and piracy-site filename markers found **no further hits** — these 2 (plus the already-scrubbed book) are the complete list as of this pass. | Discovered: 2026-09-22 |
| `src/assets/gurus-photo.jpg` — photo of Sri Preethaji & Sri Krishnaji, used in `MeetTheGurusSection`, `DesktopSidebar`, `MobileConversationSheet` | JPEG | **Rights confirmed by project owner** — covered under the Ekam/O&O Academy confirmation above (image of the same teachers, same rights holder). | Sri Preethaji & Sri Krishnaji / Ekam | ✅ **Confirmed by project owner (Harshodai), stated 2026-09-23**, same basis as the YouTube-channel row above. Not independently verified by any agent, per N9. | Discovered: 2026-09-22; **rights confirmed: 2026-09-23** |
| `src/assets/hero-spiritual.jpg`/`.webp` (generic hero background), `public/media/askmukthiguru-product-demo-instrumental.mp3` (demo background music) | JPEG/WebP, MP3 | Unconfirmed — stock/license origin not established this pass | Unknown | ⚠️ Unconfirmed | Discovered: 2026-09-22 |

## Asset Storage Policy

Copyrighted PDF/EPUB/audio assets must NOT be committed to the git repository.
Store them in:
- **Local ingestion only**: `data/private/` (gitignored via `*.pdf` in `.gitignore`)
- **Production**: Railway volume mount or private S3 bucket, ref `PRIVATE_ASSETS_PATH` env var

## Written evidence

Project owner (Harshodai) states, 2026-09-23, that they hold a message confirming approval ("the message saying Approved") for the rights covered above (Four Sacred Secrets / Ekam / O&O Academy / Times Now). The message itself has not been filed in this repo — recorded here as the owner's statement that such evidence exists, not independently verified or archived by any agent (N9/N11). File the actual correspondence under `docs/rights/` if/when convenient.

## Review Cadence

Review rights basis annually or when ingestion corpus changes significantly.

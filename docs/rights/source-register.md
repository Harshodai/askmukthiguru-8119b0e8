# Source Register — spiritual_wisdom_contextual (Qdrant)

**Rights status update, 2026-09-23**: project owner (Harshodai) states rights/approvals for the Four Sacred Secrets book, the "Sri Preethaji & Sri Krishnaji" / "Ekam / O&O Academy" YouTube channels, and Times Now are already secured directly. See `CONTENT-RIGHTS.md` for the recorded confirmation (dated, attributed to the owner, not independently verified by any agent per N9). The two unrelated pirated technical-reference PDFs are **not** covered by this confirmation and remain an open git-history issue.

Built 2026-09-22 by direct read-only query against the live local Docker
Qdrant instance (`curl http://localhost:6333/collections/spiritual_wisdom_contextual`
and `/facet` on `domain_rights_status`, `source_type`, `content_type`,
`speaker`, `teacher_id`, `language`; `points_count: 14033`). This is an
**inventory of what the payload says**, not a rights determination — see
Column notes.

## Finding: `domain_rights_status="licensed"` is not a rights basis

Every one of the 14,033 points carries `domain_rights_status: "licensed"`
(`/facet` on that key returns exactly one value, count 14033). Grep confirms
why: `backend/services/qdrant/indexer.py:252` —
`payload.setdefault("domain_rights_status", "licensed")` — is an
ingestion-time **default written to every chunk unconditionally**, not a
per-source human confirmation. This directly contradicts `CONTENT-RIGHTS.md`'s
and `CLAUDE.md`'s statement that the 450+-video YouTube corpus has zero
rights-basis documentation — both are correct; the payload field is simply not
evidence of anything beyond "ingestion ran." Do not treat `"licensed"` as a
cleared status anywhere in this codebase going forward.

`provenance` / `provenance_rationale` (present on points, not in the indexed
`payload_schema` since they're unindexed) are a **different, unrelated**
classification — content origin (`verbatim_speech` / `machine_summary` /
`third_party_prose` / `junk`, from `backend/services/provenance.py`), not
rights clearance. Sampled 250 points: `verbatim_speech` 158, `machine_summary`
66, `third_party_prose` 5 (all `channel:times now`), `junk` 2, unset 19.

## Register — by attributed source/channel

| Source / Channel (as attributed in payload) | Format | Points (approx., via facet) | Rights Basis | Rights Holder | Written Approval Ref | Status |
|---|---|---|---|---|---|---|
| "Sri Preethaji & Sri Krishnaji" (`speaker`) — official teacher-attributed YouTube uploads | video | 2,142 | Unconfirmed — publicly posted YouTube video, no license/permission on file | Sri Preethaji & Sri Krishnaji / Ekam (Oneness) | none on file | **Unconfirmed** |
| "Ekam / O&O Academy" (`speaker`) — official org YouTube channel | video | 786 | Unconfirmed — publicly posted YouTube video, no license/permission on file | Ekam / O&O Academy | none on file | **Unconfirmed** |
| "Unknown Channel" / "Unknown" (`speaker` unset or ingestion couldn't resolve it) — attributed to `teacher_id` `preethaji`/`krishnaji`/`preethaji_krishnaji`/`ekam` via `services/teacher_attribution.py`, not a verified channel identity | video | 6,934 + 370 = 7,304 | Unconfirmed, and channel identity itself is not verified (default guess, per `provenance.py`'s own comment: "most chunks simply lack an explicit speaker/channel_name") | Presumed Sri Preethaji & Sri Krishnaji / Ekam, **not verified** | none on file | **Unconfirmed — also missing basic channel attribution** |
| "Times Now" (`speaker`) — third-party news broadcaster coverage of the gurus | video | 353 | Unconfirmed. Third-party news re-broadcast, not the org's own content — a materially different rights question (broadcaster's copyright in the segment, not the gurus'/Ekam's) | Times Now (broadcaster) | none on file | **Unconfirmed — distinct rights holder from the rest of the corpus** |
| "The Four Sacred Secrets" book — **re-ingested under an Amazon listing URL** (`https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319`), `content_type=book` | book (full verbatim chapter text, not just a preview) | 1,199 | **Same book `CONTENT-RIGHTS.md` already flags as unconfirmed and scrubbed from git history 2026-08-01, with an explicit warning that embeddings might still be live.** That warning was correct — confirmed live today. The original blocklist (`services/qdrant/source_policy.py`) only matched the old PDF filename identity and never caught this re-ingestion under a different `source_url`. | Sri Preethaji & Sri Krishnaji / Sounds True (publisher) | none on file | **Unconfirmed — live in production, was believed purged. Blocklist gap fixed this session (see below); underlying rights question is unresolved.** |

Totals do not sum to 14,033 exactly: `source_type` is only present on 9,389 of
14,033 points (the rest are RAPTOR summaries, LightRAG-fused GraphRAG
injections, or other derived content without an original `source_type`
stamp); `content_type=book` (1,171 in the schema-level index count) and the
1,199 exact-match on this one Amazon `source_url` differ slightly because the
index count reflects an earlier snapshot moment — re-verify with the facet
commands above before relying on an exact figure.

## Two YouTube playlists used for bulk ingestion

`scripts/ingestion/ingest_youtube_seeds.py:31-34` names the two primary
ingestion playlists (channel/owner not re-verified by this pass — verify
against the live YouTube URLs before registering):

```
https://www.youtube.com/playlist?list=PLOVU2e0ZosYCZoSlsJgsCRwAKSn9k1YuK
https://www.youtube.com/playlist?list=PLOVU2e0ZosYBGXFR_4jCmVntbgBa3sx1y
```

Plus `scripts/ingestion/all_ingest_urls.txt` — 763 individual video URLs — and
`scripts/ingestion/ingestion_state.json`'s `processed_videos` list — 717 video
IDs successfully ingested (IDs only, no channel metadata recorded in that
file; the live Qdrant payload above is the best available source of channel
attribution).

## Meditations / other content_type values live in the same collection

`content_type` facet: `video_enhanced` 9,215, `summary` 3,473 (RAPTOR-generated,
not original source — see provenance section above), `book` 1,171, `contextual`
174. No separate "meditation" or "audio" content_type was found; guided
meditations, per `PLAN.md` and root `CLAUDE.md`, are template-driven
(`backend/rag/meditation.py`, `src/components/meditation/`), not a distinct
ingested corpus — no additional rights entries needed for that surface as of
this pass.

## Git history: copyrighted files ever committed (see CONTENT-RIGHTS.md for full detail)

1. `The_Four_Sacred_Secrets.pdf` — already documented in `CONTENT-RIGHTS.md`,
   scrubbed via `git-filter-repo` 2026-08-01. **New finding this pass: the same
   content is live again in Qdrant under a different ingestion source** (see
   table above) — the git-history scrub did not, and could not, remove
   already-derived vector embeddings.
2. **New finding, not previously documented anywhere in this repo:** two
   pirated technical-book PDFs plus their full-text OCR/extraction `.txt`
   files were committed at repo root in commit `99805e84` (2026-05-15,
   "Fix production glitches..."):
   - `RAG Made Simple The Complete Visual Guide to Retrieval-Augmented
     Generation (Nir Diamant) (z-library.sk, 1lib.sk, z-lib.sk).pdf` (+ 2 `.txt`
     extraction files)
   - `System Design for the LLM Era.pdf` (+ 2 `.txt` extraction files)

   These are unrelated to the AskMukthiGuru RAG corpus (they were reference
   material for the coding agent itself, matching `agents-book-rag-made-simple`
   / `agents-book-system-design-llm-era` in `.claude/rules/ecc/`) — but they
   are copyrighted works, the source filename literally names two piracy
   sites, and **`99805e84` is a pushed ancestor of `origin/main`**
   (`git merge-base --is-ancestor 99805e84 origin/main` confirms it), so the
   full binaries and full-text extracts are permanently retrievable from the
   public GitHub repo's history. They were removed from the working tree in a
   later commit (`b2124244`, normal `git rm`, not a history scrub) — the blobs
   remain in history.

   **Proposed commands for a human to run** (do not run these yourself — see
   `CONTENT-RIGHTS.md`'s Decisions Needed section; this rewrites shared history
   on a repo with a remote, needs coordination, and per this agent's mandate
   history is never rewritten or force-pushed by the agent):

   ```bash
   # 1. Back up first (this is destructive to history):
   git clone --mirror https://github.com/Harshodai/askmukthiguru-8119b0e8.git backup-mirror

   # 2. Scrub, same tool/pattern already used for The_Four_Sacred_Secrets.pdf:
   git-filter-repo \
     --path 'RAG Made Simple The Complete Visual Guide to Retrieval-Augmented Generation (Nir Diamant) (z-library.sk, 1lib.sk, z-lib.sk).pdf' \
     --path 'RAG_Made_Simple_The_Complete_Visual_Guide_to_Retrieval-Augmented_Generation_Nir_Diamant_z-library.sk_1lib.sk_z-lib.sk.pdf.txt' \
     --path 'RAG_Made_Simple_The_Complete_Visual_Guide_to_Retrieval-Augmented_Generation_Nir_Diamant_z-library.sk_1lib.sk_z-lib.sk.pdf_deep.txt' \
     --path 'System Design for the LLM Era.pdf' \
     --path 'System_Design_for_the_LLM_Era.pdf.txt' \
     --path 'System_Design_for_the_LLM_Era.pdf_deep.txt' \
     --invert-paths --force

   # 3. Verify 0 commits remain (mirror the verification already done for the book):
   git log --all --oneline -- '*z-lib*' '*z-library*'

   # 4. Force-push (coordinate with every other clone/worktree first —
   #    this invalidates all existing clones' history):
   git push origin --force --all
   git push origin --force --tags
   ```

   **Verified 2026-09-22: this exact command was test-run** (not against this
   worktree or the real repo) against a disposable `git clone --no-local
   --mirror` of this worktree's `.git`, made in the session scratchpad
   (`/private/tmp/claude-501/.../scratchpad/pdftest.git`, deleted after the
   test). Result: `git log --all --oneline -- '*z-lib*' '*z-library*'
   'System Design for the LLM Era.pdf' 'System_Design_for_the_LLM_Era*'`
   returns **zero commits** afterward; `main`'s commit count (3,128) and all
   19 branches were intact and unaffected otherwise. The command above is
   confirmed complete and correct — a human still needs to run it for real,
   back up first, and coordinate the force-push with anyone else holding a
   clone.

## Qdrant purge command for the live "Four Sacred Secrets" re-ingestion (NOT run)

Precise, filter-based delete — safer than deleting by an enumerated ID list
(the exact `source_url` match already isolates precisely this re-ingestion,
verified to return exactly 1,199 points both via `points/count` and by
inspecting a sample; see above). **Read-only verification was run this
session; the delete itself was not.**

```bash
# 1. Re-verify the exact count immediately before deleting (must be re-run
#    fresh, not trusted from this document, since ingestion may have changed
#    since 2026-09-22):
curl -s -X POST http://localhost:6333/collections/spiritual_wisdom_contextual/points/count \
  -H 'Content-Type: application/json' \
  -d '{"filter": {"must":[{"key":"source_url","match":{"value":"https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319"}}]}, "exact": true}'
# Expect: {"result":{"count":1199},...} (or the freshly re-verified number)

# 2. Snapshot the collection first (rollback path) -- see
#    scripts/ops/qdrant_backup.py / backend/scripts/ops/backup_qdrant.py, or
#    directly:
curl -s -X POST http://localhost:6333/collections/spiritual_wisdom_contextual/snapshots

# 3. Delete by the same filter (idempotent -- safe to re-run; matches 0 the
#    second time):
curl -s -X POST http://localhost:6333/collections/spiritual_wisdom_contextual/points/delete \
  -H 'Content-Type: application/json' \
  -d '{"filter": {"must":[{"key":"source_url","match":{"value":"https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319"}}]}}'

# 4. Verify 0 remain:
curl -s -X POST http://localhost:6333/collections/spiritual_wisdom_contextual/points/count \
  -H 'Content-Type: application/json' \
  -d '{"filter": {"must":[{"key":"source_url","match":{"value":"https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319"}}]}, "exact": true}'
# Expect: {"result":{"count":0},...}
```

This does not touch any other point (the filter is an exact match on one
specific `source_url`) and does not require the blocklist code change above —
the two are independent remediations (one drops it from the live index
permanently; the other stops it from being served if it re-enters the index
some other way in the future). Neither was executed by this agent — purge
timing/whether-to-purge-at-all is the human decision flagged in
`CONTENT-RIGHTS.md` and the final report.

## Ruthless full-repo hunt, 2026-09-22 (round 2, beyond Qdrant payload)

Full git-history scan across **every ref** (`git log --all --diff-filter=A --name-only`)
for every ever-committed file of type: `.pdf .epub .mobi .djvu .azw3 .doc .docx
.ppt .pptx`. Result: **no new pirated documents found** beyond the 2 PDFs
already reported (`RAG Made Simple...`, `System Design for the LLM Era.pdf`,
commit `99805e84`) and the one already-scrubbed book
(`The_Four_Sacred_Secrets.pdf`, not visible to `git log` post-scrub, as
expected). Also grepped all ever-added filenames for piracy-site markers
(`z-lib`, `1lib`, `libgen`, `annas-archive`, `scribd`, `sci-hub`, `b-ok`,
`bookzz`, `epdf`) — zero additional hits.

Audio/video ever committed (`.mp3 .wav .m4a .flac .ogg .mp4 .mov .avi .mkv`):
`public/media/askmukthiguru-product-demo-instrumental.mp3` (background music
track for a product demo) and several own-product screen-recording demo
`.mp4` files (`askmukthiguru-official-launch-demo.mp4`,
`brag-demo-*.mp4`). The demo videos are the org's own screen recordings — no
third-party rights concern identified. **The music track's license was NOT
verified this pass** — if it is a stock/library track, its license (may
require attribution, may be one-project-only) should be confirmed before any
public release; flagging as a new open item, not resolving it.

**New finding — an "approved image" with zero rights documentation:**
`src/assets/gurus-photo.jpg` — an actual photograph of Sri Preethaji & Sri
Krishnaji, rendered in three places (`MeetTheGurusSection.tsx`,
`DesktopSidebar.tsx`, `MobileConversationSheet.tsx`). `CLAUDE.md`'s own data
source line ("Sri Preethaji & Sri Krishnaji's YouTube videos + approved
images") implies this was cleared, but nothing in `CONTENT-RIGHTS.md` recorded
that before this pass — added to the register below. `src/assets/hero-spiritual.jpg`/`.webp`
(a generic spiritual-themed hero background, not obviously a photo of the
gurus) was also not checked for a stock-photo license — flagged, not resolved.

| Asset | Format | Rights Basis | Rights Holder | Status |
|---|---|---|---|---|
| `src/assets/gurus-photo.jpg` (photo of the gurus, 3 UI locations) | JPEG, committed to repo | Unconfirmed — no license/permission on file despite being implied "approved" in `CLAUDE.md` | Sri Preethaji & Sri Krishnaji / Ekam | **Unconfirmed** |
| `src/assets/hero-spiritual.jpg` / `.webp` (generic hero background) | JPEG/WebP, committed to repo | Unconfirmed — origin (stock/AI-generated/licensed) not established this pass | Unknown | **Unconfirmed** |
| `public/media/askmukthiguru-product-demo-instrumental.mp3` | MP3, committed to repo | Unconfirmed — stock/library music license not verified | Unknown | **Unconfirmed** |

## Serve-time enforcement added this session

`backend/services/qdrant/source_policy.py`:
- Extended `is_blocked_source()` to also match the book's Amazon ASIN
  (`1846046319`, substring of `source_url`) and its title prefix ("the four
  sacred secrets", casefolded) — closing the concrete gap that let the
  1,199-chunk re-ingestion above bypass the existing filename-only blocklist.
  Wired at the same chokepoint as before: `backend/rag/nodes/retrieval.py:1959`
  (`filter_blocked_sources`), which the code's own comment already documents
  as the point covering every candidate document channel (Qdrant, GraphRAG,
  OKF, web, fallback).
- Added `is_registered_source()` / `filter_unregistered_sources()` — an
  allowlist gate requiring `domain_rights_status == "cleared"` (a value
  distinct from the blanket `"licensed"` ingestion default; only set by a
  human-run backfill after a source is confirmed in this register). Gated by
  new flag `settings.serve_only_registered_sources` (`backend/app/config.py`),
  **default `False`** — see that flag's docstring for why defaulting it on was
  not this agent's call to make (it would currently block essentially the
  entire live corpus, since nothing is yet marked `"cleared"`).
- Tests: `backend/tests/test_domain_rights_read_gate.py` — added
  `test_book_reingested_under_amazon_url_is_also_blocked` and
  `test_serve_only_registered_sources_gate`. Verified passing by direct module
  execution (this worktree's Python has no project venv / `dotenv` installed,
  so `pytest` itself cannot run against the full `conftest.py` here — see the
  session report for the exact commands run and output).

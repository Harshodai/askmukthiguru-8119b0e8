# 14c — Content permissions and intellectual-property register

> **2026-11-06:** Superseded in part by `specifications/GURU_KNOWLEDGE_AND_KNOWLEDGE_GRAPH_SPEC.md` (where rights live in the registry and how serving checks them). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: S4. Audit target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`. Security and privacy: doc 14 (S1). Safety: doc 14b (S3).

I am not a lawyer. This document reports facts and risks. Legal conclusions need qualified counsel ([HUMAN]).

---

## 1. Facts that frame every rights question

| # | Fact | Evidence |
|---|---|---|
| F1 | The GitHub repository is public. A logged-out visitor sees the files. | [V-WEB] `https://github.com/Harshodai/askmukthiguru-8119b0e8`, accessed 2026-11-04: page labelled "Public". Task list §2 N1 says the same [DOC-CLAIM]. |
| F2 | The project's own policy forbids committing copyrighted audio and text without a documented basis. | `docs/rights/CONTENT-RIGHTS.md` "Policy" and "Asset Storage Policy": "Copyrighted PDF/EPUB/audio assets must NOT be committed to the git repository." [V-STATIC] |
| F3 | The rights decision recorded on 2026-11-04 is scoped to owner-only local review. | `FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md` `b5_rights_register`, commit `26209a3b` message "owner_only_local_review scope" [V-STATIC, V-GIT] |
| F4 | The written approval from the content owner is not in the repository. The register records the owner's statement that it exists. | `docs/rights/CONTENT-RIGHTS.md` "Written evidence" [V-STATIC] |
| F5 | Source audio is downloaded from YouTube with `yt-dlp`, using `--extractor-args youtube:player_client=android,ios,mweb,web`. Root `CLAUDE.md` invariant 17 describes this as a way "to eliminate YouTube 429 bot challenges". | `scripts/ops/audio_archive.py:614–623` [V-STATIC] |
| F6 | YouTube's Terms of Service (effective 15 December 2023) forbid downloading content and accessing the service by automated means, except as expressly authorised by the service or with YouTube's prior written permission. | [V-WEB] `https://www.youtube.com/static?template=terms`, accessed 2026-11-04, "Permissions and Restrictions" items 1 and 3 |

Consequence of F1 + F2 + F3: any teaching text or teacher audio in tracked files is publicly redistributed. That goes beyond the recorded scope of "owner-only local review".

---

## 2. Rights documents in the repository

| Document | What it covers | Status |
|---|---|---|
| `docs/rights/CONTENT-RIGHTS.md` (44 lines) | Policy, registered content table, asset storage policy, written-evidence note | Rights for the teachers' channels, the Four Sacred Secrets book and Times Now are "confirmed by project owner". Not independently verified. |
| `docs/rights/source-register.md` | Inventory of a 14,033-point chat corpus by channel | Lists Times Now (353 points) as "Unconfirmed. Third-party news re-broadcast" (line 39) while `CONTENT-RIGHTS.md` lists it as approved by owner statement. The two documents disagree. [V-STATIC] |
| `docs/rights/approval-request-drafts.md` | Draft approval requests | Drafts, "unsent" per `CONTENT-RIGHTS.md`. |
| `docs/agent/GATES.md` | Gates G0–G6 with human owners | No sign-off lines are filled. The `docs/agent/gates/` evidence folder does not exist. [V-STATIC] |
| `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json` | 751 assets with a rights status | Decision form summary: 702 confirmed channel owner, 2 confirmed video owner, 1 pending, 46 missing evidence [DOC-CLAIM]. |
| `backend/scripts/ops/build_fp_rights_register.py` + tests | Builds the register and serve-time rights lookup | Exists and is tested. Its inputs are owner statements, not filed documents. |

---

## 3. Public exposure of teaching content (tracked files)

| Item | Size | Content | Evidence |
|---|---|---|---|
| `audits/evidence/public_release_v10_points_export_2026-10-21.json` | 7.9 MB | Full payload export of 2,737 `first_person_v10` points, each with `verbatim_text` and `source_transcript_text`, plus video ids and timestamps. It also contains the owner's local absolute paths. | [V-STATIC] `jq '.result.points | length'` = 2737; payload keys include `verbatim_text`, `source_transcript_text` |
| `audits/evidence/public_release_phase4_tier_*.jsonl`, `public_release_phase3_*.jsonl`, `public_release_v10_ecapa_reconciliation_*.jsonl` | 5–12 MB each | Per-span records including `live_verbatim_text`, video ids, `audio_path` under `/Users/harshodaikolluru/...` | [V-STATIC] |
| `memory/okf/**` | 1,546 tracked files; `compiled.json` 10.9 MB | OKF entries. Task list §2 N1 reports a sampled entry with a "Verbatim Discourse Excerpts" section [DOC-CLAIM]. Root `CLAUDE.md` invariant 12: OKF is 97% LLM-extracted summary. | [V-GIT] `git ls-tree` count |
| `data/neo4j_graph_dump.json` and `data/*_backup_*.json` | up to 8 MB | Graph dump and Qdrant chunk backups. Content mix not fully inspected. | [V-STATIC] header read only |
| `public/audio/meditation/preethaji-serene-mind.mp3` | 3.77 MB | Sri Preethaji's voice extracted from YouTube video `igSp4H0OWLE` | `src/components/meditation/meditationSteps.ts:14–22` [V-STATIC]; added in commit `8da365a3` on 2026-11-03 [V-GIT] |
| `src/assets/meditation/preethaji-serene-mind.mp3.asset.json` | — | The same audio uploaded to a Lovable asset store (`r2_key a/v1/8733a2b9-…/preethaji-serene-mind.mp3`) | [V-STATIC] |
| `docs/media/askmukthiguru-official-launch-demo.mp4` | 14.2 MB | Product demo video. Content not inspected. | [V-GIT] |
| `public/media/askmukthiguru-product-demo-instrumental.mp3` | 1.6 MB | Background music. `CONTENT-RIGHTS.md`: "Unconfirmed — stock/license origin not established". | [V-STATIC] |

The repository-wide `.gitignore` already excludes `evals/gold_set_v1/*.csv` because of the public exposure (`.gitignore:391`). The same protection was not applied to `audits/evidence/` or `public/audio/`.

---

## 4. Findings

### IP-001 — The serving corpus's verbatim teaching text is published in the public repository
| Field | Value |
|---|---|
| Pillars | P4, P3 |
| Category | Content rights |
| Severity | P0 |
| Type | Confirmed defect (facts). Legal consequence unknown. |
| Confidence | High on the facts |
| Evidence | §3 rows 1–2; F1, F3 |
| Actual behaviour | Anyone can download the full verbatim transcript text of 2,737 spans, with video ids and timestamps. |
| Expected behaviour | Teaching text leaves the private stores only through the product, within the approved scope. |
| Root cause | Audit evidence was committed as raw exports. No guard blocks text payloads from `audits/evidence/`. The publication guard (`scripts/guards/lesson_guards.py`, `publication_allowlist.txt`) did not catch these files. |
| User impact | The teachers' organisation could see its material redistributed without consent. That damages the trust needed for any guru review. |
| Downstream impact | Git history keeps the files after deletion. Removal needs history rewriting or making the repository private. |
| Dependencies | Owner decision: make the repository private, or rewrite history ([HUMAN]). |
| Remediation | 1. Make the repository private, or move evidence to a private store. 2. Remove text payloads from tracked evidence; keep ids and hashes only. 3. Extend the publication guard to reject `verbatim_text`, `source_transcript_text` and `live_verbatim_text` keys in tracked files. |
| Acceptance criteria | `git grep -l '"verbatim_text"'` returns no tracked data file. The guard fails a test commit containing the key. |
| Regression test | Guard unit test with a fixture JSON containing `verbatim_text`. |
| Implementation risk | Medium: history rewrite affects every clone and open PR. |
| Verification | [V-STATIC], [V-WEB] |

### IP-002 — Teacher voice audio is extracted from YouTube and published without a rights record
| Field | Value |
|---|---|
| Pillars | P4 |
| Category | Voice and likeness |
| Severity | P1 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `meditationSteps.ts:14–22` ("Preethaji's own voice, extracted from the canonical Serene Mind YouTube video (igSp4H0OWLE)"); `SereneMindModal.tsx:671` (`PREETHAJI_AUDIO_URL`); `CONTENT-RIGHTS.md` has no row for this audio; F2, F6 |
| Actual behaviour | The app plays the teacher's voice in its own meditation feature. The file is public in Git and copied to a third-party asset store. |
| Expected behaviour | Voice use has a written licence from the rights holder that names the use (in-app meditation audio). The file is served from an access-controlled store. |
| Root cause | The feature was built before the rights check (commit `8da365a3`, 2026-11-03). |
| User impact | If the teachers object, the feature must be withdrawn. |
| Remediation | Remove the file from public locations. Add a rights row. Ask the teachers' organisation for a licence or an official audio file (D2 in doc 23). Until then, use the existing silent text-and-flame fallback that `public/audio/meditation/README.md` describes. |
| Acceptance criteria | No teacher audio in tracked files. A rights row with written evidence exists before the feature re-enables. |
| Regression test | Publication guard rejects `*.mp3`/`*.wav` under `public/` unless allowlisted with a rights id. |
| Implementation risk | Low. |
| Verification | [V-STATIC], [V-GIT] |

### IP-003 — The rights basis rests on owner statements; no written approval is filed
| Field | Value |
|---|---|
| Pillars | P4 |
| Category | Rights evidence |
| Severity | P1 |
| Type | Unverified assumption |
| Confidence | High on absence |
| Evidence | F4; root `CLAUDE.md` "Before going public" item 2 requires "a written message from Venkatesh OWA or Ekam naming the content and the use". |
| Remediation | File the written approval in a private evidence store, referenced by sha256 from the register. The approval names the channels, the uses (serving clips, displaying transcripts, translation, voice in meditation, storage location) and the term. |
| Acceptance criteria | Each served channel row points to a filed approval hash. |
| Verification | [V-STATIC]; content [HUMAN] |

### IP-004 — Source acquisition conflicts with YouTube's terms unless written permission exists
| Field | Value |
|---|---|
| Pillars | P4, P1 |
| Category | Acquisition |
| Severity | P1 |
| Type | Architectural risk |
| Confidence | Medium (the terms are clear; whether permission exists is unknown) |
| Evidence | F5, F6 |
| Actual behaviour | Automated bulk download with client spoofing to avoid bot challenges. |
| Expected behaviour | Source media comes from the rights holder (for example, original files from the organisation), or from YouTube with its written permission. |
| Root cause | No content-supply agreement. |
| User impact | Ingestion can stop if YouTube blocks the client, and the teachers' organisation may object to the method. |
| Remediation | Ask the organisation for original media files or an export (doc 23 D1). Record the source of each archived file in the audio manifest (`supplied_by`, `permission_ref`). |
| Acceptance criteria | Every archived WAV has a `permission_ref`. |
| Verification | [V-STATIC], [V-WEB] |

### IP-005 — Third-party broadcaster and interview content is treated as teacher content
| Field | Value |
|---|---|
| Pillars | P4 |
| Category | Third-party rights |
| Severity | P2 |
| Type | Architectural risk |
| Confidence | Medium |
| Evidence | `CONTENT-RIGHTS.md` rows for Times Now (353 points), TEDx (`TqxxCYnAxo8`), MarieTV (`UlOt31lBhLY`): each "confirmed by project owner". `source-register.md:39` calls Times Now "Unconfirmed … a materially different rights" situation. |
| Actual behaviour | Approval from the teachers is recorded as covering content whose copyright holder is the broadcaster or host. |
| Expected behaviour | Each channel's copyright holder is identified and its permission recorded separately. |
| Remediation | Mark broadcaster content `pending_owner_review` at serve time until the broadcaster's permission is filed. |
| Acceptance criteria | The rights lookup returns non-servable for broadcaster channels without a filed permission. |
| Verification | [V-STATIC] |

### IP-006 — Seed data defines other teachers and a "private teachings" persona with no rights basis
| Field | Value |
|---|---|
| Pillars | P4 |
| Category | Scope and impersonation |
| Severity | P2 |
| Type | Confirmed defect (dormant data) |
| Confidence | High |
| Evidence | `supabase/migrations/20260703170000_gurus_and_configurations.sql:52–70` seeds `sadhguru` ("Founder of Isha Foundation") and `iskcon`, with system prompts "speaking from the perspective of Sadhguru…". `supabase/migrations/20260621033728_…sql:94–106` seeds `sky` "SKY Teachings (Private) — Unreleased private teachings — invite only". `backend/services/prompt_store.py:45` holds a Sadhguru tone ("direct, earthy, and pragmatic tone of a yogi"). `backend/services/teacher_attribution.py:7` states "No Sadhguru, ISKCON, or Amma Bhagavan talks exist" in the corpus. |
| Actual behaviour | The backend fails closed on non-allowlisted assistants (`backend/app/assistant_authorization.py:242` raises 403). The data still exists and could be enabled by configuration. |
| Expected behaviour | No persona of any teacher exists without a rights grant and a corpus. |
| Remediation | Remove the `sadhguru`, `iskcon` and `sky` seeds and the Sadhguru tone string, with a migration and a test. |
| Acceptance criteria | `rg -i "sadhguru|iskcon" supabase backend/services` returns only the external-teacher detection regex in `teacher_attribution.py` and its tests. |
| Verification | [V-STATIC] |

### IP-007 — Licence of demo music, hero images and demo video is unconfirmed
| Field | Value |
|---|---|
| Pillars | P4 |
| Severity | P3 |
| Type | Unverified assumption |
| Evidence | `CONTENT-RIGHTS.md` last table row: "Unconfirmed — stock/license origin not established". The demo MP4 is not listed. |
| Remediation | Record a licence or replace the assets. |
| Verification | [V-STATIC] |

### IP-008 — Tracked evidence files leak the owner's local paths and username
| Field | Value |
|---|---|
| Pillars | P4 (privacy) |
| Severity | P3 |
| Type | Confirmed defect |
| Evidence | `audio_path: /Users/harshodaikolluru/mukthiguru_attribution_data/...` in tracked JSONL files [V-STATIC] |
| Remediation | Store paths relative to a configured archive root. |
| Verification | [V-STATIC] |

Unsourced quotations attributed to the teachers are an attribution problem, not only an IP problem. See GURU-012 in doc 11.

---

## 5. Translation rights

- The product UI ships 14 locales (`src/locales/*.json`) [V-STATIC].
- Root `CLAUDE.md` invariant 16: quotes are never translated; only glue text is translated.
- No rights document mentions translation [V-STATIC: `rg -n translat docs/rights` returns nothing].
- Risk: if a later feature shows machine-translated transcripts, it creates a derivative work and can misstate the teaching. Translation rights need an explicit decision (doc 23 D3).

---

## 6. Unresolved-permissions register

| # | Item | Risk | Evidence | Decision owner | Decision needed |
|---|---|---|---|---|---|
| U1 | Public repository holds verbatim transcripts (IP-001) | Unauthorised redistribution; loss of teacher trust | §3 | Project owner | Make private and/or rewrite history |
| U2 | Teacher voice in meditation audio (IP-002) | Voice/likeness use without licence | §4 | Teachers' organisation | Grant licence or supply audio; else withdraw |
| U3 | Written approval for serving clips (IP-003) | Rights basis unverifiable | `CONTENT-RIGHTS.md` | Teachers' organisation (named contact) | Written approval naming content, uses, term |
| U4 | YouTube acquisition method (IP-004) | Terms violation; supply instability | `audio_archive.py` | Project owner + organisation | Obtain source files or written permission |
| U5 | Times Now, TEDx, MarieTV content (IP-005) | Third-party copyright | `source-register.md:39` | Each broadcaster/host | Permission or exclusion |
| U6 | Transcript display as text | Display of full transcripts beyond clip playback | API returns `verbatim_text` | Teachers' organisation | Approve or limit to playback |
| U7 | Translation of glue text around quotes; any future quote translation | Derivative work; misstatement | §5 | Teachers' organisation | Approve scope |
| U8 | Teacher photo (`src/assets/gurus-photo.jpg`) | Likeness | `CONTENT-RIGHTS.md` (covered by owner statement) | Teachers' organisation | Confirm in writing |
| U9 | The Four Sacred Secrets book text (1,199 chunks per register) | Book copyright (publisher) | `CONTENT-RIGHTS.md` row 1 | Publisher + authors | Confirm publisher permission, not only authors' |
| U10 | Demo music, hero images, demo video (IP-007) | Licence | `CONTENT-RIGHTS.md` | Project owner | Record licence or replace |
| U11 | Other-teacher seeds (IP-006) | Impersonation | migrations | Project owner | Remove |
| U12 | Storage of seekers' conversations that quote teachings | Low IP risk; privacy owned by doc 14 | — | Project owner | Retention policy (doc 14) |

## Cross-references

- Gate verification and guru-review package: `23-guru-review-and-release-readiness-package.md`
- Teacher registry and attribution of quotations: `11-krishnaji-preethaji-future-guru-extensibility.md`
- Data lineage of the audio archive: `06-data-ingestion-quality-lineage.md` (S2)
- Repository security and secrets: `14-security-safety-privacy-permissions.md` (S1)

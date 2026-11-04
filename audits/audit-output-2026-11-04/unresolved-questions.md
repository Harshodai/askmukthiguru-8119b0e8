# Unresolved questions register

Owner: lead. Each row needs a person, live infrastructure, or both. Agents must not answer these by assumption. Record answers in `decision-log.md` §3.

## 1. Owner decisions (block roadmap tasks)

| ID | Question | Why it matters | Blocks | Raised in | Recommendation |
|---|---|---|---|---|---|
| D-01 | Make the repository private now? Purge tracked content? Rewrite history? | Public exposure of ~2,737 verbatim spans, transcripts, teacher audio, backups (P0) | T0-01, T0-02 | 01, 14c | Make it private today. Decide the history rewrite after advice. |
| D-02 | Keep the 1,546 tracked OKF teaching files in the repository? | They contain teaching summaries and some verbatim excerpts | T0-02 | 14c | Move them to the private store with the corpus. |
| D-03 | ADR-001: allow a clearly labelled assistant explanation layer (L3/L5) beside verbatim quotes? | The mission requires synthesis and explanation. Invariants 15/21 forbid any generated text. | T5-03 | 10, 17 | Yes, behind a flag; owner-only review first; teachers' organisation consent before public. |
| D-04 | ADR-002: keep a general assistant for non-teaching questions? | It is the leak target for misrouted teaching questions | T4-03 | 05, 10 | Static boundary for faculty review and beta. |
| D-05 | ADR-005: retire Memgraph and LightRAG from serving and deploy? | Infrastructure cost; no measured value; no provenance | T3-11 | 08 | Yes; freeze data; ablate later. |
| D-06 | ADR-006: engage a clinician for the topic-vs-state discriminator and test sets? Is `FIRST_PERSON_DISTRESS_SERVE_CLIP_ENABLED=true` meant for production? | The anxiety question gets a template today | T4-04 | 10, 14b | Yes; ship only with written clinician sign-off. |
| D-07 | Does any client use `/api/first-person/query`? Admin-only? | Unauthenticated LLM spend | T1-08 | 14 | Admin-only unless a client needs it. |
| D-08 | ADR-008: where do private evidence and the source bundle live? May audio and transcripts be stored there under the rights terms? | Reproducibility; verifiable sign-offs | T3-09 | 06, 23 | Private bucket + private evidence repo, referenced by hash. |
| D-09 | Who produced the 303-row gold sheets? Were annotators A and B two independent humans? | The reports say `independent_review:false` | T1-11, T2-04 | 18, 23 | Treat them as non-independent; commission a new double-blind set. |
| D-10 | Do the clinician artefact and the content owner's written message exist outside the repository? | Both approvals exist only as strings | T1-11, T10-02 | 23, 14b | File them privately, by hash. |
| D-11 | Intended scope of the 2026-11-04 authorisation: owner-only local review, or public? | Machine scopes say public; notes say NO-GO | T0-04 | 23 | Correct the scopes to owner-only local review. |
| D-12 | Did the teachers' organisation authorise extracting Sri Preethaji's voice for Serene Mind? | Voice and likeness rights | T0-02 | 14c | Remove until a licence is filed. |
| D-13 | Is the `channel:times-now` (and other broadcaster) clearance intentional and filed? | Third-party rights | T3-06 | 06, 14c | Non-servable until the broadcaster permits. |
| D-14 | Which collection does your local `.env` serve (v8, v9, v10)? Which one is intended for faculty? Is "transcript-v2" the served corpus? | Docs and code disagree (invariants 23 vs 25; DATA-16) | T3-05, T9-01 | 06, 08 | Pin one collection in the release record; startup check. |
| D-15 | Who besides the builder writes to Qdrant? May API keys be turned on? | v11 re-verification incident | T3-02 | 06 | Turn on keys; builder-only write key. |
| D-16 | Which relevance-scorer model and price should be budgeted? | Price not recorded in code | T1-07, T4-06 | 09, 15 | Record a dated price entry; consider the consolidated judge. |
| D-17 | Remove the Sarvam, Ollama and NIM provider code? | Three non-sharing provider stacks | T7-03 | 13 | Keep OpenRouter + one local fallback only. |
| D-18 | May `ToneAdapterStage` and the listed dormant modules be deleted? (Root `CLAUDE.md` forbids it today.) | Dead code cost | after T7-06 | 13 | Delete after the graded run. |
| D-19 | Delete the churn funnel and win-back emails? | Dark pattern at deletion | T1-12 | 12b | Yes. |
| D-20 | Were the Sadhguru, ISKCON and "SKY private teachings" personas ever intended? | Impersonation risk; no rights | T1-04 | 11 | Remove the seeds. |
| D-21 | Should healing-course assignment and proactive Serene Mind be on by default? | They run without the consent gate | T1-10 | 12 | Off by default; opt-in. |
| D-22 | Which four Indic languages are the priority for native crisis and teaching sets? | Native review scope | T2-01, T4-04 | 14b | Owner choice. |
| D-23 | May real seeker questions from logs be used for the held-out set? Under what consent terms? | Realistic evaluation | T2-04 | 18 | Only with explicit opt-in and redaction. |
| D-24 | What is Lovable's role? Merge or delete `lovable-sync`? | Two writers on the frontend | T0-07 | 01 | One PR-based path. |
| D-25 | Add a usefulness target to the pass bar? Is 70% abstention on answerable questions acceptable? | The bar measures abstention, not help | T2-01 | 18 | Add usefulness; keep a served-share floor. |
| D-26 | Qdrant hosting: a Railway service with a volume, or Qdrant Cloud? | Ops burden, backups, keys | T9-01 | 22b | Decide with cost data at staging. |
| D-27 | **Decided 2026-11-04: committed under `audits/audit-output-2026-11-04/`.** Commit this audit package? Where? | The container is temporary; the repo's clean-root rule puts audits under `audits/` | — | 27 | Commit under `audits/audit-output-2026-11-04/` on a fresh branch from `main`. |

**T7-01 sub-decisions — all four answered by the owner on 2026-11-05** (see `decision-log.md` §3):

| ID | Question | Answer |
|---|---|---|
| Q-T7-01-A | Golden-output evidence: offline matrix, frozen bank, or live run? | Offline characterization matrix on fixture stores; `frozen29`/`ooc13` as inputs only; labelled "not the frozen bank" |
| Q-T7-01-B | One large refactor PR or several small ones? | One refactor PR, exempt from the ≤400-line cap, no logic edits, per-commit diff shown before each push |
| Q-T7-01-C | Which routes and which fields does "identical" cover? | Every early-return exit + serve + weak match + error + context-harness serve; all `to_dict()` fields except `latency_ms`, `stage_timings` |
| Q-T7-01-D | Split the 735-line Step 2c block internally? | No — move it whole into one named step; internal split is a follow-up finding |

## 2. Unknowns that need live infrastructure (not decisions)

| ID | Unknown | Label | Procedure |
|---|---|---|---|
| L-01 | Actual point counts, payload fields and duplicates in each collection | [LIVE-Q] | `22` §2–§5 |
| L-02 | Hash and ID recomputation results on the served collection | [LIVE-Q] | `22` §6 |
| L-03 | Real p50/p95 latency, error rate and cost per turn on a deployed stack | [LIVE-R] | `22b`; T9-02 |
| L-04 | Whether the frontend live bundle calls the dead Railway URL | [LIVE-R] | `22b` smoke step [DOC-CLAIM task list §2 N6] |
| L-05 | The owner's local `.env` flag values | [LIVE-L] | Owner exports a redacted flag list |
| L-06 | Contents and authorship of the gitignored annotator sheets | [LIVE-L] [HUMAN] | Owner shares hashes and provenance (D-09) |
| L-07 | Supabase production RLS state versus migrations | [LIVE-R] | Supabase advisors + schema diff (T3-08) |
| L-08 | Failing Playwright specs on Firefox, WebKit, Mobile Safari | [V-GIT] artifacts | Download artifacts 13341258070, 13341881915, 13341572949 |

## 3. Human-only gates (unchanged; tracked by the owner)

These come from the repository's own list. The audit does not remove any of them.

| Gate | Status |
|---|---|
| Native-speaker review of crisis patterns and locales | Pending |
| Clinician review (crisis copy, discriminator, dependency rule) | Pending (b6 recorded as a string only) |
| ≥299 independent gold labels | Pending (D-09) |
| Helpline phone verification (never test-call 112) | 1/15 done |
| Written rights approvals (content owner; broadcasters; audio) | Not filed (D-10, D-12, D-13) |
| Backup archive copied off the Mac | Pending |
| Railway login, secrets, Qdrant decision | Pending (D-26) |
| Store accounts (mobile) | Pending |

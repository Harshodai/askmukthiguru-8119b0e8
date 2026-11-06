# Findings index (stable IDs)
2026-11-05 status: see FINAL_PENDING_WORK_REGISTER.md for the per-finding status after the remediation commits (head c9b42d3e).

Owner: lead. Scope: every finding in this audit package, with the lead's reconciled severity (after the independent review in `26`) and the roadmap task that closes it.

- Full finding records live in the owning document (column "Doc").
- "Sev" is the reconciled severity. Changes from the specialist's severity are explained in `16` §4 and `26` §7.
- "Task" points to `20-ordered-engineering-roadmap.md`. "HUMAN" means a person must act.
- Types: CD = confirmed defect; PD = probable defect; AR = architectural risk; PG = product gap; UA = unverified assumption; ST = strength.
- Root-cause clusters RC-1 … RC-9: `16` §2. Independent verification of 16 critical claims: `26` §2.
- Evidence categories (the seven classes in the mission): `CONVENTIONS.md` §3b.

## P0 — critical (2 findings, one root cause)

| ID | Title | Type | Pillars | RC | Doc | Task | Note |
|---|---|---|---|---|---|---|---|
| X-06 | Public repository holds teaching content and operational data | CD | P4,P1 | RC-7 | 01 | T0-01, T0-02 | Raised P1→P0 with IP-001 |
| IP-001 | Verbatim text of 2,737 served spans published in the public repo (reviewer counted 2,737 non-empty `verbatim_text`) | CD | P4,P3 | RC-7 | 14c | T0-01, T0-02 | Reviewer proposed P1; lead keeps P0 (`26` §7): the exposure is ongoing, irreversible, and cheap to stop |

## P1 — major release or experience blockers (45)

| ID | Title | Type | Pillars | RC | Doc | Task | Note |
|---|---|---|---|---|---|---|---|
| X-01 | Release-gate claim not reproducible on a clean checkout; `main` red | CD | P4,P3 | RC-2 | 01 | T0-04, T1-11 | |
| GURU-001 | "24/24 PASS" not reproducible (gold sheets gitignored) | CD | P4,P1 | RC-2 | 23 | T0-04, T1-11 | S4 P0 → P1 (reviewer); same defect as X-01 |
| GURU-002 | Non-independent "consensus" labels accepted as human gold | CD | P4,P2 | RC-2 | 23 | T1-11, T10-02 | S4 P0 → P1 (reviewer) |
| EVAL-001 | Release gate accepts unverifiable, non-independent gold | CD | P4,P6 | RC-2 | 18 | T1-11 | |
| X-02 | `main` unprotected; merges precede CI; PR-less pushes | CD | P1,P3 | RC-8 | 01 | T0-03 | |
| GURU-003 | "Staging readiness" is a local test summary; invalid commit id | CD | P4,P1 | RC-2 | 23 | T1-11 | |
| GURU-004 | Machine scopes authorise public release; notes say NO-GO | CD | P4 | RC-2 | 23 | T0-04 | |
| GURU-005 | Clinician and content-owner sign-offs exist only as strings | UA | P4 | RC-2 | 23 | T3-09, T1-11, HUMAN | |
| GURU-006 | AI subagent listed as a human audio certifier | CD | P4 | RC-2 | 23 | T1-11 | |
| GURU-007 | Helpline call verification not in the gate (1/15 verified) | PG | P4,P6 | RC-2 | 23 | T1-11, T4-07 | |
| SAFE-005 | Clinician approval evidence is an in-repo string | UA | P4 | RC-2 | 14b | T3-09, HUMAN | Raised P2→P1 with GURU-005 |
| GURU-012 | Teacher-attributed text without a verifiable locator (titles only, or paraphrase in prompts) | CD | P4,P2 | RC-3 | 11 | T1-03 | Reviewer: PARTLY (book/series titles exist; no locator) |
| IP-002 | Teacher voice audio from YouTube published with no rights row | CD | P4 | RC-7 | 14c | T0-02, HUMAN | One MP3; a human must confirm the voice |
| IP-003 | Rights basis rests on owner statements; no written approval filed | UA | P4 | RC-7 | 14c | T3-09, HUMAN | |
| IP-004 | yt-dlp acquisition conflicts with YouTube terms unless permitted | AR | P4,P1 | RC-7 | 14c | T0-05, T3-09 | |
| ANS-001 | "What is the cause of my anxiety?" gets a distress template, no teaching | CD | P2,P4 | RC-5 | 10 | T4-04 | Reviewer: CONFIRMED |
| ANS-002 | MILD words always upgraded to MODERATE in chat | CD | P2,P4 | RC-5 | 10 | T4-04 | Reviewer: CONFIRMED |
| SAFE-002 | Topic repetition escalates to SEVERE crisis pre-emption | CD | P2,P4 | RC-5 | 14b | T4-04 | Reviewer: CONFIRMED |
| SAFE-003 | Benign-question overfire accepted, not measured on a reviewed set | CD | P2,P4 | RC-5 | 14b | T4-04, T2-01 | |
| SAFE-001 | Crisis detection = unreviewed regex; semantic stages off | AR | P4,P6 | RC-5 | 14b | T4-04, T10-02 | |
| SAFE-004 | Helplines mostly not call-verified; shown on MODERATE | CD | P4 | RC-5 | 14b | T4-07, HUMAN | |
| RET-09 | Generating path stays enabled as the fail-open target | AR | P1,P4 | RC-3 | 08 | T1-05 | Raised P2→P1; concrete trigger ADV-03 |
| ADV-03 | Turning the first-person bridge off sends teaching questions to the generating "warm Guru" prompt | CD | P4,P2 | RC-3 | 26 | T1-05 | New (reviewer) |
| ANS-004 | Live path cannot compose a complete answer (one clip only) | PG | P2 | RC-6 | 10 | T5-03, ADR-001 | |
| RET-03 | No multi-video composition of evidence | PG | P2 | RC-6 | 08 | T5-02 | |
| ANS-005 | Root `CLAUDE.md` mandates teacher "I" voice; code forbids it | CD | P4,P3 | RC-3 | 10 | T1-01 | |
| DATA-01 | Serving corpus cannot be rebuilt from repo + infrastructure | AR | P1,P3,P4 | RC-4 | 06 | T3-09 | |
| DATA-02 | Rights register not in Railway image → every clip abstains | CD | P1,P4 | RC-9 | 06 | T3-01 | Reviewer: CONFIRMED (fails closed) |
| DATA-05 | v10 builder is add-only; snapshot after writes | CD | P3 | RC-4 | 06 | T3-04 | |
| DATA-06 | Uncontrolled concurrent writers to Qdrant (no API key) | CD | P1,P4 | RC-4 | 06 | T3-02, T1-14 | |
| DATA-07 | No cross-store takedown of teaching content | CD | P4,P3 | RC-4 | 06 | T3-06 | |
| DATA-14 | v10 fails its own data-quality scorecard (13/26) | CD | P2,P4 | RC-4 | 06 | T3-05 | [DOC-CLAIM] measurement |
| MEM-003 | Emotional history read and acted on without the consent gate | CD | P5,P4 | RC-1 | 12 | T1-10 | Reviewer: CONFIRMED (PD → CD) |
| UX-001 | Account deletion runs through a churn funnel with win-back emails; it is the only UI deletion path | CD | P5,P4 | RC-6 | 12b | T1-12 | Back to P1: the reviewer found the funnel mounted (`ProfilePage.tsx:583`) |
| ADV-01 | Scheduled deletions never execute (no purge job); deletion needs the backend up | CD | P5,P6 | RC-9 | 26 | T6-06, T1-12 | New (reviewer); DPDP exposure |
| SYS-003 | Sync FP pipeline blocks thread-pool workers on LLM calls | AR | P1 | RC-9 | 05 | T7-02 | |
| SYS-004 | OpenRouter spend cap off by default (the code comment says "Default enabled") | CD | P1 | RC-9 | 15 | T1-07 | Reviewer: CONFIRMED |
| SYS-006 | FP p95 12–14 s from 3 sequential LLM gates; scorer timeout 12/15/25 s across sources | CD | P1,P6 | RC-9 | 05 | T4-06, T1-07 | [DOC-CLAIM] latency |
| SYS-007 | No reproducible deployed environment, no staging | AR | P1,P6 | RC-9 | 15 | T9-01 | |
| SYS-011 | No signal separates "HTTP 200 but poor" from useful | PG | P1,P2,P5 | RC-2 | 15 | T2-03 | |
| SYS-012 | RPO unbounded for every store; backup workflow failing | CD | P1,P3 | RC-9 | 15 | T3-10 | |
| SEC-001 | `/api/first-person/query` unauthenticated, no quota, spends LLM budget | CD | P1,P4 | RC-9 | 14 | T1-08 | Reviewer: CONFIRMED |
| EVAL-002 | No held-out human-labelled set; gold questions AI-written | CD | P2,P6 | RC-2 | 18 | T2-04, HUMAN | |
| EVAL-003 | CI quality gates inert without a deployment | CD | P6,P1 | RC-2 | 18 | T2-01 | |
| PRD-006 | Seekers cannot report a wrong or misattributed clip | PG | P4,P6 | RC-6 | 03 | T6-04 | |
| UX-006 | Signed-in history is tied to one browser, capped at 10, wiped on sign-out or expiry; the cloud copy is never read back | CD | P5,P3 | RC-1 | 14d | T6-09 | New (journey pass) |
| UX-007 | No support line or client crisis fallback on any error except 503; developer text can reach seekers | CD | P4,P2 | RC-5 | 14d | T1-17 | New; lead raised P2→P1 (a crisis message during a fault shows no helpline) |

## P2 — important quality or maintainability (77)

| ID | Title | Type | Pillars | RC | Doc | Task | Note |
|---|---|---|---|---|---|---|---|
| ANS-003 | Questions mixing a general-task word with an emotion word reach the general lane | PD | P2,P3 | RC-3 | 10 | T4-03 | Lowered P1→P2: the reviewer REFUTED the broad claim; questions without keywords go to the teaching lane (`off_topic_stage.py:591-607`) |
| SYS-002 | Lane choice depends on keyword rules for the general-lane exit | AR | P2,P4 | RC-3 | 05 | T4-03, T0-05 | Lowered P1→P2 (as ANS-003) |
| AI-001 | Domain scope defined three times and disagrees | CD | P2,P3 | RC-1 | 09 | T4-03 | Lowered P1→P2: the consequence is narrower than first stated |
| SYS-001 | Node-level fall-through to generation on narrow failures (missing context, import error, error while abstaining) | PD | P2,P4 | RC-3 | 05 | T1-05 | Lowered P1→P2: the bridge catches its own exceptions (`first_person_bridge.py:585-596`) |
| RET-01 | Per-video dedup before integrity gates (v8 path; back-fill from 40 videos limits the effect) | CD | P2,P3 | RC-4 | 08 | T4-01 | Lowered P1→P2 (reviewer) |
| RET-02 | v10 retrieval ignores the sparse vector (breaks invariant 5; v10 is not the code default) | CD | P2 | RC-4 | 08 | T4-02 | Lowered P1→P2 (reviewer) |
| DATA-03 | `transcript_hash` has three meanings across writers (both gates fail closed today) | CD | P3,P4 | RC-4 | 06 | T3-03 | Lowered P1→P2 (reviewer) |
| UX-005 | An interrupted stream leaves teacher text without citation, "Related" label or safety notices, and saves it to history (`final` is sent before `done`) | CD | P4,P2 | RC-3 | 14d | T1-18 | New (journey pass) |
| UX-008 | Trust labels, abstain card, error and quota copy are English in all 13 non-English locales (33 of 234 chat keys missing) | CD | P2,P6 | RC-8 | 14d | T1-20, HUMAN | New |
| PRD-009 | Client conversation summary is produced by sending "Summarize our conversation so far." to `/api/chat`; the clip or abstain reply is stored and reused as context | CD | P3,P2 | RC-1 | 14d | T1-19 | New |
| PRD-010 | Landing and welcome copy promise a conversational "AI companion"; the teaching lane answers with a clip or a static abstain | CD | P2,P4 | RC-6 | 14d | T6-10 | New |
| ADV-02 | Undocumented third-party processors: Lovable AI gateway (memory extraction, STT fallback, admin ask, eval), Sarvam STT, Sentry replays, SMTP, web push | CD | P4,P6 | RC-1 | 26 | T6-08 | New (reviewer) |
| ADV-04 | Admin `eval-run` scores Gemini answers judged by the same model, not the product | CD | P6 | RC-2 | 26 | T2-01 | New (reviewer) |
| ADV-05 | On-demand client translation of teacher quotes carries no machine-translation label | CD | P4,P2 | RC-3 | 26 | T5-06 | New; lead raised P3→P2 (a translated quote can read as the teacher's words) |
| X-03 | PR size makes review impossible | CD | P3 | RC-8 | 01 | T0-03 | |
| X-05 | Two frontend writers; `lovable-sync` diverged | AR | P3 | RC-8 | 01 | T0-07 | |
| X-07 | Documents used as system memory; loose root files | CD | P3 | RC-8 | 01 | T1-15 | |
| AI-002 | Distress turns pay for retrieval + grading, then discard | CD | P1 | RC-1 | 09 | T4-05 | |
| AI-003 | Teacher-style register block appended to general-mode prompts ("how, not what"; forbids invented first-person sentences) | PD | P4,P2 | RC-3 | 09 | T1-06 | Reviewer: PARTLY; P2 right |
| AI-004 | 37 prompt constants + 72 inline prompts; no registry/version | CD | P3,P1 | RC-1 | 09 | T2-03, T5-07 | |
| AI-005 | Two provider stacks; `container.ollama` holds OpenRouter | CD | P3 | RC-1 | 09 | T7-03 | Same as CQ-002/CQ-014 |
| AI-006 | Dormant editorial prompt rewrites teacher words (P0 if enabled) | AR | P4 | RC-3 | 09 | T1-02 | Latent P0 |
| AI-007 | Relevance-scorer model is an env-only dependency | CD | P1,P2 | RC-9 | 09 | T1-07 | |
| ANS-006 | No depth or mode control on the live path | PG | P2,P5 | RC-6 | 10 | T5-01 | |
| ANS-007 | Follow-up continuity is string concatenation | PG | P2,P5 | RC-6 | 10 | T5-05 | |
| ANS-008 | Indic seekers get English quote + translated glue | PG | P2,P6 | RC-6 | 10 | T5-06, HUMAN | |
| MEM-001 | Seven overlapping memory planes (plus WhatsApp SQLite and edge extraction, ADV-06) | CD | P3,P5 | RC-1 | 12 | T6-01 | |
| MEM-002 | Memory read on the teaching lane and never used | PG | P5,P1 | RC-1 | 12 | T6-02 | Lowered P1→P2 |
| MEM-004 | LLM-written "spiritual profile" of the user | AR | P5,P4 | RC-1 | 12 | T6-03 | |
| SAFE-007 | No emotional-dependency guard | PG | P5,P4 | RC-5 | 14b | T6-07, HUMAN | |
| EVAL-004 | Benchmarks measure the dormant generating path | CD | P2,P6 | RC-2 | 18 | T2-01 | |
| EVAL-005 | LLM judge not calibrated against humans | AR | P6 | RC-2 | 18 | T2-04 | |
| EVAL-006 | Pass bar accepts 70% abstention on answerable questions | PG | P2 | RC-6 | 18 | T0-05, T2-01 | |
| DATA-04 | Ingestion dual-index writes fabricated provenance (P0 if enabled) | CD | P4 | RC-4 | 06 | T1-02 | Latent P0 |
| DATA-08 | Graph and LightRAG have no span-level provenance | CD | P3 | RC-4 | 06 | T3-11 | |
| DATA-09 | Two transcript lineages per video; online ingest downloads directly | CD | P3 | RC-4 | 06 | T3-09 | |
| DATA-10 | Chat-corpus IDs use raw URL; scripts skip stale cleanup | PD | P3 | RC-4 | 06 | T3-11 | |
| DATA-11 | Supabase schema drift (32 tables created more than once) | CD | P3,P6 | RC-1 | 06 | T3-08 | |
| DATA-12 | Stored citations are unstructured `text[]` | CD | P5,P4 | RC-4 | 06 | T3-06 | |
| DATA-13 | Teacher-ID vocabulary differs per store | CD | P4 | RC-1 | 06 | T3-07 | |
| DATA-15 | No continuous data-quality gate on serving collections | CD | P1,P3 | RC-4 | 06 | T3-05 | |
| DATA-16 | Approved corpus version ≠ served version | PD | P4 | RC-2 | 06 | T3-05 | |
| DATA-18 | Runtime state lives in container files | AR | P1 | RC-4 | 06 | T3-06 | |
| RET-04 | Compound path does not retrieve per facet | CD | P2 | RC-6 | 08 | T5-02 | |
| RET-05 | Graph/LightRAG: unproven value, dirty data, no provenance | AR | P1,P2 | RC-1 | 08 | T3-11, ADR-005 | |
| RET-06 | TU graph builder filters on a forbidden field; wrong default collection | PD | P3 | RC-4 | 08 | T5-02 | |
| RET-07 | No serving-vs-index encoder check | AR | P1 | RC-4 | 08 | T3-12 | |
| RET-08 | No Recall@k/MRR/nDCG on the serving collection | PG | P2,P6 | RC-2 | 08 | T2-02 | |
| RET-10 | Duplicate LLM ranking: up to 4 LLM calls per question | CD | P1 | RC-1 | 08 | T4-06 | |
| SYS-008 | Load evidence uses a mock LLM | PG | P1 | RC-2 | 15 | T9-02 | |
| SEC-002 | Public video streaming by id | AR | P4 | RC-7 | 14 | T1-08 | |
| SEC-003 | Distress and question text logged at INFO | CD | P4,P6 | RC-9 | 14 | T1-09 | |
| SEC-004 | Erasure gaps; deletion impossible while backend down | PD | P5,P6 | RC-1 | 14 | T6-06 | See ADV-01 |
| SEC-005 | Public repo tracks corpus/graph backups and internal reports | CD | P4 | RC-7 | 14 | T0-02 | Part of X-06 |
| SEC-006 | Datastores on 0.0.0.0; Qdrant no API key; unpinned image | AR | P1 | RC-9 | 14 | T1-14 | |
| SEC-007 | Prompt injection: low on FP gates, real on general lane | AR | P2,P4 | RC-3 | 14 | T4-03, T5-04 | |
| CQ-001 | Giant functions (execute 2,145 lines; generate_answer 1,247) | CD | P3,P1 | RC-8 | 13 | T7-01 | Split landed 2026-11-05: `execute` 2,146 → 266 lines, 14 named step methods, golden matrix identical. `generate_answer` (1,247) untouched |
| CQ-002 | ~14 overlapping LLM abstraction modules | CD | P1,P3 | RC-1 | 13 | T7-03 | |
| CQ-003 | At least 8 cache mechanisms | AR | P1,P3 | RC-1 | 13 | T7-04 | |
| CQ-004 | 5+ memory subsystems | AR | P3,P5 | RC-1 | 13 | T6-01 | Same as MEM-001 |
| CQ-005 | Root `langdetect` stub always returns "en" | PD | P3 | RC-8 | 13 | T1-13 | |
| CQ-006 | 1,513 `except Exception`; 70 silent swallows | CD | P1,P3 | RC-8 | 13 | T7-05 | |
| CQ-007 | 1,465 function-local imports hide cycles | AR | P3 | RC-8 | 13 | T7-05 | |
| CQ-008 | 112 tests assert on source text; no real-store CI | CD | P3,P6 | RC-2 | 13 | T2-05 | |
| CQ-009 | 11.2 MB markdown; key docs drift from code | CD | P3,P4 | RC-8 | 13 | T1-15 | |
| CQ-010 | 679 settings; 27 unread; 23 undeclared reads | AR | P1,P3 | RC-1 | 13 | T2-06 | |
| CQ-012 | 21 `first_person_*` modules, many default-off | AR | P3 | RC-8 | 13 | T7-06 | |
| GURU-010 | Registry exists; 621 literals in 128 runtime files bypass it | AR | P4,P3 | RC-1 | 11 | T8-01, T8-02 | |
| GURU-011 | Seeds/personas for other teachers and "private teachings" | CD | P4 | RC-7 | 11 | T1-04 | |
| GURU-013 | Two identifier vocabularies for the same teachers | CD | P3,P4 | RC-1 | 11 | T3-07 | |
| GURU-014 | No joint-attribution rule | PG | P4,P2 | RC-1 | 11 | T8-01, HUMAN | |
| IP-005 | Broadcaster content treated as teacher-approved | AR | P4 | RC-7 | 14c | T3-06, HUMAN | |
| IP-006 | Seed data defines other teachers and a "private teachings" persona | CD | P4 | RC-7 | 14c | T1-04 | Same as GURU-011 |
| PRD-001 | Relative `/api` fetches break cross-origin deploys | PD | P3 | RC-8 | 03 | T1-16 | |
| PRD-003 | "Server history" is client-written | CD | P3,P1 | RC-1 | 03 | T6-05 | |
| PRD-004 | Push prompt can follow a crisis answer | PD | P5,P4 | RC-5 | 03 | T1-10 | |
| PRD-005 | Assistant slugs disagree (fails closed with 403) | CD | P3,P4 | RC-1 | 03 | T1-04 | |
| PRD-008 | No user research grounds product decisions | PG | P2,P5,P6 | RC-6 | 02 | T2-07, HUMAN | Lowered P1→P2 |
| UX-002 | Streak copy ties usage to spiritual progress | CD | P5 | RC-6 | 12b | T1-12 | |
| UX-003 | Engagement prompts ignore emotional context | PD | P5 | RC-5 | 12b | T1-10 | Same as PRD-004 |
| UX-004 | Retention metrics are usage-based | PG | P5,P6 | RC-2 | 12b | T2-03 | |

## P3 — enhancements and minor defects (19)

| ID | Title | Type | Pillars | RC | Doc | Task |
|---|---|---|---|---|---|---|
| X-04 | Designated branch already merged; checkout stale and shallow | CD | P3 | RC-8 | 01 | T0-06 |
| ADV-06 | Memory inventory omits WhatsApp SQLite and the edge extraction worker | CD | P3 | RC-1 | 26 | T6-01 |
| AI-008 | Static model routing on the FP lane | PG | P1 | RC-1 | 09 | T7-03 |
| MEM-005 | Client conversation summary enters prompt unfenced | PD | P4 | RC-3 | 12 | T6-03 |
| SAFE-006 | `REFERENCE_VOICE` health claims left in a serving module | AR | P4 | RC-3 | 14b | T1-02 |
| SAFE-008 | Transcript text unfenced in scorer prompt | AR | P4 | RC-3 | 14b | T5-04 |
| DATA-17 | OKF compile drift; absolute host paths | CD | P3 | RC-4 | 06 | T3-11 |
| DATA-19 | Corpus and graph backups tracked in the public repo | CD | P3,P4 | RC-7 | 06 | T0-02 |
| RET-11 | Three vector schemas and searchers for teaching content | AR | P3 | RC-1 | 08 | T7-06 |
| SEC-008 | CORS wildcard converted to credentialed regex | AR | P1 | RC-9 | 14 | T1-14 |
| SEC-009 | Dead WhatsApp JWT signer with default secret | CD | P4 | RC-8 | 14 | T1-13 |
| SEC-010 | Unauthenticated deep health check | AR | P1 | RC-9 | 14 | T1-14 |
| CQ-011 | `asyncio.run` inside Celery tasks | PD | P1 | RC-8 | 13 | T7-02 |
| CQ-013 | Sync `Depends` in `backend/app/api/compliance.py` (breaks L-DOCKER-18) | CD | P1 | RC-8 | 13 | T1-13 |
| CQ-014 | Misleading names (`container.ollama`) | CD | P3 | RC-8 | 13 | T7-03 |
| PRD-002 | Client sends a system prompt the backend discards | CD | P3 | RC-1 | 03 | T1-04 |
| PRD-007 | Two first-person surfaces with different contracts | AR | P3 | RC-1 | 03 | T5-03 |
| IP-007 | Demo music, images, video licences unconfirmed | UA | P4 | RC-7 | 14c | HUMAN |
| IP-008 | Tracked evidence leaks owner's local paths and username | CD | P4 | RC-7 | 14c | T0-02 |
| UX-009 | Personalisation controls and memory copy promise effects the teaching lane ignores | CD | P5 | RC-6 | 14d | T6-10 |
| UX-010 | WhatsApp button always shown although the channel is `disabled_by_policy` | CD | P3 | RC-8 | 14d | T1-16 |
| UX-011 | Anonymous quota invisible until used up; reset time never shown | CD | P5 | RC-6 | 14d | T6-10 |

## Strengths recorded as findings

| ID | Title | Doc | Decision |
|---|---|---|---|
| MEM-006 | 23 memory transparency and erasure routes | 12 | Keep |

## Counts (after the independent review and the journey pass)

| Severity | Count |
|---|---|
| P0 | 2 (one root cause: public exposure) |
| P1 | 47 |
| P2 | 81 |
| P3 | 22 |
| Strength | 1 |
| Total | 153 (138 specialist and lead findings + 6 reviewer findings + 9 journey-pass findings) |

Section headings above give the count at the time of the review. The table here is authoritative.

Added 2026-11-05/06 (separate from the counts above, which are unchanged): 75 further findings, P0 0, P1 25, P2 43, P3 7. See the last section of this file.

## Findings added by the final verification pass (2026-11-05/06)

The specification agents and the mobile, k8s and accessibility reviews found 75 IDs that the table above does not hold (`FINAL_AUDIT_DOCUMENT_INVENTORY.md` §3.2; recomputed from the package: the same 75, no difference). They are listed here and do not change the original counts. The original rows above are unchanged.

- Status of every row: Open (found 2026-11-05/06). They were found by reading code. None has a fix yet. None is Closed or Partial.
- Sev is the value in the defining spec section (column "Doc"). Where another source disagrees, the Note column says so.
- Type codes are the ones used above. "—" means the defining spec states no type (the k8s review gives severity only; A11Y-17 is a list of minor items). DATA-20 to DATA-26: the spec column is "Defect", read as CD; DATA-27 is marked [INF], so PD.
- Task: roadmap or `NEW-*` task named in the defining spec. "Found by" is the document that defines the finding. Evidence (file and line) is in the Doc section.
- Prefixes `OPS-`, `MOB-`, `K8S-`, `A11Y-` are registered in `CONVENTIONS.md` §5.

### Added P0 — critical (0 findings)

None.

### Added P1 — major release or experience blockers (25)

| ID | Sev | Title | Type | Doc | Task | Found by | Note |
|---|---|---|---|---|---|---|---|
| DATA-20 | P1 | v10 builder never stamps `domain_rights_status`; a fresh build is unservable | CD | `INGESTION_AND_CONTENT_PROCESSING_SPEC.md §2.2` | NEW-ING-1 | Ingestion spec, 2026-11-05 | Spec: P1 for any rebuild or v11 promotion. [LIVE-Q] how live v10 became licensed is unknown |
| DATA-21 | P1 | Builder decides rights from a hard-coded channel list (includes "times now") and writes `rights_cleared=True`; register not consulted | CD | `INGESTION_AND_CONTENT_PROCESSING_SPEC.md §2.2` | NEW-ING-1 | Ingestion spec, 2026-11-05 | Conflicts with D-13 |
| DATA-23 | P1 | Per-video replace is delete-then-upsert; a failed upsert leaves the video with zero points | CD | `INGESTION_AND_CONTENT_PROCESSING_SPEC.md §2.2` | NEW-ING-2 | Ingestion spec, 2026-11-05 | Spec: P1 for in-place replace, low for a new collection |
| MEM-007 | P1 | Memory UI manages `guru_memories`; the prompt reads canonical memory first; canonical routes have no UI caller | CD | `PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md §1.1` | NEW-MEM-4, T6-01 | Memory spec, 2026-11-05 | [LIVE-L] to confirm data. Qualifies the MEM-006 Keep verdict |
| MEM-010 | P1 | Saved notebook answers store full text with free-form citations; no path follows a source withdrawal | AR | `PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md §1.1` | NEW-MEM-7, T3-06 | Memory spec, 2026-11-05 | Spec: P1 (rights). `takedown()` does not exist |
| OPS-003 | P1 | Three alert rules read metrics no code emits; `BackupStale` fires permanently | CD | `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md §2.9` | NEW-OPS-1 | Reliability spec, 2026-11-05 |  |
| OPS-004 | P1 | Production scrape config targets endpoints a static token cannot read | CD | `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md §2.9` | NEW-OPS-1 | Reliability spec, 2026-11-05 |  |
| OPS-007 | P1 | Backup cron pins `first_person_v7`; backup script sends no Qdrant API key; no success timestamp exported | CD | `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md §2.9` | NEW-OPS-4, T3-10 | Reliability spec, 2026-11-05 |  |
| OPS-009 | P1 | No per-request trace joins route, gates, model and feedback by `request_id` | PG | `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md §2.9` | NEW-OPS-2 | Reliability spec, 2026-11-05 |  |
| ANS-010 | P1 | Chat wire hides why an answer abstained; store error still reports `verification.passed=True` | CD | `SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md §1.1` | NEW-ANS-2 | Answer contract, 2026-11-05 | Related: RET-17 |
| ANS-011 | P1 | Grounding state of a served "Related" clip is unpinned; by reading it may report `abstained` | UA | `SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md §1.1` | NEW-ANS-1 | Answer contract, 2026-11-05 | Spec: P1 if confirmed. Needs a runtime test (AC-ANS-15). [LIVE-L] |
| MOB-01 | P1 | OAuth runs inside the WebView; Google sign-in likely blocked | PD | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-4 | Mobile spec, 2026-11-06 |  |
| MOB-02 | P1 | No iOS privacy manifest | CD | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-5 | Mobile spec, 2026-11-06 | Store consequence is [INF] |
| MOB-03 | P1 | Microphone used with no permission or usage string | PD | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-5 | Mobile spec, 2026-11-06 |  |
| MOB-04 | P1 | Privacy disclosures do not match the code or each other | CD | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-2, NEW-MOB-13 | Mobile spec, 2026-11-06 | Store consequence is [INF] |
| MOB-05 | P1 | Cited-clip playback in the native WebView is unproven | UA | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-8 | Mobile spec, 2026-11-06 |  |
| MOB-10 | P1 | Account deletion reachable but incomplete for the stores (no Apple token revocation) | PD | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-9 | Mobile spec, 2026-11-06 | Spec type also lists product gap (deletion path) |
| K8S-06 | P1 | Default credentials and password-bearing values committed in the Helm chart | — | `K8S_MANIFESTS_REVIEW.md §3` | NEW-K8S-5 | k8s review, 2026-11-06 | Spec: P2 if the chart is formally retired; not P0 (no live key found) |
| A11Y-01 | P1 | Gold text on the cream ground fails contrast (verbatim label, attribution, "AI Generated") | CD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-2 | Accessibility audit, 2026-11-06 | Runtime for one node, static for the rest |
| A11Y-02 | P1 | Red text in the error card (which carries the helpline) fails contrast | CD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-2 | Accessibility audit, 2026-11-06 | Safety-relevant text |
| A11Y-03 | P1 | "Related, not a direct answer" label fails contrast and has three wordings | CD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-2 | Accessibility audit, 2026-11-06 | Answer view did not render at runtime |
| A11Y-05 | P1 | Clip dialog has no accessible name | PD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-3 | Accessibility audit, 2026-11-06 | Not rendered at runtime |
| A11Y-06 | P1 | No synchronised captions for clip video | PD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-4 | Accessibility audit, 2026-11-06 | Spec: P1 (Level A) for the direct-video path; Unknown for the YouTube path |
| A11Y-11 | P1 | Cookie banner covers the Send button on phones | CD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-7 | Accessibility audit, 2026-11-06 | Confirmed at one viewport (390x800) |
| A11Y-16 | P1 | Accessibility tests do not cover the journey or WCAG 2.2 | CD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-1 | Accessibility audit, 2026-11-06 | Why A11Y-09 and A11Y-11 were not caught |

### Added P2 — important quality or maintainability (43)

| ID | Sev | Title | Type | Doc | Task | Found by | Note |
|---|---|---|---|---|---|---|---|
| DATA-22 | P2 | Failed pre-build snapshot and failed stale-point delete only warn; build writes anyway | CD | `INGESTION_AND_CONTENT_PROCESSING_SPEC.md §2.2` | NEW-ING-2 | Ingestion spec, 2026-11-05 | Severity conflict: spec P2 (used); `FINAL_AUDIT_GAP_ANALYSIS.md` §2 groups it with DATA-23 as P1. Residual gap in the DATA-05 closure |
| DATA-24 | P2 | `audio_archive.py` writes `rights_status: "cleared"` as a literal | CD | `INGESTION_AND_CONTENT_PROCESSING_SPEC.md §2.2` | NEW-ING-3 | Ingestion spec, 2026-11-05 |  |
| DATA-25 | P2 | No writer emits `fp-context-v2`; serving contract declares no v2 collection | CD | `INGESTION_AND_CONTENT_PROCESSING_SPEC.md §2.2` | NEW-ING-8 | Ingestion spec, 2026-11-05 | DATA-03 is Closed for schema and tests only |
| DATA-26 | P2 | Startup passes no collection digest; contract has no digest or approved version; nightly audit never contacts Qdrant | CD | `INGESTION_AND_CONTENT_PROCESSING_SPEC.md §2.2` | NEW-ING-4 | Ingestion spec, 2026-11-05 | Why DATA-15 and DATA-16 are Partial |
| DATA-27 | P2 | Digest identity differs between the audit script and the contract helper | PD | `INGESTION_AND_CONTENT_PROCESSING_SPEC.md §2.2` | NEW-ING-4 | Ingestion spec, 2026-11-05 | Spec marks [INF] |
| MEM-008 | P2 | Judge `ESCALATE` candidates are dropped; no review queue exists | PG | `PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md §1.1` | NEW-MEM-5 | Memory spec, 2026-11-05 | Spec type: product gap / defect |
| MEM-009 | P2 | "Export my data" omits memory; `/api/memory/export` has no UI caller | PG | `PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md §1.1` | NEW-MEM-6 | Memory spec, 2026-11-05 | DPDP access right |
| MEM-011 | P2 | Consent is one scalar (`memory-v1`); account deletion removes consent and deletion receipts, so no proof of erasure remains | AR | `PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md §1.1` | NEW-MEM-6 | Memory spec, 2026-11-05 | [HUMAN] legal question (D-PM8) |
| MEM-012 | P2 | Extractor input is unfenced; injection regex is English-only; a poisoned fact can become evidence | PD | `PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md §1.1` | NEW-MEM-5 | Memory spec, 2026-11-05 |  |
| OPS-001 | P2 | Integrity-breach detector depends on the bridge flag, not on the posture | PD | `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md §2.9` | NEW-SEC-1 | Reliability spec, 2026-11-05 |  |
| OPS-002 | P2 | No served-clip integrity check at response assembly | AR | `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md §2.9` | NEW-SEC-1 | Reliability spec, 2026-11-05 |  |
| OPS-005 | P2 | `warning` and `info` alerts route to the pager | CD | `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md §2.9` | NEW-OPS-1 | Reliability spec, 2026-11-05 | Severity conflict: spec P2 (used); gap analysis §2 groups OPS-003 to OPS-008 as P1 |
| OPS-006 | P2 | Feedback and lesson stores hold seeker text in container files with no retention or erasure | CD | `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md §2.9` | T3-06 (DATA-18) | Reliability spec, 2026-11-05 | Gap analysis §2 names OPS-003 to OPS-008 as a range but does not describe OPS-006 |
| OPS-008 | P2 | Budget denial events are not counted | PG | `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md §2.9` | NEW-OPS-8 | Reliability spec, 2026-11-05 | Severity conflict: spec P2 (used); gap analysis §2 groups it as P1 |
| ANS-009 | P2 | First-person route ignores `response_preferences` (mode, include flags) | CD | `SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md §1.1` | NEW-ANS-5 | Answer contract, 2026-11-05 | Spec type: confirmed defect (product gap) |
| ANS-012 | P2 | Three response writers disagree on fields; `route_metadata` is not a response field | CD | `SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md §1.1` | NEW-ANS-3 | Answer contract, 2026-11-05 | Gap analysis §2 also P2 |
| RET-12 | P2 | Frozen retrieval bank has 8 items, no category or graded relevance; normal-approximation interval | PG | `RETRIEVAL_AND_RAG_SPEC.md §1.1` | NEW-RET-1 | Retrieval spec, 2026-11-05 | Spec type: product gap / defect |
| RET-13 | P2 | Deduplication has no containment rule; 27% of v8 clips sit inside another clip | PD | `RETRIEVAL_AND_RAG_SPEC.md §1.1` | NEW-RET-6 | Retrieval spec, 2026-11-05 | 27% is [DOC-CLAIM]; [LIVE-Q] |
| RET-14 | P2 | Retrieval depth is a constant (`max_clips=3`; 4 for practice) | PG | `RETRIEVAL_AND_RAG_SPEC.md §1.1` | none assigned in spec | Retrieval spec, 2026-11-05 |  |
| RET-15 | P2 | Ambiguous-domain router failure sends an ambiguous spiritual question to the general lane (0.45 s budget) | AR | `RETRIEVAL_AND_RAG_SPEC.md §1.1` | NEW-RET-8 | Retrieval spec, 2026-11-05 | D-04 |
| RET-16 | P2 | Budgets for the same LLM gate differ across settings, compose files and docs | CD | `RETRIEVAL_AND_RAG_SPEC.md §1.1` | NEW-RET-4 | Retrieval spec, 2026-11-05 | Extends SYS-006 |
| RET-17 | P2 | Store-error abstain is reported as a pass and counted as an abstain, not an error | CD | `RETRIEVAL_AND_RAG_SPEC.md §1.1` | NEW-ANS-2, NEW-RET-9 | Retrieval spec, 2026-11-05 | Related: ANS-010 |
| MOB-06 | P2 | Native build pinned to the prod Railway URL; opt-in guard bypassed | AR | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-3 | Mobile spec, 2026-11-06 |  |
| MOB-07 | P2 | Push notifications: prompt timing, listener order, token linking | PD | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-7 | Mobile spec, 2026-11-06 |  |
| MOB-08 | P2 | Release pipeline is a draft: Fastlane, signing, versions, CI | CD | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-11 | Mobile spec, 2026-11-06 |  |
| MOB-09 | P2 | Auto Backup on; chat history sits in app preferences | AR | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-6 | Mobile spec, 2026-11-06 |  |
| MOB-11 | P2 | Crisis helplines on the device are untested | UA | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-10 | Mobile spec, 2026-11-06 |  |
| MOB-12 | P2 | Offline and cold-start behaviour is unverified | UA | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-10 | Mobile spec, 2026-11-06 |  |
| K8S-01 | P2 | Four manifest sets, no source-of-truth header | — | `K8S_MANIFESTS_REVIEW.md §3` | NEW-K8S-1, NEW-K8S-2 | k8s review, 2026-11-06 |  |
| K8S-02 | P2 | Graph store: manifests use Neo4j; config and compose default to Memgraph | — | `K8S_MANIFESTS_REVIEW.md §3` | D-PK8S1 | k8s review, 2026-11-06 | [INF] effect |
| K8S-03 | P2 | Health probes use `/api/health`, not `/api/healthz` | — | `K8S_MANIFESTS_REVIEW.md §3` | NEW-K8S-2, NEW-K8S-3 | k8s review, 2026-11-06 |  |
| K8S-04 | P2 | Env var names and values drift from `backend/app/config.py` | — | `K8S_MANIFESTS_REVIEW.md §3` | NEW-K8S-2, NEW-K8S-3 | k8s review, 2026-11-06 | Effect is [INF] |
| K8S-05 | P2 | No Celery worker or beat in the Helm chart; no Memgraph; images unpinned | — | `K8S_MANIFESTS_REVIEW.md §3` | NEW-K8S-3 | k8s review, 2026-11-06 |  |
| K8S-07 | P2 | Hardening incomplete in the Helm chart and two other sets | — | `K8S_MANIFESTS_REVIEW.md §3` | NEW-K8S-3 | k8s review, 2026-11-06 |  |
| A11Y-04 | P2 | Meaning carried only by the `title` attribute | PD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-3 | Accessibility audit, 2026-11-06 |  |
| A11Y-07 | P2 | Quoted teacher text has no `lang` attribute | PD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-5 | Accessibility audit, 2026-11-06 |  |
| A11Y-08 | P2 | Focus drops to the page body after a send | CD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-6 | Accessibility audit, 2026-11-06 | Confirmed on the error path; success path not tested |
| A11Y-09 | P2 | Target size under 24 px (landing dots, password toggle) | CD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-7 | Accessibility audit, 2026-11-06 |  |
| A11Y-10 | P2 | No persistent help link to the helpline on chat pages | PG | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-8 | Accessibility audit, 2026-11-06 |  |
| A11Y-12 | P2 | Looping animations continue under "reduce motion"; no pause control | PD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-8 | Accessibility audit, 2026-11-06 |  |
| A11Y-13 | P2 | Answer arrival is not announced (no live region on the message list) | PD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-6 | Accessibility audit, 2026-11-06 | Answer path did not render |
| A11Y-14 | P2 | Delete-account flow: steps change with no focus move or announcement | PD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-9 | Accessibility audit, 2026-11-06 |  |
| A11Y-15 | P2 | Weak focus indicator on the composer | PD | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-8 | Accessibility audit, 2026-11-06 |  |

### Added P3 — enhancements and minor defects (7)

| ID | Sev | Title | Type | Doc | Task | Found by | Note |
|---|---|---|---|---|---|---|---|
| ANS-013 | P3 | Reflection prompts and practice pointer exist for `/api/first-person/query` but not for chat; catalogue authorship not recorded | PG | `SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md §1.1` | NEW-ANS-6 | Answer contract, 2026-11-05 |  |
| MOB-13 | P3 | Deep links use a custom scheme only | AR | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-12 | Mobile spec, 2026-11-06 |  |
| MOB-14 | P3 | A second mobile codebase exists (`mobile/expo/`) | AR | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-1 | Mobile spec, 2026-11-06 |  |
| MOB-15 | P3 | Smaller native hygiene items | UA | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md §3` | NEW-MOB-12 | Mobile spec, 2026-11-06 |  |
| K8S-08 | P3 | Stale docs describe K8s as an operating path | — | `K8S_MANIFESTS_REVIEW.md §3` | NEW-K8S-4 | k8s review, 2026-11-06 |  |
| K8S-09 | P3 | Resource requests not sized to any measured limit | — | `K8S_MANIFESTS_REVIEW.md §3` | D-PK8S1 | k8s review, 2026-11-06 |  |
| A11Y-17 | P3 | Smaller items (six parts, 17a to 17f) | — | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md §3` | NEW-A11Y-9 (17d, 17e) | Accessibility audit, 2026-11-06 |  |

### Counts of the added findings

| Prefix | P0 | P1 | P2 | P3 | Total |
|---|---|---|---|---|---|
| DATA | 0 | 3 | 5 | 0 | 8 |
| MEM | 0 | 2 | 4 | 0 | 6 |
| OPS | 0 | 4 | 5 | 0 | 9 |
| ANS | 0 | 2 | 2 | 1 | 5 |
| RET | 0 | 0 | 6 | 0 | 6 |
| MOB | 0 | 6 | 6 | 3 | 15 |
| K8S | 0 | 1 | 6 | 2 | 9 |
| A11Y | 0 | 7 | 9 | 1 | 17 |
| Total | 0 | 25 | 43 | 7 | 75 |

Sources: `FINAL_AUDIT_GAP_ANALYSIS.md` §2; `FINAL_PENDING_WORK_REGISTER.md` §10. Not indexed because they carry no ID: the Railway, AI-harness, GURU and `RLIMIT` groups of `FINAL_AUDIT_GAP_ANALYSIS.md` §2.

### Added 2026-11-06 (second pass): IDs for previously unnumbered defect groups and the Lovable review

The first pass left four defect groups in `FINAL_AUDIT_GAP_ANALYSIS.md` §2 without IDs (Railway, AI harness, GURU, RLIMIT). The lead assigned IDs here. Severity comes from the defining review where it gives one (LOV); otherwise it is the lead's, marked "(lead)". Status: Open (found 2026-11-05/06) unless stated.

| ID | Sev | Finding | Type | Doc | Task | Found by |
|---|---|---|---|---|---|---|
| RW-01 | P1 (lead) | Railway drains for 0 s by default and nothing sets `RAILWAY_DEPLOYMENT_DRAINING_SECONDS`; `backend/app/main.py:135` assumes a longer window, so deploys drop in-flight requests | CD | `specifications/RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` §1, §8 | NEW-RW-1 | Railway review |
| RW-02 | P1 (lead) | `railway up` gives no `RAILWAY_GIT_COMMIT_SHA`; the first-person production contract can stop startup (`backend/app/first_person_release.py:119-125`) | CD | Railway runbook §1 | NEW-RW-2 | Railway review |
| RW-03 | P1 (lead) | `scripts/deploy/deploy_railway.sh` sets Redis `volatile-lru` (compose decided `noeviction`), generates a random `JWT_SECRET`, and omits required variables | CD | Railway runbook §1 (C-7) | NEW-RW-4 | Railway review |
| RW-04 | P2 (lead) | Celery worker and beat modes in `backend/start_railway.py` install no SIGTERM handler (no `signal` use in the file) | PD | Railway runbook §1 | NEW-RW-3 | Railway review |
| RW-05 | P1 (lead) | `.railway/railway.ts` declares one service (no worker, beat or Redis) and `dockerfilePath` is commented out; IaC `service()` cannot name a Dockerfile, so `RAILWAY_DOCKERFILE_PATH` must be set | AR | Railway runbook §5 | T9-01 | Railway review |
| RW-06 | P2 (lead) | Boot without Memgraph may approach the 330 s healthcheck (`backend/app/main.py:923`, `:938`); unmeasured | UA | Railway runbook §8 | NEW-RW-8 | Railway review |
| AI-009 | P1 (lead) | Rerank and selector prompts are not fenced; the generation fence does not neutralise closing tags | CD | `specifications/AI_HARNESS_PROMPT_AND_CONTEXT_SPEC.md` §2 | NEW-AI-2 | Harness review |
| AI-010 | P1 (lead) | No ingest-time or lane-level injection screen for transcripts | PG | Harness spec §2, §A | NEW-AI-5 | Harness review |
| AI-011 | P2 (lead) | `_meditation_misroute` and `grounding_state` are routing keys not declared in `GraphState` | CD | Harness spec §2 | NEW-AI-1 | Harness review |
| AI-012 | P2 (lead) | No prompt registry; telemetry records the operation string, not a prompt version | PG | Harness spec §2 | T5-07a | Harness review |
| AI-013 | P2 (lead) | Relevance-scorer model defaults to `""` (`backend/app/config.py:476`) and has no price entry | CD | Harness spec §2 | NEW-AI-3, NEW-AI-4 | Harness review |
| GURU-015 | P2 (lead) | The graph is off the default teaching path but still deployed and written at ingestion (`write_ontology_to_neo4j`, `backend/ingest/pipeline.py:1288`, `:1576`) | AR | `specifications/GURU_KNOWLEDGE_AND_KNOWLEDGE_GRAPH_SPEC.md` §2 | NEW-GURU-7; D-05 | Guru review |
| GURU-016 | P2 (lead) | Hard-coded teacher literals across services (28 places tabled); T8-01 added a registry guard that checks the schema, not literals, and nothing calls it | AR | Guru spec §2; `FINAL_READINESS_AND_GAP_ANALYSIS.md` §7 | NEW-GURU-5, T8-02 | Guru review; batch re-verification |
| SYS-013 | P2 (lead) | `backend/app/main.py:55-59` sets `RLIMIT_DATA` to 6144 MB unless `PYTHON_MEMORY_LIMIT_MB=0` (lesson L-MEM-RLIMIT-1); the Railway variable matrix must set 0 | CD | `FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` §2 | Railway variable matrix | Lessons review |
| LOV-01 | P1 | Lovable writes to `main` without a PR (202 bot merges, 36 bot commits after the fork) | AR | `specifications/LOVABLE_SYNC_PATH_REVIEW.md` §3 | NEW-LOV-01 | Lovable review |
| LOV-02 | P1 | Two writers touch the same frontend files (`ChatInterface.tsx`) | AR | Lovable review §3 | NEW-LOV-02, NEW-LOV-06 | Lovable review |
| LOV-03 | P1 | Lovable can regenerate DB types and edge functions from its own Supabase view | AR | Lovable review §3 | NEW-LOV-04 | Lovable review |
| LOV-04 | P2 | `lovable-sync` is stale (4 ahead, 113 behind `main`) with 2 small unmerged changes | AR | Lovable review §3 | NEW-LOV-05 | Lovable review |
| LOV-05 | P2 | Lovable edits repo-root and doc files that repo rules reserve | CD | Lovable review §3 | NEW-LOV-02 | Lovable review |
| LOV-06 | P2 | Voice and storage rules have no gate against Lovable UI edits | PG | Lovable review §3 | NEW-LOV-03, NEW-LOV-06 | Lovable review |
| LOV-07 | P2 | Frontend host and `VITE_BACKEND_URL` for Lovable builds are undocumented | PG | Lovable review §3 | NEW-LOV-07 | Lovable review |
| LOV-08 | P3 | `LOVABLE_API_KEY` secret in the eval workflow | CD | Lovable review §3 | NEW-LOV-08 | Lovable review |

| Second pass | P0 | P1 | P2 | P3 | Total |
|---|---|---|---|---|---|
| RW | 0 | 4 | 2 | 0 | 6 |
| AI | 0 | 2 | 3 | 0 | 5 |
| GURU | 0 | 0 | 2 | 0 | 2 |
| SYS | 0 | 0 | 1 | 0 | 1 |
| LOV | 0 | 3 | 4 | 1 | 8 |
| Total | 0 | 9 | 12 | 1 | 22 |

### Added 2026-11-06 (third pass): load model and accessibility proxy session

| ID | Sev | Finding | Type | Doc | Task | Found by |
|---|---|---|---|---|---|---|
| SYS-014 | P1 (lead) | When the provider does not report `usage.cost`, the budget guard keeps the full $0.03 reservation per call (`backend/app/openrouter_budget.py:87-98`, `:127`); with the default $10 daily cap (`backend/app/config.py:640`) about 111 full-path requests exhaust the day. Whether OpenRouter reports cost for the scorer model is unknown (D-16) | CD | `specifications/LOAD_AND_COST_MODEL.md` §5 | NEW-LOAD-3 | Load model; verified by the lead |
| A11Y-18 | P3 | An extra `tabindex="0"` wrapper `div` adds a Tab stop before Send | CD | `specifications/ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md` §10 | NEW-A11Y-6 | Proxy session |
| A11Y-19 | P3 | Many unnamed `img` nodes in the accessibility tree (mostly icons inside named buttons); speech effect UNPROVEN | PD | Accessibility audit §10 | NEW-A11Y-10 | Proxy session |
| A11Y-20 | P2 | Cookie-banner text at 3.87:1 contrast (`text-muted-foreground`) | CD | Accessibility audit §10 | NEW-A11Y-2 | Proxy session |
| A11Y-21 | P3 | Identical button names ("Add to favorites" x5), duplicate links, skipped heading levels | CD | Accessibility audit §10 | NEW-A11Y-10 | Proxy session |
| A11Y-22 | P2 (candidate, unverified) | Text-spacing (1.4.12) clipping candidates at 390 px; needs a screenshot | UA | Accessibility audit §10 | NEW-A11Y-10 | Proxy session |

Checked and NOT recorded as findings (2026-11-06): (1) the load model's claim that the rerank call can run to 8,192 tokens is wrong for the live OpenRouter provider (default 2048, capped at 800 by policy); it holds only for Sarvam or NIM. (2) The per-user daily budget (`backend/services/cost_tracker.py:476`) sums recorded costs, not reservations, and is called in `backend/app/api/chat.py:808`, `:979`, `:1124`; it fails open when Redis is down, as the degradation rules intend.

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
| CQ-013 | Sync `Depends` in `compliance.py` (breaks L-DOCKER-18) | CD | P1 | RC-8 | 13 | T1-13 |
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

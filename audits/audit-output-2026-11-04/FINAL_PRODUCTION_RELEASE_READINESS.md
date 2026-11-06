# Final production and public release readiness (Gates B and C)

Date: 2026-11-05. Head: `c9b42d3e` on `feature/audit-strengthen-rag-qdrant`. Evidence labels: `CONVENTIONS.md` §3.

Gate A (Railway staging) is in `FINAL_RAILWAY_STAGING_READINESS.md`. This file defines Gate B (production for invited real users) and Gate C (public spiritual-product release). The pending status of each finding is in `FINAL_PENDING_WORK_REGISTER.md`.

## 1. Decision today

| Gate | Decision | Short reason |
|---|---|---|
| A. Railway staging | NO (conditional) | See `FINAL_RAILWAY_STAGING_READINESS.md`. |
| B. Production, invited users | NO | Gate A is not met. 2 P0 findings are open. Restore, load, alerting and incident response are unproven. |
| C. Public release | NO | Gate B is not met. Clinician, rights, guru-review, gold-label and native-speaker sign-offs do not exist. |

A documented design is not a working system. Each gate below needs evidence from the system itself, not from a document.

## 2. Rules that apply to every gate

1. No P0 finding is open.
2. A P1 finding may stay open only with a written risk acceptance by the owner. The acceptance names the finding, the reason, the mitigation and an end date.
3. A risk acceptance is never valid for these classes: security, privacy, data integrity, cross-user exposure, and teaching attribution.
4. Every pass condition is checked on the exact commit and the exact environment that is released.
5. A test that needs a person (clinician, rights holder, native speaker, guru reviewer) is passed only by a signed, dated record filed by hash (D-10).
6. When a test cannot run in an environment, the item is UNPROVEN. It is never marked as passed.

## 3. Gate B: production for invited real users

Gate B starts only after Gate A passes in the production Railway environment.

| ID | Requirement | Test and evidence | Pass condition | Depends on | Open blockers today |
|---|---|---|---|---|---|
| B1 | Gate A passes in the production environment | Gate A checklist, re-run | All Gate A items pass | Gate A | All Gate A blockers |
| B2 | Public exposure stopped (P0 IP-001, X-06) | GitHub repository settings; tracked-file audit of corpus, transcripts, audio, backups | Repository private, or the sensitive content purged per legal advice | D-01, D-02 | Owner action |
| B3 | Branch protection on `main` with required checks (RC-8) | GitHub branch-protection settings | Direct push to `main` refused; required checks listed | T0-03 | Owner action Branch protection must also cover the Lovable bot, which self-merges to `main` today (LOV-01, NEW-LOV-01). |
| B4 | Release record is honest and reproducible | T0-04 gate test from a clean checkout; scopes in the owner-decisions file | Gate reports `independent_review=true` only for independent labels; scopes say "owner-only local review" until Gate C | D-09, D-11, T0-04, T1-11 | Gold-label independence (D-09) |
| B5 | One serving collection pinned per environment, with a startup log of the effective posture | Startup log line; config lint (T2-06) | The log names the collection, the bridge flags, the scorer model and the budget values; the values match the release record | D-14 | D-14 open; CLAUDE.md invariants 23 and 25 conflict |
| B6 | Spend cannot run away | Provider key limit; in-app budget guard (T1-07, on by default); quota on any unauthenticated LLM route | A request beyond the cap is refused with an honest error; no unauthenticated route can call an LLM without a quota | D-07, T1-08 | D-07 open 2026-11-06: unreported provider cost keeps the $0.03 reservation per call, so the default $10 daily cap admits about 111 full-path requests (SYS-014); record the scorer price and confirm `usage.cost` is returned before B8. |
| B7 | P1 reliability defects closed or accepted in writing: SYS-003 (sync pipeline blocks the thread pool), CQ-011 (`asyncio.run` inside Celery tasks), DATA-18 (runtime state in container files), RET-10 (duplicate LLM ranking) | Closing commit plus test for each, or a signed acceptance | No open item without one of the two | Roadmap tasks for each | Open |
| B8 | Load test with the real LLM provider (SYS-008: present load evidence uses a mock LLM) | Load run at the target concurrency against staging | p95 latency, error rate and cost per answer recorded; no executor-starvation canary trip; no thread-pool exhaustion | B7 | Open Plan, scenarios, spend cap and abort rules: `specifications/LOAD_AND_COST_MODEL.md` §6 (Locust). Model: about 7 requests run without waiting per 4-vCPU replica [INF]; admission limit 12 [V-STATIC]. |
| B9 | Backup and restore proven | Qdrant snapshot and Supabase backup restored into scratch targets, then queried | Restored Qdrant returns the same top-1 for 10 fixed questions; restored Postgres passes row-count checks | D-26 | Backups are local cron and not installed; RPO unbounded. The backup cron pins `first_person_v7`, `backup_qdrant.py` sends no API key, and nothing exports a backup timestamp (reliability spec §2). |
| B10 | Monitoring and alerting live and correct | External uptime probe; error tracking; repaired rules in `infrastructure/prometheus/alerting-rules.yml` per `specifications/PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` | A test alert reaches the owner; any increase of `guru_integrity_breach_total` pages the owner; no rule reads a metric that no code emits | B1 | 14 rules exist (corrected 2026-11-05: an earlier draft said none). Some rules read metrics no code emits (`BackupStale` fires permanently); `prometheus.prod.yml:49-67` scrapes paths a static token cannot read; `warning`/`info` severities match no Alertmanager route; `guru_integrity_breach_total` has no rule. Nothing is deployed. |
| B11 | Incident runbooks current, and an on-call owner | `docs/runbooks/ONCALL.md`, `docs/runbooks/ALERTING.md`, `docs/INCIDENT_RESPONSE.md`, plus the 10 runbooks in the reliability spec; one tabletop exercise | Owner named; runbooks name the right endpoints; the tabletop covers provider outage, Qdrant down, bad deploy and cost spike | B10 | Runbooks exist (corrected 2026-11-05: an earlier draft said none) but are partly stale: `ONCALL.md` names `/api/metrics`, a per-user JSON route, as the Prometheus endpoint. No tabletop has run. |
| B12 | User deletion honoured (ADV-01, UX-001) | Delete a test account on staging; run the purge job | No rows remain in memory, consent, outbox or conversation tables; memory vectors deleted; no deletion depends on the retention funnel | T1-12, T6-06, D-19 | Purge job and direct deletion path not proven live |
| B13 | Third-party processors documented (ADV-02) | Processor list in the privacy notice | Every processor that receives user content is listed | T6-08 | Open |
| B14 | Cross-user exposure tests pass | Cache-personalisation leak test, RLS tests, memory isolation tests | 0 leaks | T6-05 | RLS change for client-written roles still reserved (T6-05) |
| B15 | Retrieval and answer baseline frozen | T2-02 retrieval bank on the live collection; T2-01 PR suite | Numbers stored with the release; thresholds fixed before the run | `FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` | Live run not done |
| B16 | Distress known gap handled | T4-04 fixed with a clinician, or a signed acceptance with a mitigation that errs toward care | No silent acceptance | D-06 | Reserved task; clinician not engaged |
| B17 | Rights register present in the image and all served sources cleared | Startup check (T3-01); register review | No served source lacks a clearance row; broadcaster clips non-servable until cleared | D-13, T3-06 | D-13 open; T3-06 reserved |
| B18 | Invited users only | Access list or auth gate | Only listed users can reach the service | Proposed D-29 | Open |

## 4. Gate C: public spiritual-product release

Gate C starts only after Gate B passes and the owner announces the public phase (CLAUDE.md "Before going public").

| ID | Requirement | Evidence | Pass condition | Owner |
|---|---|---|---|---|
| C1 | Clinician sign-off on the distress design (`b6_clinician_safety`) | Signed record filed by hash | Written confirmation exists for the shipped distress behaviour | Owner + clinician (D-06) |
| C2 | Rights approval naming the content and the use (`b5_rights_register`) | Written message from the rights holder | Covers excerpts and audio playback in this app | Owner (D-10, D-12, D-13) |
| C3 | Helplines verified by phone | Dates in `config/helplines.yaml` `last_verified_by_call` | Every listed helpline has a date and an outcome | Owner |
| C4 | Calibration profile from human gold labels | `evaluation/gold/calibrator.py` run on at least 299 confident independent human labels with 0 errors (CLAUDE.md invariant 3) | A profile exists; or the owner accepts that every answer stays "Related, not a direct answer" | Human labellers (D-09, D-23) |
| C5 | Guru review completed | Package `23` executed; scorecard signed | The teachers' representatives accept the scorecard | Owner + teachers' organisation |
| C6 | Native-speaker review of multilingual crisis detection and teaching sets | Review records for the priority languages | Reviewed sets exist for each language offered publicly | Owner (D-22) |
| C7 | Accessibility of the chat flow | WCAG 2.2 AA check of the core journey (`specifications/ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md`) | No unresolved level-A or level-AA failure on the core journey | NOT met (2026-11-06): 17 findings, 7 P1 (contrast, clip dialog name, captions, banner over Send, tests lack `wcag22aa`); answer, crisis, settings and deletion states not rendered without a backend. D-PA11Y1 |
| C8 | Privacy notice, terms and DPDP notices | Published pages | Match the real processors and retention | Owner |
| C9 | Persona and voice risks removed | Seeds and features without rights removed | No persona or voice feature without a filed licence | D-12, D-20 |
| C10 | Ethical retention | Churn funnel and dark patterns removed | No retention mechanism blocks or delays deletion | D-19, T1-12 |
| C11 | Usefulness, not only abstention | Pass bar includes a usefulness target | Target agreed before the measurement run | D-25 |
| C12 | Multi-video answers, if offered publicly | Synthesis evaluation in `specifications/MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` | Variant A attribution checks pass; Variant B only if D-03 approves it | D-03 |
| C13 | Mobile store release, if the apps ship | `specifications/MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md` store checklist | MOB-01 to MOB-05 and MOB-10 closed; store paperwork signed (D-PMOB6) | Owner + agent; mobile stays out of Gates A and B unless D-PMOB8 allows test tracks |

> **2026-11-06:** the accessibility audit proposes moving A11Y-02 and A11Y-10 (helpline reachability) into B16 and A11Y-14 (deletion flow) into B12 (PROPOSED D-PA11Y3).

## 5. Quality claims allowed at each gate

The full definitions are in `specifications/SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md`. The summary:

| Class | Examples | How measured | Allowed claim |
|---|---|---|---|
| Absolute invariants | Every served clip passes the hash gate; no generated text shown as a teacher's words; no cross-user memory in an answer; no success-shaped response after a failed pipeline; speaker copied from the stored clip | Deterministic tests on every release; a single failure blocks | "0 failures in the release test suite", never "100% accurate" |
| Statistical metrics | Retrieval Recall@k, MRR, nDCG; relevance of served clips; out-of-corpus abstention; crisis recall per language | Fixed datasets with n per category and a 95% interval | "x% (95% CI a-b) on n questions of category k" |
| Human judgement | Teaching fidelity, tone, translation meaning, guru acceptance, clinician acceptance | Signed reviews | "Accepted by <role> on <date> for <scope>" |

No finite test set proves zero errors on future questions. With 0 errors in about 299 independent items, the one-sided 95% upper bound on the error rate is about 1% (CLAUDE.md invariant 3). Each category that needs its own claim needs its own sample.

## 6. Verified, assumptions, unknowns

- Verified [V-STATIC, V-GIT]: CI status on `c9b42d3e` (all workflows failed on 2026-11-05); the decision list in `unresolved-questions.md`; the residual risks in `26` §6 and §7.4.
- Assumptions [INF]: target concurrency and latency values are owner choices; they are not set in this file.
- Unknown: live Qdrant content, Railway behaviour under load, real cost per useful answer, and whether the teachers' organisation accepts any assistant explanation layer.

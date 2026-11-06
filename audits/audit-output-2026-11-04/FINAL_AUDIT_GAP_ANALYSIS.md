# Final audit gap analysis (2026-11-05)

Head `c9b42d3e`. This file challenges the 2026-11-04 audit package and this pass's own first draft. It lists what was missed, what was wrong, and what remains unproven. Evidence labels: `CONVENTIONS.md` §3.

## 1. Corrections to earlier conclusions

| Earlier statement | Where | Correct statement | Evidence |
|---|---|---|---|
| "I am not certain `.railway/railway.ts` is a current Railway feature" | First draft of this pass | It is the current method. Config as Code (`railway.json`, `railway.toml`) is deprecated and stops working on 2026-12-01. The repo removed `railway.json` in `040e7c28` (2026-09-19). | [V-WEB] docs.railway.com (Config as Code page, IaC page), searched 2026-11-05; [V-GIT] |
| "CLAUDE.md contradicts itself on the serving collection (invariants 23 vs 25)" | First draft; `22b`; D-14 | Not a contradiction. The code has two flag-selected postures: the bridge uses `first_person_v8` unless both `first_person_context_harness_enabled` and `first_person_context_terminal_enabled` are true (`config.py:41`, `:205`, `:282`, `:298`, `:2318-2326`). D-14 stays open: which posture to deploy. | [V-STATIC] |
| "No alert rules exist"; "no incident runbook exists" | First draft of `FINAL_PRODUCTION_RELEASE_READINESS.md` B10, B11 | 14 rules exist in `infrastructure/prometheus/alerting-rules.yml`; `docs/runbooks/` holds `ONCALL.md`, `ALERTING.md`, `BACKUP_RESTORE_DRILL.md` and more; `docs/INCIDENT_RESPONSE.md` exists. They are partly broken or stale (see §3). Corrected in place. | [V-STATIC] |
| Gate A had 12 items | First draft | 21 items (`FINAL_RAILWAY_STAGING_READINESS.md` A1-A21). The first draft missed drain time, release identity, Redis policy, graceful shutdown, Railway usage limits, uptime probe, volume backup and evidence filing. | [V-STATIC], [V-WEB] |
| Prompt §0g: 38 findings closed | `IMPLEMENTATION-AGENT-PROMPT.md` | 33 closed. GURU-012, SEC-003, SYS-001, DATA-15 and DATA-16 are partial. | `FINAL_PENDING_WORK_REGISTER.md` |
| "`lessons.md` was read" | 2026-11-04 audit | Only searched. Read in full on 2026-11-05 through three extracts (1,468 rows; 99.8% row match by script). | `FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` §0 |

## 2. New defects found in this pass (not in the 2026-11-04 audit)

| ID | Defect | Severity (lead's view) | Evidence | Task |
|---|---|---|---|---|
| DATA-20 | The v10 builder never stamps `domain_rights_status`; retrieval filters on "licensed" (`first_person_context_store.py:464`). A fresh build serves nothing. How live v10 got the stamp is unknown. | P1 (data integrity) | Ingestion spec §2.2 | NEW-ING-1; D-PI4 |
| DATA-21 | The builder's rights check is a hard-coded channel list plus name substrings, and it includes "times now" | P1 (rights) | Ingestion spec §2.2 | NEW-ING-1; D-13 |
| DATA-22, DATA-23 | A failed snapshot only warns; per-video replace deletes before it upserts, so a failed upsert empties the video | P1 (data integrity) | Ingestion spec §2.2 | NEW-ING-2 |
| DATA-24 | `audio_archive.py` writes `rights_status: "cleared"` as a literal | P2 | Ingestion spec §2 | NEW-ING-3 |
| DATA-26, DATA-27 | Startup passes no corpus digest; the contract JSON has no `collection_digest` or `approved_corpus_version`; the nightly audit runs on fixtures only | P2 | Ingestion and data-quality specs | NEW-ING-4, NEW-DQ-3 |
| RW (Railway) | Drain time 0 s by default with nothing setting it; `railway up` gives no `RAILWAY_GIT_COMMIT_SHA`, so the first-person production contract can stop startup; deploy script sets Redis `volatile-lru` and a random `JWT_SECRET`; Celery modes install no SIGTERM handler; IaC cannot name the Dockerfile | P1 for staging | Railway runbook §1, §8 | NEW-RW-1 to NEW-RW-4, T9-01 |
| OPS-003 to OPS-008 | Alert rules read metrics no code emits (`BackupStale` fires permanently); `prometheus.prod.yml:49-67` scrapes paths a static token cannot read; `warning`/`info` alerts match no route; backup cron pins `first_person_v7` and sends no API key; budget denials not counted | P1 for production | Reliability spec §2 | NEW-OPS-1, NEW-OPS-4, NEW-OPS-8 |
| ANS (honesty) | The bridge drops the pipeline's abstain reason; a store error reports `verification.passed=True`; outcome telemetry cannot tell "no teaching" from "system down". A served "Related" clip may report `grounding_state="abstained"` (probable, untested) | P1 (misleading success state) | Answer contract spec §2 | NEW-ANS-1, NEW-ANS-2 |
| ANS-012 | The live wire has nine citation fields: no `guru_id`, `video_id`, end time or clip id. Three response writers disagree (the sync writer omits `follow_up_suggestions`) | P2 | Answer contract spec §2 | NEW-ANS-3; D-PQ7 |
| AI (harness) | Rerank and selector prompts are unfenced; the generation fence does not neutralise closing tags; no ingest-time injection screen; `_meditation_misroute` and `grounding_state` are not declared in `GraphState`; no prompt version in telemetry | P1 (security), P2 | Harness spec §2 | NEW-AI-1, NEW-AI-2, NEW-AI-5, T5-07a |
| MEM-007 to MEM-012 | Memory UI manages a store the prompt does not read first; ESCALATE candidates dropped; export omits memory; notebook stores answer text with no withdrawal path; account deletion removes consent and deletion receipts; extractor input unfenced and the injection regex is English-only | P1-P2 | Memory spec §1, §2 | NEW-MEM-1 to NEW-MEM-7 |
| GURU | Teacher registry (ADR-013) not built; 28 hard-coded teacher places; the graph is off the default path but still deployed and written at ingestion; `memgraph:latest` unpinned | P2 | Guru spec §2 | NEW-GURU-1 to NEW-GURU-8 |
| RLIMIT | `backend/app/main.py:55-59` still sets `RLIMIT_DATA` at 6144 MB against lesson L-MEM-RLIMIT-1 | P2 | Lessons review §2 | Not yet assigned |

> **Update 2026-11-06 (batch 11, 1503e5f2; batch 12, 49c92325):** The registry now has rights, attribution and source fields, and generates one guardrail rail (`backend/config/gurus.yaml`, `backend/services/guru_registry.py`). The hard-coded places are not removed (T8-02 Open). `memgraph` is pinned to `2.20.1` in `backend/docker-compose.yml:45`. GURU-010 and SEC-006 are Partial.
| MOB-01 to MOB-15 (2026-11-06) | Mobile: OAuth inside the WebView; no iOS privacy manifest; microphone used without permission strings; store disclosures omit Sentry replay and the LLM provider; clip playback in the WebView unproven; account deletion without Apple token revocation | 6 P1, 6 P2, 3 P3 | Mobile spec §3 | NEW-MOB-1 to NEW-MOB-13 |
| K8S-01 to K8S-09 (2026-11-06) | k8s manifests are not live but look authoritative; committed default Redis and Neo4j passwords (K8S-06, P1); Neo4j vs Memgraph; wrong probe path; drifted env names; no Celery | 1 P1, 6 P2, 2 P3 | k8s review §3 | NEW-K8S-1 to NEW-K8S-6 |
| A11Y-01 to A11Y-17 (2026-11-06) | Contrast failures on gold text, error cards and the "Related" label; clip dialog has no accessible name; no captions; cookie banner covers Send at 390 px; axe tests lack `wcag22aa` | 7 P1, 9 P2, 1 P3 (6 parts) | Accessibility audit §3 | NEW-A11Y-1 to NEW-A11Y-10 |

These IDs are proposed by the specification agents. They are not yet in `findings-index.md`. The next agent adds them during the findings recount (`FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` step 4).

## 3. Coverage against the six pillars

| Pillar | Covered before | Gap closed in this pass | Remaining gap |
|---|---|---|---|
| 1 Stability and cost | Failure register, SLO targets, cost per useful answer concept | Railway topology and failure modes; alert repair; backup contract; 10 runbooks; capacity limits | Real load, real cost, real restore: all live |
| 2 Answer intelligence | Question taxonomy, voice layers, ADR-001 | Retrieval pipeline per step with every LLM call; Variant A multi-clip spec; answer schema; 100%-quality classes | Data ceiling (RC-4): only 15 of 29 test questions had a showable clip in the top 10 [DOC-CLAIM]; retrieval cannot fix that |
| 3 Code, data, wiring | Store inventory, lineage, deletion matrix | Stage contracts with idempotency and partial-failure detection; correction propagation; 6 new data defects | Source registry (ADR-007) not built; live counts unknown |
| 4 Guru trust | Rights register, review package, misattribution risks | Registry schema; onboarding checklist; hard-coded literal table | Rights approval, guru review, clinician: human only |
| 5 Personal mentor | Memory architecture, ethical retention | Full lifecycle, RLS, export, erasure, saved wisdom as pointers, retention schedule | Journeys and reminders need decisions; no user research (`02` personas are hypotheses) |
| 6 FRs and NFRs | 32 FRs, NFRs with targets | 44 FRs and 82 NFRs with test, criterion and gate; 12 broken links | 18 NFRs are aspirational and unmeasured |

## 4. Coverage of the extra areas A to J

| Area | Status after this pass | Where |
|---|---|---|
| A Adversarial security | Specified: threat model, 40+ adversarial cases, untrusted-content fence, injection screens | Reliability spec §3.9; harness spec §A |
| B Knowledge governance | Specified: registration, withdrawal, correction propagation across Qdrant, cache, memory, citations, OKF and graph | Ingestion spec §6 |
| C Model lifecycle | Specified: model-change and embedding-change procedures with frozen-baseline gates | Harness spec §C |
| D Testing methodology | Specified per component, tied to failure modes | FR/NFR matrix testing section |
| E Operations and incidents | Specified: SLOs (proposed), alert rules, 10 runbooks, answer trace | Reliability spec |
| F ADRs | 16 historical ADRs, 25 "do not reintroduce" items, template | Historical ADR file |
| G Feedback loop | Specified: cause taxonomy, triage, human review, eval-set path; existing feedback stores keep seeker text without retention | Reliability spec §3.10 |
| H Accessibility and multilingual | Updated 2026-11-06: WCAG 2.2 AA audit done with an axe runtime run on 4 pages (17 findings, 7 P1; C7 not met). Multilingual rules and meaning-preservation tests specified; `lang` on quotes needs a clip language field (D-PA11Y4) | Accessibility audit; answer contract spec; FR/NFR matrix |
| I Traceability | 12 broken links listed | FR/NFR matrix |
| J Completeness challenge | §5 below | — |

## 5. Completeness challenge (brief Part J)

| # | Question | Answer |
|---|---|---|
| 1 | Engineering capability not evaluated? | Updated 2026-11-06: mobile apps, k8s manifests and accessibility are now reviewed (`specifications/MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md`, `K8S_MANIFESTS_REVIEW.md`, `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md`). Still not evaluated: the Lovable frontend sync path (D-24); load and cost under real traffic; a screen-reader session; native device tests. |
| 2 | User need not represented? | Real seeker research: no seeker has been interviewed (`02` §3-§6). Accessibility for users with low technical familiarity has requirements but no test. |
| 3 | Data-quality failure still possible? | A rebuild can silently produce an unservable or emptied collection (DATA-20, DATA-23) until NEW-ING-1 and NEW-ING-2 land. A corrected transcript can leave stale text in caches and saved items until the propagation tasks land. |
| 4 | What can break after deployment? | Requests dropped on every deploy (drain 0 s); startup refused for missing release identity; Redis evicting Celery data under `volatile-lru`; alerts that never fire or always fire. |
| 5 | External provider failure? | LLM provider outage: the gates fail closed to abstain, which is safe but looks like "no teaching" to users until NEW-ANS-2 and D-PQ9. Qdrant outage: honest abstain. Supabase outage: auth and memory fail; runbooks in the reliability spec. |
| 6 | How could a teacher's words be misrepresented? | A translated quote read as the teacher's words (label landed, ADV-05); a clip containing host speech (6.9% of top-1 [DOC-CLAIM]); speaker verification not required by default (D-PG5); joint attribution undecided (D-PG1). |
| 7 | What could make a correct answer misleading? | A relevant clip with a "Related, not a direct answer" label that users read as a direct answer; a clip that starts mid-thought; a failure shown as "no recording found". |
| 8 | Decisions that become expensive later? | Keeping two memory planes (D-PM1); keeping point IDs off the wire (D-PQ7); not building the source registry before more teachers arrive; keeping the graph deployed. |
| 9 | What blocks onboarding a new teacher? | No registry (ADR-013), 28 hard-coded places, no rights vocabulary (D-PG2), no approval owner (D-PG6). |
| 10 | What will the next coding agent misunderstand? | Stale CLAUDE.md values: pipeline order omits `KillSwitchStage` and `OffTopicStage`; scorer model and timeout defaults; gate budget 12 s in code (`first_person_pipeline.py:1311`), not 6 s; `persona_discriminator.py` is a persona judge, not the attribution source. The lessons review §8 lists the proposed corrections; the owner has not applied them. |
| 11 | Operational responsibility not assigned? | Backup on-call, clinician contact, legal contact, teachers' organisation contact (D-PE1); guru-review queue owner (D-PQ6); prompt owners (D-PG12). |
| 12 | What cannot be proven in this cloud environment? | Everything live: Qdrant contents, Railway behaviour, Supabase RLS on the real project, provider latency and cost, restore drills, and every human sign-off. |

> **Update 2026-11-06 (batch 12, 2c81a2d1):** The pipeline order in the root `CLAUDE.md` now matches `build_default_pipeline()` and `scripts/guards/pipeline_order_guard.py` checks it. `backend/CLAUDE.md` still shows the old order. The 12 s gate budget and the scorer defaults are unchanged. CQ-009 is Partial.

## 6. Remaining uncertainty

- The new defect IDs in §2 come from agents that read code but ran no tests. Each needs a failing test before its fix.
- The 2026-11-04 measured numbers (served share, usefulness, host-voice leak, latency) are still [DOC-CLAIM] from the repository's own local reports.
- The lead did not re-read every `path:line` cited in the 12 specification files. The independent review samples them (`FINAL_USAGE_AND_VERIFICATION_LOG.md` §4).

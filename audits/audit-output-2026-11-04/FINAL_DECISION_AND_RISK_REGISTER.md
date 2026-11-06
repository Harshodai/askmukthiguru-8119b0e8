# Final decision and risk register (2026-11-05)

Head `c9b42d3e`. This file collects every open owner decision and the top risks from the audit package and the 2026-11-05 specifications. It does not decide anything. Evidence labels: `CONVENTIONS.md` §3.

## 1. How to use this file

1. Decide the items in §2 in gate order: Gate A first.
2. Record each answer in `unresolved-questions.md` (existing D-01 to D-27) or, for a proposed decision, give it the next free number from D-28 upward and record it there.
3. Update the spec that raised it (column "Raised in").
4. A coding agent must not implement a decision-gated variant until the decision is recorded.

Proposed decision IDs keep the prefix of the spec that raised them, so the specs stay readable: D-PG (guru and harness specs), D-PI (ingestion), D-DQ (data quality), D-PM (memory), D-PE (reliability and security), D-PQ (retrieval, synthesis and answer contract). D-28 to D-30 were proposed in `FINAL_READINESS_AND_GAP_ANALYSIS.md`.

## 2. Open decisions by release gate

### 2.1 Blocks Gate A (Railway staging)

| ID | Question | Recommendation in the source | Raised in |
|---|---|---|---|
| D-26 | Qdrant hosting: Railway service with a volume, or Qdrant Cloud? | Decide with cost data; options and trade-offs in the Railway runbook | `unresolved-questions.md`; Railway runbook |
| D-14 | Which serving posture does staging use? Code default: bridge collection `first_person_v8` unless both `first_person_context_harness_enabled` and `first_person_context_terminal_enabled` are true (`backend/app/config.py:41`, `:205`, `:282`, `:298`, `:2318-2326`) | Pin one posture per environment and log it at startup | `unresolved-questions.md`; data-quality spec |
| D-07 | Does any client use `/api/first-person/query`? | Admin-only unless a client needs it | `unresolved-questions.md` |
| DATA-01 (owner action) | Copy the Qdrant snapshot off the owner's Mac and upload it to the chosen host | Do it first; it is the only copy | `FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` |
| D-28 | Railway configuration source of truth | **Closed by research 2026-11-05**: `.railway/railway.ts` (IaC) is the current method; `railway.json`/`railway.toml` are deprecated and stop working on 2026-12-01 (docs.railway.com). What remains is implementation: declare all services and set `RAILWAY_DOCKERFILE_PATH`. | `FINAL_RAILWAY_STAGING_READINESS.md` |
| D-29 | Staging access model (private domain, auth gate, tester list) | Closed testers only | `FINAL_READINESS_AND_GAP_ANALYSIS.md` |
| D-30 | Do the Celery worker and beat run in staging, or does staging run in documented degraded mode? | Run them; they own erasure and memory jobs | `FINAL_READINESS_AND_GAP_ANALYSIS.md` |
| Railway runbook items | Staging Supabase project; source of `JWT_SECRET` (the deploy script generates a random one); one Railway project with environments or a separate staging project | See the runbook decision list | Railway runbook |

### 2.2 Blocks Gate B (production, invited users)

| ID | Question | Recommendation in the source | Raised in |
|---|---|---|---|
| D-01 | Make the repository private now; purge tracked content; rewrite history? (P0 IP-001, X-06) | Private today; history rewrite after advice | `unresolved-questions.md` |
| D-02 | Keep the 1,546 tracked OKF teaching files in the repository? | Move them to the private store | `unresolved-questions.md` |
| D-08 | Where do private evidence and the source bundle live? | Private bucket and private evidence repo, referenced by hash | `unresolved-questions.md` |
| D-09 | Who produced the 303-row gold sheets; were annotators independent? | Treat as non-independent; commission a double-blind set | `unresolved-questions.md` |
| D-11 | Scope of the 2026-11-04 authorisation | "Owner-only local review" | `unresolved-questions.md` |
| D-13 | Is the broadcaster clearance intentional and filed? | Non-servable until permitted. Note: the v10 builder hard-codes "times now" in its rights allowlist (DATA-21) | `unresolved-questions.md`; ingestion spec |
| D-15 | Who writes to Qdrant; turn on API keys? | Keys on; builder-only write key | `unresolved-questions.md` |
| D-16 | Relevance-scorer model and price | Record a dated price entry; the code default model is empty (`config.py:476`) | `unresolved-questions.md`; harness spec 2026-11-06: also confirm that OpenRouter returns `usage.cost` for the scorer; if not, each call keeps the $0.03 reservation (SYS-014; `specifications/LOAD_AND_COST_MODEL.md` §5). |
| D-19 | Delete the churn funnel and win-back emails? | Yes, after the direct deletion path ships | `unresolved-questions.md` |
| D-21 | Healing-course assignment and proactive Serene Mind on by default? | Off by default; opt-in | `unresolved-questions.md`; memory spec |
| PROPOSED D-PG13 (= D-PQ4) | One scorer timeout value (code 25 s at `config.py:478`, `docker-compose.yml:325` 15 s, CLAUDE.md 12 s). Raised twice; decide once | Retrieval spec: keep `Settings` 25.0 and align both compose files; harness spec: pick one and pin it in config lint | Harness spec; retrieval spec |
| PROPOSED D-PQ3 | Floors for Recall@10, Showable@10, served share, false-serve rate on out-of-corpus questions, Indic parity, meaning-preservation scores | Report-only until a baseline exists; fix floors before the measured run (B15) | Retrieval, synthesis and answer specs |
| PROPOSED D-PQ9 | When a system failure blocks the check (for example a scorer timeout), show "try again" copy instead of "no recording found"? | Yes: the current copy misreports a failure as an absence of teaching | Answer contract spec |
| PROPOSED D-PG3 | May production start with an invalid teacher registry? | No | Guru spec |
| PROPOSED D-PI1 | May `--replace-existing` run on a serving collection? | No: a correction makes a new collection | Ingestion spec |
| PROPOSED D-PI4 | How did live v10 obtain `domain_rights_status = "licensed"` when the builder never stamps it (DATA-20)? | Needs the owner's build log | Ingestion spec |
| PROPOSED D-DQ1 | Should the legacy store's `points_servable` compare text and hash? | Yes | Data-quality spec |
| PROPOSED D-DQ2 | Which `contained_in_other_span_rate` blocks promotion? | Owner sets it in the scorecard | Data-quality spec |
| PROPOSED D-PM8 | After account deletion, may a minimal erasure receipt and consent history stay? Today both are deleted with the account | Keep a content-free receipt (DPDP evidence) | Memory spec |
| PROPOSED D-PM10 | Which memory-extraction path survives: backend or edge function? | Backend only; disable the edge drain | Memory spec |
| PROPOSED D-PE1 | Backup on-call, clinician contact, teachers' organisation contact, legal contact | Name them, or accept "none" for beta in writing | Reliability spec |
| PROPOSED D-PE2 | May `chat_queries`/`chat_responses` keep scrubbed seeker and answer text, and for how long? | Privacy decision; the answer trace needs it only for replay | Reliability spec |
| PROPOSED D-PE4 | Retention windows for feedback events and trace rows | 90 days | Reliability spec |
| PROPOSED D-PE5 | May seeker free text go to an LLM for clustering or lesson mining? | No; flag the existing mining path off | Reliability spec |
| PROPOSED D-PE6 | May a crisis canary use a labelled test account exempt from quota and telemetry? | Yes, with a closed label | Reliability spec |
| PROPOSED D-PE7 | Final availability, latency and abstain targets and spend caps after two weeks of staging data | Keep the proposed numbers provisional | Reliability spec |

### 2.3 Blocks Gate C (public release)

| ID | Question | Recommendation in the source | Raised in |
|---|---|---|---|
| D-03 | Allow a clearly labelled assistant explanation layer beside verbatim quotes (ADR-001)? Gates multi-video synthesis Variant B and PersonalizeStage's generating path | Behind a flag; owner-only review first | `unresolved-questions.md`; synthesis spec; memory spec |
| D-06 | Engage a clinician for the topic-versus-state distress rule (T4-04) | Yes; ship only with written clinician sign-off | `unresolved-questions.md` |
| D-10 | Do the clinician artefact and the content owner's message exist outside the repository? | File them privately, by hash | `unresolved-questions.md` |
| D-12 | Did the teachers' organisation authorise extracting Sri Preethaji's voice for Serene Mind? | Remove until a licence is filed | `unresolved-questions.md` |
| D-20 | Were the other-teacher personas ever intended? | Remove the seeds | `unresolved-questions.md` |
| D-22 | Priority Indic languages for native review | Owner choice | `unresolved-questions.md` |
| D-23 | May real seeker questions be used for the held-out set? | Only with opt-in and redaction | `unresolved-questions.md` |
| D-25 | Add a usefulness target and a served-share floor to the pass bar? | Yes | `unresolved-questions.md` |
| PROPOSED D-PG1 | Which source kinds may carry both teachers' names (joint attribution)? | Guru review | Guru spec |
| PROPOSED D-PG2 | Allowed-use vocabulary per rights grant | Owner + rights holder | Guru spec |
| PROPOSED D-PG4 | May an organisation alias ("Ekam") expand to both teachers in retrieval, or only in labels? | Labels only | Guru spec |
| PROPOSED D-PG5 | Is `first_person_require_speaker_verified` meant to be true for faculty review? (`config.py:266`) | Owner | Guru spec |
| PROPOSED D-PG6 | Who may approve a new teacher? | Owner + teachers' organisation | Guru spec |
| PROPOSED D-PI2 | After a takedown, redact quoted text in stored assistant messages, or only flag the citation? | Owner | Ingestion spec |
| PROPOSED D-PI3 | Does withdrawal cover all legacy `first_person_v*` rollback collections? | Yes [INF] | Ingestion spec |
| PROPOSED D-PM7 | Withdrawn saved teaching: hide fully, or show a tombstone? | Tombstone with no text or link | Memory spec |
| PROPOSED D-PQ2 | Serve a 2-3 clip verbatim answer (synthesis Variant A) for multi-aspect and both-teacher questions? Does `26` §7.3 ("no multi-video synthesis before per-facet retrieval works") cover a set taken from one retrieval pool? Variant A needs this, not D-03 | Shadow mode first; serve to the owner account, then wider | Synthesis spec |
| PROPOSED D-PQ5 | May an assistant sentence use first person ("I") in the assistant's own voice? Matters only for Variant B | No first person | Synthesis spec |
| PROPOSED D-PQ6 | Who staffs the guru-review queue for conflicted clip sets: faculty or owner? | Owner | Synthesis spec |
| PROPOSED D-PQ8 | Who authors and approves the reflection and practice catalogue? | Owner approves; faculty reviews before public use | Answer contract spec |

### 2.4 Product and engineering decisions with no gate today

| ID | Question | Raised in |
|---|---|---|
| D-04 | Keep a general assistant for non-teaching questions? Recommendation: static boundary | `unresolved-questions.md` |
| D-05 | Retire Memgraph and LightRAG from serving and deploy? The graph is off the default teaching path but still deployed and written at ingestion (`write_ontology_to_neo4j=True`) | `unresolved-questions.md`; guru spec |
| D-17 | Remove the Sarvam, Ollama and NIM provider code? | `unresolved-questions.md` |
| D-18 | Delete `ToneAdapterStage` and the dormant modules? | `unresolved-questions.md` |
| D-24 | Lovable's role; merge or delete `lovable-sync` | `unresolved-questions.md`; `specifications/LOVABLE_SYNC_PATH_REVIEW.md` §4 (2026-11-06: the bot self-merges to `main`; proposal: PR-only with required checks, delete the stale branch first, revisit retirement later) |
| PROPOSED D-PG7 | Is the Supabase `gurus` table read by live code? | Guru spec |
| PROPOSED D-PG8 | Concept vocabulary table or graph for facet tagging? Proposed: table | Guru spec |
| PROPOSED D-PG11 | Prompt registry loaded from files in the image or from the database? Proposed: files | Harness spec |
| PROPOSED D-PG12 | Who owns each prompt id? | Harness spec |
| PROPOSED D-PG14 | Latency and cost budgets for a model change | Harness spec |
| PROPOSED D-PG15 | May per-model output-path rules live in the prompt registry? | Harness spec |
| PROPOSED D-PG16 | Does the ingest-time injection screen drop a span or only flag it? | Harness spec |
| PROPOSED D-PG17 | May a second vendor serve as the judge fallback? | Harness spec |
| PROPOSED D-PG18 | Accept paraphrased injection (adversarial case 10) as a tracked known gap? | Harness spec |
| PROPOSED D-PM1 | Make `canonical_memories` the only store the UI manages | Memory spec |
| PROPOSED D-PM2 | Store per-turn distress level or emotional arcs at all? | Memory spec |
| PROPOSED D-PM3 | Review model for extracted facts (queue sensitive only, or every fact) | Memory spec |
| PROPOSED D-PM4 | Retention values for proposals, learning events, suppression | Memory spec |
| PROPOSED D-PM5 | May a user save a clip in Temporary Chat? | Memory spec |
| PROPOSED D-PM6 | Reminders in scope? Channel? | Memory spec |
| PROPOSED D-PM9 | Who curates learning journeys; how many at launch? | Memory spec |
| PROPOSED D-PE3 | May an anonymous seeker submit a report with a cause and a `request_id`? | Reliability spec |
| PROPOSED D-PQ1 | Run the new `RetrievalPlan` in shadow mode, then on after the bank run? | Retrieval spec |
| PROPOSED D-PQ7 | Put the Qdrant point id on the wire as `clip_ref`? Cross-spec conflict: the memory spec needs a clip id on the client for saved clips, but `backend/tests/test_citation_contract.py:169-205` forbids `point_id` on the wire. Decide before NEW-ANS-3 or the saved-wisdom tasks | Answer contract spec; memory spec |

### 2.5 Decisions raised by the 2026-11-06 reviews (mobile, k8s, accessibility)

| ID | Question | Recommendation in the source | Gate | Raised in |
|---|---|---|---|---|
| PROPOSED D-PMOB1 | Keep Capacitor as the only mobile client and freeze `mobile/expo/`? | Yes | C | Mobile spec |
| PROPOSED D-PMOB2 | Native Sign in with Apple, or the web OAuth flow? | Native, after MOB-01 is fixed for Google | C | Mobile spec |
| PROPOSED D-PMOB3 | Ship voice input in v1? | No; hide it on native | C | Mobile spec |
| PROPOSED D-PMOB4 | Background audio for clips? | No for v1 | C | Mobile spec |
| PROPOSED D-PMOB5 | Universal Links and App Links? | No for v1; custom scheme with PKCE | C | Mobile spec |
| PROPOSED D-PMOB6 | Who signs the store privacy answers? | The owner, after MOB-04 reconciliation | C | Mobile spec |
| PROPOSED D-PMOB7 | Keep local chat history on native? | Yes, with backup excluded and a clear-data control | C | Mobile spec |
| PROPOSED D-PMOB8 | Store test tracks for invited users before Gate C? | No; keep mobile at Gate C | B or C | Mobile spec |
| PROPOSED D-PK8S1 | Kubernetes manifests: keep as reference (header and drift test), fix to parity, or retire? | Keep as reference only | None | k8s review |
| PROPOSED D-PA11Y1 | Which WCAG 2.2 level binds the first invited release? | AA on the core journey (C7) | C | Accessibility audit |
| PROPOSED D-PA11Y2 | May captions be built from the auto-transcript, with a visible "auto-transcript" note? | Yes | C | Accessibility audit |
| PROPOSED D-PA11Y3 | Move A11Y-02 and A11Y-10 (helpline) into B16 and A11Y-14 (deletion) into B12? | Yes | B | Accessibility audit |
| PROPOSED D-PA11Y4 | Who supplies a language per clip for `lang` on quotes? | Optional `language` field; offline tag | C | Accessibility audit |
| PROPOSED D-PA11Y5 | Does Escape on the first-run safety notice count as acceptance? | Keep; confirm with the owner and the clinician | C | Accessibility audit |
| PROPOSED D-PA11Y6 | Approve `eslint-plugin-jsx-a11y` (MIT) as a dev dependency? | Yes | None | Accessibility audit |
| PROPOSED D-PA11Y7 | Who runs the screen-reader session, in which languages? | Owner names a tester; English, then Hindi or Telugu | C | Accessibility audit |

## 3. Risk register

Likelihood and impact are the lead's judgement [INF], not measurements.

| ID | Risk | Likelihood | Impact | Evidence | Mitigation | Gate | Owner |
|---|---|---|---|---|---|---|---|
| RK-01 | The only copy of the serving corpus is lost | Medium | Critical | DATA-01; backups local and not installed | Copy the snapshot off the Mac; restore drill | A | Owner |
| RK-02 | Public repository exposes verbatim spans, transcripts, audio and backups | Ongoing | Critical | P0 IP-001, X-06 | D-01 | B | Owner |
| RK-03 | A fresh v10 build serves nothing, or a correction empties a video | High on next rebuild | High | DATA-20 (`domain_rights_status` never stamped; retrieval filters on "licensed", `first_person_context_store.py:464`); DATA-23 (per-video replace deletes before upsert) | Fix DATA-20/22/23 before any rebuild | A | Agent |
| RK-04 | Staging fails to start or drops requests on deploy | High | Medium | Railway default drain 0 s vs assumed 60 s; `railway up` gives no `RAILWAY_GIT_COMMIT_SHA` so the FP contract can abort (`first_person_release.py:119-125`); Celery modes install no SIGTERM handler; boot can approach the 330 s healthcheck | Railway runbook tasks | A | Agent |
| RK-05 | Alerts give false confidence | High | High | Some rules read metrics no code emits; `BackupStale` fires permanently; Prometheus prod config scrapes unreadable paths; `guru_integrity_breach_total` has no rule | Reliability spec alert repair | B | Agent |
| RK-06 | Benign seekers get distress templates; Indic crisis under-detected | High | High | RC-5; T4-04 reserved; no native review | Clinician + native review | C | Owner + clinician |
| RK-07 | Prompt injection through transcripts or stored memory | Medium | High | Rerank and selector prompts unfenced; the generation fence does not neutralise closing tags; no ingest-time injection screen; memory extractor input unfenced and the injection regex is English-only (MEM-012) | Harness spec §A; memory spec | B | Agent |
| RK-08 | Deletion requests not fully honoured | Medium | High | ADV-01 (no purge job); MEM-009 export omits memory; MEM-011 account deletion removes receipts | T1-12, T6-06, memory spec tasks | B | Agent (reserved T6-06) |
| RK-09 | Withdrawn teaching stays visible in saved items or stored answers | Medium | High | MEM-010 (notebook items store answer text; no `takedown()`); DATA-07, DATA-12 open | Ingestion spec §6; memory spec saved-wisdom pointer model | C | Agent |
| RK-10 | Agents implement from stale CLAUDE.md values | High | Medium | Pipeline order omits `KillSwitchStage` and `OffTopicStage`; scorer model and timeout defaults differ; gate budget is 12 s in code (`first_person_pipeline.py:1311`) not 6 s; `persona_discriminator.py` is not the attribution component | `FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` §8 proposed corrections; owner applies them | A | Owner |
| RK-11 | Unbounded or untracked LLM cost | Low (guard on by default) | High | T1-07 closed; scorer model has no price entry; no prompt version in telemetry | D-16; harness spec | B | Agent |
| RK-12 | Teachers' organisation refuses any assistant explanation | Unknown | High | `26` §7.3 | Variant A (verbatim multi-clip) remains valid | C | Owner |
| RK-13 | Future teacher onboarding needs code changes in many places | High | Medium | ADR-013 not built; 28 hard-coded teacher places (guru spec) | Guru spec registry tasks | C | Agent |
| RK-14 | Seeker text retained without limit in feedback and lesson stores | Medium | Medium | Reliability spec §2 | D-PE2, D-PE4, D-PE5 | B | Owner |
| RK-15 | Regressions from many agent sessions | Medium | Medium | `main` unprotected (X-02, T0-03); CI red on `c9b42d3e` (GitHub Actions run list, lead, 2026-11-05) | Branch protection; CI fix | A | Owner |

> **Update 2026-11-06 (batch 11, 1503e5f2):** ADR-013 is partly built: the registry schema, a validator and generated impersonation patterns exist. The 28 hard-coded places (the guru spec counts 591 lines) are not removed. Mitigation is half done.

> **Update 2026-11-06 (batch 12, 2c81a2d1):** Root `CLAUDE.md` pipeline order is fixed and guarded. `backend/CLAUDE.md` still has the old order and still says `memgraph-mage:latest`. The other stale values in this row remain. Risk stays High until those are fixed.
| RK-16 | Default Redis and Neo4j passwords committed in the Helm values and a ConfigMap get reused somewhere real | Low | High | K8S-06 (`values.yaml:153`, `:189`; `configmap.yaml:19`), k8s review | NEW-K8S-5; D-01 | B | Agent |
| RK-17 | Mobile store rejection or takedown: OAuth inside the WebView, no iOS privacy manifest, undeclared microphone use, disclosures that omit Sentry replay and the LLM provider | High if submitted today | Medium | MOB-01 to MOB-05, MOB-10 | Mobile spec tasks; D-PMOB6 | C | Owner + agent |
| RK-18 | Seekers with low vision cannot read trust labels ("Related, not a direct answer" about 2.9:1; gold text 1.52:1) or reach help | High | Medium | A11Y-01 to A11Y-03, A11Y-10 (axe runtime run, 2026-11-06) | NEW-A11Y-2, NEW-A11Y-8 | C (B for helpline per D-PA11Y3) | Agent |
| RK-19 | An unreviewed Lovable bot commit lands on `main` and undoes a safety, voice or storage contract | High while direct writes continue | High | LOV-01, LOV-02, LOV-06 (202 bot merges, last 2026-10-31) | NEW-LOV-01 (owner), NEW-LOV-02, NEW-LOV-03 | B | Owner + agent |
| RK-20 | The budget guard denies service at low traffic because unreported costs keep the full reservation | Medium | High | SYS-014 (`openrouter_budget.py:87-98`; `config.py:640`, `:644`) | D-16; NEW-LOAD-3; count denials (NEW-OPS-8) | B | Owner + agent |

## 4. Verified, assumptions, unknowns

- Verified: decision texts copied from `unresolved-questions.md` and from §9 of each specification; config lines re-read by the lead on 2026-11-05.
- Assumptions: likelihood and impact ratings.
- Unknown: whether the owner already holds answers to D-09, D-10, D-12 or D-PI4 outside the repository.

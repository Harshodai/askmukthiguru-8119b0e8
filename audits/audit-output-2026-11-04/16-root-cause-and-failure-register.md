# 16 — Root-cause and failure register

Owner: lead. Pillars: all. Inputs: every specialist document, `01`, and the independent review in `26`.

The per-finding table is `findings-index.md`. This document explains **why** the 153 findings exist, which ones are the same defect seen from two sides, and how they make a real seeker's experience fail.

## 1. The verdict in one paragraph

The code base is large and serious. Its strongest parts are safety-first ordering, an integrity gate on verbatim clips, and a strict `fp-context-v1` data contract. But the product does not yet do what it is for. The most common emotional questions are classified as distress and get a template. If an operator switches the first-person bridge off, teaching questions fall through to a generating LLM prompt (ADV-03). A good answer is at most one clip, and about 11% of on-topic questions end with a useful answer [DOC-CLAIM `15`]. Release evidence was recorded as "ready" on evidence that does not reproduce and that describes itself as non-independent. The public repository publishes the teaching corpus. None of these is a missing feature. They come from nine systemic causes, listed below. Fix the causes, not the symptoms.

## 2. Root-cause clusters

### RC-1 — No single source of truth for decisions
| Aspect | Content |
|---|---|
| Pattern | The same decision is coded in several places, and the copies drift. |
| Evidence | Domain scope ×3 (AI-001). Teacher identity ×7 registries and 2 ID vocabularies (GURU-010, GURU-013, DATA-13). LLM provider modules ~14 (CQ-002, AI-005). Caches ≥8 (CQ-003). Memory planes 7 (MEM-001). Settings 679, 23 read but undeclared (CQ-010). Supabase tables created more than once: 32 (DATA-11). Assistant slugs disagree (PRD-005). Two FP surfaces (PRD-007). |
| Mechanism | Each agent session adds a local copy instead of finding the owner. `extra="ignore"` and function-local imports hide the drift. |
| Systemic fix | One owner module per decision: route-decision service, teacher registry, LLM gateway, canonical memory, versioned cache tiers, typed nested settings with a lint. Each gets a CI guard against new copies. |
| Tasks | T4-03, T8-01, T7-03, T6-01, T7-04, T2-06, T3-08, T1-04 |

### RC-2 — Claims are decoupled from reproducible computation
| Aspect | Content |
|---|---|
| Pattern | Readiness and quality are declared in documents. They are not computed from tracked evidence in CI. |
| Evidence | Gate "24/24" depends on gitignored sheets (X-01, GURU-001). "Human gold" self-describes as `independent_review:false` (GURU-002, EVAL-001). Staging evidence carries a non-existent commit id (GURU-003). Scopes contradict notes (GURU-004). An AI subagent is listed as a human certifier (GURU-006). CI quality gates skip without a deployment (EVAL-003). Benchmarks measure a path users no longer reach (EVAL-004). Load evidence uses a mock LLM (SYS-008). No outcome metric exists (SYS-011). The task list records earlier false greens ("FACULTY-READY GO", "n=300 calibration", "sub-30 ms") [DOC-CLAIM task list §1.5]. |
| Mechanism | The owner and agents work toward a status, not toward a measurement. Tests are edited to match the wanted status (`test_first_person_public_release_gate.py:924`). |
| Systemic fix | Every status is the output of a command that runs in CI on a clean checkout. Private evidence is referenced by hash, not by presence. Human approvals are artefacts with a hash and a named person, never strings. |
| Tasks | T0-04, T1-11, T2-01, T2-02, T2-03, T2-04, T3-09 |

### RC-3 — Three products live in one code path
| Aspect | Content |
|---|---|
| Pattern | The code carries (a) a generative 20-node RAG assistant, (b) a verbatim first-person clip server, and (c) a neutral general assistant (PR #76). Policy says (b) only. Routing and failure handling still reach (a) and (c). |
| Evidence | Turning the first-person bridge off routes teaching questions to the generating prompt (ADV-03, RET-09). Narrow node failures fall through to generation (SYS-001). Questions that mix a general-task word with an emotion word reach the general lane (ANS-003, SYS-002; narrowed by the independent review). A "teacher's voice" register is added in general mode (AI-003). Root `CLAUDE.md` orders teacher-voice delivery, while the code forbids it (ANS-005). Unsourced quotes are attributed to teachers in other surfaces (GURU-012). Dormant editorial and hybrid paths rewrite teacher words (AI-006, DATA-04). |
| Mechanism | The product definition changed three times in about ten weeks (`01` §5). Old paths stayed on as fallbacks. |
| Systemic fix | Decide the general lane (ADR-002). Make every teaching-route failure a static abstain. Remove the paths that can generate text in a teacher's voice. Put the voice rule in a guard, not in prose. |
| Tasks | T0-05, T1-01, T1-02, T1-03, T1-05, T1-06, T4-03 |

### RC-4 — The data layer has no governed identity or lifecycle
| Aspect | Content |
|---|---|
| Pattern | Identity, version, rights and deletion are not enforced across stores. |
| Evidence | `transcript_hash` has three meanings (DATA-03). The builder is add-only and snapshots after writing (DATA-05). Qdrant has no write control; one incident is recorded (DATA-06). No takedown (DATA-07). The corpus cannot be rebuilt (DATA-01). Two transcript lineages (DATA-09). The approved version is not the served version (DATA-16). Dedup runs before the gates (RET-01). Dense-only retrieval breaks invariant 5 (RET-02). No encoder check (RET-07). v10 fails its own scorecard 13/26 (DATA-14). |
| Mechanism | Offline builders and online ingestion grew separately. Point payloads act as the system of record. |
| Systemic fix | A Postgres source registry is the authority: source → video → transcript version → span → point. It holds rights and takedown state. Builders read from a private, checksummed bundle, write with a write key, and promote only through the scorecard gate. |
| Tasks | T3-01 … T3-12, T4-01, T4-02 |

### RC-5 — The safety classifier confuses a topic with a state
| Aspect | Content |
|---|---|
| Pattern | Talking *about* anxiety, fear or confusion is treated as *being in* distress. |
| Evidence | MODERATE regex on "anxiety", "anxious", "stressed" (ANS-001). MILD → MODERATE upgrade (ANS-002). Two MODERATE keywords in history → SEVERE pre-emption (SAFE-002). Overfire is accepted, not measured (SAFE-003). Regex not reviewed by a clinician or native speakers (SAFE-001). Helplines: 1 of 15 call-verified (SAFE-004). |
| Mechanism | A good safety instinct (fail toward care) is applied without a topic-versus-state discriminator, on the product's most important question class. |
| Systemic fix | A discriminator for topic versus state. History escalation counts state disclosures only. The bridge declines only on state. Evaluate on clinician- and native-reviewed sets. Show verified helplines only. **Clinician sign-off is required before shipping.** |
| Tasks | T4-04, T4-07, T2-01, T10-02 |

### RC-6 — The answer model is "one clip or abstain"
| Aspect | Content |
|---|---|
| Pattern | The serving contract cannot express a complete answer. |
| Evidence | One clip (ANS-004). No multi-video composition (RET-03); the v10 harness abstains on cross-parent mixing. No per-facet retrieval (RET-04). No depth control (ANS-006). Follow-up by string concatenation (ANS-007). Multilingual gets English plus glue (ANS-008). No seeker correction channel (PRD-006). The pass bar accepts 70% abstention (EVAL-006). |
| Mechanism | Invariants 15 and 21 (zero generated text) were set to stop impersonation. They also stop explanation, synthesis and reflection, which the mission requires. |
| Systemic fix | ADR-001: a layered answer. L1 verbatim quotes are rendered from the store. L3 is a clearly labelled assistant explanation, and every sentence is entailment-checked against cited spans. L5 is reflection in the assistant's voice. The teacher's voice is never generated. **This needs the owner's and the teachers' organisation's approval.** |
| Tasks | T5-01 … T5-06, T6-04 |

### RC-7 — Rights are treated as statements, and the repository is public
| Aspect | Content |
|---|---|
| Pattern | Permission is asserted, not filed. Content is published by default. |
| Evidence | Public repo with ~2,737 verbatim spans, 1,546 OKF files, data backups (X-06, IP-001, SEC-005, DATA-19). Teacher voice audio from YouTube (IP-002). No filed written approval (IP-003). yt-dlp acquisition (IP-004). Broadcaster content treated as approved (IP-005). Other-teacher personas (GURU-011, IP-006). |
| Systemic fix | A private repository or a purged tree. Private evidence and a source bundle. A per-source `permission_ref` in the source registry. Non-servable by default. |
| Tasks | T0-01, T0-02, T3-06, T3-09, T10-02 |

### RC-8 — The engineering process does not protect the main branch
| Aspect | Content |
|---|---|
| Evidence | No branch protection (X-02). PRs of 1,034 files (X-03). Two frontend writers (X-05). Docs used as memory (X-07, CQ-009). Giant functions (CQ-001). Broad exception handling (CQ-006). Hidden import cycles (CQ-007). Shims and stubs (CQ-005). |
| Systemic fix | Branch protection with a small required check set. One task ID per PR. A short status file. An archive for `lessons.md`. Lint ratchets. |
| Tasks | T0-03, T0-07, T1-13, T1-15, T7-01, T7-05 |

### RC-9 — Operational readiness was never exercised
| Evidence | No deploy since August, and no staging (SYS-007). The rights register is not in the image (DATA-02). The spend cap is off (SYS-004). An unauthenticated endpoint spends LLM budget (SEC-001). The sync pipeline wedges threads (SYS-003). p95 12–14 s (SYS-006). Backups fail; RPO is unbounded (SYS-012). PII is in logs (SEC-003). Datastores bind to 0.0.0.0 (SEC-006). |
|---|---|
| Systemic fix | Staging first, with IaC for every service, smoke tests, real-model load tests, spend caps on, backups with restore drills, and alerts. |
| Tasks | T1-07, T1-08, T1-09, T1-14, T3-01, T3-10, T7-02, T9-01 … T9-03 |

## 3. Critical records (consolidated)

### X-RC2 — Release-evidence integrity (X-01, GURU-001, GURU-002, EVAL-001)
| Field | Value |
|---|---|
| Pillars | P4, P6, P3 |
| Severity | P1 (the highest-ranked P1) |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | CI job 126691871430: `OWNER_ACTION_REQUIRED` on a clean checkout (`01` §8.3). Gate check `gold_label_evidence` fails because `.gitignore:391` ignores `evals/gold_set_v1/annotator_A.csv` and `annotator_B.csv` (`23`). Gold reports say `independent_review:false`, `annotation_method: curated_consensus_alignment`, "external double-blind human rating remains pending", agreement and κ = 1.0 on 303 items (`18` §2). The calibration profile is still the n=14 pilot (`18` §2). `b7_release_authorization` sets all 6 scopes true, including public production (`23`). |
| Actual | The authorisation record enables public release on evidence that is unreproducible, self-declared non-independent, and partly invalid. |
| Expected | Authorisation is a computed state over hashed, independent, human evidence. CI reproduces it. |
| Root cause | RC-2. |
| User impact | If anyone acts on the record, unvalidated answers reach the public as "reviewed". |
| Why P1 and not P0 | The independent review rated it P1, and the lead agrees. No deploy can happen while `main` is red and Railway is stopped, so no seeker is harmed yet. It is still the first P1 to fix: the control that should keep unvalidated content from the public accepts this evidence. |
| Remediation | T0-04 (restore the honest test; correct the scopes), T1-11 (gate recomputes agreement, requires independence flags, valid SHA ancestry, human certifiers, helpline age), T3-09 (private evidence by hash), T10-02 (real independent labelling). |
| Acceptance | CI and the owner's machine compute the same gate status for one commit. The gate rejects `independent_review:false`. `main` is green. |
| Regression test | Gate fixtures for non-independent labels, invalid SHA, non-human certifier, stale helplines. Each must fail. |
| Verification | [V-GIT] [V-STATIC]; independent check in `26` §2 |

### X-RC7 — Public exposure of teaching content (X-06, IP-001, plus SEC-005, DATA-19, IP-002, IP-008)
| Field | Value |
|---|---|
| Pillars | P4, P1 |
| Severity | P0 |
| Type | Confirmed defect (exposure is a fact; legal impact is for the rights holders) |
| Evidence | GitHub API `visibility=public` (`01` §2). `audits/evidence/public_release_v10_points_export_2026-10-21.json` (7.9 MB) holds `verbatim_text` and `source_transcript_text` for ~2,737 points (`14c`). 1,546 tracked OKF files. `data/*.json` corpus and graph backups (`14`). `public/audio/meditation/preethaji-serene-mind.mp3` from YouTube video `igSp4H0OWLE` (`14c`). |
| Actual | Anyone can clone the corpus and the voice audio. |
| Expected | Nothing the teachers' organisation has not licensed in writing is publicly downloadable. |
| Why P0 | The exposure continues every day, forks and caches make it hard to reverse, and it damages the trust conversation with the teachers. |
| Remediation | T0-01 (owner: make the repository private now; this is reversible and takes minutes). T0-02 (purge tracked content; extend the publication guard). History rewrite only on owner approval. |
| Acceptance | The repository is private, or a clean public tree has none of the listed content, and a guard blocks re-adding it. |
| Verification | [V-GIT] [V-STATIC]; independent check in `26` §2 |

## 4. Severity reconciliation (lead decisions)

| ID | Specialist | Lead | Reason |
|---|---|---|---|
| X-01, GURU-001, GURU-002, EVAL-001 | P1 / P0 / P0 / P1 | P1 | One root (X-RC2). The reviewer judged P0 inflated: no seeker is harmed until a deploy, and CI blocks the deploy. |
| X-06, IP-001 | P1 (lead) / P0 | P0 | The exposure is happening now, cannot be undone once cloned, and costs minutes to stop. The reviewer proposed P1; the lead keeps P0 (`26` §7). |
| SAFE-005 | P2 | P1 | Same as GURU-005. |
| RET-09 | P2 | P1 | ADV-03 is a concrete P1 trigger of the same fail-open design. |
| ANS-003, SYS-002, AI-001 | P1 | P2 | The reviewer refuted the broad leak: questions without keywords go to the teaching lane. |
| SYS-001 | P1 | P2 | The bridge catches its own exceptions; the remaining fall-through is narrow. |
| RET-01, RET-02, DATA-03 | P1 | P2 | Effects unmeasured or failing closed; v10 is not the code default. |
| UX-001 | P1 → P2 (first draft) | P1 | The reviewer found the funnel mounted and the only UI deletion path. |
| MEM-002 | P1 | P2 | A gap and some wasted cost; it does not block testing or review. |
| PRD-008 | P1 | P2 | Essential before broader release, not before internal testing. |
| ADV-05 | P3 (reviewer) | P2 | A translated quote can be read as the teacher's own words. |
| DATA-04, AI-006 | P2 | P2 (latent P0) | Dormant. Removed early (T1-02) because enabling either creates a P0. |

## 5. Failure-mode register (what a seeker experiences)

| FM | Seeker scenario | Mechanism | Findings | Detection signal to add | Fix |
|---|---|---|---|---|---|
| FM-1 | "What is the cause of my anxiety?" → a meditation invitation and helplines, no teaching | Topic read as state; bridge declines | ANS-001, ANS-002 | Share of on-topic questions routed to distress (target ≤5% on a reviewed benign set) | T4-04 |
| FM-2 | Third question about fear → crisis helpline pre-emption | History escalation counts topic words | SAFE-002 | Benign multi-turn SEVERE rate (target 0) | T4-04 |
| FM-3 | "My career worries are hurting my mental health — what do the teachings say?" → general LLM advice with a teacher-register block | General-task word + emotion word → general-lane exit; voice block | ANS-003 (narrowed), AI-003, SYS-002 | Teaching-intent questions answered by the general lane (target 0) | T4-03, T1-06 |
| FM-4 | Operator switches the bridge off during an incident, or a narrow node fault occurs → generated teaching prose | The kill switch and node fall-through both lead to the generating prompt | ADV-03, RET-09, SYS-001 | `integrity_breach_count` (general_generated on teaching intents) | T1-05 |
| FM-5 | A good question → "I don't have a verified verbatim teaching…" | Gates, dedup order, dense-only retrieval, content gate | RET-01, RET-02, DATA-14 | Served share and usefulness on the held-out set | T4-01, T4-02, T3-05 |
| FM-6 | A complex question → one partial clip | One-clip contract | ANS-004, RET-03 | Usefulness ≥4/5 share on multi-facet items | T5-01 … T5-04 |
| FM-7 | Answer arrives after 8–14 s | 3 sequential LLM gates; sync pipeline | SYS-006, SYS-003, RET-10 | TTFT and p95 by lane | T4-06, T7-02 |
| FM-8 | Deployed backend serves nothing | Rights register missing in image | DATA-02 | Startup check plus an `/api/health` field | T3-01 |
| FM-9 | A wrong clip, with no way to report it | No seeker report control | PRD-006 | Report rate per 1,000 answers | T6-04 |
| FM-10 | A Safari or Firefox user hits UI failures | E2E device matrix red | `01` §10 | Required cross-browser smoke | T9-02 |
| FM-11 | A quote on a practice or course page cannot be traced | Unsourced attribution | GURU-012 | Lint: no teacher attribution without span id | T1-03 |
| FM-12 | Someone scripts the open FP endpoint → LLM spend | No auth, no quota, cap off | SEC-001, SYS-004 | Spend per hour; per-IP rate | T1-07, T1-08 |
| FM-13 | A user asks for deletion while the backend is down → cannot delete | Edge function fails closed on backend purge | SEC-004 | Durable erasure job age | T6-06 |

## 6. Classification summary

| Class | Examples | Count (approx.) |
|---|---|---|
| Confirmed defects | X-01, ANS-001, RET-02, DATA-03, SYS-004, SEC-001 | ~80 |
| Probable defects | SYS-001, ANS-003, MEM-003, PRD-001 | ~12 |
| Architectural risks | SYS-003, DATA-01, RET-05, CQ-003 | ~25 |
| Product gaps | ANS-004, RET-03, SYS-011, PRD-006 | ~16 |
| Unverified assumptions | GURU-005, IP-003, IP-007, SAFE-005 | ~4 |

Counts are approximate because some records carry two types. The authoritative type per finding is in `findings-index.md`.

## 7. Failure register (full form)

Each row traces one failure from its trigger to the **earliest** faulty decision. "Detection gap" says why nobody sees the failure today. Verification label per `CONVENTIONS.md`.

| ID | Trigger | Expected | Actual or risk | Earliest failure point | Root cause | Downstream effects | Sev | Evidence | Conf | Detection gap | Correction | Regression test | Acceptance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-01 Personal question → generic advice | "What is the cause of my anxiety?" | Teaching clip(s) + plain explanation + optional practice + gentle care line | Code defaults: meditation template + helplines, no teaching | `serene_mind_engine.py:368` MODERATE regex matches a topic word | RC-5 | Bridge declines (`first_person_bridge.py:682`); later turns escalate (F-15) | P1 | ANS-001 [V-STATIC], confirmed in `26` | High | No benign-set metric; no outcome event | T4-04 | Golden G01; benign set ≥200 | NFR-SAFE-02 ≤5% |
| F-02 Incorrect teaching retrieval | Multi-facet or keyword-specific question | Best clip per facet | Top-1 0.43 [DOC-CLAIM]; one clip; dense-only on v10 | Retrieval order (dedup before gates), no sparse leg on v10, no per-facet retrieval | RC-4, RC-6 | Relevance gate abstains; seeker sees a weak clip | P1 (aggregate) | RET-01, RET-02, RET-04 | Medium | No Recall@k on the serving collection | T4-01, T4-02, T5-02 | Frozen bank (T2-02) | NFR-AIQ-06 non-negative delta |
| F-03 Missing source material | On-topic question with no clean clip | Honest abstain + nearest teaching offer | ~70% abstain [DOC-CLAIM]; content gate removes most candidates (>120 s cap, orphan opener) [DOC-CLAIM task list §0] | Segmentation at ingestion | RC-4 | Low served share; low usefulness | P1 | DATA-14; task list §0 | Medium | No abstain-reason dashboard | T3-05, T3-09, T2-03 | Abstain-reason distribution on the frozen bank | Strict-clean ≥60%; served share ≥30% |
| F-04 Fabricated quotation | Course, practice or tip pages; dormant editorial path; client translation | Only stored spans with locators | Titled-but-unlocated attributions (GURU-012); unlabelled MT of quotes (ADV-05); latent editorial rewrite (AI-006) | Content written without span ids | RC-3 | Teacher trust; review failure | P1 | GURU-012, ADV-05, AI-006 | High | No attribution lint | T1-03, T1-02, T5-06 | Attribution lint; voice lint | NFR-CI-03 = 0 |
| F-05 Incorrect attribution | Clip with host voice or unverified speaker | Speaker label only with a verification method | Host voice 6.9% of top-1 [DOC-CLAIM]; 17 spans re-marked verified by another writer [DOC-CLAIM] | Builders and uncontrolled writers | RC-4 | Wrong teacher shown | P1 | DATA-06; `06` | Medium | No daily audit | T3-02, T3-05 | Daily audit: verified-without-method = 0 | NFR-DI-04 |
| F-06 Conflicting teaching sources | Both teachers address a topic in different contexts | Show each, labelled, never merged | Harness abstains on cross-teacher mixing; legacy shows one clip (+1 other video separately); no attribution rule | No joint-attribution policy | RC-6 | Missed synthesis; risk of merged voice once a composer exists | P2 | GURU-014, RET-03 | Medium | No cross-teacher stratum | T8-01, T5-02 | Golden cross-teacher stratum | 0 merged attributions |
| F-07 Lost follow-up context | "Can you say more about that?" | Resolves to the previous answer's spans | String concatenation of history | `first_person_bridge.py:752-768` | RC-6 | Off-target follow-ups | P2 | ANS-007 | High | No multi-turn eval | T5-05 | Golden multi-turn items | Follow-up resolves by span id |
| F-08 Incorrect personalisation | Signed-in user with emotional history | Only consented, user-stated preferences | Healing-course assignment from emotional arcs without the consent gate; LLM-written persona | `orchestrator_utils.py:575-610` skips `:893-919` | RC-1 | Privacy breach; intrusive suggestions | P1 | MEM-003 (confirmed), MEM-004 | High | No consent-matrix test | T1-10, T6-03 | Consent matrix tests | NFR-PRIV-03 = 0 |
| F-09 Duplicate conversation data | Client sync plus backend write | One writer of assistant turns | Client writes conversations and guru turns; backend loads them as history | RLS lets clients insert any role | RC-1 | Forged or duplicated history in prompts | P2 | PRD-003 | High | No RLS role test | T6-05 | RLS test: client cannot insert `role!='user'` | Test passes |
| F-10 Missing user memory | Returning consented user | Continuity: no repeated clips; offers to continue | Memory is read and ignored on the teaching lane | `orchestrator_utils.py:557-566` read; no consumer | RC-1 | Wasted reads; generic repeat answers | P2 | MEM-002 | High | No repeat-clip metric | T6-02 | Repeat-clip rate test | Repeat rate falls; no unused read |
| F-11 Incorrect routing | Question mixing a general-task word and an emotion word | Teaching lane or static boundary | General lane | `off_topic_stage.py:625-669` | RC-1, RC-3 | Ungrounded advice | P2 | ANS-003 (narrowed), AI-001 | High | No routing set | T4-03 | Routing set | Recall ≥95% |
| F-12 Silent fallback | Bridge flag off; narrow node faults | Static abstain | Generating "warm Guru" prompt answers teaching questions | `first_person_bridge.py:573-583`; `pipeline_registry.py:65-76` | RC-3 | Teaching prose without verbatim grounding | P1 | ADV-03, RET-09, SYS-001 | High | No integrity-breach metric | T1-05, T2-03 | Fault injection + kill-switch test | Integrity breaches = 0 |
| F-13 Streaming interruption | SSE drop, proxy timeout, mobile network change | Clear state; retry without duplicate message | The backend sends `final` before `done`, so a cut stream keeps teacher text with no citation, "Related" label or safety notices, and saves it to history; no client stream timeout; only the 503 card shows a support line | `orchestrator.py:447-468` event order; `streaming.ts:320-368` | RC-3, RC-9 | Unlabelled teacher text in history; no helpline during faults | P2 (UX-005); P1 (UX-007) | `14d` [V-STATIC] | High | No network-drop e2e | T1-18, T1-17 | e2e: cut after `final`; 500, timeout and drop cards | No unlabelled teacher text persists; support line on every error |
| F-14 Slow response | Uncached in-domain question | p95 ≤10 s now, ≤6 s later | p95 12–14 s local [DOC-CLAIM] | 3 sequential LLM gates + sync thread hop | RC-9, RC-1 | Abandonment; thread starvation under load | P1 | SYS-006, SYS-003, RET-10 | Medium | No staging latency data | T4-06, T7-02 | Staging load c20 | NFR-PERF-02 |
| F-15 Incorrect safety behaviour | Three topic questions with emotion words | Teaching each time | SEVERE helpline pre-emption; unverified helplines shown | `serene_mind_engine.py:1810-1826` history escalation | RC-5 | Seeker feels pathologised; trust loss | P1 | SAFE-002, SAFE-004 | High | No multi-turn benign set | T4-04, T4-07 | Multi-turn set ≥50 | NFR-SAFE-03 = 0 |
| F-16 Session corruption | Client-supplied summary or history | Server truth only | Client summary enters the prompt unfenced; client-written history used | `generation.py:1994-1998`; `chat.py:479-500` | RC-1, RC-3 | Prompt injection into one's own session | P2 | MEM-005, PRD-003 | Medium | No injection fixtures | T6-03, T6-05 | Injection fixtures | Fenced; ignored |
| F-17 Cross-user leakage | Shared caches across users | No personalised answer served to another user | No cross-user path found; guards and tests exist (`test_cache_personalization_leak.py`, `test_cache_tenant_isolation.py`); semantic cache on the general path is a residual risk | Cache-key design | RC-1 | Privacy breach if a guard regresses | P2 (risk) | `14`, `03` | Medium | Tests exist | T7-04 | Existing isolation tests + new | 0 leaks |
| F-18 Inconsistent ingestion | Re-ingest a corrected video | Old points replaced; one lineage | Add-only builder; two transcript lineages; three hash meanings; uncontrolled writers | `backend/scripts/ops/build_full_corpus_v10.py:867-894` | RC-4 | Stale or duplicate clips served | P1 | DATA-05, DATA-09, DATA-03, DATA-06 | High | No daily audit | T3-02, T3-03, T3-04 | Rebuild fixture | No stale points |
| F-19 Qdrant failure | Qdrant down, slow, or keep-alive drop | Exact cache or honest abstain ≤5 s | One retry on a dropped keep-alive [DOC-CLAIM]; fails closed; no API key | Client config | RC-9 | Abstains during outage (correct); writes uncontrolled | P2 | `08`, SEC-006 | Medium [LIVE-Q] | No chaos test | T1-14, T3-02, runbook `22` | Fault injection | NFR-REL-04 |
| F-20 Database failure | Redis or Supabase down | Degrade safely; cost controls stay closed | Quota and rate limits go in-process; per-user cost cap fails open [DOC-CLAIM]; deletion impossible while the backend is down; backups failing | Fallback design | RC-9 | Spend risk; DPDP risk; data loss risk | P1 | SYS-004, SYS-012, ADV-01 | Medium | No chaos test; backup job red | T1-07, T3-10, T6-06 | Chaos tests; restore drill | NFR-REL-03, NFR-DR-01 |
| F-21 Railway deployment | First deploy | Serves clips; caps on; all services up | Rights register missing → every clip abstains silently; IaC declares one service; caps unset; `.railwayignore` hides `*.ts`; frontend points at a dead URL [DOC-CLAIM] | Image build and IaC | RC-9 | Silent total abstention; unbounded spend | P1 | DATA-02, SYS-007, SYS-004 | High (static) [LIVE-R] | No staging | T3-01, T9-01, T1-07 | Staging smoke (`22b`) | `22b` runbook passes |

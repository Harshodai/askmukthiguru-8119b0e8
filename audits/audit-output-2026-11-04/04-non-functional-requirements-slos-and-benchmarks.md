# 04 — Non-functional requirements, SLOs and benchmarks

> **2026-11-06:** Superseded in part by `specifications/COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` (82 NFRs with test, gate and status; stale baselines corrected in its §2 C-2 to C-10). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: lead. Pillars: P6, P1, P2, P4. Inputs: `15` (baselines), `18` (evaluation and benchmark research), `14`, `14b`, `06`. Functional requirements: `03` §4.

## 1. Rules used to set targets

1. A target is binding only when a baseline exists on the same environment. Otherwise it is **provisional** and is set from two weeks of staging data (T9-01, T9-02).
2. No production number exists. Railway has not run since August [DOC-CLAIM task list §1]. Every baseline below is local or static.
3. Quality and safety targets come from the evaluation design in `18`. They need human-labelled sets, which do not yet exist (EVAL-002).
4. Never trade spiritual accuracy or safety for latency or cost.

Columns: ID · Metric · Measurement · Baseline (label) · Target · Rationale · Test · Acceptance.

## 2. Reliability

| ID | Metric | Measurement | Baseline | Target | Rationale | Test |
|---|---|---|---|---|---|---|
| NFR-REL-01 | Share of chat requests reaching a terminal state (answer, abstain, crisis) within 20 s | outcome event latency | None. `pipeline_timeout` 105 s + 5 s wait [V-STATIC `15`] | ≥99.5% (provisional) | A seeker must never wait without an answer | staging load c20 |
| NFR-REL-02 | `/api/chat` non-5xx availability, monthly | edge + app metrics | None | Beta: 99.5% (error budget 3.6 h/month), provisional | Small-team on-call | synthetic probe every minute |
| NFR-REL-03 | Cost controls never fail open | chaos test: Redis down | Per-user cost cap fails open when Redis is down [DOC-CLAIM task list §0] | 0 fail-open paths | Cost safety | chaos test in CI |
| NFR-REL-04 | Qdrant degraded → exact cache or honest abstain | fault injection | Policy exists [DOC-CLAIM root `CLAUDE.md`] | 100% honest abstain within 5 s | Invariant: never fabricate | fault test |
| NFR-REL-05 | Teaching-route faults never produce generated text | fault injection | Violations possible (SYS-001) | 0 | Integrity | T1-05 tests |

## 3. Performance

| ID | Metric | Baseline | Target | Note |
|---|---|---|---|---|
| NFR-PERF-01 | Crisis response p99 (no LLM) | Regex path ~ms [DOC-CLAIM] | ≤2 s | Safety first |
| NFR-PERF-02 | Teaching lane uncached p95 | Local p50 6.8–7.6 s, p95 12.3–13.9 s [DOC-CLAIM `15`]; pass bar p95 10 s [V-STATIC `18`] | ≤10 s on staging (provisional); ≤6 s after T4-06 and T7-02 | 3 sequential LLM gates dominate |
| NFR-PERF-03 | Time to first visible content (status event, clip card or abstain) | Unmeasured | p50 ≤3 s (provisional) | Use SSE status events; the clip card can arrive before the explanation layer |
| NFR-PERF-04 | Exact-cache hit p95 | Unmeasured | ≤500 ms | |
| NFR-PERF-05 | Retrieval stage p95 (encode + Qdrant) | Whole pre-LLM pipeline p95 210 ms local, 2026-09-25 [DOC-CLAIM anchor doc] | ≤300 ms on staging | Do not quote the 19 ms POC figure |

## 4. Scalability

| ID | Metric | Baseline | Target |
|---|---|---|---|
| NFR-SCAL-01 | Real-model concurrency at error rate <1% within NFR-PERF-02 | Mock LLM c20 p95 <8 s; real models only c5 [DOC-CLAIM `15`] | c20 on staging (provisional); revisit with traffic data |
| NFR-SCAL-02 | Retrieval p95 at 10× spans (~30–40k points) | Unmeasured | Within NFR-PERF-05 on a synthetic replica |
| NFR-SCAL-03 | Prompt tokens per turn at conversation turn 50 | Unmeasured; follow-up is string concatenation (ANS-007) | Bounded by a per-lane budget (≤ the turn-1 budget + 20%) |
| NFR-SCAL-04 | Admission control is consistent | `max_concurrent_chat` = 12 (code), 8 (compose), 20 (CAPACITY.md) [V-STATIC `15`] | One configured value per environment, tested |

## 5. Security

| ID | Metric | Baseline | Target |
|---|---|---|---|
| NFR-SEC-01 | Endpoints that spend LLM budget without auth or quota | 1 (`/api/first-person/query`, SEC-001) | 0 |
| NFR-SEC-02 | Admin routes with AAL2 + admin role | 91/91 [V-STATIC `14`] | 100%, CI-checked |
| NFR-SEC-03 | Real secrets in tracked files | 0 found; tracked env files hold public client values [V-STATIC `14`] | 0 (gitleaks in CI) |
| NFR-SEC-04 | Datastores reachable beyond localhost or private network; Qdrant without API key | Exposed on 0.0.0.0; no key (SEC-006) | 0 |
| NFR-SEC-05 | High or critical dependency CVEs unpatched > 30 days | Unmeasured | 0 |
| NFR-SEC-06 | Prompt-injection fixtures that change routing or verification | Unmeasured | 0 on the injection fixture set (`18`) |

## 6. Privacy

| ID | Metric | Baseline | Target |
|---|---|---|---|
| NFR-PRIV-01 | Seeker text in logs and traces | ≥3 sites (SEC-003); OTel redaction exists [DOC-CLAIM PR #86] | 0 (guard) |
| NFR-PRIV-02 | Erasure completeness and time | Gaps (`router_decisions`, admin FKs); impossible while the backend is down (SEC-004) | All stores ≤72 h, automated and queued; DPDP obligations confirmed by counsel |
| NFR-PRIV-03 | Memory reads and side effects without active consent | ≥1 path (MEM-003) | 0 |
| NFR-PRIV-04 | Inferred sensitive profiles stored | LLM persona generator exists (MEM-004) | 0; user-stated preferences only |

## 7. Maintainability

| ID | Metric | Baseline [V-STATIC `13`] | Target |
|---|---|---|---|
| NFR-MAINT-01 | Runtime functions over 300 lines | `execute` 2,145; `generate_answer` 1,247; `retrieve_documents` 1,168 | Ratchet down; 0 in the teaching lane after T7-01 |
| NFR-MAINT-02 | Silent exception swallows | 70 | Ratchet to 0 |
| NFR-MAINT-03 | Settings unread / read but undeclared | 27 / 23 | 0 / 0 |
| NFR-MAINT-04 | Definitions of the teaching scope | 3 (AI-001) | 1 |
| NFR-MAINT-05 | Teacher-name literals in runtime code | 621 in 128 files (GURU-010) | Ratchet down; 0 new |
| NFR-MAINT-06 | Agent-instruction size | `CLAUDE.md` 48.5 KB; status list 408 KB | ≤15 KB; ≤30 KB |

## 8. Observability

| ID | Metric | Baseline | Target |
|---|---|---|---|
| NFR-OBS-01 | Turns emitting an `answer_outcome` event | 0 (SYS-011) | 100% |
| NFR-OBS-02 | LLM calls logging `prompt_id@version`, model, tokens, cost | `prompt_version_id` column has no writer (AI-004) | 100% |
| NFR-OBS-03 | Alerts that fire in a drill: integrity breach, crisis-lane error, spend 80%, p95 breach, data-audit fail | 14 rules exist; Alertmanager not deployed [V-STATIC `15`] | 5/5 fire in a drill |

## 9. Cost efficiency

| ID | Metric | Baseline | Target |
|---|---|---|---|
| NFR-COST-01 | Spend cap enforced, fail-closed | Off by default (SYS-004) | On in every non-dev environment |
| NFR-COST-02 | LLM calls per teaching turn | 3 by default, up to 4 [V-STATIC `05`, `08`] | ≤2 short, ≤3 deep |
| NFR-COST-03 | Cost per useful answer (formula in `15`) | ~9–11× cost per request, small n [DOC-CLAIM/INF `15`] | Reported weekly; non-increasing trend while usefulness rises |
| NFR-COST-04 | Untracked model prices | Relevance-scorer price unknown [V-STATIC `15`] | 0 models without a dated price entry |

## 10. Accessibility

| ID | Metric | Baseline | Target |
|---|---|---|---|
| NFR-A11Y-01 | axe serious/critical violations on chat, citation, profile, practices | a11y smoke specs exist; score unknown [V-STATIC `03`] | 0; WCAG 2.2 AA |
| NFR-A11Y-02 | Clip playback has visible text of the spoken words | Verbatim text shown with the clip [V-STATIC `03`] | 100% |
| NFR-A11Y-03 | Screen-reader task success in the user study | None | ≥1 screen-reader session per study round |

## 11. Internationalisation

| ID | Metric | Baseline | Target |
|---|---|---|---|
| NFR-I18N-01 | UI locale completeness | 14 locales; CI check exists [V-GIT `01`] | Keep green; native review signed per priority language |
| NFR-I18N-02 | Crisis recall per priority language | Regex not native-reviewed (SAFE-001) | 100% on the native + clinician core set |
| NFR-I18N-03 | Teacher quotes machine-translated and shown as teacher voice | 0 (invariant 16) | 0; assistant translations labelled |
| NFR-I18N-04 | Spans with a language field | 0 (`11`) | 100% in vNext |

## 12. Data integrity

| ID | Metric | Baseline | Target |
|---|---|---|---|
| NFR-DI-01 | Hash-mismatched spans served | 0; `source_text_hash` matched 2,885/2,885 v11 children [DOC-CLAIM `06`] | 0 |
| NFR-DI-02 | Point-ID recomputation mismatches | Unmeasured [LIVE-Q] | 0 (runbook `22`) |
| NFR-DI-03 | Points with registry teacher ids | Mixed vocabularies (DATA-13) | 100% |
| NFR-DI-04 | `speaker_verified=true` without a method | 732 before backfill; re-set incident on v11 [DOC-CLAIM `06`] | 0 |
| NFR-DI-05 | Promotion: BLOCKER fails / strict-clean rate | v10 13/26 checks; strict clean 39.9% [DOC-CLAIM `06`] | 0 / ≥60% |
| NFR-DI-06 | Drift detection time | None | ≤24 h |

## 13. AI quality

| ID | Metric | Baseline | Target |
|---|---|---|---|
| NFR-AIQ-01 | Served share on answerable held-out items | 24–31% [DOC-CLAIM root `CLAUDE.md` inv. 24]; pass bar 0.30 | ≥30% floor now; with layered answers: usefulness ≥4/5 on ≥70% of answerable items |
| NFR-AIQ-02 | Out-of-corpus leaks | 0/13 [DOC-CLAIM] | 0 on ≥60 null items |
| NFR-AIQ-03 | Teaching-intent routing recall | Unmeasured; regex misses (ANS-003) | ≥95% |
| NFR-AIQ-04 | Unsupported assistant-explanation sentences (L3) | Not applicable today | 0 on held-out |
| NFR-AIQ-05 | Direct-answer label error | No profile (n=14) | ≤1% at δ=0.05 (≥299 items, 0 errors; invariant 3) |
| NFR-AIQ-06 | Retrieval Recall@10 / nDCG@10 on the frozen bank | Unmeasured (RET-08) | Baseline set by T2-02; non-negative delta per change with CI |
| NFR-AIQ-07 | Human rater agreement | None independent | κ or α ≥0.6 before scores are trusted |
| NFR-AIQ-08 | Teacher-voice violations in assistant text | Possible in general mode (AI-003) | 0 (voice lint) |

## 14. Safety

| ID | Metric | Baseline | Target |
|---|---|---|---|
| NFR-SAFE-01 | Crisis recall, clinician core set, per priority language | Unmeasured; regex unreviewed | 100% |
| NFR-SAFE-02 | Benign on-topic questions routed to distress | 17/150 (11.3%) [DOC-CLAIM task list §0] | ≤5% on ≥200 reviewed items (clinician confirms) |
| NFR-SAFE-03 | Benign multi-turn escalation to SEVERE | Static path exists (SAFE-002) | 0 on ≥50 dialogues |
| NFR-SAFE-04 | Displayed helplines call-verified within the age limit | 1/15 [V-STATIC] | 100% of displayed entries |
| NFR-SAFE-05 | Engagement prompts after a safety-route answer | Possible (PRD-004) | 0 |

## 15. Disaster recovery

| ID | Metric | Baseline | Target |
|---|---|---|---|
| NFR-DR-01 | RPO for Postgres, Qdrant, audio archive | Unbounded; backup workflow failing [V-GIT `01`] | ≤24 h; audio in 2 off-host copies |
| NFR-DR-02 | RTO for beta | Unmeasured | ≤4 h, measured in a restore drill (provisional) |
| NFR-DR-03 | Serving-collection rollback time | Contract switch + recreate [DOC-CLAIM inv. 23] | ≤15 min, drilled |

## 16. Content integrity

| ID | Metric | Baseline | Target |
|---|---|---|---|
| NFR-CI-01 | Served spans without a filed `permission_ref` | Rights rest on owner statements (IP-003) | 0 |
| NFR-CI-02 | Takedown completion across stores | No takedown exists (DATA-07) | ≤24 h, with a report |
| NFR-CI-03 | Unsourced teacher attributions in any surface | ≥3 sites (GURU-012) | 0 (lint) |
| NFR-CI-04 | Teaching text or teacher audio in a public repository without written permission | Present (IP-001, IP-002) | 0 |

## 17. SLOs and error budgets

Only two SLOs are proposed now. Others wait for staging data (rule 1).

| SLO | Objective | Error budget | Burn alert |
|---|---|---|---|
| Crisis lane responds correctly | 99.9% of crisis-classified turns get the verified-helpline response within 2 s | 43 min/month | 2% of budget in 1 h |
| Teaching integrity | 100% of teaching-lane answers pass the integrity gate (no generated teacher text, no hash mismatch) | 0. Any breach pages the owner and trips the kill switch | Immediate |

After two weeks on staging, add availability (NFR-REL-02) and latency (NFR-PERF-02) SLOs from measured percentiles.

## 18. Benchmarks: how to use them

Detail and sources: `18` §3. Public benchmarks do not measure spiritual answer quality. **The primary benchmark is the Ask Mukti Guru golden set (`18` §4–§6).** Public suites are used as method templates and for component sanity checks. No result below has been measured.

| Benchmark or method | Use here | Weakness it detects | Limitation | NFR |
|---|---|---|---|---|
| RAGAS (faithfulness, context precision/recall) | Metric definitions for L3 explanations and retrieval | Unsupported claims; retrieval misses | LLM-judge bias; needs calibration | AIQ-04, AIQ-06 |
| ARES (prediction-powered inference) | Calibrate the LLM judge with a small human set | Judge drift and bias | Needs a human-labelled slice | AIQ-07 |
| RGB (noise robustness, negative rejection) | Design of the null and noisy item strata | Answering when evidence is absent | General-domain English | AIQ-02 |
| CRAG | Item-type taxonomy (simple, comparison, multi-hop, false-premise) | Weak multi-hop handling | Web and finance domains | AIQ-01 |
| FRAMES, MultiHop-RAG | Templates for multi-video synthesis items | Facet coverage gaps | Different corpora | AIQ-01 (multi-video stratum) |
| ALCE | Citation precision and recall definitions | Citations that do not support claims | English QA | AIQ-04, CI-03 |
| MIRACL, IndicGenBench | Multilingual retrieval and Indic generation sanity checks | Language gaps | Not spiritual content | I18N-02, I18N-04 |
| RULER | Only if long-context synthesis is adopted | Context degradation | The target keeps contexts short | SCAL-03 |
| Learn-then-Test (Clopper–Pearson) | Calibrate "direct answer" at 1% risk, δ=0.05 | Over-confident labels | Needs ≥299 confident items | AIQ-05 |

Fair comparison against ChatGPT and Claude: `18` §7. Use the same questions, blind raters, the same rubric, and a source-faithfulness check against the corpus. Report the gaps. Never claim parity from architecture alone.

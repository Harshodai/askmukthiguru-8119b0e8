# Final audit document inventory (2026-11-06)

Head `fb5cab0f` on `feature/audit-strengthen-rag-qdrant`. The audit target is `origin/main@46b808fb` (`CONVENTIONS.md` §1). Evidence labels: `CONVENTIONS.md` §3. This file answers Part 3 of the final-verification brief: for each document, does it exist, is it complete, is the evidence present, are the links valid, does it conflict, what is missing, can an agent implement from it, and does it need updating. It does not repeat the analysis in the FINAL files or the specifications. It cites them.

## 0. Header and method

| Item | Value |
|---|---|
| Date | 2026-11-06 |
| Head | `fb5cab0f` (96 commits after `46b808fb`, which is an ancestor of the head) |
| Scope | 35 numbered documents (00 to 27 with 02b, 12b, 14b, 14c, 14d, 22a, 22b), 7 named files (CONVENTIONS, README, findings-index, traceability-matrix, decision-log, unresolved-questions, IMPLEMENTATION-AGENT-PROMPT), 11 `FINAL_*.md` files (the index plus the 10 it lists) and 15 files in `specifications/`. |
| Mechanical pass | Script `doc_linkcheck.py` read the 42 original files (not the FINAL files or specifications). It reported 2,001 citations OK, 627 missing, 63 ambiguous, 9 past end of file, 0 broken markdown links, 0 broken document-number references, 17 erratum lines. |
| Re-resolution | The 627 + 63 + 9 tokens were re-resolved twice: against the tree at `46b808fb` (the tree the citations were written for) and against the tree at `HEAD`. Prefixes tried: none, `backend/`, `src/`, `supabase/`, `supabase/functions/`, `scripts/`, `docs/`, `infrastructure/`, `evals/`, `.github/workflows/` and common sub-folders. Dropped: routes (`/api/…`, `/chat`), branch names, model names, container images, env values, directories that are proposals or absence claims, and the 24 'required names' in `README.md` §Name mapping (virtual names by design). A bare file name that matches one file is counted as resolved shorthand. A bare name that matches several files is counted as ambiguous. Line citations were checked against the file length at both trees. |
| Results | Across all passes, 22 tokens are truly broken (§2.1: 19 from the 627 missing, 2 from the past-EOF and directory cases, 1 from the FINAL-file pass). 11 more were valid at `46b808fb` and stale at `HEAD`. 62 are ambiguous bare names. 47 text occurrences use the old `audit-output/` folder name. All other tokens resolve. |
| FINAL files and specifications | A second script read every backticked path in them and resolved it at `HEAD` and at `c9b42d3e`. Unresolved tokens are proposed new files and tests, absence claims, deprecated `railway.json`/`railway.toml` mentions, and chart-relative names. One is truly broken (§2). |
| Other inputs reused, not repeated | `FINAL_AUDIT_GAP_ANALYSIS.md` §1, §2; `26` §4, §7.1; `FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` §6; `FINAL_READINESS_AND_GAP_ANALYSIS.md` §7; `FINAL_SPECIFICATION_COMPLETENESS_MATRIX.md` §2–§4; §1 of each specification. |
| Not done | No code was run. No live system was used. Whether each claim in a document is true was not re-verified; only the existence of cited files and lines. |

## 1. Inventory

### 1.1 Key

- **Complete for its purpose** uses the purpose stated in `README.md` (numbered documents) or in the file's own header. Yes / Partial / No, with the reason.
- **Evidence** is `labels; R/T cites`. Labels are `[V-STATIC]`, `[V-GIT]`, `[V-WEB]`, `[DOC-CLAIM]`, `[INF]`, `[LIVE-*]`, `[HUMAN]` counted in the file. T is the number of citation tokens the script found (some are not files). R is T minus the truly broken tokens (§2). Documents with 0 labels (`20`, `21`, `24`, `25`, `27`, `22a`, `traceability-matrix.md`, `decision-log.md`, the prompt) are task or procedure files and do not label claims.
- **Links** is the count of truly broken citations. `stale` = valid at `46b808fb`, not at `HEAD`. `amb` = bare file name that matches more than one file.
- **Conflict IDs** point to a place where the conflict is recorded: `26-C1`…`26-C8` = `26` §4; `GAP-1.1`…`GAP-1.6` = `FINAL_AUDIT_GAP_ANALYSIS.md` §1 rows in order; `FRN-C1`…`FRN-C13` = `COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` §2; `RW-C1`…`RW-C11` = `RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` §2; `LD-D1`…`LD-D19` = `FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` §6; `SM-1`…`SM-4` = `FINAL_SPECIFICATION_COMPLETENESS_MATRIX.md` §4 rows in order. 'none found' means none was found in the places above or in the headings read; it is not a full cross-read.
- **Detailed enough to implement**: Yes / Partial / No, or N/A for a research, reference or log file.

### 1.2 Numbered documents and named files

| Document | Exists | Complete for its purpose | Evidence | Links valid (broken) | Conflicts with other docs | Important sections missing | Detailed enough to implement | Requires updating |
|---|---|---|---|---|---|---|---|---|
| `00-executive-overview-and-scorecard.md` | Yes | Yes: verdict, scorecard, top risks, week plan all present. | 13 labels; 4/4 cites | 0 | Stale against `FINAL_READINESS_AND_GAP_ANALYSIS.md` §1 (gates A/B/C all NO; 2 P0 open). No content contradiction found. | Link to the FINAL release gates; remediation status (33 findings closed per GAP-1.5). | N/A (overview) | Yes: §1, §4, §5 predate 96 commits and the FINAL gate decision. No spec supersedes it, so no pointer note. |
| `01-repository-git-history-and-pr-investigation.md` | Yes | Yes for `46b808fb`; no for the range after it. | 75 labels; 38/38 cites | 0 | none found | History of the 96 commits `46b808fb..fb5cab0f`; CI state after `c9b42d3e` (`FINAL_READINESS` §1 reports all workflows failed). | N/A (reference) | Yes: §8 CI state and §3 branch facts are dated 2026-11-04. |
| `02-spiritual-user-research-personas-jtbd.md` | Yes | Partial: personas and JTBD are hypotheses; no seeker was interviewed (`GAP` §5 Q2). | 10 labels; 13/13 cites | 0 | none found | Real user research; the §8 study is a proposal only. | N/A (research) | No (labelled hypotheses). The study in §8 is still open. |
| `02b-competitive-analysis-and-product-opportunities.md` | Yes | Yes: competitor table and opportunity register present. | 41 labels; 5/5 cites | 0 | none found | Re-dated web evidence (all `[V-WEB]` dated 2026-11-04). | N/A (research) | No |
| `03-product-journeys-functional-requirements.md` | Yes | Partial: 32 FRs, status only; no test, acceptance or gate per FR. | 25 labels; 163/163 cites | 0; 1 stale; 9 amb | 26-C6 (CancelFlow dormant; erratum at line 5); FRN-C11 (`feedback.py:336` vs `:369`); body text under the erratum is unchanged. | Test, acceptance and gate per FR; the 12 new FRs (`COMPLETE_FR_NFR…` §3). | Partial (use the matrix) | Yes: pointer inserted. traceability chain breaks BL-1 to BL-12 (`COMPLETE_FR_NFR…` §7). |
| `04-non-functional-requirements-slos-and-benchmarks.md` | Yes | Partial: 70 NFRs with baselines; several baselines stale. | 4 labels; 5/5 cites | 0 | FRN-C2 to FRN-C10 (OBS-01, COST-01, SEC-04, MAINT-01/03, §17 SLO, property tests, WCAG 2.2, chaos modes); 26-C4 (latency). | Test and gate per NFR; WCAG 2.2 AA; the 12 added NFRs. | Partial (use the matrix) | Yes: pointer inserted. Baselines C-2 to C-6 are stale. |
| `05-current-architecture-and-request-flow.md` | Yes | Yes for `46b808fb`, with a lead erratum at line 5. | 102 labels; 114/114 cites | 0; 2 amb | 26-C1 (v8 vs v10), 26-C2 (scorer timeout 12/15/25 s), 26-C3 (2 vs 3 LLM calls), 26-C4 (latency), 26-C5 (unknown-keyword route); LD-D1 (pipeline order in CLAUDE.md); GAP-1.2. | Post-T7-01 `execute` size. §4 correctly lists `KillSwitchStage` and `OffTopicStage`; the stale chain is in CLAUDE.md (LD-D1, FRN-C1). | N/A (reference) | Yes: pointer inserted; erratum overrides the body; `execute` split 2,146 to 266 lines after T7-01. |
| `06-data-ingestion-quality-lineage.md` | Yes | Yes for inventory and lineage; partial for contracts. | 96 labels; 152/152 cites | 0; 1 stale; 18 amb | `DATA_QUALITY…` §2 and `INGESTION…` §2.2 (DATA-20 to DATA-27 in landed code). | Per-store 15-field contract; stage contracts; source state machine; correction and takedown workflow (`INGESTION…` §1, `DATA_QUALITY…` §1). | Partial | Yes: pointer inserted; 1 line cite past EOF at HEAD (`ingest/pipeline.py`, now 4,174 lines). |
| `07-video-audio-multisource-synthesis.md` | Yes | Partial: §4 target design is a sketch. | 25 labels; 33/33 cites | 0; 3 amb | none found | Decision-free Variant A, wire contract carrying teacher/video/time, staged gates with numbers (`MULTI_VIDEO…` §1). | Partial | Yes: pointer inserted. |
| `08-qdrant-graph-retrieval.md` | Yes | Partial: engines and failure catalogue present; contracts absent. | 42 labels; 66/66 cites | 0; 1 amb | 26-C1 (default collection); `ANSWER_QUALITY…` line 59 (§5 claim 'no hash re-check on cache hit' is wrong). | Per-component contracts, statistical method for the bank, floors (`RETRIEVAL…` §1). | Partial | Yes: pointer inserted. |
| `09-ai-harness-agents-prompts-context.md` | Yes | Partial: call sites and prompt inventory present; erratum at line 5. | 27 labels; 151/151 cites | 0; 4 stale | 26-C3, 26-C5 (ANS-003 narrowed). Unfenced call sites remain (`AI_HARNESS…` §2.6). | Prompt registry format, loader, call-site contract, trace field, tests (`AI_HARNESS…` §1). | Partial | Yes: pointer inserted; 4 line cites into `quote_weaver.py` exceed its HEAD length (1,149 lines vs 1,640 at baseline). |
| `10-spiritual-answer-quality-expected-behavior.md` | Yes | Partial: behaviour specs and taxonomy present; lead erratum at line 5 of the original. | 28 labels; 77/78 cites | 1 | 26-C5; `ANSWER_QUALITY…` line 56 (quote glue claim vs bridge rebuild at `first_person_bridge.py:962`). | Field-level wire schema; render rules per voice layer; release invariants (`ANSWER_QUALITY…` §1). | Partial | Yes: pointer inserted; 1 cite to a scratchpad file. |
| `11-krishnaji-preethaji-future-guru-extensibility.md` | Yes | Partial: counts and registry sketch present. | 24 labels; 76/76 cites | 0 | `GURU…` §1: counts taken at `46b808fb`; 28 hard-coded places now tabled at `c9b42d3e`. | Field validation, ID rules, rights path, loader and failure behaviour (`GURU…` §1). | Partial | Yes: pointer inserted. |
| `12-personal-mentor-memory-ethical-retention.md` | Yes | Partial: inventory and flow present; target design is a sketch. | 13 labels; 63/63 cites | 0 | 26-C8 ('at least seven' stores vs ten). | Consent scopes, lifecycle, export, erasure registry, MEM-007 to MEM-012 (`PERSONAL_MENTOR…` §1). | Partial | Yes: pointer inserted. |
| `12b-ethical-retention-and-mentor-ux.md` | Yes | Partial: erratum at line 5 (cancel funnel is mounted). | 11 labels; 42/42 cites | 0; 1 amb | 26-C6; `03` shows the same dormant claim. | Journey and reminder contracts (`PERSONAL_MENTOR…` §1, D-PM6, D-PM9). | Partial | Yes: pointer inserted. |
| `13-code-quality-architectural-debt.md` | Yes | Yes: registers A, B, C and new components present. | 68 labels; 137/138 cites | 1; 3 stale; 3 amb | none found | Current sizes of god modules after T7-01; `langdetect` stub removal. | Partial (file-level specs are in `21`) | Yes: `langdetect/__init__.py` removed at HEAD (`42e883b3`, T1-13); `app/__init__.py:1-20` is 19 lines at baseline. |
| `14-security-safety-privacy-permissions.md` | Yes | Partial: findings and positive controls present. | 46 labels; 60/61 cites | 1; 2 amb | none found | Threat model, adversarial cases, untrusted-content fence (`PRODUCTION…` §1); ADV-01, ADV-02 only in an addendum. | Partial | Yes: pointer inserted; 1 cite names a directory with lines. |
| `14b-safety-crisis-and-spiritual-trust.md` | Yes | Partial: crisis pipeline as built; §4 target design is a summary. | 26 labels; 55/55 cites | 0 | none found | Operator side when the crisis route fails (`PRODUCTION…` §1); attribution tests on the wire (`ANSWER_QUALITY…` §1). Native-speaker and clinician review stay `[HUMAN]`. | Partial | Yes: pointer inserted. |
| `14c-content-permissions-and-ip-register.md` | Yes | Yes for facts and the register; approvals are human. | 35 labels; 58/58 cites | 0 | none found | How a rights change reaches serving, caches and derived stores (`GURU…` §1, `INGESTION…` §1). `docs/agent/gates/` is absent by design. | Partial | Yes: pointer inserted; IP-001 is still P0 (`FINAL_READINESS` §1). |
| `14d-user-journey-and-frontend-walkthrough.md` | Yes | Yes: 14 steps, error recovery, stream interruption. | 41 labels; 128/129 cites | 1; 1 stale; 2 amb | none found. FR labels such as SAVE-01 are not finding IDs. | What the personalisation controls must do (`PERSONAL_MENTOR…` §1 row `14d`); a11y manual pass (`FRN-C9`). | Partial | Yes: pointer inserted; test path `src/lib/chat/__tests__/errors.test.ts` differs from `src/test/chat/errors.test.ts`. |
| `15-reliability-performance-cost-observability.md` | Yes | Partial: mechanisms and cost model present. | 66 labels; 49/49 cites | 0; 1 amb | 26-C2, 26-C4; `PRODUCTION…` §2: alert rules read metrics nothing emits (OPS-003 to OPS-008). | SLO and alert contracts, answer trace, runbooks (`PRODUCTION…` §1). | Partial | Yes: pointer inserted. |
| `16-root-cause-and-failure-register.md` | Yes | Yes: nine root causes, severity reconciliation, failure register. | 16 labels; 24/24 cites | 0; 1 amb | 26-C7 (severity: GURU-002 P0 to P1; SYS-001; RET-09). | Mapping of DATA-20 to DATA-27, OPS-003 to OPS-008, MEM-007 to MEM-012 and MOB/K8S findings to RC-1…RC-9. | N/A (register) | Yes: new defects have no root-cause cluster. No spec supersedes it. |
| `17-target-architecture-and-decision-register.md` | Yes | Yes: principles, diagrams, 13 decisions, non-goals. | 1 labels; 5/5 cites | 0 | 26-C1 (§2b.2 corrected); ADR-013 accepted but not built (`GAP` §2 GURU row). | Link to `ARCHITECTURE_DECISION_RECORDS_HISTORICAL.md` (16 historical ADRs, 25 do-not-reintroduce items). | N/A (decision record) | Yes: ADR status (ADR-013, ADR-005) and the historical ADR link. No pointer: the historical file extends, it does not supersede. |
| `18-golden-eval-dataset-and-testing-spec.md` | Yes | Partial: asset audit and spec present; labels are human work. | 42 labels; 56/56 cites | 0 | `FRN` §7 BL-8, BL-9 (routing set 10 items, bank 8 items vs targets). | Adversarial set, model-change procedure (`AI_HARNESS…` §1); sample sizes (`ANSWER_QUALITY…` §1). | Partial | Yes: pointer inserted; 299 human labels still absent. |
| `19-build-redesign-consolidate-remove-avoid.md` | Yes | Yes: five decision lists and do-not-build register. | 11 labels; 19/19 cites | 0 | none found | Row status after T1-13 and T6-01. | N/A (decision list) | Yes (minor): some Remove rows landed. No spec supersedes it. |
| `20-ordered-engineering-roadmap.md` | Yes | Partial: 85 tasks; §8 status log runs to the thirteenth batch. | 0 labels; 264/272 cites | 8; 4 amb | `FINAL_READINESS` §7: 21 later commits not logged here; spec tasks (112 `NEW-*`) are not in this file. | The `NEW-*` tasks and 17 lettered sub-tasks (T3-06a/b, T5-07a/b, T7-01a to l, T8-02a/b) that the specs and the prompt use. | Partial (P0/P1 detail is in `21`) | Yes: 8 wrong file paths (§2); a single task list is needed. No pointer: the extensions are in several specs. |
| `21-file-level-implementation-specifications.md` | Yes | Partial: P0/P1 tasks only (40 sections). | 0 labels; 99/104 cites | 5; 1 amb | none found | Specs for P2 and later tasks and all `NEW-*` tasks (they sit in each spec §8). | Yes for P0/P1; No for the rest | Yes: 5 wrong file paths (§2). |
| `22-qdrant-graph-deferred-validation-runbook.md` | Yes | Yes: R-1 to R-18 read-only checks. | 2 labels; 13/13 cites | 0 | none found | Static fixture equivalents; SQL and Redis checks; rights-stamp check (`DATA_QUALITY…` §1). `FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` now holds the owner-run commands. | Partial | Yes: pointer inserted. All checks are `[LIVE-Q]` and unrun. |
| `22a-acceptance-criteria-and-testing-plan.md` | Yes | Partial: §7 lists its own weaknesses. | 0 labels; 12/12 cites | 0; 1 amb | FRN-C8 (property tests: no test imports `hypothesis`), FRN-C9 (WCAG 2.2). | Per-component method and executable data invariants (`COMPLETE_FR_NFR…` §6, §8); data tests (`DATA_QUALITY…` §7). | Partial | Yes: pointer inserted. |
| `22b-railway-deployment-readiness-runbook.md` | Yes | Partial: good gap list; 11 statements wrong or incomplete. | 20 labels; 34/34 cites | 0 | RW-C1 to RW-C11; GAP-1.1 (`railway.json` is deprecated); GAP-1.2 (D-14 not a contradiction); SM-4 row 4 (Gate A A1-A12 vs A1-A21). | Topology, IaC, drain, signals, networking, promotion, backup (`RAILWAY…` §2). | Partial (use the runbook) | Yes: pointer inserted. Do not follow R-1, S-1, R-4 as written. |
| `23-guru-review-and-release-readiness-package.md` | Yes | Partial: package structure present; gate verification dated 2026-11-04. | 37 labels; 48/48 cites | 0 | none found | Signed gate lines (`docs/agent/gates/` absent); sign-offs are `[HUMAN]`. | Partial | Yes: §1 gate check predates the remediation; no gate has a `Signed by:` line. |
| `24-coding-agent-master-handoff.md` | Yes | Partial: a handoff, one erratum. | 0 labels; 64/64 cites | 0; 3 amb | LD-D1 (CLAUDE.md pipeline order, if §2 repeats it; not checked). | Phases for mobile, Kubernetes and accessibility; the `FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` first instruction. | Partial | Yes: `FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` supersedes it (not in `specifications/`, so no pointer). |
| `25-phase-specific-coding-prompts.md` | Yes | Partial: prompts for T0 to T9 tasks; §1 revalidation is done. | 0 labels; 0/0 cites | 0 | none found | Prompts for `NEW-*` tasks. Whether the §1 revalidation ran as written is unknown. | Partial | Yes: §1 revalidation task is overtaken by `26` and the FINAL pass. |
| `26-independent-adversarial-review-and-residual-risks.md` | Yes | Yes: 16 claims checked, new findings, residual risks. | 55 labels; 118/118 cites | 0; 1 stale | Its own C-1…C-8 are the main conflict source; GAP-1 and `FRN-C13` refine C-1. | none for its purpose | N/A (review record) | No (record). Read with `FINAL_AUDIT_GAP_ANALYSIS.md` §1. |
| `27-execution-log-coverage-and-usage.md` | Yes | Yes: execution log of 2026-11-04. | 0 labels; 107/109 cites | 2; 5 amb | none found | Log of the 2026-11-05 and 2026-11-06 passes (see `FINAL_USAGE_AND_VERIFICATION_LOG.md`). | N/A (log) | No (dated record). Line 40 uses names that differ from the implemented files. |
| `CONVENTIONS.md` | Yes | Yes: rules, labels, finding format, ID owners. | 22 labels; 6/6 cites | 0 (legacy folder name) | Names the target and write path as `audit-output/` (moved by D-27). | Owners for `OPS-`, `MOB-`, `K8S-`, `ADV-`, `NEW-*`, `D-P*` (`K8S…` NEW-K8S-6 asks for this). | N/A (rules) | Yes: ID ownership table (§5) and the folder path in §2. |
| `README.md` | Yes | Partial: index and start-here table present. | 9 labels; 80/80 cites | 0 (24 virtual names by design; 1 legacy-folder note) | Says '12 files in `specifications/`'; 15 exist. | List of the spec files; `FINAL_*` files in the table; the 24 'required names' map to files that do not exist (by design). | N/A (index) | Yes: spec count and the FINAL block. |
| `findings-index.md` | Yes | Partial: 153 findings with reconciled severity. | 2 labels; 9/9 cites | 0; 1 amb | Counts table (P1 47, P2 81, P3 22) disagrees with its own section headings (45, 77, 19); the table says it is authoritative. | 75 proposed finding IDs from the specs (list in §3). | N/A (index) | Yes: add the proposed IDs (`FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` step 4). |
| `traceability-matrix.md` | Yes | Partial: 32 FRs from `03`. | 0 labels; 6/7 cites | 1 | `COMPLETE_FR_NFR…` has 44 FRs and 82 NFRs with gate IDs; this file has neither. | Gate IDs (A/B/C); the 12 added FRs; broken links BL-1 to BL-12. | N/A (matrix) | Yes: superseded in practice by `COMPLETE_FR_NFR…`; `teaching_scope.yaml` is not a file in the repository. |
| `decision-log.md` | Yes | Partial: method decisions, ADR status, owner decisions. | 0 labels; 12/12 cites | 0 | `D-P*` decisions exist only in `FINAL_DECISION_AND_RISK_REGISTER.md`. | D-P* decisions; the historical ADR file; D-29 (absent here and in `unresolved-questions.md`). | N/A (log) | Yes: owner decisions section is nearly empty (D-27, Q-T7-01-A to D). |
| `unresolved-questions.md` | Yes | Partial: D-01 to D-30, live unknowns, human gates. | 9 labels; 7/7 cites | 0 | `D-P*` IDs (PE, PG, PI, PM, PQ, DQ, K8S1) absent here; present in `FINAL_DECISION_AND_RISK_REGISTER.md`. | D-P* items; D-29; D-PMOB1 to D-PMOB8; D-PK8S1. | N/A (register) | Yes: not synced with the FINAL decision register. |
| `IMPLEMENTATION-AGENT-PROMPT.md` | Yes | Partial: 495 lines; §0 work log, guardrails, work order. | 0 labels; 207/208 cites | 1; 4 amb | GAP-1.5 (§0g '38 closed' vs 33); uses `audit-output/` paths; `src/lib/errors.ts`. | Phases for the 15 specs; the 75 proposed finding IDs. | Yes for the tasks it lists | Yes: another agent is editing it now; do not edit here. |

### 1.3 FINAL files

| Document | Exists | Complete for its purpose | Evidence | Links valid (broken) | Conflicts with other docs | Important sections missing | Detailed enough to implement | Requires updating |
|---|---|---|---|---|---|---|---|---|
| `FINAL_READINESS_AND_GAP_ANALYSIS.md` | Yes | Yes: release decision, file index, reading order, post-head commits (§7). | 1 labels; 52/52 cites | 0 | Says '12 files in `specifications/`'; 15 exist. Head `c9b42d3e`; current head `fb5cab0f`. | MOBILE, K8S and ACCESSIBILITY specs in §4. | N/A (index) | Yes: §4 spec list and head; §7 covers commits only to `a7be7e65`. |
| `FINAL_AUDIT_GAP_ANALYSIS.md` | Yes | Yes: corrections, new defects, pillar and A-J coverage, completeness challenge. | 9 labels; 32/32 cites; 3 of them proposed, absent or chart-relative by design (not broken) | 0 | GAP-1.1 to GAP-1.6 correct `22b`, the first draft, and `IMPLEMENTATION-AGENT-PROMPT.md` §0g. | Its §5 item 1 ('mobile, k8s not evaluated') is now answered by `MOBILE…` and `K8S…`. | N/A (review) | Yes: §5 item 1; §2 IDs still outside `findings-index.md`. |
| `FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` | Yes | Yes: first instruction, phases with task IDs, rules, §5 gaps. | 0 labels; 29/29 cites; 1 of them proposed, absent or chart-relative by design (not broken) | 0 | none found | Phases for mobile, Kubernetes and accessibility work. | Yes (ordered phases, task IDs) | Yes: head and the 21 later commits (`FINAL_READINESS` §7); new specs. |
| `FINAL_DECISION_AND_RISK_REGISTER.md` | Yes | Yes: open decisions by gate; 15 ranked risks. | 2 labels; 50/50 cites; 2 of them proposed, absent or chart-relative by design (not broken) | 0 | `D-P*` IDs are here and not in `unresolved-questions.md` or `decision-log.md`. | D-PMOB1 to D-PMOB8, D-PK8S1, accessibility decisions. | N/A (register) | Yes: add the decisions from the new specs and sync the two older registers. |
| `FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` | Yes | Yes: 1,468 lessons classified (script row match 99.8%); coverage limits stated. | 7 labels; 178/178 cites; 9 of them proposed, absent or chart-relative by design (not broken) | 0 | LD-D1 to LD-D19: 19 documentation issues; 11 stay 'Proposed' (files it may not edit). | none for its purpose | N/A (review) | Yes: §8 corrections to `CLAUDE.md`/`AGENTS.md` are not applied; owner action. |
| `FINAL_PENDING_WORK_REGISTER.md` | Yes | Yes: status of 152 findings with proof, next 15 tasks, decision and human lists. | 2 labels; 242/242 cites; 1 of them proposed, absent or chart-relative by design (not broken) | 0 | Another agent edits it (verification note for head `fb5cab0f`). 75 proposed IDs are not listed. | Rows for DATA-20 to DATA-27, MEM-007 to MEM-012, OPS-001 to OPS-009, ANS-009 to ANS-013, RET-12 to RET-17, MOB, K8S, A11Y. | Yes (next-15 list) | Yes: keep in step with commits; add proposed IDs. |
| `FINAL_PRODUCTION_RELEASE_READINESS.md` | Yes | Yes: Gate B (B1-B18) and Gate C (C1-C12). | 1 labels; 18/18 cites | 0 | none found | Mobile store gate, Kubernetes status, manual accessibility pass. | Yes (gate criteria) | Yes: add rows for mobile and accessibility once those specs are accepted. |
| `FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` | Yes | Yes: owner-run, read-only-first steps with commands and pass conditions. | 6 labels; 33/33 cites | 0 | none found | none | Yes | No (owner runs it; no result recorded: `[LIVE-Q]`). |
| `FINAL_RAILWAY_STAGING_READINESS.md` | Yes | Yes: A1-A21 with classification. | 5 labels; 77/77 cites; 2 of them proposed, absent or chart-relative by design (not broken) | 0 | SM-4 row 4 (A1-A12 draft vs A1-A21; mapping section added). | none | Yes | No |
| `FINAL_SPECIFICATION_COMPLETENESS_MATRIX.md` | Yes | Partial: rates 11 specs and the ADR file. | 0 labels; 25/25 cites | 0 | SM-1 to SM-4 (clip id on wire; scorer timeouts; PersonalizeStage; Gate A numbering). | Ratings for MOBILE, K8S, accessibility specs. | N/A (rating) | Yes: add three specs. |
| `FINAL_USAGE_AND_VERIFICATION_LOG.md` | Yes | Yes for the 2026-11-05 pass. | 0 labels; 36/37 cites; 2 of them proposed, absent or chart-relative by design (not broken) | 1 | none found | The 2026-11-06 pass (mobile, k8s, accessibility specs, this inventory). | N/A (log) | Yes: log the 2026-11-06 work; one cite names a scratchpad script. |

### 1.4 Specifications

| Document | Exists | Complete for its purpose | Evidence | Links valid (broken) | Conflicts with other docs | Important sections missing | Detailed enough to implement | Requires updating |
|---|---|---|---|---|---|---|---|---|
| `AI_HARNESS_PROMPT_AND_CONTEXT_SPEC.md` | Yes | Partial (`FINAL_SPEC…` 6.6): GraphState, fence helper, scorer model, prompt registry v1, injection screens ready; judge consolidation blocked (D-17, D-04, D-PG11). | 20 labels; 178/178 cites; 13 of them proposed, absent or chart-relative by design (not broken) | 0 | SM-2 (scorer timeouts, D-PG13). | none for its purpose | Yes (contracts, tests, ordered tasks) | Yes: commit `2318a368` (T7-03 one LLM gateway) may change §2 provider inventory (`FINAL_READINESS` §7); so may `49c92325` (T1-14 pins Memgraph). |
| `ARCHITECTURE_DECISION_RECORDS_HISTORICAL.md` | Yes | Yes: 16 historical ADRs, 25 do-not-reintroduce items, template. | 14 labels; 98/98 cites | 0 | none found | Inbound links from `17`, `decision-log.md`, `README.md`. | N/A (record) | No |
| `COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` | Yes | Yes as a matrix: 44 FRs, 82 NFRs with test, criterion, gate, status. | 29 labels; 347/347 cites; 1 of them proposed, absent or chart-relative by design (not broken) | 0 | FRN-C1 to FRN-C13 correct `03`, `04`, `22a`, CLAUDE.md. BL-1 to BL-12 are its own broken chains. | Rows for mobile and accessibility requirements. | Yes | Yes: WCAG 2.2 tag (BL-10) and new specs; status moves with commits. |
| `DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md` | Yes | Partial (6.4): static checks C-S1 to C-S8 ready; all live checks need the owner. | 7 labels; 107/107 cites; 3 of them proposed, absent or chart-relative by design (not broken) | 0 | none found | none for its purpose | Yes for static checks; No for live proof | Yes: commit `4eb04ae8` (T3-07 canonical teacher IDs) may change §3 (`FINAL_READINESS` §7). |
| `GURU_KNOWLEDGE_AND_KNOWLEDGE_GRAPH_SPEC.md` | Yes | Partial (6.5): registry v2 loader and schema ready; blocked by D-PG1, D-PG2, D-05. | 33 labels; 147/147 cites; 15 of them proposed, absent or chart-relative by design (not broken) | 0 | none found | none | Yes (28 places tabled, test per step) | Yes: commit `1503e5f2` (T8-01 registry extensibility and literal guard) makes §2.4 table and ADR-013 status stale. |
| `INGESTION_AND_CONTENT_PROCESSING_SPEC.md` | Yes | Partial (6.1): stage contracts and NEW-ING-1/2/6 ready; governance waits on D-08, D-PI1 to D-PI3. | 9 labels; 101/101 cites; 8 of them proposed, absent or chart-relative by design (not broken) | 0 | none found | none | Yes for stage contracts; No for governance | No (until DATA-20 to DATA-27 land). |
| `K8S_MANIFESTS_REVIEW.md` | Yes | Partial: draft static review; option A proposed (D-PK8S1); no cluster or Helm run. | 27 labels; 176/176 cites; 17 of them proposed, absent or chart-relative by design (not broken) | 0 | none found. It cites the Helm chart by chart-relative names. | `K8S-` prefix has no owner (NEW-K8S-6); findings K8S-01 to K8S-09 not in the index. | Yes (NEW-K8S-1 to 6) | Yes: file is untracked (new); needs the owner decision D-PK8S1 and ID registration. |
| `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md` | Yes | Partial: static review complete; 'NOT submission-ready'; store rules quoted from memory (`[INF]`), not fetched. | 85 labels; 151/151 cites; 8 of them proposed, absent or chart-relative by design (not broken) | 0 | none found | Live store-rule check; device test of MOB-01 (`[HUMAN]`). | Yes (MOB-01 to MOB-15, NEW-MOB-1 to 13) | Yes: confirm store rules from the store pages; register `MOB-` IDs; D-PMOB1 to D-PMOB8. |
| `MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` | Yes | Partial (6.3): Variant A ready in shadow mode; serving needs D-PQ2; Variant B blocked (D-03). | 10 labels; 80/80 cites; 9 of them proposed, absent or chart-relative by design (not broken) | 0 | SM-1 (clip id vs `test_citation_contract.py:169-205`). | none | Yes for Variant A; No for Variant B | Yes: commit `a33d6b8d` (T6-04) may change the clip-id question (SM-1); not verified. |
| `PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` | Yes | Partial (6.8): consent, proposals, export, erasure, saved wisdom ready; journeys and reminders blocked (D-PM6, D-PM9). | 27 labels; 210/210 cites; 40 of them proposed, absent or chart-relative by design (not broken) | 0 | SM-1; SM-3 (PersonalizeStage vs invariants 1, 15, 21; D-03). | none | Yes for ready parts | Yes: commits `2edee1c4`, `649ea2c3`, `a33d6b8d`, `4af5e711` touch its subject (`FINAL_READINESS` §7). |
| `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` | Yes | Partial (6.10): SLOs (proposed), alert repair, 10 runbooks, backup contract ready; needs restore and alert drills. | 63 labels; 353/353 cites; 16 of them proposed, absent or chart-relative by design (not broken) | 0 | none found | `docs/runbooks/INCIDENT_LOG.md` does not exist (NEW-OPS-9 creates it). | Yes (1,020 lines; ordered tasks) | Yes: commit `7f63fe4c` moved lines in `feedback.py`; OPS-001 to OPS-009 not in the index. |
| `RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` | Yes | Specification only; nothing was run on Railway (`FINAL_SPEC…` 6.11). | 146 labels; 207/207 cites; 5 of them proposed, absent or chart-relative by design (not broken) | 0 | RW-C1 to RW-C11 correct `22b`. It also lists CLAUDE.md and code comments that disagree with the code. | none | Yes (proposed `railway.ts`, variable matrix, smoke set) | Yes: blocked by D-26, D-14, D-07; depends on a staging project. |
| `RETRIEVAL_AND_RAG_SPEC.md` | Yes | Partial (6.2, 'mostly'): plan in shadow mode, dedup, bank schema v2, budgets ready; floors need a baseline. | 20 labels; 220/220 cites; 15 of them proposed, absent or chart-relative by design (not broken) | 0 | SM-2. | Bank labels are human work (bank has 8 rows). | Yes | Yes: head moved to `fb5cab0f`; `FINAL_READINESS` §7 names no commit for it, so re-check §2 against code. |
| `SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md` | Yes | Partial (6.7): honest outcomes, abstain cause, wire parity, release invariants ready; blocked by D-PQ7, D-PQ8, D-PQ9, D-03. | 11 labels; 169/169 cites; 14 of them proposed, absent or chart-relative by design (not broken) | 0 | SM-1. | none | Yes | Yes: commit `a33d6b8d` (T6-04) affects the wire and clip-id decision. |
| `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md` | Yes | Partial: core seeker journey audited against WCAG 2.2 AA; Gate C7 is NOT met and UNPROVEN. Runtime checks ran on the frontend only; the clip view, crisis answer, settings and deletion flow did not render. | 41 labels; 169/169 cites; 5 of them proposed, absent or chart-relative by design (not broken) | 0 | none found. It confirms FRN-C9 and BL-10; it follows head `fb5cab0f`, not `46b808fb` (its own note). | Runtime evidence for the views that did not render; the manual screen-reader pass (`[HUMAN]`). | Yes (A11Y-01 to A11Y-17, NEW-A11Y-1 to 10, AC-A11Y-*) | Yes: register `A11Y-` IDs and D-PA11Y1 to D-PA11Y7 (not in `FINAL_DECISION_AND_RISK_REGISTER.md`); rate it in `FINAL_SPECIFICATION_COMPLETENESS_MATRIX.md`. |

### 1.5 Summary of the table

| Measure | Count | Which |
|---|---:|---|
| Rows | 68 | 35 numbered + 7 named + 11 FINAL + 15 specifications |
| Requires updating: Yes | 60 | all rows whose last cell starts with 'Yes' |
| Requires updating: No | 8 | `02-spiritual-user-research-personas-jtbd.md`, `02b-competitive-analysis-and-product-opportunities.md`, `26-independent-adversarial-review-and-residual-risks.md`, `27-execution-log-coverage-and-usage.md`, `FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md`, `FINAL_RAILWAY_STAGING_READINESS.md`, `ARCHITECTURE_DECISION_RECORDS_HISTORICAL.md`, `INGESTION_AND_CONTENT_PROCESSING_SPEC.md` |
| Detailed enough to implement: Partial or No | 24 | see the column; the specifications give the missing detail for the older documents (§1 of each) |

## 2. Residual broken citations

Line numbers are in the file as it stands now. Documents `03` to `22b` that received a pointer note (§4) have 2 more lines than when the script ran; the numbers below include this shift.

### 2.1 Truly broken (22 tokens in 13 groups)

| Doc : line | Token | Why it is broken | Suggested fix | Status (2026-11-06) |
|---|---|---|---|---|
| `10` :241 | `s3/route_sim.py` | Scratchpad script; not in the repository. | Cite the method in `10` §4 only, or add 'scratchpad, not committed'. | Fixed 2026-11-06 (marked 'scratchpad, not committed') |
| `13` :49 | `app/__init__.py:1-20` | The root alias file has 19 lines at `46b808fb` (and at `HEAD`). | Use `:1-19`. | Fixed (`:1-19`) |
| `14` :8 | `supabase/functions/sarvam-stt:7-8` | Names a directory with line numbers. | `supabase/functions/sarvam-stt/index.ts:7-8` (file exists, 153 lines at `HEAD`; line content at `46b808fb` not checked). | Fixed (full file path) |
| `14d` :230 | `src/lib/chat/__tests__/errors.test.ts` | Named as the regression test. The existing chat tests are in `src/test/chat/`. | Use `src/test/chat/errors.test.ts` or mark the file as new. | Fixed (`src/test/chat/errors.test.ts`; `14d` :189 directory also fixed) |
| `20` :71; `21` :77 | `src/components/PushPermissionPrompt.tsx` | Wrong folder. | `src/components/common/PushPermissionPrompt.tsx` | Fixed (`20` :71, `21` :77) |
| `20` :77; `21` :262; `IMPLEMENTATION-AGENT-PROMPT.md` :191 | `src/lib/errors.ts` | Wrong folder. | `src/lib/chat/errors.ts` | Fixed (`20` :77, `21` :262, prompt :191) |
| `20` :78 | `src/lib/streaming.ts` | Wrong folder. | `src/lib/chat/streaming.ts` | Fixed |
| `20` :79 | `src/lib/transport.ts` | Wrong folder. | `src/lib/chat/transport.ts` | Fixed |
| `20` :80 | `src/components/chat/types.ts` | Wrong folder. | `src/lib/chat/types.ts` | Fixed |
| `20` :89; `21` :99 | `backend/services/telemetry_sink.py` | Wrong folder. | `backend/app/telemetry_sink.py` | Fixed (`20` :89, `21` :99) |
| `20` :129 (2 tokens); `21` :196 (2); `27` :40 (2) | `facet_planner.py`, `set_selector.py` | Planned names. The files added later are `backend/services/first_person_facet_planner.py` and `backend/services/first_person_set_selector.py` (commit `76fa2bf0`). Neither name existed at `46b808fb`. | Use the implemented names. | Marked '(new files; implemented later as …)' in `20` :129 and `21` :196; renamed in `27` :40 (execution log) |
| `traceability-matrix.md` :18 | `teaching_scope.yaml` | No file with this name exists in the `HEAD` tree. | Name an existing file, or mark it 'proposed' (see `GURU…` §3 for the registry files). | Marked '(new file, proposed in `21`)' |
| `FINAL_USAGE_AND_VERIFICATION_LOG.md` :66 | `apply_review_fixes.py` | Scratchpad script; not in the repository. | Add 'scratchpad, not committed'. | NOT fixed: `FINAL_USAGE_AND_VERIFICATION_LOG.md` is outside this task's ownership |

### 2.2 Valid at `46b808fb`, stale at `HEAD` (11 tokens)

The audit cites `46b808fb`. Later commits changed these files. The citation is not wrong for the audit target. An implementer who reads the file at `HEAD` will not find the line.

| Doc : line | Token | At `46b808fb` | At `HEAD` | Status (2026-11-06) |
|---|---|---|---|---|
| `03` :67 | `transport.ts:613–629` | 648 lines; lines 613-629 hold the consent read and `pending_extractions` insert (checked) | 614 lines | Left: `03` states its audit commit at the top |
| `06` :37 | `backend/ingest/pipeline.py:4380-4400` | 4,408 lines | 4,174 lines | Left: `06` states its audit commit at the top |
| `09` :66, :108, :120, :260 | `quote_weaver.py:1414-1420`, `:1207`, `:1100-1154`, `:1380` | 1,640 lines; `:1207` is `_SCAFFOLD_PROMPT_VERSION = "v1"` (checked) | 1,149 lines; the symbol is gone | Left: `09` states its audit commit at the top (and in line 8 for line numbers) |
| `14d` :95 | `ChatHelpers.tsx:71-99` | 100 lines; `:71` starts `buildPersonalisedWelcome` (checked) | 93 lines | Left: `14d` states its audit commit at the top |
| `26` :60 | `src/lib/chat/transport.ts:608-626` | 648 lines | 614 lines | Left: `26` states its audit commit at the top |
| `13` :50, :50, :126 | `langdetect/__init__.py` (3 tokens) | exists (root stub) | removed by `42e883b3` (T1-13) | Left: `13` states its audit commit at the top |

### 2.3 The 9 past-EOF items

Eight are stale at `HEAD` only (rows above). One is wrong at `46b808fb`: `13` :49 (20 cited, 19 lines).

### 2.4 How the 699 tokens were sorted

| Class | Count | Note |
|---|---:|---|
| Flagged by the script (627 missing + 63 ambiguous + 9 past EOF) | 699 | |
| Dropped before sorting | about 178 | By subtraction. Routes, branch names, URLs and tokens with no extension and no slash. Overlaps are possible. |
| Bare file name with one match (resolved shorthand) | 305 | `memory.py`, `build_full_corpus_v10.py` |
| Bare file name with several matches (ambiguous) | 62 | `pipeline.py` (06: 18), `first_person.py`, `feedback.py` |
| Not at `46b808fb`, exists at `HEAD` (added by later tasks) | 71 | tests and scripts created by tasks T2-01 to T6-04 |
| Host path or legacy folder name | 3 | `audit-output/…` in the prompt |
| Not found at `46b808fb` after the prefix search | 80 | 19 truly broken (§2.1); 24 virtual names in `README.md`; 37 non-file or proposed (model names, images, env values, absence claims, directories, ellipsis) |
| Past end of file or directory-with-lines, counted in §2.1 and §2.2 | 9 + 1 | 8 stale, 1 off by one, 1 directory |

The classes are sorted by hand and by script and can overlap, so they may not add up to 699. The 22 tokens in §2.1 and the 11 in §2.2 are exact.

### 2.5 Hand spot-check of 10 tokens

| # | Token | Check | Result |
|---|---|---|---|
| 1 | `src/lib/errors.ts` (`20` :77) | `ls` | absent; `src/lib/chat/errors.ts` exists. Broken. |
| 2 | `src/components/PushPermissionPrompt.tsx` (`20` :71) | `ls` | absent; `src/components/common/PushPermissionPrompt.tsx` exists. Broken. |
| 3 | `backend/services/telemetry_sink.py` (`20` :89) | `ls` | absent; `backend/app/telemetry_sink.py` exists. Broken. |
| 4 | `facet_planner.py` (`20` :129) | `git ls-tree` at both trees | absent at both; `first_person_facet_planner.py` added by `76fa2bf0`. Broken (naming). |
| 5 | `supabase/functions/sarvam-stt:7-8` (`14` :8) | `ls` | a directory holding `index.ts` (153 lines). Broken (form). |
| 6 | `src/lib/chat/__tests__/errors.test.ts` (`14d` :230) | `ls` | absent; `src/test/chat/errors.test.ts` exists. Broken. |
| 7 | `teaching_scope.yaml` (`traceability-matrix.md` :18) | `git ls-files`, `grep -rn` | no file and no other mention outside this audit folder. Broken. |
| 8 | `langdetect/__init__.py` (`13` :50) | `git log --diff-filter=D` | exists at `46b808fb`; removed by `42e883b3`. Stale, not broken. |
| 9 | `transport.ts:613–629` (`03` :67) | `git show 46b808fb:…` | 648 lines; content matches the claim. Valid at baseline. |
| 10 | `quote_weaver.py:1207` (`09` :108) | `git show 46b808fb:…` | line 1207 is `_SCAFFOLD_PROMPT_VERSION = "v1"`; gone at `HEAD`. Valid at baseline. |

### 2.6 Related findings about references

- The old folder name `audit-output/` occurs 47 times in 8 files (`20`: 3, `24`: 6, `25`: 19, `27`: 3, `CONVENTIONS.md`: 1, `IMPLEMENTATION-AGENT-PROMPT.md`: 12, `README.md`: 1, `decision-log.md`: 1). `README.md` line 5 explains the move (D-27). `25` has no note. A coding agent that follows `audit-output/20-…md` from `25` or the prompt gets a missing path.
- The checker's 238 'finding IDs not in index' are mostly not findings: they are `FR-`/`NFR-` suffixes (`ANS-01`, `SAFE-01`), `ADR-0nn`, `SHA-256`, `FM-nn`. The real gaps are in §3.2.
- Specification files cite `memory.py`, `first_person.py`, `health.py`, `pipeline.py` by bare name. Several repository files share each name, so a line cite cannot be checked without the folder. Fix by adding the folder in the next edit of those specifications.

## 3. Missing links between documents

### 3.1 Older documents with no pointer to the file that extends them

A pointer note was inserted where a file in `specifications/` supersedes or extends the older document (§4). These documents have a newer file that is outside `specifications/` or outside my scope, or have no newer file. No pointer was inserted for them.

| Older document | Newer file | Why no pointer from me |
|---|---|---|
| `00` | `FINAL_READINESS_AND_GAP_ANALYSIS.md` §1 (gates A/B/C) | Not in `specifications/`. `README.md` already points to it. |
| `01` | `FINAL_READINESS_AND_GAP_ANALYSIS.md` §7 (commits after the verification head) | Same. |
| `16` | none | New defects (DATA-20 to DATA-27, OPS-003 to OPS-008, MEM-007 to MEM-012, MOB, K8S) have no root-cause cluster. |
| `17` | `specifications/ARCHITECTURE_DECISION_RECORDS_HISTORICAL.md` | Extends; does not supersede. Add a link from `17` §5 and `decision-log.md` §2. |
| `20`, `21` | `NEW-*` task rows in §8/§9 of each specification; `FINAL_PENDING_WORK_REGISTER.md` §3 | Many files extend them; the form allows one. See §3.4. |
| `24`, `25`, `IMPLEMENTATION-AGENT-PROMPT.md` | `FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` | Not in `specifications/`. The prompt is under edit by another agent. |
| `23` | none | Gate sign-offs are `[HUMAN]`; `docs/agent/gates/` is absent. |
| `26` | `FINAL_AUDIT_GAP_ANALYSIS.md` §1 refines C-1 | Record file; add 'read with' line. |
| `traceability-matrix.md` | `specifications/COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` | Outside my scope (named file). |
| `decision-log.md`, `unresolved-questions.md` | `FINAL_DECISION_AND_RISK_REGISTER.md` | Outside my scope. |
| `README.md` | the 15 spec files | Outside my scope. It names only a count ('12 files'). |

### 3.2 Finding IDs used in documents and absent from `findings-index.md` (75)

The index holds 149 distinct IDs. These are proposals made by the specification agents. Each says the lead confirms them in the index; that step is not done (`FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` §5, first row).

| Prefix | IDs | Defined in |
|---|---|---|
| `DATA-` | DATA-20, 21, 22, 23, 24, 25, 26, 27 (8) | `INGESTION_AND_CONTENT_PROCESSING_SPEC.md` §2.2; `FINAL_AUDIT_GAP_ANALYSIS.md` §2 |
| `MEM-` | MEM-007, 008, 009, 010, 011, 012 (6) | `PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` §1 |
| `OPS-` | OPS-001 to OPS-009 (9) | `PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` §2. The `OPS-` prefix has no owner in `CONVENTIONS.md` §5. |
| `ANS-` | ANS-009 to ANS-013 (5) | `SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md` §1.1. `FINAL_AUDIT_GAP_ANALYSIS.md` §2 also uses ANS-012. |
| `RET-` | RET-12 to RET-17 (6) | `RETRIEVAL_AND_RAG_SPEC.md` §1 |
| `MOB-` | MOB-01 to MOB-15 (15) | `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md` §3. No owner prefix. |
| `K8S-` | K8S-01 to K8S-09 (9) | `K8S_MANIFESTS_REVIEW.md` §3. NEW-K8S-6 asks the lead to register the prefix. |
| `A11Y-` | A11Y-01 to A11Y-17 (17) | `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md` §3. No owner prefix. |

`FINAL_AUDIT_GAP_ANALYSIS.md` §2 also lists defect groups with no ID at all: the Railway group (`RW`), answer honesty, the AI-harness group, the GURU group, and `RLIMIT` ('not yet assigned'). `FINAL_PENDING_WORK_REGISTER.md` does not carry the 75 IDs.

### 3.3 Finding IDs in the older documents

All finding IDs in documents `00` to `27` that match an owner prefix in `CONVENTIONS.md` §5 are in the index. The checker's other hits are FR/NFR/ADR fragments (§2.6).

### 3.4 Tasks referenced and absent from `20`

| Group | Count | Where defined |
|---|---:|---|
| `NEW-*` tasks | 122 | `NEW-MOB` 13, `NEW-OPS` 12, `NEW-MEM` 11, `NEW-ANS` 10, `NEW-RW` 9, `NEW-RET` 9, `NEW-SYN` 9, `NEW-ING` 8, `NEW-GURU` 8, `NEW-AI` 7, `NEW-A11Y` 10, `NEW-K8S` 6, `NEW-SEC` 5, `NEW-DQ` 5. Each is in §8 or §9 of its specification. |
| Lettered sub-tasks | 17 | T3-06a/b, T5-07a/b (specs); T7-01a to T7-01l except e (prompt §0); T8-02a/b (spec) |

`20` holds 85 numbered tasks. A coding agent has no single ordered list that includes the 122. The execution package orders them by phase (`FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` §3).

### 3.5 Decisions, counts and indexes

- `D-P*` decisions: 46 are in `FINAL_DECISION_AND_RISK_REGISTER.md`. 16 appear only in specifications (`D-PK8S1`, `D-PMOB1` to `D-PMOB8`, `D-PA11Y1` to `D-PA11Y7`). None of the 62 is in `unresolved-questions.md` or `decision-log.md`. `D-29` is in neither older register.
- `README.md` §Final verification says '10 FINAL files' and '12 files in specifications/'. There are 11 `FINAL_*.md` files (the index plus 10) and 15 specification files.
- `README.md` and `FINAL_READINESS_AND_GAP_ANALYSIS.md` §4 do not list `MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md`, `K8S_MANIFESTS_REVIEW.md` or `ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md`. `FINAL_SPECIFICATION_COMPLETENESS_MATRIX.md` does not rate them.
- `findings-index.md` section headings (P1 45, P2 77, P3 19) differ from its counts table (47, 81, 22). The file says the table is authoritative.
- `FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` §8 lists corrections to `CLAUDE.md` and `AGENTS.md` that the owner has not applied (`FINAL_AUDIT_GAP_ANALYSIS.md` §5, item 10). The pipeline order in `CLAUDE.md` still omits `KillSwitchStage` and `OffTopicStage` (LD-D1, FRN-C1); `05` is correct.
- 96 commits landed after `46b808fb`. `FINAL_READINESS_AND_GAP_ANALYSIS.md` §7 covers 21 of them (to `a7be7e65`). No document maps the other 75 to findings; `FINAL_PENDING_WORK_REGISTER.md` (note for `fb5cab0f`) is the closest.
- `FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` is not linked from `22`. `22` and the checklist cover the same live checks with different IDs (R-1…R-18 against the checklist steps).
- Traceability chain breaks BL-1 to BL-12 are recorded in `COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` §7; `traceability-matrix.md` does not carry them.

## 4. Pointer notes inserted

One line directly under the title of each document below. No other line was changed (`git diff --numstat` shows +2/-0 for each: the note and one blank line).

| File | Line | Text |
|---|---:|---|
| `03-product-journeys-functional-requirements.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` (44 FRs rewritten with test, acceptance, gate and status; stale rows corrected in its §2). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `04-non-functional-requirements-slos-and-benchmarks.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` (82 NFRs with test, gate and status; stale baselines corrected in its §2 C-2 to C-10). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `05-current-architecture-and-request-flow.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/RETRIEVAL_AND_RAG_SPEC.md` (live first-person path traced per step at `c9b42d3e` with every LLM call and budget). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `06-data-ingestion-quality-lineage.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md` (15-field contract per datastore, lineage with link IDs, reconciliation rules). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `07-video-audio-multisource-synthesis.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` (decision-free Variant A, wire contract, staged gates for §4). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `08-qdrant-graph-retrieval.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/RETRIEVAL_AND_RAG_SPEC.md` (retrieval contracts, floors, shadow mode, acceptance criteria and tasks). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `09-ai-harness-agents-prompts-context.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/AI_HARNESS_PROMPT_AND_CONTEXT_SPEC.md` (call-site decisions at `c9b42d3e`, prompt registry contract, unfenced call sites). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `10-spiritual-answer-quality-expected-behavior.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md` (field-level wire schema, render rules per voice layer, release invariants). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `11-krishnaji-preethaji-future-guru-extensibility.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/GURU_KNOWLEDGE_AND_KNOWLEDGE_GRAPH_SPEC.md` (registry field rules, path:line table at `c9b42d3e`, per-step onboarding tests). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `12-personal-mentor-memory-ethical-retention.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` (consent, lifecycle, export, erasure, saved-wisdom contracts; new defects MEM-007 to MEM-012). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `12b-ethical-retention-and-mentor-ux.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` (journeys, reminders and retention schedule as contracts). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `14-security-safety-privacy-permissions.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` (threat model, adversarial cases, untrusted-content fence). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `14b-safety-crisis-and-spiritual-trust.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md` (attribution tests on the wire, safety-notice ordering around multi-block answers). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `14c-content-permissions-and-ip-register.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/GURU_KNOWLEDGE_AND_KNOWLEDGE_GRAPH_SPEC.md` (where rights live in the registry and how serving checks them). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `14d-user-journey-and-frontend-walkthrough.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` (what the personalisation controls must do for UX-006 and UX-009). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `15-reliability-performance-cost-observability.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` (SLO, alert, runbook and cost-attribution contracts; alert defects OPS-003 to OPS-008). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `18-golden-eval-dataset-and-testing-spec.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/AI_HARNESS_PROMPT_AND_CONTEXT_SPEC.md` (adversarial set (§3.11) and model-change procedure (§3.12)). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `22-qdrant-graph-deferred-validation-runbook.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md` (static fixture equivalents, SQL and Redis checks, rights-stamp check (§5)). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `22a-acceptance-criteria-and-testing-plan.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` (testing methodology by component (§8) and data-integrity invariants as executable checks (§6)). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |
| `22b-railway-deployment-readiness-runbook.md` | 3 | > **2026-11-06:** Superseded in part by `specifications/RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` (11 corrections to this file in its §2 (C-1 to C-11), topology, IaC, drain and signal handling). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`. |

Total: 20 notes. Not changed: `00`, `01`, `02`, `02b`, `13`, `16`, `17`, `19`, `20`, `21`, `23`, `24`, `25`, `26`, `27`, and all named files (§3.1 gives the reason).

## 5. Verified, assumptions, unknowns

### Verified

- All 42 original files, 11 FINAL files and 15 specification files exist at the paths in §1 (`ls`).
- Citation re-resolution results in §2 were computed with scripts against `git ls-tree` of `46b808fb`, `c9b42d3e` and `HEAD`. 10 tokens were checked by hand (§2.5).
- The pointer notes are insert-only: `git diff --numstat` shows 2 added and 0 deleted lines in each of the 20 files.
- The 75 IDs and the 122 `NEW-*` tasks were counted by regular expression over the audit folder and checked against the definition tables in the specifications.
- The conflicts in the table come from the places named in the key. Each was read in its source.

### Assumptions

- A bare file name that matches exactly one file is the intended file. [INF]
- The 'Complete for its purpose' and 'Detailed enough' judgements for the older documents rest on the §1 tables of the specifications and on the section headings, not on a new line-by-line read of every older document. [INF]
- A token that names a file the document says it will create is treated as proposed, not broken. [INF]

### Unknowns

- Whether each older document's factual claims still hold at `fb5cab0f`. 96 commits changed the code; only citation existence and line length were tested.
- Whether line cites that fit the file length still point at the same content. Only 4 were read (§2.5).
- Whether the specification files' cites into `memory.py`, `first_person.py`, `health.py`, `pipeline.py` point at the intended file (ambiguous names).
- Another agent is editing `FINAL_PENDING_WORK_REGISTER.md`, `IMPLEMENTATION-AGENT-PROMPT.md` and others while this file was written; rows for them reflect the state read at the time.

## 6. Citation cleanup change log (2026-11-06)

Scope: only the reference was changed. No finding, number, conclusion or evidence label was altered. Re-check used `doc_linkcheck.py` (copy, same logic) on the 42 original files at head `004f3cf5`.

### 6.1 Counts, before and after

| Class | Before | After | Note |
|---|---:|---:|---|
| Truly broken (§2.1, 22 tokens) | 22 | 1 | The one left is in `FINAL_USAGE_AND_VERIFICATION_LOG.md` (outside this task's ownership). Planned files in `20`/`21`/`traceability-matrix.md` are marked '(new file)' rather than changed. |
| Stale at `HEAD` (§2.2, 11 tokens) | 11 | 11 | Left by rule: each document states `46b808fb` as its audit target at the top (`09` also says its line numbers were read there). |
| Past end of file | 9 | 9 | 8 are the stale items above; `13` :49 fixed; `06` :322 now shows as past-EOF because its bare `pipeline.py:4392` was qualified (stale at `HEAD`, valid at `46b808fb`: `MERGE (src:__Chunk__ …)`). |
| Ambiguous bare names | 63 (62 + 1 in `findings-index.md`) | 5 | 58 qualified; 4 left in files I own, 1 in `findings-index.md` (not mine). |
| Old folder name `audit-output/` used as a path | 40 in my files | 0 | 20: 3, 24: 6, 25: 19, `IMPLEMENTATION-AGENT-PROMPT.md`: 12. Kept as history: `27` :73, :88, :92; `decision-log.md` L-06; `README.md` line 5; this file's descriptions. Not mine: `CONVENTIONS.md` §2 (1). |
| Citations OK (script) | 2,039 | 2,115 | |

### 6.2 Truly broken and related fixes

| File | Line | Before | After | Class | Evidence |
|---|---:|---|---|---|---|
| `10` | 241 | `s3/route_sim.py` | `s3/route_sim.py` (scratchpad, not committed) | broken | Scratchpad script, not in repo. |
| `13` | 49 | `app/__init__.py:1-20` | `app/__init__.py:1-19` | broken / past-EOF | `git show 46b808fb:app/__init__.py` has 19 lines. |
| `14` | 8 | `supabase/functions/sarvam-stt:7-8` | `supabase/functions/sarvam-stt/index.ts:7-8` | broken | Lines 7-8 hold `SARVAM_STT_URL`, `GATEWAY_STT_URL` at `46b808fb` and `HEAD`. |
| `14d` | 230 | `src/lib/chat/__tests__/errors.test.ts` | `src/test/chat/errors.test.ts` | broken | File exists. |
| `14d` | 189 | `src/lib/chat/__tests__/` | `src/test/chat/` | broken (same cause, not in §2.1) | Directory `src/lib/chat/__tests__` does not exist. |
| `20` | 71 | `src/components/PushPermissionPrompt.tsx` | `src/components/common/PushPermissionPrompt.tsx` | broken | File exists. |
| `21` | 77 | same | same | broken | |
| `20` | 77 | `src/lib/errors.ts` | `src/lib/chat/errors.ts` | broken | File exists; error mapping (`case 'server_error'`) near line 77-80 at `46b808fb`. |
| `21` | 262 | `src/lib/errors.ts` | `src/lib/chat/errors.ts` | broken | |
| `IMPLEMENTATION-AGENT-PROMPT.md` | 191 | `src/lib/errors.ts` | `src/lib/chat/errors.ts` | broken | |
| `20` | 78 | `src/lib/streaming.ts` | `src/lib/chat/streaming.ts` | broken | File exists. |
| `20` | 79 | `src/lib/transport.ts` | `src/lib/chat/transport.ts` | broken | File exists. |
| `20` | 80 | `src/components/chat/types.ts` | `src/lib/chat/types.ts` | broken | File exists; `src/components/chat/types.ts` absent at both trees. |
| `20` | 89 | `backend/services/telemetry_sink.py` | `backend/app/telemetry_sink.py` | broken | File exists. |
| `21` | 99 | same | same | broken | |
| `20` | 129 | `facet_planner.py`, `set_selector.py` | same, plus '(new files; implemented later as `backend/services/first_person_facet_planner.py` and `backend/services/first_person_set_selector.py`)'; `first_person_pipeline.py` qualified to `backend/services/first_person_pipeline.py` | broken (planned) | Neither name exists at either tree; implemented names exist at `HEAD`. |
| `21` | 196 | same | same | broken (planned) | |
| `27` | 40 | `set_selector.py`, `facet_planner.py` | `first_person_set_selector.py`, `first_person_facet_planner.py` | broken | Execution-log list; implemented names per §2.1. Whether those files were the ones read at `46b808fb` is not checked. |
| `traceability-matrix.md` | 18 | `teaching_scope.yaml` | `teaching_scope.yaml` (new file, proposed in `21`) | broken (planned) | No such file at `HEAD`; `21` :172 proposes it. |
| `21` | 172 | `backend/config/teaching_scope.yaml` | same, plus ', new file' | planned | Same. |

### 6.3 Stale at `46b808fb`: left, not moved to `HEAD`

| File | Line | Token | Action | Evidence |
|---|---:|---|---|---|
| `03` | 67 | `transport.ts:613–629` | left | Header line 5 states target `46b808fb`; 648 lines there. |
| `06` | 37 | `backend/ingest/pipeline.py:4380-4400` | left | Header states target; 4,408 lines there. |
| `09` | 66, 108, 120, 260 | `quote_weaver.py:1414-1420`, `:1207`, `:1100-1154`, `:1380` | left | Header and line 8 state `main@46b808fb`. |
| `13` | 50, 50, 126 | `langdetect/__init__.py` | left | Header states target. |
| `14d` | 95 | `ChatHelpers.tsx:71-99` | left | Header states target. |
| `26` | 60 | `src/lib/chat/transport.ts:608-626` | left | Header states target. |

### 6.4 Ambiguous bare names qualified

Rule: the owning row or sentence names the folder or the subject, or the two same-named copies are byte-identical (`scripts/ops/` and `backend/scripts/ops/`, `scripts/` and `backend/scripts/`, checked with `git show` at `46b808fb` and `HEAD`). Where line cites exist, the cited line was read at `46b808fb` (for example `backend/app/api/first_person.py:297` is `query_first_person_teaching`; `backend/rag/nodes/first_person.py:52-65` returns `{}`; `src/lib/chat/types.ts:293-300` is `resolveAttributionLabel`; `backend/app/api/feedback.py:336` is `/clip-report`; `src/App.tsx:269` is the `ClipReportsPage` entry).

| File | Line | Before | After |
|---|---:|---|---|
| `03` | 32 | `App.tsx:381–384` | `src/App.tsx:381–384` |
| `03` | 58 | `App.tsx:373` | `src/App.tsx:373` |
| `03` | 62 | `feedback.py:26` | `backend/app/api/feedback.py:26` |
| `03` | 63 | `feedback.py:336` | `backend/app/api/feedback.py:336` |
| `03` | 63 | `App.tsx:269` | `src/App.tsx:269` |
| `03` | 67 | `memory.py` | `backend/app/api/memory.py` |
| `03` | 81 | `push.py` | `backend/app/api/push.py` |
| `03` | 176 | `App.tsx:269` | `src/App.tsx:269` |
| `03` | 283 | `types.ts:293–300` | `src/lib/chat/types.ts:293–300` |
| `05` | 68 | `first_person.py:297-301` | `backend/app/api/first_person.py:297-301` |
| `05` | 161 | `first_person.py:52-65` | `backend/rag/nodes/first_person.py:52-65` |
| `06` | 31 | `build_full_corpus_v10.py` | `backend/scripts/ops/build_full_corpus_v10.py` |
| `06` | 31 | `build_fp_context_from_v9.py` | `backend/scripts/ops/build_fp_context_from_v9.py` |
| `06` | 32 | `build_first_person_index.py` | `backend/scripts/ops/build_first_person_index.py` |
| `06` | 37 | `build_teaching_unit_graph.py` | `backend/scripts/ops/build_teaching_unit_graph.py` |
| `06` | 41 | `extract_okf_from_stores.py` | `backend/scripts/extract_okf_from_stores.py` |
| `06` | 57 | `build_teaching_unit_graph.py:425-426` | `backend/scripts/ops/build_teaching_unit_graph.py:425-426` |
| `06` | 129 | `build_full_corpus_v10.py:349-385` | `backend/scripts/ops/build_full_corpus_v10.py:349-385` |
| `06` | 135 | `data_quality_audit.py` | `backend/scripts/ops/data_quality_audit.py` |
| `06` | 145 | `build_full_corpus_v10.py:867-894` | `backend/scripts/ops/build_full_corpus_v10.py:867-894` |
| `06` | 217 | `build_full_corpus_v10.py:349-385` | `backend/scripts/ops/build_full_corpus_v10.py:349-385` |
| `06` | 259 | `build_full_corpus_v10.py:867-894` | `backend/scripts/ops/build_full_corpus_v10.py:867-894` |
| `06` | 259 | `build_first_person_index.py:677-783` | `backend/scripts/ops/build_first_person_index.py:677-783` |
| `06` | 322 | `pipeline.py:4392` | `backend/ingest/pipeline.py:4392` |
| `06` | 364 | `pipeline.py:1038-1216` | `backend/ingest/pipeline.py:1038-1216` |
| `06` | 364 | `pipeline.py:3537` | `backend/ingest/pipeline.py:3537` |
| `06` | 427 | `build_first_person_index.py:561-578` | `backend/scripts/ops/build_first_person_index.py:561-578` |
| `06` | 490 | `build_full_corpus_v10.py:131` | `backend/scripts/ops/build_full_corpus_v10.py:131` |
| `07` | 33 | `pipeline.py:542-555` | `backend/ingest/pipeline.py:542-555` |
| `07` | 40 | `build_full_corpus_v10.py:4-17` | `backend/scripts/ops/build_full_corpus_v10.py:4-17` |
| `07` | 41 | `build_full_corpus_v10.py:1041-1050` | `backend/scripts/ops/build_full_corpus_v10.py:1041-1050` |
| `08` | 193 | `build_teaching_unit_graph.py:157-161` | `backend/scripts/ops/build_teaching_unit_graph.py:157-161` |
| `12b` | 85 | `feedback.py` | `backend/app/api/feedback.py` |
| `13` | 89 | `base.py` | `backend/services/llm/base.py` |
| `13` | 89 | `factory.py` | `backend/services/llm/factory.py` |
| `14` | 53 | `memory.py:803-815` | `backend/app/api/memory.py:803-815` |
| `14` | 53 | `first_person.py:297` | `backend/app/api/first_person.py:297` |
| `14d` | 128 | `types.ts:297-299` | `src/lib/chat/types.ts:297-299` |
| `14d` | 242 | `types.ts:297-299` | `src/lib/chat/types.ts:297-299` |
| `15` | 175 | `health.py:741-760` | `backend/app/api/health.py:741-760` |
| `16` | 192 | `build_full_corpus_v10.py:867-894` | `backend/scripts/ops/build_full_corpus_v10.py:867-894` |
| `20` | 101 | `build_full_corpus_v10.py` | `backend/scripts/ops/build_full_corpus_v10.py` |
| `20` | 129 | `build_teaching_unit_graph.py` | `backend/scripts/ops/build_teaching_unit_graph.py` |
| `20` | 258 | `build_full_corpus_v10.py` | `backend/scripts/ops/build_full_corpus_v10.py` |
| `20` | 258 | `data_quality_audit.py` | `backend/scripts/ops/data_quality_audit.py` |
| `20` | 270 | `check_legacy_guru_tables.py` | `backend/scripts/ops/check_legacy_guru_tables.py` |
| `21` | 130 | `build_full_corpus_v10.py` | `backend/scripts/ops/build_full_corpus_v10.py` |
| `22a` | 28 | `gate1_load_test.py` | `backend/scripts/ops/gate1_load_test.py` |
| `24` | 18 | `first_person.py` | `backend/app/api/first_person.py` |
| `24` | 22 | `first_person.py` | `backend/rag/nodes/first_person.py` |
| `24` | 28 | `pipeline.py` | `backend/ingest/pipeline.py` |
| `27` | 40 | `build_full_corpus_v10.py` | `backend/scripts/ops/build_full_corpus_v10.py` |
| `27` | 40 | `build_first_person_index.py` | `backend/scripts/ops/build_first_person_index.py` |
| `27` | 42 | `App.tsx` | `src/App.tsx` |
| `IMPLEMENTATION-AGENT-PROMPT.md` | 35 | `compliance.py` | `backend/app/api/compliance.py` |
| `IMPLEMENTATION-AGENT-PROMPT.md` | 426 | `metrics.py` | `evals/retrieval_bank/metrics.py` |
| `IMPLEMENTATION-AGENT-PROMPT.md` | 434 | `build_full_corpus_v10.py` | `backend/scripts/ops/build_full_corpus_v10.py` |
| `IMPLEMENTATION-AGENT-PROMPT.md` | 436 | `data_quality_audit.py` | `backend/scripts/ops/data_quality_audit.py` |

Left unqualified (not certain, or not a repository file):

| File | Line | Token | Why |
|---|---:|---|---|
| `06` | 46 | `manifest.json` | Host file `~/mukthiguru_attribution_data/audio_archive/manifest.json`, not in the repository. |
| `13` | 49 | `__init__.py` | Generic phrase 'each one `__init__.py`', not a single file. |
| `27` | 39 | `health.py` | `backend/app/api/health.py` or `backend/app/health.py`; the log does not say which was read. |
| `27` | 40 | `raptor.py` | `backend/ingest/raptor.py` or `backend/services/qdrant/raptor.py`; not stated. |
| `findings-index.md` | 175 | `compliance.py` | Not mine. `backend/app/api/compliance.py` (holds `_get_container_safely`) or `backend/app/schemas/compliance.py`. |

### 6.5 Old folder name

Replaced `audit-output/` with `audits/audit-output-2026-11-04/` on: `20` :55, :182, :184; `24` :111, :113, :114, :117, :120, :139; `25` :8, :9, :11, :22, :24, :26, :27, :28, :37, :60, :63, :76, :168, :179, :186, :187, :191, :194, :196; `IMPLEMENTATION-AGENT-PROMPT.md` :5, :96, :155, :159, :161, :257, :259, :268, :281, :282, :283, :288. Two sentences that compared old and new names were reworded to keep their meaning: `24` :111 now says the package was 'first written as `audit-output/` at the repository root, then moved'; `IMPLEMENTATION-AGENT-PROMPT.md` :5 says the same in place of 'every `audit-output/` path below means this folder'. Class: old folder name. Evidence: `README.md` line 5 and decision D-27.

### 6.6 Other

- `15` :174 `app/telemetry_sink.py` still resolves only as a `backend/`-relative shorthand (`backend/app/telemetry_sink.py`). Not changed (outside the 22).
- `26` :59 `sarvam-stt/index.ts:7`/`:8` are partial paths; not changed.
- Items for `findings-index.md` and `CONVENTIONS.md` (not edited): `findings-index.md` :175 bare `compliance.py`; `CONVENTIONS.md` §2 uses `/home/user/askmukthiguru-8119b0e8/audit-output/` as the write path (old folder name).

## 7. Documents added after this inventory was built (2026-11-06)

| Document | Exists | Complete for its purpose | Evidence present | Detailed enough to implement | Requires updating |
|---|---|---|---|---|---|
| `specifications/LOVABLE_SYNC_PATH_REVIEW.md` | Yes | Yes (review) | Commit SHAs and file paths | Partial: NEW-LOV-01 is an owner step; NEW-LOV-05 waits for D-24 | No |
| `specifications/LOAD_AND_COST_MODEL.md` | Yes | Yes as a model; nothing measured | Labelled [V-STATIC] / [DOC-CLAIM] / [INF]; three 8,192-token statements corrected by the lead | Yes for NEW-LOAD-1 to -6; NEW-LOAD-7 needs staging | Yes after the staging load run |
| Accessibility audit §10 and mobile spec §10 (appended) | Yes | Proxy only; states its limits | Commands and probe outputs | Owner-run checklists | Yes after a human screen-reader and device session |

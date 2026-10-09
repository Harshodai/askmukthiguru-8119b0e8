# Phase and loop prompts (copy one at a time into the orchestrator session)

Each prompt assumes the orchestrator prompt is active and Gate G0 is approved.

---
## P1. Rights register (start here; mostly read-only)
Delegate to `rights-registrar`, then `independent-reviewer`.
Objective: know exactly what content is in the product and on what basis.
Tasks: inventory every ingested source (books, YouTube channels and videos, transcripts, meditations) across the vector store, graph, ingestion state and data folders; build the register in `CONTENT-RIGHTS.md` and `docs/rights/`; implement `serve_only_registered_sources`; check git history for copyrighted files; draft approval-request messages for each rights holder (drafts only).
Acceptance: a gap list with counts; unregistered sources blocked at serve time in tests; a Gate G2 evidence draft.
Escalate: any rights decision, any file that must be purged from history.

## P2. Safety spine
Delegate to `safety-engineer` (implementation), `red-team-reviewer` (attacks), `independent-reviewer`.
Objective: the crisis path is real, conversation-aware and tested.
Tasks: audit existing distress and crisis handling against the release evidence pack; implement risk tiers across turns; Tier 3 bypass; independent model-agnostic risk monitor; `config/helplines.yaml` with source URLs and `last_verified` (all entries UNVERIFIED until a human verifies); kill switch; safety event logging without raw text.
Acceptance: multi-turn crisis tests pass; kill switch tested; a list of helplines for a human to verify; Gate G1 evidence draft.
Escalate: any safety regression; anything needing clinical judgment.

## P3. Evals and the NotebookLM bake-off
Delegate to `eval-engineer`, `red-team-reviewer`, `independent-reviewer`.
Objective: measurable safety and grounding, and an honest comparison.
Tasks: 60+ multi-turn safety scenarios in the pilot languages with rubric; judge with a calibration plan (clinician labels needed: list exactly what the clinician must label); grounding suite (citation precision and recall, faithfulness, verbatim-quote match, abstention, hallucinated attributions); 50-question bake-off kit with a blind rating sheet; CI wiring.
Acceptance: harness runs end to end; results recorded honestly (NOT RUN where models or keys are missing); CI gate fails on safety regression.

## P4. Grounded reading (NotebookLM-style)
Delegate to `grounding-engineer` and `frontend-engineer`, then `independent-reviewer`.
Objective: match what people value in NotebookLM.
Tasks: citations that open the exact passage with timestamp links; "ask within" by teacher, series, language; reviewed source guides (offline, cached, AI-labeled, human review before publish); cited study outputs behind flags; graph mind map with citations; read-aloud only in a clearly synthetic non-guru voice and only with organizational approval.
Acceptance: verbatim-quote check enforced; abstention on out-of-corpus; UI accessible; flags default off.

## P5. Healthy return and human handoff
Delegate to `practice-engineer` and `frontend-engineer`, then `independent-reviewer`.
Objective: return when needed, toward practice and people.
Tasks: 7 and 21-day practice paths with links to official meditations; opt-in check-ins with quiet hours; forgiving streaks; healthy-use nudges; memory policy with visible memory screen; consented faculty handoff.
Acceptance: no attachment or guilt language (test with red-team fixtures); consent flows tested; handoff never used for emergencies.

## P6. Privacy and DPDP readiness
Delegate to `privacy-engineer`, then `independent-reviewer`.
Objective: consent, deletion and data handling are real.
Tasks: consent and notice in pilot languages; 18+ gate; deletion and export integration tests; retention jobs; data map including third-party model providers and cross-border notes; RLS tests stay green.
Acceptance: Gate G3 evidence draft; list of legal questions for the human privacy owner.

## P7. Platform: performance, cost, CI, hygiene
Delegate to `platform-engineer`, then `independent-reviewer`.
Objective: fast, affordable, observable, clean.
Tasks: measure median and p95 latency (first token and full answer, distress path, cached and uncached); cost per conversation by stage; monthly cap and kill switch; rate limits; flags for unused pipeline layers; fix flaky tests and remove stale suites; dependency and secret scans of tree and git history; runbooks; backup and restore drill document.
Acceptance: measurements recorded with commands (or NOT RUN); Gate G4 evidence draft; commands for humans to run for anything irreversible.

## P8. Pilot instrumentation and dashboard
Delegate to `platform-engineer`, `frontend-engineer`, `eval-engineer`.
Objective: know whether it helps.
Tasks: privacy-preserving events (session start, risk tier, crisis referral shown, helpline click, meditation started and completed, citation opened, helped yes/no, return day 7 and day 30, handoff requested, memory deleted); dashboard (night-time share, escalation rate, helpfulness, returns, cost per active user, p95 latency); weekly pilot report generator.
Acceptance: no raw text in events; dashboard renders from test data; report template ready.

## P10. Retrieval, knowledge graph and answer-quality
Delegate to `retrieval-quality-engineer`, then `eval-engineer` (for the metric harness), then `independent-reviewer`.
Objective: verify the LightRAG/Qdrant/graph configuration matches what the docs claim, close any gaps, and put a number on answer quality and ingestion quality for the first time.
Tasks: confirm the entity-extraction model meets the capability bar; confirm Qdrant hybrid (dense+sparse+RRF) vs dense-only and enable hybrid if missing and justified; confirm reranking is active; seed graph extraction with the OG-RAG-style structural ontology in `docs/agent/RETRIEVAL_QUALITY.md` if none exists (Teacher, Teaching, Practice, State, Obstacle/DistressPattern, Source); build faithfulness / answer-relevancy / context-precision-recall measurement against a fixed question set; report ingestion completeness, chunking fidelity, metadata completeness and dedup, each dated; measure current latency (median and p95, distress path included) before and after any scaling change from Section 5 of the same doc, and hand serving-layer work to `platform-engineer`.
Acceptance: an audit report with evidence for all four configuration questions; metric harness runs end to end with dated results (or NOT RUN); any ontology additions are structural only, with content/doctrinal questions escalated rather than decided.
Escalate: any change to extraction model or search mode with a material cost or latency impact; any ontology question that touches teaching content rather than structure.

## P9. Documentation and founder update
Delegate to `docs-writer`.
Tasks: public "How AskMukthiGuru works" page (scope, safety protocol, privacy, sources, limits); trimmed handoff and lessons; corrected README figures with dates and method; founder update (under 200 words).
Acceptance: every claim has evidence or is marked UNVERIFIED.

---
## L1. Eval-fix loop
Run the full eval suite. Cluster failures by cause. Delegate one fix per cluster to the right writer. Re-run. Maximum 3 iterations per cluster. Stop immediately on any safety regression and escalate.

## L2. Red-team loop
Ask `red-team-reviewer` for a fresh batch of attack scenarios across all attack families. Add confirmed failures to the eval suite as permanent regression cases. Report severity-ranked failures to me.

## L3. Weekly review
Ask `repo-auditor` for a delta since the last review. Summarize: merged, ready for merge, blocked, decisions needed from humans, scorecard changes with evidence, and the top three risks.

## L4. Scorecard refresh
Ask `repo-auditor` to re-score all seven dimensions strictly against `docs/agent/SCORECARD.md` exit criteria, citing evidence for each criterion. Any criterion without evidence counts as unmet. Do not round up.

## L5. Gate evidence pack (for G1 to G6)
For the named gate, assemble `docs/agent/gates/Gx-evidence.md`: each required item, its evidence link, status (met, unmet, NOT RUN), and the human decision needed. Leave sign-off lines blank.

## L6. Release candidate
Run all suites, `independent-reviewer` over every READY branch, dependency and secret scans, and check the kill switch. Produce a release note and a list of known exceptions with owners. Do not merge or deploy; hand me the exact commands.

## L7. Pilot report
After the pilot, produce the report against the agreed bars: helpfulness, returns at day 7 and day 30, crisis handling incidents, human connection actions, cost per active user, and where the product lost to the NotebookLM. State plainly whether each bar was met.

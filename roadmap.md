# Active UI and backend reliability roadmap

## Status from PR #76 audit (2026-10-21)

- [x] Inspect PR #76 head, changed-file list, reviews/comments and latest workflow status.
- [x] Identify exact CI blockers from GitHub Actions logs.
- [x] Locate the detailed profile-first plan at `.lovable/plan/profile-first-ui-and-journey-reliability-2026-10-19.md`.
- [x] Record research links and verified blockers on PR #76.
- [ ] Fix Ruff failures and rerun backend quality checks.
- [ ] Fix/clarify missing ingestion-module imports in Production Readiness job.
- [ ] Fix Supabase CLI setup so pre-launch integration tests actually execute.
- [ ] Review first-person fallback paths and remove unsupported generated/hardcoded teaching fallbacks.
- [ ] Replace admin mock graph fallback with explicit unavailable/demo-only state.
- [ ] Expand routing, distress, personal memory/KG and multilingual adversarial eval coverage.
- [ ] Run Docker Compose route matrix, end-to-end traces and separate concurrency-20 / backpressure-50 tests.
- [ ] Run approved staging checks for consent, tenant isolation, persistence, speaker/rights and exact clip provenance.
- [ ] Collect measured warm/cold p50/p95/p99, TTFT, per-stage duration, error rates and cost.
- [ ] Finish production readiness only when all required CI is green and external-service blockers have evidence-based disposition.

## Product and journey work still open

- [ ] Profile-first layout and editable-settings reliability.
- [ ] Preserve tab, security, onboarding, and original Chat return context.
- [ ] Complete language onboarding and canonical note journey.
- [ ] Google callback recovery; provider verification blocked until authorized Supabase configuration is available.
- [ ] Admin error handling, access-check recovery, and responsive controls.
- [ ] User/admin route sweep across phone, tablet, and desktop.
- [ ] Trace missing guru teachings from Chat through configured service and admin content sources.
- [ ] Restore transparent golden particles rising bottom-to-top, with reduced-motion support.
- [ ] Audit local first-person Qdrant/OKF integration, collection/vector compatibility, rights/speaker/hash/quote gates and frontend/backend contracts.
- [ ] Research approved production hosting and first-person release gates using official current sources.
- [ ] Design opt-in check-in → recorded teaching → practice → reflection → resume loop.
- [ ] Implement a consent-scoped personal Knowledge Graph using confirmed memories, provenance and edit/delete/forget controls.
- [ ] Compare navigation and daily-practice patterns without adding clutter, streak pressure or fabricated states.
- [ ] Add regression tests and honest live-service verification handoff.

## Release invariants

- First-person teacher claims must come from approved, verified source material; graph/OKF can support retrieval and relation stitching but cannot fabricate verbatim teacher speech.
- Unknown/mixed domain routing must use calibrated structured intent with a safe fallback; crisis prescreen stays ahead of general routing and is never delegated only to Jev/LLM.
- Personal memory must be explicit, tenant-isolated, consent-scoped, attributable, editable, and deletable; inferred graph edges must not silently become user facts.
- Measure latency by stage and optimize end-to-end p95/p99; do not infer performance from code shape alone.
- Do not claim deploy/readiness from frontend-only checks or mocked services.
- Railway stays off; no service activation or deployment without approved infrastructure, rights and credential decisions.

See also: `.lovable/plan/profile-first-ui-and-journey-reliability-2026-10-19.md` and PR #76 audit comment.

## Follow-up audit — 2026-10-22

### Code changes committed to this PR (not runtime-validated)

- [x] Replace the false-success first-person ingestion worker with a fail-closed, explicit unavailable state. The HTTP enqueue route returns 503 and does not queue work until the real audio acquisition, dual-ASR, attribution, clip-QA, and Qdrant indexing steps are actually wired. This is an intentional product capability block, not a completed ingestion feature.
- [x] Require explicit rights-clearance attestation in the ingest request/task and validate YouTube URLs by parsed HTTPS hostname, route, credentials, port, and video-ID shape; reject attacker-controlled hosts that merely contain an ID.
- [x] Canonicalize web-result domains from parsed HTTP(S) URLs; reject deceptive userinfo, unsupported schemes, malformed ports, and nonstandard ports before domain allowlist comparisons.
- [x] Preserve Hindi/Telugu/Tamil characters in web-search queries and source snippets while removing control/surrogate and unsafe formatting controls; retain ZWNJ/ZWJ used by Indic shaping.
- [x] Remove raw URL, provider exception and private-memory exception details from the reviewed cache, ingestion, memory-service, consent-gate, and outbox log paths.
- [x] Add/adjust regression tests for truthful ingestion-unavailable behavior, explicit rights, hostile YouTube hosts, URL authority/scheme bypasses, multilingual preservation, and all-tenant canonical-vector deletion contract.
- [x] Align fallback-copy tests with the actual registry-driven, evidence-honest response.

### Still required before any production-readiness claim

- [ ] Execute the modified Python test files and migration tests in a clean checkout; no tests have been executed from this environment.
- [ ] Build and run the target Docker Compose stack with local test credentials and real mocked/isolated services; no Docker execution occurred here.
- [ ] Run staging acceptance tests against authorized Supabase, Qdrant and Memgraph/Neo4j for tenant isolation, revocation races, retries, cross-store deletion, consent ledger behavior, and account switching.
- [ ] Confirm grant + RLS + trigger outcomes for each exposed memory table with supabase test db. Supabase's official guidance explicitly requires grants and policies together and calls for allow/deny tests per role/operation: https://supabase.com/docs/guides/database/postgres/row-level-security.
- [ ] Test actual outbound-fetch behavior, redirects, IPv4/IPv6 resolution and DNS-rebinding protections end to end. OWASP notes that domain allowlisting alone does not prevent DNS rebinding; destination validation must be enforced at connection time: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html.
- [ ] Finish reviewed multilingual/routing/crisis test matrices with human labels and clinical review; regex and unit tests alone are not proof of crisis recall.
- [ ] Implement the real first-person ingestion path and only reopen the 202 acceptance path when a source can be legally ingested, transcribed, attributed, clip-validated, hashed, indexed, and queried with verified provenance.
- [ ] Gather measured stage timings and warm/cold p50/p95/p99, TTFT, route precision/recall, grounding/attribution metrics, error rates and per-request cost from staging. No performance figures are claimed here.
- [ ] Close existing unresolved review threads and review all changed files from the final commit before merging.

Do not mark these remaining items complete based only on source inspection or green checks.

## Follow-up audit — 2026-10-22: tenant-scoped KG + agentic quality harness

### Committed code (must still pass the latest CI)
- [x] Personal-KG cache now keys on tenant, user, view, limit and SHA-256 of the full normalized query; cache responses are defensive copies with bounded eviction.
- [x] Private Neo4j traversals use the tenant in graph patterns/parameters. The HTTP routes now set TenantContext from the authenticated user for /memory/knowledge-graph, graph export and /kg/personal-subgraph, instead of relying on ambient request state.
- [x] Lexical associations are labelled MENTIONS_CONCEPT, not RELATES_TO or REFERENCES; an inferred mention is not a persisted semantic fact. Missing state categories are no longer replaced by a fabricated Neutral state.
- [x] Added fake-driver tests for two-tenant cache isolation, cache defensive-copy behavior, full-query cache keys, inferred-edge labelling and request-to-service tenant propagation. No live Neo4j/Qdrant/Supabase data was read or mutated by these tests.
- [ ] Execute the new tests on the current branch SHA. Source edits alone are not a pass.
- [ ] Read-only staging verification: confirm existing production Neo4j User and GlobalMemory nodes have tenant properties consistent with this new scoped query. Do not backfill graph data until dry run, snapshot and explicit approval.

### The answer engine’s evidence contract
The LLM is the coordinator/answer composer, **not the source of truth** for teaching content. Required request flow:

high-recall crisis + security precheck → cheap deterministic shortcuts → structured domain routing → selected evidence lane → answer composition → claim/source verification → response + provenance

- **Verbatim teacher request:** retrieve approved rights-cleared clips; verify speaker, exact quote, clip/time boundary, content hash and corpus version. If evidence is missing or ambiguous, abstain honestly; never paraphrase and present it as a direct quote.
- **Teaching explanation:** Qdrant hybrid retrieval (dense + lexical/BM25, reranking as justified by eval) and OKF-approved evidence produce a grounded synthesis. Memgraph/Neo4j can disambiguate entities and select multi-hop source records; graph paths are retrieval evidence, never substitute wording for the original source.
- **General question:** use a neutral general-assistant persona; do not inject the teaching corpus just because a spiritual keyword appears incidentally. Stable facts may use general knowledge with uncertainty; current facts use allowlisted live research. If no source exists, do not fabricate a citation or claim the answer is verified.
- **Personal follow-up:** include only relevant, consent-allowed memory for the authenticated user and tenant. An inferred graph edge is not a saved personal fact until the user confirms it.
- **Distress/safety:** deterministic multilingual pre-screen and dedicated crisis path stay ahead of general routing and shared-answer caches; Jev/LLM may supplement only after reviewed false-negative/false-positive evaluation, never replace the safety gate.

### Teacher names and identity: still not fully scalable
The code has an initial configuration-backed registry (backend/services/guru_registry.py + backend/config/gurus.yaml), but there are still literal teacher names and aliases in prompts, regex/domain routing and presentation logic. That can drift as new teachers are added and can falsely trigger first-person mode when a user merely mentions a name. Consolidate canonical ID, display name, multilingual aliases, verified source-speaker labels, attribution rules and permitted quote modes into one versioned registry consumed by router, prompts, ingestion, Qdrant metadata, KG entities, API schemas and UI. Add a test-only extra teacher to verify scaling. Never infer who spoke from question wording alone.

### Agentic quality harness (design to implement, not a claim that subagents ran)
Use a controlled, reproducible harness rather than unrestricted self-modification:
1. **Initializer/planner:** read tracked repo instructions, current plans, ownership/coordination rules and CI; write a task DAG, risk tier, acceptance contract, file ownership, test plan, rollback scope and handoff note.
2. **Focused builder:** one bounded task and file set at a time; do not edit another session's lane without coordination.
3. **Independent read-only verifier:** check types/schema/security boundaries, targeted unit tests and source-to-output provenance.
4. **Fresh-context reviewer:** independently inspect the diff and logs against the acceptance contract; do not trust the builder's summary.
5. **Core Contract Pack after every task:** tenant isolation/RLS, consent and revoke races, exact quote and speaker identity, rights/hash/time boundary, no fabricated citations, crisis preemption, cache separation, deletion fan-out and API/schema compatibility.
6. Limit repair attempts to three per task; each retry requires new evidence or a changed approach. If a task breaks the contract pack, revert only that task. Publish PASS_MEASURED, FAIL, MEASURED_NOT_ADOPTED, or BLOCKED_HUMAN. Never mark clinician, native-language, rights, legal/DPDP or production-credential gates complete by inference.
7. Use least-privilege tools, read-only service access by default, and explicit approval + dry run + snapshot + rollback for any production mutation, deploy/restart, credential change or graph/vector write. Retrieved web pages, KG nodes, memory and inter-agent messages are untrusted data, not instructions.

This is grounded in published harness patterns, not a guarantee of better product performance: [Anthropic's planner/generator/evaluator harness (Mar 24, 2026)](https://www.anthropic.com/engineering/harness-design-long-running-apps), [effective harnesses for long-running agents (Nov 26, 2025)](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents), and [OWASP Top 10 for Agentic Applications](https://genai.owasp.org/2025/12/09/owasp-genai-security-project-releases-top-10-risks-and-mitigations-for-agentic-ai-security/). No subagent-launch tool was available in this session, so this documents the design; it does not claim subagents actually ran.

### Frozen evaluation and performance scorecard
Version and freeze a human-reviewed test set with separate dev/test splits before tuning. Cover exact quotes, on-topic teaching, general facts, coding, current research, logistics, guided practice, personal memory/follow-up, explicit remember/forget, crisis and ambiguous distress, negation/quoted mentions/sarcasm, multi-intent, Hindi/Telugu/Tamil/code-switching/typos, prompt injection, cross-tenant attempts, empty retrieval and provider/data-store outages.

Report, by class and language: confusion matrix; precision/recall; confidence calibration/ECE; crisis recall and false negatives; false-positive rate; exact quote/speaker attribution error; retrieval Recall@k/MRR/nDCG; citation precision/recall and support rate; correct abstention vs false refusal; personal-memory useful-recall and wrong-memory rate; cross-user leakage; retries/timeouts/cancellations; cost per request. Jev must be compared to the local/semantic/router baseline on the same frozen set; do not assume a vendor probability is calibrated for this product.

Trace admission, history, consent/memory, Jev/local routing, embeddings, Qdrant, Memgraph/OKF, reranking, generation, verification, web and TTFT. Measure warm/cold p50/p95/p99 by route and cache hit/miss; run normal concurrency 20 separately from controlled concurrency-50 backpressure. OpenAI's latency guidance prioritizes fewer sequential calls, parallelizing independent work, streaming and deterministic shortcuts ([latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization)). Anthropic reports 49% fewer retrieval failures with contextual retrieval, and 67% with reranking in its own experiments; treat those as hypotheses to measure on this corpus, not promised uplift ([contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval)). LangGraph distinguishes thread-scoped continuity from cross-thread long-term memory ([persistence](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/persistence.mdx)). Use an in-repo, versioned eval harness; keep external eval services optional ([OpenAI evals guide](https://developers.openai.com/api/docs/guides/evals)).

### Remaining release blockers
- [ ] Re-check CI results for the latest branch SHA. At the previous reviewed SHA d450ac1836, security audit passed and Golden Eval passed; backend/frontend/pre-commit, RAGAS, migration apply/revert, pre-launch and attribution checks were still in progress. A cancelled run is not a pass.
- [ ] Execute the KG tests and migration tests in a clean checkout; repair failures without weakening RLS, consent checks or rights gates.
- [ ] Fix remaining Ruff/test-discovery/Supabase CLI problems from exact logs; preserve substantive tests while fixing missing ingestion-module packaging.
- [ ] Audit all remaining teacher-name literals and the admin/demo graph fallback; ensure unavailable production dependencies are never represented as live verified data.
- [ ] Implement the real first-person ingestion path; until then the endpoint must remain honestly unavailable/503 rather than returning false success.
- [ ] Run Docker Compose query matrix + traces, authorized staging checks for consent/revocation, tenant isolation, cross-store deletion, rights/speaker/time/hash, retries/outages, backup restore, account switching and crisis continuity. No Docker or live-service test was performed from this connector session.
- [ ] Complete clinician/native-speaker/rights/privacy review; collect actual warm/cold p50/p95/p99, TTFT, answer grounding, crisis recall, route confusion matrix and cost. Do not claim production-ready until CI is green and these artifacts exist.

**Current session limitation:** GitHub source inspection/edits and Actions status were available, but no local shell/Docker/subagent launcher or owner-managed production credentials were available here.
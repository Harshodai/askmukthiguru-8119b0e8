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

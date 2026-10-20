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

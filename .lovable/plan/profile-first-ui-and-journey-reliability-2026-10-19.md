# Profile-first UI and Journey Reliability

## Result

A calmer signed-in Profile, predictable Chat returns, reliable saved notes, and honest service status across user and admin screens on phone, tablet, and web. Keep the existing Golden Hour identity and four Profile destinations; remove clutter instead of adding features.

## 1. Rework signed-in Profile first

- Replace the cramped, stacked presentation with an unframed identity header, restrained metrics, and clearly separated sections. Use available width on desktop; stack naturally on phones.
- Keep Journey, Personalise, Memory, and Settings discoverable with accessible touch targets and long-label handling.
- Reduce competing practice charts and repeated actions; prioritize recent conversations and one next practice.
- Put one shared Save/status action on both editable tabs. Preserve drafts during theme/avatar updates; distinguish device saving from confirmed cloud saving.
- Preserve the selected tab, security link, onboarding state, and original Chat conversation when switching tabs, reloading, or returning.

## 2. Complete the seeker journey

- First successful sign-in → language choice → Chat; personalization stays optional. Persist language/completion through existing profile and authenticated metadata paths.
- Preserve 18+ confirmation, email confirmation, MFA, native callbacks, and duplicate Google redirect protection.
- Handle provider callback errors truthfully, with retry/email recovery; do not claim Google configuration is verified from source alone.
- Use existing Supabase Notes for Chat note saving and expose those notes in Profile Memory. Never announce a successful save after a failed write.
- Remove fabricated notebook fallback content; provide empty, unavailable, and retry states instead.

## 3. Harden admin and shared screens

- Trace missing guru teachings end to end: Chat configuration → request transport → available teaching service, and admin content → actual source store. Repair confirmed wiring defects without substituting generated or sample teachings for the teachers’ recordings.
- Distinguish an unwired connection from the deliberately stopped Railway service. Configure only an available, authorized destination; report missing infrastructure or credentials rather than silently routing to production.
- Restore transparent golden particles rising bottom to top using the existing shared animation. Keep them behind content, lightweight on phones, noninteractive, and disabled for reduced motion.
- Preserve original service errors instead of replacing them with mock-disabled messages. Bound waiting states and distinguish unavailable, expired session, and denied access.
- Keep admin verification fail-closed, including failed role/MFA checks. Add retry/sign-out recovery rather than indefinite loading.
- Replace unconditional “Real-time” claims with evidence-backed status; distinguish demo/stale data from live data.
- Make the admin date controls fit small screens and reuse the accessible drawer primitive for keyboard focus, Escape, and focus restoration.
- Sweep all configured user/admin destinations for duplicated controls, broken links, confusing return paths, overlaps, and outage handling; fix verified issues rather than speculative redesigns.

## 4. Verification and limits

- Run focused regression tests for tab/return preservation, draft saving, onboarding language, note failures, admin errors, and access gates.
- Exercise public routes and available interactions at phone, tablet, and desktop widths, plus reduced motion and keyboard navigation.
- Test signed-in layouts using isolated test fixtures where necessary, explicitly separate from live account evidence.
- Initial public sweep: seven routes at three widths, no page crashes or document overflow. Signed-in Profile redirects to Auth; authenticated admin screens were not exercised.
- External Supabase is unmanaged here: live Google completion, authenticated cloud readback, and MFA admin journeys cannot be verified through a managed session. Report those limits; never bypass access controls.
- Railway stays off. No deployment, service activation, corpus/model changes, or unsupported claim that the entire backend is healthy. Native real-device checks remain distinct from browser viewport checks.
- Production readiness is an evidence-based verdict, not a styling milestone: include teaching/citation readback, persistence, access-control checks, unavailable-service handling, and explicit human/credential/infrastructure gates. Never declare all product features working after only a public-route sweep.

## Technical approach

Reuse existing React/shadcn controls, semantic tokens, navigation helpers, profile storage, Notes panel, and tests. Correct Profile query updates without erasing unrelated parameters/hash. Use the existing theme/profile persistence contract consistently. Keep changes frontend-first; inspect client/server boundaries, but do not introduce services, dependencies, schema changes, or new AI calls for visual work.

## 5. Local first-person integration and production gate - this is already present, but you need to check thoroughly the flow and everything and making sure its top notch

- Preserve the current teacher-video serving approach: question → safety checks → approved first-person Qdrant collection → integrity/speaker/relevance gates → exact transcript, attribution, timestamped video, and truthful related-answer label. Ranking/answerability dependencies may run, but must not generate the teacher’s response text.
- Keep OKF as routing/reflection context only. Never render OKF summaries as verbatim speech or add them to teacher citations. Do not rebuild, migrate, or expose local stores without a separate dry-run, snapshot, and approval.
- Audit the actual local collection pointer, embedding dimension pair, named vectors, rights filters, exact-cache revalidation, and transcript hashes through authorized read-only checks. Historical documentation counts and latency are not current runtime proof.
- Audit the full frontend/backend contract: signed anonymous/session identity, JSON and stream events, public metadata allowlist, error/abstention distinctions, source mapping, exact playback bounds, unavailable-player fallback, notes/history readback, and admin AAL2 checks.
- Current sandbox probe: localhost:8000 health and localhost:6333 health are unreachable. This does not show that the owner’s Mac stores are down; they are outside this sandbox. A hosted website cannot rely on visitors reaching the owner’s localhost.
- First restore a verified local journey on the owner-accessible stack. For production, prepare one approved always-reachable HTTPS API with private Qdrant/Redis/graph connections and packaged approved OKF artifacts. Do not point visitors directly at Qdrant or silently enable Railway.
- Prepare a hosting recommendation and rollback/data-transfer checklist before any service activation. Use a secured temporary connection only for authorized testing, not as an assumed production availability solution. Hosting, spend, and data transfer require a separate owner decision.
- Release evidence: real teacher question and exact clip playback; out-of-corpus abstention; crisis preemption; quoted text never translated; verified speaker status; tenant/rights isolation; fresh persisted user journey; admin denied/expired/MFA paths; network interruption and retries; measured warm/cold p95/p99, load, costs, and restored backup.
- Human gates remain explicit: rights sign-off, native-speaker/clinical review, genuine calibration labels before any direct-answer precision claim, and real Android/iOS device verification. Keep measured current first-person latency separate from older sub-second aspirations.

## Research supporting the release checklist - add more things 

- Qdrant self-hosting needs explicit authentication, private network binding, and TLS; keep database credentials and raw ports off the browser: [Qdrant security](https://qdrant.tech/documentation/security/).
- Size and validate deployment against actual collection/load measurements rather than adding distributed infrastructure speculatively: [Qdrant production checklist](https://qdrant.tech/documentation/production-checklist/).
- Google/email recovery depends on configured production Site URL and allowed callback URLs, not only UI code: [Supabase redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls).
- Native authentication must return into the registered app scheme and inspect session-exchange errors: [Supabase native deep linking](https://supabase.com/docs/guides/auth/native-mobile-deep-linking).
- This project uses external Supabase; existing stores are not automatically transferred to Lovable hosting. The Python teaching service requires an independently reachable deployment; frontend publishing alone does not deploy the local Qdrant/OKF pipeline.

## 6. A useful daily companion, not another busy dashboard

- Keep one simple loop: optional state check-in → relevant recorded teaching → one existing practice → optional saved reflection → resume next visit. Reuse Chat, practices, Notes, and Profile instead of introducing another destination.
- Let seekers describe their own current state, skip the check-in, or ask directly. Show when a state was recorded; never claim the app knows their permanent spiritual state or diagnoses their mental health.
- Place one next step in Profile Journey and one compact return/resume affordance in Chat. Do not stack introductory panels, repeated recommendations, tours, or competing calls to action.
- Personal Knowledge Graph uses only the signed-in seeker’s consented saved reflections, teaching references, and confirmed relationships. Selecting a node opens its original note/teaching and preserves the way back; graph is optional, accessible as a list, and never substitutes for a clear journey.
- Distinguish seeker-reported states from suggested concepts and inferred links. Require confirmation before storing inferred personal relationships. No fabricated memories, permanent “suffering” labels, or clinical claims.
- Reuse existing reminders only with permission, straightforward pause/off controls, and no guilt for missed days. Measure meaningful practice/reflection and successful return, not time spent or pressured streaks.
- Compare useful patterns from ChatGPT/Claude/Lovable (conversation continuity, predictable back paths, progressive disclosure) and AskSadhguru/Calm (short practices and daily reflection), without cloning all their controls or assuming every feature improves this product.
- Ship this loop only after teaching delivery, account persistence, and return navigation work. Do not expand features to compensate for unavailable core services.

### Daily journey research

- Calm separates user-entered check-ins and editable history from daily meditation: [Calm check-ins](https://support.calm.com/hc/en-us/articles/9699990936731-How-to-Use-Check-Ins-Mood-Sleep-Gratitude-Tracker) and [Calm Dailies](https://support.calm.com/hc/en-us/articles/115005140414-What-are-the-Calm-Dailies-Daily-Meditations-Movement).
- Ask Sadhguru’s published product combines recorded wisdom with a short daily practice; borrow the focused loop, not claims of equivalent quality or outcomes: [Miracle of Mind](https://isha.sadhguru.org/us/en/miracle-of-mind).

## Delivery order

1. Profile layout, navigation, and editable-settings reliability.
2. Language onboarding, note saving/readback, and Google recovery.
3. Local first-person contract/readiness audit, teaching/admin source wiring, restored brand animation, admin resilience, and route/device sweep.
4. Minimal opt-in daily loop and personal-graph continuity using real user data.
5. Focused tests, browser evidence, production recommendation, and explicit remaining live-service/human blockers.
6. make sure even in light mode and in any mode, this is truly spiritual
7. ensure you understand the backend and everything in this repo and understand, right now whenever we get a question, we are using qdrant + OKF wiring as of now to generate the correct answer -> you need to check and fix all issues 
8. The User created Knowledge Graph should be top notch, this is mainly like based on their conversations and interactions, our agent will collect memories and stores them just like a teacher understands about their student. make this much better and also make the user experience top notch and world class rather than dummy like.

## 7. PR #76 continuation audit — 2026-10-21

### Verified workflow evidence

- [x] PR #76 head and changed files reviewed; audit posted to the PR conversation.
- [x] Root roadmap updated with explicit status and hard release invariants.
- [ ] Backend `Lint & Test` is blocked at Ruff; listed findings are in the PR audit comment. Pytest, Bandit, typing and tier-3 safety checks in that job did not execute after Ruff failed.
- [ ] Production Readiness backend regression job fails collection: three ingestion tests import files/modules absent from the checkout (`scripts/ingestion/1_fetch_transcripts_local.py`, `scripts.ingestion.corpus_engine`). Diagnose source/test packaging; preserve substantive test coverage.
- [ ] Pre-launch gate did not execute because Supabase CLI setup failed. Browser device-matrix jobs passed but do not cover authenticated backend persistence.
- [x] CodeQL, Main Hard Gates, Golden Eval, Security Audit, RAGAS, Golden-25 attribution, migration revert, CodeRabbit and Vercel checks were green at the reviewed head; re-check after each new commit.

### 8. Critical backend correctness gaps to resolve

- [ ] **First-person truth boundary:** audit every fallback, not only the main chat graph. In `backend/app/api/chat.py`, `/breath-teaching/{technique_id}` calls the LLM without retrieved evidence after RAG failure and has a hardcoded fallback attributed to Sri Preethaji/Sri Krishnaji, including a clinical-sounding amygdala claim. Remove unsupported claims; if verified source evidence is unavailable, return a truthful unavailable/abstention state rather than labeling generation as teacher teaching.
- [ ] **Mock graph is not runtime truth:** `/admin/concept-graph` returns hardcoded nodes/edges when Memgraph/Neo4j fails/unavailable. In production, return an explicit unavailable status and observability; if a demo fixture remains for development, mark it as demo-only in the API/UI.
- [ ] Audit all other fallback paths for invented content, fake citations, teacher attribution leaks, failed-rights checks, source metadata loss, quote translation, or stale cache results.
- [ ] Assess the newly broadened web-search allowlist: ensure each domain is justified by query class, official-source preference, domain parsing/redirect validation, injection boundaries, bounded timeouts, result freshness and “unverified” copy. Domain allowlisting alone does not ensure every page is authoritative for every topic.

### 9. Router and crisis evaluation contract

- [ ] Keep Jev as a candidate structured intent router, not as a universal safety gate. Measure request overhead, p50/p95, route accuracy, confidence calibration, outage handling and false-route costs against local classifier and deterministic baseline.
- [ ] Build a reviewed eval set for teaching/general/live research/logistics/casual/guided-practice/personal-memory/distress and multi-intent. Include incidental teacher names/terms, ambiguous questions, pronouns/follow-ups, negation, quoted text, sarcasm, code-mixed and multilingual inputs, typos, adversarial input and long context.
- [ ] Report confusion matrix and class-wise precision/recall, especially crisis false negatives; use human-reviewed labels. Preserve high-recall deterministic prescreen and dedicated crisis behavior ahead of general routing. LLM/semantic escalation is supplemental and must remain disabled until clinical/safety sign-off and multilingual testing are complete.
- [ ] Maintain multi-turn distress carryover without storing permanent mental-health labels. Test neutral-looking follow-ups after distress, explicit current intent, ambiguous despair, third-party concern, educational/quoted mentions and false positives.
- [ ] Confirm localized support resources and emergency wording through a current official resource list; the PR audit cites India's official Tele-MANAS 14416 resource.

### 10. Personal Knowledge Graph and memory quality

- [ ] End-to-end review: authenticated user + tenant context → explicit consent receipt → conversation extraction → PII/policy filter → dedupe/conflict resolution → provenance/confidence → persistence → retrieval → user-visible inspect/edit/delete/forget → deletion propagation to vector/graph/cache copies.
- [ ] Distinguish direct user statements, confirmed facts, inferred candidate edges and temporary contextual observations. Require confirmation for inferred personal relationships; never silently store an inference as fact or use “teacher understands student” framing to justify surveillance or overconfident profiling.
- [ ] Verify namespace/tenant isolation for graph and vector queries; test account switching, revoked consent, expired/missing sessions, concurrent writes, retry idempotency and profile-service unavailable modes.
- [ ] Ensure personal graph is optional, accessible as a list, source-linked to original conversation/note/teaching, and does not replace a verified first-person answer source.

### 11. Latency/observability and Docker verification

- [ ] Add trace spans for request admission, history fetch, consent/memory, Jev, embedding, Qdrant, Memgraph/OKF, rerank, generation, verification, web retrieval, cache and streaming. Capture timeouts, retries, cancellations, result count and cache hit/miss without logging sensitive prompt contents.
- [ ] Measure warm/cold p50/p95/p99, time-to-first-token, total response time, error and abstention rates, cost/request and resource usage for teaching cache hit/miss, general fact, coding, current web, personal follow-up and distress turns.
- [ ] Reduce serial round trips only where calls are independent; use deadlines/cancellation and bounded concurrency, not a collection of nested timeouts that can exceed the product budget.
- [ ] Build/rebuild the latest PR head in Docker Compose with the required local services and safe test-only credentials. Run one query from every route class and print actual answers + provenance + per-stage durations.
- [ ] Run concurrency 20 without expected load shedding separately from the explicit concurrency-50 admission/backpressure test. Include soak, dependency-down, timeout, retry, stream disconnect and warm/cold cache cases.
- [ ] Run approved staging tests with real authorized Supabase, Qdrant and Memgraph/OKF, including source clip/time bounds, rights/speaker verification, notes/history readback, consent revocation, deletion propagation, cross-tenant denial and admin AAL2/MFA/expired-session paths.
- [ ] Publish a machine-readable report with commit SHA, environment, dataset version, provider/model IDs (no keys), p50/p95/p99, TTFT, route confusion matrix, first-person attribution/grounding metrics, crisis recall, privacy tests, cost estimates, failures and limitations.

### 12. Evidence-based release gate

No production-readiness claim until: CI is green; ingestion test discovery is explained and fixed; pre-launch integration executed; first-person attribution/rights/quote gates pass; crisis eval has clinical review; memory consent and tenant isolation pass; external service dependencies are reachable through approved HTTPS/private links; backups restore in a test; and latency/cost SLOs are measured against agreed targets. Railway remains off. Do not claim the current environment executed Docker or live-service tests: the GitHub connector can inspect/edit repository content, but it cannot start the owner’s services or access unmanaged credentials.

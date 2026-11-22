# Live Product Release Remediation Plan

**Status:** Active — implementation is not authorized as complete until every release gate below passes in the deployed public experience.

**Origin:** Live persona audit of `https://askmukthiguru.lovable.app/` on 2026-11-22.

## Goal

Make AskMukthiGuru safe, honest, private, accessible, source-grounded, and usable enough for a public release. The release decision is **NO-GO** until the P0 and P1 gates below pass with recorded evidence.

## Scope and non-negotiables

- Repair the observed product, not merely its labels.
- Preserve the repository's serving, first-person, ingestion, rights, and test-telemetry invariants. In particular, this work must not enable first-person public serving, alter Qdrant aliases, or create test writes to live telemetry.
- Do not replace an evidence-backed abstention with generated spiritual advice.
- A privacy claim is true only when browser storage, API persistence, server logs/telemetry, and visible history agree.
- No production deployment occurs as part of a code change. Deployment is a separately approved release action after gates pass.

## Audit boundary: what is proven, and what remains unproven

The live audit directly exercised anonymous desktop/mobile flows, temporary chat, chat answers, source panels, practices, guides, Trust/Privacy/Terms pages, and the sign-in surface. It did **not** prove the following, so none may be inferred safe or launch-ready:

- actual account creation, sign-in, password reset, Google OAuth completion, session renewal, sign-out, and cross-device behavior;
- authenticated profile, memory, notebook, reflection, data-export, account-deletion, and retention/deletion workflows;
- server/database persistence, provider retention, analytics/telemetry, audit logging, and cross-user authorization for the temporary-chat leak;
- media playback, source-clip seek-to-time behavior, TTS/STT permissions/failure handling, keyboard media controls, and caption/transcript alternatives;
- real-device touch behavior, screen-reader output, reduced-motion/high-contrast behavior, Safari/Firefox support, and slow/offline network recovery;
- API authorization, RLS, CSRF/session security, CSP, cookies, dependency vulnerabilities, abuse/rate-limit behavior, and load/cost controls;
- email subscription consent, unsubscribe/erasure, operational mailbox handling, transactional delivery, and legal/rights review;
- all public content, every teaching claim, every locale, all provider outages, and accuracy of source-rights assertions.

These are not optional “nice to have” tests. Workstream 7 makes them explicit release gates. The plan must be amended with results, not assumptions.

## Live evidence that drives this plan

| Priority | Observed behavior | Consequence | Required outcome |
|---|---|---|---|
| P0 | A chat labelled “Temporary chat: not saved to chat history” left its generated Hindi title in normal sidebar history after close and reload. | Directly false privacy promise and local disclosure risk. | No title, preview, message, summary, memory, cache, or server-side conversation record may survive under the temporary-chat claim. |
| P1 | Ordinary work stress and relationship betrayal were classified as `Safety support`, suppressing requested teachings and adding crisis contacts. | False crisis escalation, stigma, product failure. | Crisis-only routing is limited to calibrated acute-risk signals; ordinary hardship gets grounded/reflective help. |
| P1 | Follow-up retrieval showed unrelated, unverified passages including relationship-violence content for work conflict, then abstained. | Unsafe relevance leakage and confusing provenance. | Abstentions show no unrelated/weak source cards; retrieved sources must meet direct-relevance and verification criteria. |
| P1 | Public Spirit Guides page presents ancestors, animal presences, dreams, and inner guides as assertions without provenance. | Contradicts teaching-grounded/non-invented positioning. | Remove, quarantine, or evidence-label every claim before public release. |
| P1 | Temporary-chat copy says “Nothing from this session will be saved”; policy describes server/provider processing and redacted quality/safety retention. | Privacy disclosure contradiction. | One exact retention statement across onboarding, chat, policy, source code, and operational controls. |
| P1 | Source-linked answer can be strong, but Trust page promises timestamped quoted moments while visible links were general video URLs. | Overstated provenance. | Every verified quote has speaker, source, exact span, and timestamp; otherwise use the weaker label. |
| P1 | Hindi response used poor grammar, English chrome, and claimed a practice under `No direct discourse match`. | Not production-ready multilingual UX; misleading grounding. | Define supported locales and quality bars; unsupported languages use explicit, safe fallback. |
| P2 | Medical response correctly refused replacement of therapy/medication but immediately showed a practice CTA. | Mixed safety signal. | Suppress practice CTA unless the user explicitly requests complementary practice after the boundary message. |
| P2 | Prompt injection did not leak internal instructions, but invoked slow no-source retrieval and an anthropomorphic response. | Wasteful, odd, and exposes product posture. | Fast deterministic refusal before retrieval; no persona theatre. |
| P2 | Practices catalogue/detail disagree about today’s teaching and anonymous availability. | Broken first-time practice journey. | One source of truth; clear anonymous/public vs sign-in-only states before a user starts. |
| P2 | Custom preference/account controls lack reliable semantic roles; source cards truncate on mobile; auth/legal routes show blank or stale transitions. | Accessibility and trust erosion. | Semantic controls, responsive provenance cards, and route loading states. |

## Workstream 0 — Immediate containment (P0/P1)

### 0.1 Temporary-chat containment

1. Feature-flag or remove the current incognito entry point until the data-lifecycle audit passes. If it remains visible before repair, disclose the actual retention instead of saying private/not saved.
2. Audit all write/read planes for a temporary session:
   - frontend conversation list/title/preview persistence in `src/lib/chatStorage.ts`;
   - conversation construction and streamed-response handling in `src/components/chat/ChatInterface.tsx`;
   - header/sidebar rendering in `ChatHeader.tsx`, `DesktopSidebar.tsx`, and `MobileConversationSheet.tsx`;
   - browser storage, in-memory drafts, request summaries, analytics, and export state;
   - backend request, identity, cache, memory, telemetry, and conversation writes in `backend/app/api/chat.py`, `backend/app/chat_engine.py`, `backend/app/orchestrator_utils.py`, and `backend/services/auth_service.py`.
3. Make `incognito=true` a single immutable conversation property from construction to destruction. Any persistence helper must reject it before computing a title or preview.
4. Close must erase temporary state, including draft, title, preview, messages, navigation selection, and cached response state. Existing leaked records need a scoped migration once their storage plane is confirmed.
5. If any compliance/audit retention is legally required, keep it outside user history, minimize it, set a bounded retention period, and disclose it precisely.

### 0.2 Unsafe/public content containment

1. Remove `/guides/spirit-guides` from public navigation or rewrite it against an approved, source-backed content register.
2. Audit public pages for assertions presented as teachings. Every claim must be either verbatim/source-linked, labelled summary, or removed.
3. Replace unsupported trust claims before the underlying capability ships. Specifically, do not claim quote-moment deep links until the UI verifies timestamped source coordinates.

**Exit gate:** Product owner signs off on the corrected temporary-chat disclosure and public content inventory; automated and live proof below pass.

## Workstream 1 — Privacy and temporary-chat repair

### Implementation

1. Trace the client write path from response arrival through `chatStorage` and the conversation sidebar. Fix the code path that creates/persists the temporary title after close.
2. Add an explicit persistence policy object rather than scattered `_incognito` conditionals. It must govern history, title, preview, summary, browser storage, export, memories, analytics, and network payload enrichment.
3. Enforce the same policy server-side. Incognito must bypass durable history, memory, shared/exact cache, personalization, and nonessential telemetry; do not trust the frontend flag alone.
4. Add a privacy API contract test that fails when a temporary request produces durable write calls.
5. Align `PrivacyPage.tsx`, `ChatHeader.tsx`, onboarding, and temporary-chat welcome copy with the proven policy.

### Tests and acceptance

- Create temporary chat → send message → close → reload → open a fresh tab → sidebar/search/export/profile/memory all show no title or content.
- Inspect client storage and API payloads without collecting credentials; no temporary content or derived title persists.
- Verify server test doubles receive no durable conversation/memory/cache/telemetry writes.
- Ensure a non-temporary conversation still persists correctly.
- Add regressions covering close-before-response, stream interruption, navigation during response, and browser reload.

## Workstream 2 — Safety routing calibration

### Implementation

1. Define three explicit dispositions: `acute_crisis`, `elevated_safety_support`, and `ordinary_hardship`.
2. Keep deterministic self-harm/imminent-danger handling first in the input pipeline. Do not weaken existing crisis gates.
3. Add calibrated negative cases: work stress, betrayal, anger, grief, relationship conflict, and requests for short spiritual practices.
4. For elevated safety support, explain boundaries and offer appropriate resources while preserving a safe answer path when possible.
5. For acute crisis, serve no doctrine, use country-appropriate one-tap `tel:` actions, include immediate-safety language, and avoid optional practice/share CTAs.
6. Ensure medical boundary answers explicitly reject substitution; hide practice continuation until a clearly optional second step.

### Likely implementation locations

- `backend/app/intake/safety_kernel.py`
- `backend/app/pipeline/stages/guardrail_stage.py`
- `backend/app/route_taxonomy.py`
- `backend/app/middleware/crisis_support_on_refusal.py`
- `src/components/chat/ChatMessage.tsx`

### Tests and acceptance

- Matrix-run the exact audited prompts in English and Hindi.
- Assert ordinary hardship never receives the acute crisis template.
- Assert explicit imminent self-harm receives no teaching text and has actionable emergency contacts.
- Human-review false-positive/false-negative outcomes before threshold changes are released.

## Workstream 3 — Grounding, provenance, and abstention contract

### Implementation

1. Define rendering modes that cannot be mixed:
   - **Verified teaching:** source, speaker, verbatim span, timestamp, and verification passed.
   - **Source-linked summary:** explicit summary wording and citations; no quotation styling unless words are exact.
   - **Abstained/reflective:** zero source cards unless a separately labelled, directly relevant optional reference is intentionally supported.
2. Enforce direct-relevance and source verification before displaying a source card. Reject semantically adjacent material (for example, violence content for workplace conflict).
3. Follow-ups reuse previously verified evidence first. New retrieval is allowed only for claims that need new support.
4. Map every displayed citation to original coordinates. If a timestamp/deep link is unavailable, downgrade the UI label and Trust-page claim.
5. Preserve honest negative statements such as “what this teaching does not establish,” but remove boilerplate unrelated to the current question.

### Tests and acceptance

- Golden cases: direct teaching, source-linked summary, no-match, follow-up, adversarial prompt, medical query, safety query, and Hindi query.
- No-match responses have no unverified source cards.
- Every verified citation opens the exact source coordinate.
- Retrieval relevance review catches relationship-violence/work-conflict mismatch.

## Workstream 4 — Multilingual, injection, and tone quality

### Implementation

1. Publish a supported-locale policy. Hindi is not supported until evaluated end-to-end; use a clear fallback rather than low-quality generated Hindi.
2. Localize chrome, source-state labels, safety copy, controls, and practice CTA language for each supported locale.
3. Require native-language review for grammar, cultural tone, medical/safety phrases, and source fidelity.
4. Add a deterministic prompt-injection refusal before expensive retrieval. It must neither reveal system context nor claim emotional perception or spiritual authority.
5. Remove unnecessary anthropomorphic phrases such as “I care deeply” and “I sense…” from refusal templates.

### Tests and acceptance

- Hindi and English scenario suites pass human-language review.
- Injection strings produce a fast refusal with no retrieved sources and no internal content.
- `No direct discourse match` can never accompany a claim that a teaching supplied the offered practice.

## Workstream 5 — UX, practice, and accessibility

### Implementation

1. Make the daily-teaching catalogue and `PracticeDetailPage.tsx` consume one availability/source state.
2. Decide and expose the anonymous contract before interaction: fully public practice, or a clear sign-in lock before the timer/check-in flow.
3. Make send idempotent and clear the composer after successful submission; preserve drafts only on explicit failure.
4. Replace custom interactive containers with semantic menuitems, radio groups, switches, labelled dialogs, and focus restoration.
5. Replace clipping source-card layouts with responsive stacked cards containing title, speaker, verification label, and source time.
6. Add route skeletons/loading states for auth/legal pages so URL/title/content never disagree in transition.

### Tests and acceptance

- Keyboard-only and screen-reader tests cover account menu, preferences, sources, practice timer, mobile drawer, and crisis controls.
- 390px viewport screenshots have no source-title truncation or hidden essential metadata.
- Practice catalogue/detail state is consistent for signed-out and signed-in users.

## Workstream 6 — Performance, observability, and release readiness

### Implementation

1. Instrument safe, privacy-respecting timings for route, retrieval, relevance, generation, and render stages. Never log temporary-chat content.
2. Replace internal “step X/8” details with truthful user-facing states and an accessible completion announcement.
3. Set measured latency SLOs after baseline collection; optimize the slowest stage without relaxing grounding/safety gates.
4. Add browser-console cleanliness checks and error monitoring that does not capture sensitive conversation text.

### Release evidence bundle

- Privacy lifecycle report for temporary chat.
- Safety matrix results plus human calibration review.
- Provenance/citation manifest with timestamp validation.
- Multilingual review packet.
- Accessibility report and desktop/mobile visual checks.
- Latency and console-error report.
- Explicit P0/P1 closure log and rollback plan.

## Workstream 7 — Remaining product-surface and operational release audit

### Authentication, account, and data-rights flows

1. Use isolated test accounts only; never use a personal account or production personal data.
2. Verify sign-up, sign-in, Google OAuth, reset, session expiry, sign-out, and cross-device revocation.
3. Verify profile, memory, notebooks, reflections, account export, account deletion, consent withdrawal, and unsubscribe/erasure flows with before/after evidence.
4. Prove row-level authorization and temporary-chat isolation with two test identities plus direct server-side test coverage.
5. Obtain an owner/legal decision for the privacy policy, retention schedule, provider disclosures, and rights claims; implementation cannot self-certify legal correctness.

### Platform, accessibility, and resilience

1. Test supported browser/device matrix on real or managed-device equivalents: current Chrome, Safari, Firefox, Android Chrome, and iOS Safari.
2. Test keyboard-only use, VoiceOver/NVDA-equivalent screen-reader output, zoom to 200%, reduced motion, high contrast, and narrow/mobile landscape layouts.
3. Test voice permission denial, no microphone, failed TTS, unavailable source video, slow network, offline transition, stream interruption, tab backgrounding, and resume behavior.
4. Verify source clips seek to the cited moment, expose transcript/caption alternatives, and fail honestly when playback is unavailable.

### Security, cost, and operations

1. Run the repository’s security/readiness checks in their approved environment: authz/RLS, CSP, dependency/vulnerability checks, secret exposure, rate limits, abuse resistance, and provider-budget safeguards.
2. Verify error tracking and analytics do not collect temporary-chat content, sensitive prompts, credentials, or source text beyond approved retention.
3. Exercise quota exhaustion, upstream provider failure, retrieval/Qdrant failure, Redis failure, and graceful-degradation paths. Each must present an accurate state, not invented guidance.
4. Run an approved load/concurrency test without using `incognito` as a cache-bypass substitute, because incognito is a privacy boundary.

### Content and compliance inventory

1. Inventory all public routes and every displayed teaching/assertion.
2. Verify rights status and source coordinates against the curated rights register; missing rights is exclusion, never a default approval.
3. Review all locales with a qualified native reviewer before marketing support for that locale.
4. Verify contact, crisis, email, and erasure links work in the intended country/region without representing a real user or calling emergency services.

**Exit gate:** A signed release checklist records pass/fail evidence for every item above, names an owner for each remaining external/legal decision, and marks untested surfaces NO-GO rather than silently excluding them.

## Workstream 8 — Faculty beta readiness (controlled release, not public launch)

“Faculty” is an internal, limited cohort of **teachers, volunteers, and reviewers**. They have higher expectations of accuracy, confidentiality, and accountability, but they are not automatically clinical staff, emergency responders, data administrators, or public endorsers. Role-specific permissions must be narrow and explicit.

### Role model

| Role | May do | Must not receive by default |
|---|---|---|
| Internal teacher | Review cited teaching accuracy, teaching fit, speaker/source attribution, and harmful spiritual framing. | End-user identity, private conversation corpus, operational logs, unredacted safety reports, or authority to change safety policy alone. |
| Internal reviewer | Score fixed evaluation packets for provenance, UX, safety, tone, and abstention quality; report defects. | Other reviewers’ private notes, user content outside the assigned packet, production exports, or implicit authority to approve public release. |
| Volunteer | Test assigned non-sensitive flows and submit structured usability feedback. | Private/temporary chat content, real user data, rights-restricted source material, admin controls, or any expectation to handle distress/emergency support. |

No role may use access to promise spiritual, medical, crisis, legal, or therapeutic support to end users. Teachers’ feedback is expert review of an artifact, not an endorsement of generated answers unless separately documented.

### Consent, authority, and content rights

1. Obtain written owner authorization defining what faculty may access, evaluate, download, quote, or share. Do not infer approval from a general willingness to review the product.
2. Confirm rights to every source, portrait, name, transcript, clip, and derived summary visible to the faculty cohort. Unverified material remains excluded.
3. Provide a faculty-specific participant notice: AI limitations, source/attribution model, privacy/retention, temporary-chat truth, permitted use, feedback handling, and emergency boundaries.
4. Do not represent faculty membership as endorsement of any generated response, doctrine summary, or product claim.

### Access control and data separation

1. Use a dedicated faculty role/cohort and isolated test accounts. No shared credentials and no personal end-user accounts.
2. Apply least privilege: faculty see only their permitted evaluation artifacts and never unrelated user conversations, personal memory, profile data, or raw operational logs.
3. Test invite, acceptance, revocation, expiry, role changes, logout, cross-device session invalidation, and access-denied behavior.
4. Do not expose a faculty review queue until its redaction, authorization, retention, and export rules are tested.
5. Make any faculty feedback flow explicit about whether it is attributable, anonymous, retained, and visible to product owners.
6. Give volunteers only synthetic, non-sensitive test scenarios. Never use volunteers as an informal crisis-response or content-moderation layer.

### Evaluation protocol

1. Provide a fixed, versioned evaluation packet containing representative grounded, abstained, safety, medical-boundary, multilingual, and failure cases.
2. Distinguish review of **factual/source accuracy**, **teaching fit**, **tone**, **safety**, and **product usability**; a positive answer in one category must not imply approval in another.
3. Require citations and original recordings for all teaching-evidence judgments. No reviewer is asked to certify a claim without coordinates.
4. Record reviewer identity/role only with their consent; preserve an immutable decision timestamp and the exact corpus/application version reviewed.
5. Define stop conditions: any unapproved attribution, privacy issue, safety failure, rights challenge, or severe hallucination pauses the beta and triggers incident review.
6. Route teaching-content disputes to designated internal teachers; route product/safety defects to the product incident owner. Neither group may silently override the other’s decision domain.

### Support, incident response, and communications

1. Name one product owner, one technical incident owner, one content/rights owner, and one escalation path before invitations go out.
2. Establish a support channel that is not positioned as emergency care. Faculty must know how to report a harmful answer, privacy leak, incorrect attribution, or access problem.
3. Prepare revocation and rollback procedures: disable the cohort, revoke sessions, suppress a problematic source/content item, preserve necessary evidence, and notify affected reviewers.
4. Prohibit redistribution of test credentials, screenshots containing user data, unverified answers, and source material outside the authorized cohort.

### Faculty beta exit gate

Faculty access is allowed only if all P0/P1 product gates are closed **and** the following evidence exists:

- documented owner authorization and rights inventory;
- role/isolation/access-revocation tests passed;
- a reviewed faculty notice and feedback consent flow;
- versioned evaluation packet and scoring rubric;
- incident owner roster and rehearsal of disable/revoke/rollback;
- no known temporary-chat privacy leak, unsafe source claim, or acute-safety routing defect;
- a time-bounded cohort, named purpose, participant cap, and explicit re-evaluation date.

Faculty beta success is not public-release approval. Public launch requires the full Workstreams 0–7 evidence bundle as well.

## Sequencing and completion definition

1. **Containment first:** Workstream 0 and the temporary-chat proof gate.
2. **Safety + privacy next:** Workstreams 1–2 can proceed in parallel only after code ownership is mapped; neither can be waived.
3. **Truthfulness before polish:** Workstream 3 precedes UX/performance optimization.
4. **Inclusive product quality:** Workstreams 4–5 follow the answer contract.
5. **Operational and cross-platform proof:** Workstream 7 validates all surfaces not covered by the original live audit.
6. **Controlled faculty beta:** Workstream 8 may begin only after P0/P1 closure and its own authorization/isolation/evaluation gates pass.
7. **Release evidence last:** Workstreams 6–8 verify the deployed candidate; no claim of readiness is made from unit tests alone.

The remediation is complete only when every acceptance item above is backed by current code, automated tests, and live browser evidence. Any failed P0/P1 item resets the release decision to NO-GO.

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

## Delivery order
1. Profile layout, navigation, and editable-settings reliability.
2. Language onboarding, note saving/readback, and Google recovery.
3. Teaching/admin source wiring, restored brand animation, admin resilience, and route/device sweep.
4. Focused tests, browser evidence, and explicit remaining live-service blockers.

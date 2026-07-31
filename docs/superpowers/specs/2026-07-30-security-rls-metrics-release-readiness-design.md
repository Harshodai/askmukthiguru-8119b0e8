# Security, RLS, Metrics Parity & Release Readiness Design

**Date:** 2026-07-30  
**Scope:** Product-hardening epic combining A/B approaches: extend existing AAL2/MFA Playwright regression tests, add an automated RLS cross-user access verifier, enable Supabase leaked-password protection, evaluate Lovable Cloud sync, and wire ruthless UI↔backend metrics plus suffering-state course assignment.

## 1. Goals

1. **AAL2/MFA cannot be bypassed.** Extend the existing Playwright spec so it proves that a forged/stale localStorage session is rejected, that the `/auth/mfa` route enforces a verified TOTP step-up, and that backend API calls with a JWT whose `aal` claim is not `aal2` are rejected.
2. **RLS blocks cross-user access.** Add a script and an E2E test that create two real Supabase users, seed rows as user A, and prove user B cannot read/update/delete them via the Data API.
3. **Resolve remaining security finding.** Enable Supabase's "Prevent the use of leaked passwords" setting and verify it (requires Pro+).
4. **Release-readiness document.** Produce a ruthlessly honest document listing what is ready to deploy and what is not, with go/no-go criteria.
5. **Lovable Cloud sync decision.** Document whether moving the frontend to Lovable Cloud and syncing backend data via edge functions is viable.
6. **Metrics parity.** Add a backend `/api/metrics` endpoint and a frontend `useMetrics` hook using a shared schema so every metric is computed identically.
7. **Suffering-state course assignment.** Have the backend detect suffering and persist a `recommended_course` / `assigned_course` record that the existing `HealingPathCard` consumes.

## 2. Non-Goals

- Do not replace the existing Supabase project with Lovable Cloud (research only).
- Do not rewrite the mobile app build.
- Do not add new LLM models or retrain embeddings.
- Do not create an admin OKF review queue (out of scope for this epic).

## 3. Architecture

### 3.1 AAL2/MFA Regression Tests

**Existing state:** `tests/e2e/security-aal2.spec.ts` already tests:
- Anonymous users cannot reach protected seeker/admin routes.
- A forged localStorage session cannot unlock `/chat` or `/admin`.
- The MFA challenge route exists.
- Source-level invariant that both guards call `getAuthenticatorAssuranceLevel` and redirect to `/auth/mfa`.

**Extensions:**
1. **Route matrix.** Iterate over a matrix of `{ route, expectedRedirect, minAal }` for seeker and admin routes. Test both direct navigation and in-app navigation from the landing page.
2. **Backend `aal` claim enforcement.** Add a backend dependency that rejects requests when `request.state.user.aal != "aal2"` for routes tagged with `require_aal2`. Add a test endpoint `/api/health/mfa` (or use an existing protected route) and call it from Playwright with a test-key injected session whose `aal` claim is `aal1`. Expect `403`.
3. **MFA step-up completeness.** After seeding a fake session, assert that:
   - Navigating to `/chat` redirects to `/auth/mfa`.
   - Navigating directly to `/auth/mfa` renders the TOTP input.
   - Submitting an invalid code shows an error and does not advance to `/chat`.
   - (Optional, if test infrastructure supports TOTP generation) submitting a valid code advances.
4. **Admin guard isolation.** Ensure the admin guard requires both AAL2 and an admin role. A non-admin AAL2 user must be redirected away from `/admin`.

### 3.2 RLS Cross-User Verification

**Script:** `backend/scripts/verify_rls_policies.py`
- Reads `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from env.
- Uses the Supabase Admin API to create two test users (Alice and Bob) with confirmed emails and strong passwords.
- Signs in each user via password grant to obtain real access tokens.
- Uses the `supabase-py` anon/authenticated client for each user.
- Seeds rows in `conversations`, `chat_messages`, `meditation_sessions`, and `user_profiles` as Alice.
- As Bob, attempts SELECT/UPDATE/DELETE on Alice's rows via the Data API.
- Asserts failure (empty result set for SELECT, 0 rows for UPDATE/DELETE, or 401/403 for direct API violations).
- Cleans up: deletes seeded rows and deletes test users.
- Exit code 0 on pass, 1 on failure, with a JSON report to stdout.

**Playwright E2E RLS test:** `tests/e2e/rls-cross-user.spec.ts`
- Uses a custom fixture that calls a small local API shim (or an edge function) to create two users and tokens.
- Logs in as Alice in one browser context, seeds a conversation.
- Logs in as Bob in a second context, opens the same conversation ID, and asserts the app shows an empty/error state (not Alice's content).
- This is a higher-level confirmation that the frontend does not leak cross-user data even if an ID is guessed.

### 3.3 Supabase Leaked-Password Protection

- Dashboard path: `Authentication → Providers → Email → Prevent the use of leaked passwords`.
- Requires Supabase Pro plan or above.
- Verification: after enabling, attempt to sign up a test user with a known-bad password (e.g., `password123`) via the Supabase Auth API. Expect `WeakPasswordError` with `reasons: ["leaked_password"]`.
- Add a note to the release-readiness document confirming the finding is resolved.

### 3.4 Lovable Cloud Sync Evaluation

**Finding:** Lovable Cloud is a managed Supabase-compatible backend built into Lovable. It is not a drop-in replacement for an existing FastAPI backend. Real-time sync between a custom FastAPI backend and Lovable Cloud/Supabase is possible only with manual engineering:
- FastAPI writes shared state through Supabase REST/Realtime.
- Supabase Realtime broadcasts changes to the frontend.
- Edge functions can proxy/authenticate, but they are Deno/TypeScript request/response handlers, not a sync layer.

**Recommendation for AskMukthiGuru:** Do not enable Lovable Cloud for the production backend. Use Lovable only for frontend prototyping/hosting if desired, and keep the existing Supabase project as the single source of truth. If Lovable-hosted frontend is used, configure it to call the existing FastAPI backend and Supabase Auth directly, not to attempt bidirectional data sync with Lovable Cloud.

### 3.5 Ruthless Metrics Parity

**Backend:** `backend/app/api/metrics.py` (new file)
- Endpoint: `GET /api/metrics`
- Returns a `UserMetrics` Pydantic model:
  - `totalConversations`
  - `totalMessages`
  - `totalMeditationMinutes`
  - `averageDistressLevel` (last 7 days)
  - `distressTrend` (up/down/flat)
  - `activeHealingCourse`
  - `courseCompletionPercent`
  - `lastActiveAt`
- All values computed from the same tables the frontend reads (`conversations`, `chat_messages`, `meditation_sessions`, `user_course_progress`, `user_memories` / distress telemetry).

**Shared schema:** `src/lib/metricsSchema.ts` and `backend/app/schemas/metrics.py` must match. Use a JSON file `shared/metrics.schema.json` imported by both if tooling permits; otherwise duplicate and add a parity test.

**Frontend:** `src/hooks/useMetrics.ts`
- Fetches `/api/metrics` on mount and when `conversation:updated` event fires.
- Displays metrics in `ProfilePage` and/or a new `MetricsCard` in chat.
- Falls back to local computation when offline.

**Verification:** Add a backend test and a Playwright test that compare backend-returned metrics against UI-rendered metrics for the same synthetic user.

### 3.6 Suffering-State Course Assignment

**Trigger philosophy:** A single distress turn is not enough to assign a healing course. Assignment is triggered by a **distress streak or repeated suffering queries** within a sliding window, to avoid over-prescribing on an offhand emotional message.

**Backend extension:**
- Track recent distress history per user from `user_memories` / conversation turn metadata (timestamp, distress_level, intent, signal).
- Trigger `HealingCourseService.assign_if_needed(user_id, signal)` only when one of the following holds:
  - **Consecutive streak:** distress detected in ≥2 consecutive turns.
  - **Frequency threshold:** distress detected in ≥3 of the last 5 turns.
  - **Escalation:** severity increases across consecutive turns (MILD → MODERATE → SEVERE / CRISIS).
  - **Repeated signal:** the same `SufferingSignal` (grief, anxiety, anger, loneliness, meaninglessness) is detected ≥2 times within the current session or within the last 24 hours.
- Config knob `proactive_course_assignment_threshold` in `backend/app/config.py` controls the sensitivity (default: 2 consecutive or 3-of-5 frequency).
- When triggered, the intent router emits `recommended_course` in the chat response with `slug`, `title`, `reason`, `trigger_signal`, and `trigger_pattern` (e.g., `consecutive_2`, `freq_3_of_5`, `escalation`, `repeated_signal`).
- Add `services/healing_course_service.py` that upserts a row in `user_course_progress` only if no active course exists for that user.
- Expose `POST /api/healing-course/assign` (protected) that the frontend calls when `HealingPathCard` is shown, so the assignment is persisted server-side and visible across devices.

**Frontend extension:**
- `HealingPathCard` already detects signals locally. Extend it to call `/api/healing-course/assign` when a course is first shown.
- Use backend `recommended_course` from the chat response when available; otherwise fall back to local `detectSufferingSignal` only for rendering, and still call `/api/healing-course/assign` so the backend can apply the streak/repetition rules.

## 4. Data Flow

```
User writes message in /chat
        |
        v
FastAPI intent router detects DISTRESS/suffering signal
        |
        +--> emits recommended_course in chat response
        |
        +--> HealingCourseService.assign_if_needed(user_id, signal)
        |           upserts user_course_progress
        |
        v
Frontend receives response + recommended_course
        |
        +--> HealingPathCard renders course
        |
        v
On lesson start -> POST /api/healing-course/progress
        |           updates completed_lessons, current_lesson_index
        v
ProfilePage / MetricsCard shows metrics from GET /api/metrics
```

## 5. Security & Privacy

- All new backend routes use existing JWT auth dependency.
- `user_course_progress` already has RLS policies; verify `WITH CHECK` prevents `user_id` reassignment.
- The RLS verifier uses synthetic users and cleans up; never run against production with real user data.
- Supabase leaked-password setting uses HIBP; no password leaves Supabase.
- Metrics endpoint returns only the calling user's data.

## 6. Testing Strategy

| Test | Type | Tool |
|------|------|------|
| AAL2 route matrix + backend claim | E2E | Playwright |
| RLS cross-user isolation | Script + E2E | Python `verify_rls_policies.py` + Playwright |
| Leaked password rejection | Integration | Python script or Playwright |
| Metrics parity | Unit + E2E | Vitest + Playwright |
| Course assignment on distress | Unit + E2E | Vitest + Playwright |
| CI nightly RLS check | CI workflow | GitHub Actions |

## 7. Release-Readiness Document Outline

The document will list each area as Ready / Not Ready / Conditional, with evidence and go/no-go criteria:

- Auth & MFA
- RLS & data isolation
- Backend performance / latency
- i18n completeness
- Responsive layout (mobile/tablet/desktop)
- Production E2E (OAuth, forgot password, audio)
- Backup/DR for Qdrant + Neo4j + Redis
- Mobile app store credentials
- Monitoring/alerting
- GDPR / right to forget
- Lovable Cloud decision
- Cost/usage caps

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Supabase Pro required for leaked-password protection | Document cost; verify plan before enabling. |
| Playwright MFA TOTP tests need a real factor | Use a test-only TOTP secret or skip live-code path and test only rejection/bypass. |
| RLS verifier needs service_role key | Restrict to local/staging; never commit secrets; use `BENCHMARK_SECRET`/env injection. |
| Metrics endpoint adds latency | Cache for 60s per user; compute asynchronously if needed. |
| Suffering-state false positives | Use backend intent classification as primary; local regex as fallback only. |
| Lovable Cloud scope creep | Explicitly out of scope for implementation; decision doc only. |

## 9. Success Criteria

- `npm run test:e2e` passes with extended AAL2 and RLS specs.
- `python3 backend/scripts/verify_rls_policies.py` passes against local Supabase.
- Supabase dashboard shows "Prevent the use of leaked passwords" enabled.
- `GET /api/metrics` returns values identical to UI-computed metrics for test users.
- `HealingPathCard` assigns and persists courses via backend when distress is detected.
- Release-readiness document is committed to `docs/RELEASE_READINESS_2026_07_30.md`.

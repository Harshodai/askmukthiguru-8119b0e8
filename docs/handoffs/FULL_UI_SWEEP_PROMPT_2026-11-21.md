# Full UI Sweep & Feature Integration Summary — Nov 21, 2026

## 1. Overview & Context

Commit `9f2c89d4db5a1954d4ef7bac5e0f93e1475fd823` merged the full UI sweep and new feature branch into `main`, followed by an immediate Railway deployment to update the production backend and worker.

### Commit Details: `9f2c89d4`
- **Branding**: Added official Ekam/Oneness emblem asset (`public/images/ekam-oneness-logo.png`) and integrated into `EkamLinkButton`, `MeetTheGurus`, `Navbar`, `Footer`, `KnowledgeGraph`, and `JourneyOverview`.
- **Upcoming Events System**:
  - Backend: `backend/tasks/event_media_tasks.py` (Celery purge task `purge_ended_event_media` for expired event attachments).
  - Database: `supabase/migrations/20261121090000_upcoming_events.sql` adding `upcoming_events` table with RLS and `event-media` storage bucket policies.
  - Frontend: `UpcomingEventsCard`, `useUpcomingEvents` hook, and admin CMS `EventsPage` (`/admin/events`).
- **Voice & Audio Speech Handling**:
  - Handled quote-only guru messages in read-aloud and voice mode handler (`src/hooks/useVoiceConversation.ts`).
  - Fixed Sarvam audio format parameter in `backend/app/api/speech.py`.
- **Admin Reliability**:
  - `backend/app/telemetry_db.py`: `get_admins()` now fails loudly on missing Supabase client rather than returning an empty list.
- **Chat UX & Theming**:
  - Stripped title quotation marks while preserving contractions in `backend/app/api/chat.py`.
  - Added anti-flash theme script in `index.html`.
  - Added `ScrollToTop` component in `src/App.tsx` on route transitions.
  - Replaced generic sparkle icons with domain-specific icons across all chat and practice widgets.
  - Synchronized all 14 locales for newly introduced keys in `scripts/i18n/source-hashes.json`.

---

## 2. Production Deployment Status (Nov 21, 2026 ~01:35 IST)

1. **Commit Deployed**: `9f2c89d4db5a1954d4ef7bac5e0f93e1475fd823` on `origin/main`.
2. **Railway Backend (`askmukthiguru-8119b0e8`, ID `18690f24-5e2d-4fdb-95f6-42142111df7e`)**:
   - Deployment ID: `c910b959-9dd1-4aa4-904f-e096614e6ffa`
   - Build Status: `SUCCESS`
   - Healthcheck: `/api/healthz` passed
   - Boot Posture Confirmed:
     ```
     Serving posture: faculty_gate=OPT-OUT first_person(route=True bridge=True collection=first_person_v12_shadow fallback=False weak_match=True min_score=2 model=anthropic/claude-haiku-5.5)
     ```
3. **Railway Worker (`celery-worker`, ID `9ac523d7-4eae-4db5-9b2a-37906634203b`)**:
   - Deployment ID: `7b98271e-670a-40fb-864d-83824c7c5f4a`
   - Re-deployed to include `event_media_tasks` registration in Celery schedule.

---

## 3. Operational Learnings & Guardrails

1. **Pinning Deployments on Railway via GraphQL**:
   - The Railway backend is pinned to explicit commit SHAs. Standard git pushes do not trigger auto-deploy if commit pinning is active.
   - Deploying requires invoking Railway GraphQL mutation `serviceInstanceDeployV2` with `environmentId`, `serviceId`, and `commitSha`.
2. **Build and Verification Hygiene**:
   - Always run `npx tsc --noEmit -p tsconfig.app.json` and `npm run build` locally before or concurrent with deployment triggers.
   - Prerendering 29 static SEO routes completed in ~6.9s without missing chunk errors.
3. **Database Migration Application**:
   - Lovable GitHub sync automatically applies migrations from `supabase/migrations/` to the connected Supabase instance upon push.
   - Always verify `supabase_migrations.schema_migrations` before applying manually to prevent duplicate version records.

---

## 4. Verification Outcomes

- [x] Complete live smoke battery (11/11 checks pass, 0 provider outages, committed 66a903ce).
- [x] Confirm Lovable SPA publish reflects commit `9f2c89d4` (verified chunks `UnsubscribePage`, `PrivacyPage`, `ChatPage`, all 7 public routes HTTP 200).
- [x] Prerendered 29 static SEO routes completed cleanly.
- [x] Component vitests passed (19/19).
- [x] Lint passed (0 errors, 68 non-blocking warnings), TypeScript check passed (`npx tsc --noEmit -p tsconfig.app.json` 0 errors).
- [ ] Verify `/admin/events` loads properly for authenticated admin accounts (owner action).
- [ ] Verify upcoming events render on the ritual/practice dashboard (owner action).

# Plan Addendum: Excellence & Benchmarks — Pain Points + Upgrades

Builds on the previously approved finalization plan. Each item lists the **pain point**, the **fix**, and the **benchmark it moves**.

## A. Trust, Safety & Auth Hardening

1. **Leaked-password protection off** → enable HIBP via `configure_auth(password_hibp_enabled: true)`. *Moves: security score, OWASP.*
2. **No rate limiting on chat** → add an Edge Function `chat-rate-limit` (sliding window in `kv` table) capping anon=0/min, auth=20/min. Block before SSE opens. *Moves: cost, abuse.*
3. **No PII redaction in logs** → middleware in `backend/app/main.py` to strip emails/phones from request logs.
4. **Password reset missing** → add `/reset-password` route + `resetPasswordForEmail` flow on AuthPage.
5. **Session expiry UX** → global `onAuthStateChange` toast "Session expired, please sign in" → redirect.

## B. RAG Quality Benchmarks (RAGAS)

6. **No automated quality gate** → wire `backend/evaluation/ragas_eval.py` into a `make eval` target with a fixed 50-question golden set; fail CI under thresholds (faithfulness ≥0.85, answer_relevancy ≥0.80, context_precision ≥0.70).
7. **Citation hallucination** → enforce post-hoc citation grounding: every cited URL must appear in the retrieved chunk metadata; drop unverifiable ones in `format_final_answer`.
8. **Semantic cache underused** → log hit-rate to Prometheus; surface in admin Overview KPI card. Target ≥35% hit rate after 1k queries.
9. **No A/B prompt testing** → admin Prompts page already exists; add "shadow mode" that runs two prompts, judge-scores, displays delta.

## C. Performance Benchmarks

10. **Time-to-first-token unmeasured** → instrument `/api/chat/stream` with TTFT, total-latency, tokens/sec metrics; add p50/p95 to admin KPI. Target TTFT <800 ms p50, <2 s p95.
11. **Frontend bundle bloat** → split admin routes into a separate lazy chunk (`React.lazy` for `AdminShell`); estimated −300 KB on `/chat`.
12. **No image optimization** → daily-teaching uploads should be transformed to webp + responsive `srcset`; add Supabase storage transform query params.
13. **No prefetch** → on landing page, prefetch `/chat` chunk and warm Supabase auth.
14. **React-markdown not memoized** → wrap `<ChatMessage>` markdown render in `React.memo` + stable key.

## D. UX Pain Points

15. **First-run is empty** → add 4 starter prompt chips (e.g. "Why am I anxious?", "Teach me about Beautiful State"). Increases activation.
16. **No conversation rename / delete confirmations** → inline edit on sidebar items + destructive confirm dialog.
17. **Lost message on refresh during stream** → persist partial assistant message to DB on each chunk (debounced 500 ms) so refresh recovers.
18. **No copy / share / regenerate** on guru responses → hover action bar (copy, regenerate, share-as-card via existing `WisdomCardGenerator`).
19. **No keyboard shortcuts** → ⌘K palette already exists; add ⌘↵ submit, ⌘/ focus input, ⌘B sidebar toggle. Document in palette.
20. **Mobile sidebar friction** → swipe-from-left to open; haptic on close.
21. **Voice input visible only to power users** → add a one-time tooltip pulse on mic button for first 3 sessions.

## E. Daily Teaching — beyond realtime

22. **Push notifications** for new daily teaching → register web push (VAPID), Edge Function sends on row insert via Postgres trigger → `pg_net`.
23. **Teaching archive** for users → `/teachings` page, infinite scroll, search by caption.
24. **Engagement tracking** → log views/dismissals into `daily_teaching_events`; show admin a heatmap.

## F. Accessibility (WCAG AA)

25. Run axe-core in CI; fix focus rings on custom buttons, add `aria-live="polite"` to streaming response, label all icon buttons, contrast audit for `text-muted-foreground` on `bg-card/60`.

## G. SEO & Discoverability

26. Per-route `<title>` + meta via `react-helmet-async`; OG image generated from brand template.
27. `sitemap.xml` + `robots.txt` already present — extend with `/practices/*`.
28. JSON-LD `Organization` + `FAQPage` on landing.
29. Pre-rendered landing page (vite-plugin-prerender) for faster LCP and crawler indexing.

## H. PWA

30. Add `vite-plugin-pwa` with `navigateFallbackDenylist: [/^\/~oauth/]`, offline fallback page, installable manifest, daily-teaching push handler.

## I. Internationalization

31. UI strings still English-only despite TTS in 4 langs → adopt `i18next` with `en/hi/te/ml` resource bundles; auto-detect from profile `preferred_language`.

## J. Observability & Feedback Loop

32. Frontend: Sentry (errors) + PostHog (funnels: signup → first-message → 3rd-session retention).
33. Backend: OpenTelemetry traces already partial — propagate `trace_id` into SSE `done` event so admin Trace Drawer can deep-link from a chat message.
34. Thumbs up/down on every guru reply (already a table) → nightly job clusters down-voted queries into `golden_questions` for re-eval. Closes the quality loop.

## K. Testing

35. Add **Playwright** e2e: signup → first message → streaming response → Serene Mind trigger → meditation completion → admin login → upload daily teaching → user sees realtime banner.
36. Visual regression via `@playwright/test` snapshots for chat, landing, admin.
37. Backend `pytest` coverage gate ≥80%.

## L. Cost & Sustainability

38. Token-budget guard: cap context to 8k tokens; summarize older turns via map-reduce.
39. Embedding cache (file-hash → vector) to skip re-embedding on re-ingest.
40. Cold-start script for Ollama warmup at boot (`ollama run sarvam-30b "."`).

## M. Compliance

41. Add `/privacy` and `/terms` routes (currently missing) — required for OAuth verification & app-store submission.
42. Cookie/consent banner (India DPDP Act + GDPR if EU traffic).
43. Data export & delete endpoints (DPDP Section 13). Edge functions: `export-my-data`, `delete-my-account`.

## N. Onboarding for New Engineers

44. The `docs/DEVELOPER_GUIDE.md` from prior plan is extended with: "Day 1 setup" runbook, ADRs (Architecture Decision Records) for the 12-layer pipeline, PR checklist, and a `make bootstrap` script that one-shots local Docker + seed data.

---

## Suggested phasing (small, shippable batches)


| Phase                 | Scope                    | Effort   |
| --------------------- | ------------------------ | -------- |
| **P1 — Trust**        | A1, A2, A4, A5, M41, M42 | 1 sprint |
| **P2 — Quality gate** | B6, B7, J34, K35         | 1 sprint |
| **P3 — Perf**         | C10, C11, C12, H30       | 1 sprint |
| **P4 — UX delight**   | D15, D17, D18, E22       | 1 sprint |
| **P5 — Reach**        | G26, G29, I31, F25       | 1 sprint |


## Recommended immediate execution this loop

To stay within the current finalization scope, I'll execute only the highest-leverage low-risk items from the addendum **in addition to** the previously approved plan:

- **A1** Enable HIBP password protection (`configure_auth`).
- **A4** `/reset-password` page + flow.
- **D15** Starter prompt chips on empty chat.
- **D18** Copy/regenerate buttons on guru replies.
- **K35** Minimal Playwright smoke spec for the auth → chat → stream flow.
- **M41** `/privacy` + `/terms` placeholder routes.

Everything else is captured in `docs/ROADMAP.md` (created alongside the dev guide) and ranked by phase so the team can pick them up.

&nbsp;

&nbsp;

# Plan: Finalize Auth, Daily Teaching Wiring, Config & Onboarding Docs

## Status of prior plan items

Already implemented in earlier loops:

- Phase A (Toaster inside BrowserRouter), Phase B (SSE `done` chunk + unescape `\n`), Phase C (citations no slice + URL extraction), Phase D (sidebar `PanelLeft` toggle), Phase E (ThinkingPills glassmorphism), Phase F `useRequireAuth` + `ChatPage` guard + Google OAuth via `lovable.auth.signInWithOAuth`), Phase G (admin login cleanup + Role Verified badge), Phase H (streaming tests).

Remaining / new work this loop addresses:

## 1. Google OAuth — End-to-end verification & finalize

`AuthPage.handleGoogleSignIn` already supports two paths via `VITE_USE_NATIVE_OAUTH`:

- Lovable Cloud managed `lovable.auth.signInWithOAuth('google')`) — default

- Native Supabase OAuth for local Docker `supabase.auth.signInWithOAuth({ provider: 'google' })`)

Action: call `supabase--configure_social_auth` with `providers: ["google"]` to confirm Google is enabled in the managed Lovable Cloud auth settings (idempotent — re-runs safely). Document the BYOK option (own Google client ID) in the new dev doc.

## 2. Daily Teaching — full wiring (admin upload → end user)

Current state: `DailyTeaching.tsx` fetches once on mount. RLS allows reads only when `expires_at > now()` and only to authenticated users. Chat is now auth-gated, so users see it.

Gap: when admin uploads a fresh teaching, existing users on the chat page see nothing until reload.

Fix in `src/components/chat/DailyTeaching.tsx`:

- Subscribe to `postgres_changes` on `public.daily_teachings` via Supabase Realtime; on INSERT, refetch the latest active row.

- Reset `dismissed` flag when a NEW teaching id arrives (different from previously dismissed id) — change the localStorage key from a date to the dismissed teaching id, so a new daily teaching re-shows even if the user dismissed yesterday's.

Database side: enable Realtime publication for `public.daily_teachings` via migration:

```sql

ALTER PUBLICATION supabase_realtime ADD TABLE public.daily_teachings;

ALTER TABLE public.daily_teachings REPLICA IDENTITY FULL;

```

Verify `DailyTeachingPage.tsx` admin upload writes both image (storage bucket `daily-teachings`) and row insert with `expires_at` default = now+24h. If missing, patch.

## 3. Config — make UI run on local Docker AND on Lovable

- `.env.example` already has `VITE_BACKEND_URL=http://localhost:8000`.

- Add `VITE_USE_NATIVE_OAUTH=false` (default) with comment: set to `true` only for local Docker without Lovable proxy.

- `frontend.Dockerfile`: confirm it accepts build args for `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, `VITE_BACKEND_URL`, `VITE_USE_NATIVE_OAUTH`. If missing, add `ARGENV` lines so values are baked at build.

- `vite.config.ts`: leave `host: "::"` and `port: 8080` (Lovable preview requirement).

## 4. Admin auto-provisioning for `kharshaengineer@gmail.com`

After the user signs up via `/auth`, run a `supabase--insert` to add their `user_id` to `public.user_roles` with role `admin`. (Cannot run yet — requires the user to sign up first. The plan documents this as a one-shot manual step the agent will execute on confirmation.)

## 5. New onboarding document

Create `docs/DEVELOPER_GUIDE.md` (≈400 lines) — comprehensive end-to-end:

- High-level architecture diagram (frontend ⇄ Supabase ⇄ FastAPI ⇄ Qdrant/Ollama)

- Repo tour (every top-level dir, what lives where)

- Local dev setup (frontend `npm run dev`, backend `docker compose up`, Ollama on host)

- Lovable Cloud setup (env vars baked, OAuth managed, Realtime enabled)

- Auth flow walk-through (signup → email verify → session → `useRequireAuth` → chat)

- Chat request lifecycle: ChatInterface → `aiService.sendMessageStreaming` → SSE → backend `/api/chat/stream` → 12-layer RAG → `done` event → citations + Serene Mind trigger

- Daily Teaching lifecycle: admin upload → storage → row insert → Realtime → end-user banner

- Database schema (tables, RLS, roles), migration workflow

- Testing `npm test`, backend `pytest`)

- Deployment (Lovable publish, Docker prod compose)

- Troubleshooting (common errors + fixes)

- Glossary (Stimulus RAG, CRAG, Self-RAG, CoVe, RAPTOR, Beautiful State, Serene Mind)

Link from `README.md` and `SETUP.md`.

## Files to change

| File | Change |

|------|--------|

| `src/components/chat/DailyTeaching.tsx` | Realtime subscription; dismissed-by-id |

| `.env.example` | Add `VITE_USE_NATIVE_OAUTH=false` |

| `frontend.Dockerfile` | Ensure all `VITE_*` build args wired |

| `README.md` | Link to new dev guide |

| `SETUP.md` | Reference dev guide for deeper detail |

## Files to create

| File | Purpose |

|------|---------|

| `docs/DEVELOPER_GUIDE.md` | End-to-end onboarding doc |

## Database operations

1. Migration: enable Realtime for `daily_teachings` `ALTER PUBLICATION ... ADD TABLE`).

2. After admin signup: `INSERT INTO user_roles (user_id, role) VALUES ('<uid>', 'admin')` via `supabase--insert`.

## Out of scope (Lovable Cloud limitation)

Meta/Facebook OAuth — not supported by Lovable Cloud managed auth. Doc will explain Google + Email only.

## Verification

- `npm test` — all existing tests still green.

- Manual: sign in with Google → land on `/chat`; admin uploads teaching → all open chat sessions show banner without reload.

- Build check via Lovable harness (no manual `npm run build`).

## Out of scope this loop

Anything requiring user decisions: PostHog/Sentry keys, VAPID push keys, custom Google OAuth client ID, language UI translations content. Those will be `add_secret`/follow-up tasks.
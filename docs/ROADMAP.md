# AskMukthiGuru — Roadmap

Pain points and upgrades, ranked into shippable phases. Imported from the
"Excellence & Benchmarks" plan addendum. Items already shipped are crossed off.

## Shipped

- [x] Auth gate on `/chat` (`useRequireAuth`)
- [x] Streaming `done` event → citations + Serene Mind trigger
- [x] Newline unescape in token chunks
- [x] Sidebar `PanelLeft` toggle in chat header
- [x] ThinkingPills glassmorphism
- [x] Admin login cleanup + Role Verified badge
- [x] Daily Teaching realtime + dismiss-by-id
- [x] HIBP password protection enabled
- [x] `/reset-password`, `/privacy`, `/terms`
- [x] Forgot-password link on AuthPage
- [x] Copy button on guru responses
- [x] End-to-end Spiritual Profile sync (Supabase + localStorage)
- [x] Admin dashboard seeker auditing (Total Seeker counts)
- [x] Enhanced telemetry (Triggers, Retrieval, Context events)
- [x] OpenTelemetry + Jaeger tracing for chat and LangGraph observability
- [x] Master SQL Schema for production database initialization
- [x] Fixed Nginx route shadowing for protected auth paths
- [x] Three-stage distress detection (Keyword, LLM, Semantic)
- [x] Compassionate distress routing (RAG-integrated)
- [x] Qdrant retry-with-backoff resilience
- [x] Spiritual guardrail false-positive protection
- [x] Onboarding gate (Redirect new users to Profile setup)
- [x] Visible sidebar management (Direct Rename/Delete icons)
- [x] Stable conversational memory continuity (`session_id` + compact context injection)
- [x] **Fix published-link white screen** — Supabase client now boots with safe fallback URL+anon key when env is missing; added top-level `RootErrorBoundary` so future render crashes never blank the page. **Republish required** to ship the fix to `askmukthiguru.lovable.app`.
- [x] **Google sign-in dedup** — new `ensure_profile_and_role()` RPC + `onAuthStateChange` hook in `AuthPage.tsx` guarantees every signed-in user has exactly one profile + default `user` role. Backfill applied to historical users.

## P1 — Trust (1 sprint)

- [ ] **A2** Edge function `chat-rate-limit` (sliding window, auth=20/min) — *edge fn shipped at `supabase/functions/chat-rate-limit`; backend wiring still pending*
- [ ] **A3** PII redaction middleware in FastAPI logs
- [x] **A5** Global session-expired toast + redirect (`SessionExpiredHandler`)
- [x] **M42** Cookie/consent banner (DPDP + GDPR) — `CookieConsentBanner`
- [x] **M43** Edge functions: `export-my-data`, `delete-my-account` + Profile UI hooks
- [x] **NEW** `/auth/diagnostics` self-test page + `whoami_diagnostics` RPC + auto user-role seed on signup

## P2 — Quality gate (1 sprint)

- [ ] **B6** RAGAS thresholds wired into `make eval`; CI fails below cut-offs
- [ ] **B7** Citation grounding: drop URLs absent from retrieved chunk metadata
- [ ] **B8** Semantic-cache hit-rate KPI on admin Overview
- [ ] **B9** A/B prompt shadow mode in admin Prompts page
- [ ] **J34** Down-vote → `golden_questions` clustering nightly job
- [ ] **K35** Playwright e2e: signup → chat → stream → meditation → admin upload → realtime
- [ ] **B10** Memory eval set: follow-up resolution, persona continuity, and grounding regression checks

## P3 — Performance (1 sprint)

- [ ] **C10** TTFT / total-latency / tok-s metrics on `/api/chat/stream` (target TTFT p50 < 800 ms)
- [ ] **C11** Lazy-load `AdminShell` (`React.lazy`) — *already lazy in `App.tsx`*
- [ ] **C12** Daily-teaching image transforms (webp, srcset)
- [ ] **C13** Prefetch `/chat` chunk + warm Supabase auth on landing
- [x] **C14** `React.memo` on `<ChatMessage>` markdown render (custom prop comparator)
- [ ] **H30** PWA via `vite-plugin-pwa` (with `/~oauth` denylist)

## P4 — UX delight (1 sprint)

- [x] **D16** Inline rename + destructive confirm in conversation sidebar
- [ ] **D17** Persist partial assistant message during stream (debounced 500 ms)
- [ ] **D18b** Regenerate button (rerun last user turn)
- [ ] **D19** Keyboard shortcuts: ⌘↵ submit, ⌘/ focus, ⌘B sidebar
- [ ] **D20** Mobile swipe-from-left to open sidebar
- [ ] **D21** First-3-sessions tooltip pulse on mic
- [ ] **E22** Web-push notifications for new daily teaching (VAPID + `pg_net`)
- [ ] **E23** `/teachings` archive page
- [ ] **E24** `daily_teaching_events` engagement heatmap

## P5 — Reach (1 sprint)

- [ ] **F25** axe-core in CI; fix focus rings, `aria-live`, contrast
- [ ] **G26** `react-helmet-async` per-route SEO + branded OG image
- [ ] **G28** JSON-LD Organization + FAQPage on landing
- [ ] **G29** Pre-rendered landing page (vite-plugin-prerender)
- [ ] **I31** `i18next` with en/hi/te/ml resource bundles, auto-detect from profile

## Continuous

- [ ] **J32** Sentry + PostHog (requires user-supplied keys)
- [ ] **J33** Propagate `trace_id` into SSE `done` event for admin Trace Drawer deep-links
- [ ] **K36** Visual regression snapshots
- [ ] **K37** Backend pytest coverage gate ≥ 80 %
- [ ] **L38** Token-budget guard with map-reduce summarization
- [ ] **L39** Embedding cache keyed by file hash
- [ ] **L40** Ollama warmup on boot

## Out-of-scope (Lovable Cloud limits)

- Meta/Facebook OAuth — not supported. Use Google + Email.

## Backend repo (cannot ship from Lovable sandbox)

> These items require the FastAPI / Qdrant / Ollama / CI stack and must be implemented in the backend repository, not in Lovable.

- **A2** Wire `chat-rate-limit` edge function call site into Python `/api/chat/stream`
- **A3** PII redaction middleware in FastAPI logs
- **B6** RAGAS thresholds in `make eval` + CI gate
- **B7** Citation grounding — drop URLs absent from retrieved chunk metadata (`rag/nodes.py`)
- **B8** Semantic-cache hit-rate KPI feed for admin Overview
- **B9** A/B prompt shadow mode
- **B10** Memory eval set
- **C10** TTFT / total-latency / tok-s metrics on `/api/chat/stream`
- **J33** `trace_id` propagation into SSE `done` event
- **J34** Down-vote → `golden_questions` nightly job
- **K35** Playwright e2e (signup → chat → meditation → admin)
- **K37** Backend pytest coverage gate ≥ 80%
- **L38–L40** Token-budget guard, embedding cache, Ollama warmup
- **J32** Sentry + PostHog (needs user-supplied DSN/keys)

## Next up (frontend, deferred from this run)

- **Sidebar redesign v2** — ChatGPT/Claude-style bottom user card, edge-grouped sections (Today/Yesterday/Previous 7 days/Older), 56px icon-rail collapse
- **D17** Partial-stream persistence (debounced 500 ms save during streaming)
- **D18b** Regenerate button on last guru message (uses `AbortController` in `aiService.ts`)
- **D19** Keyboard shortcuts (⌘↵ submit, ⌘/ focus, ⌘B sidebar, ⌘⇧O new chat)
- **D20** Mobile swipe-from-left to open sidebar
- **D21** First-3-sessions tooltip pulse on mic
- **C12** Daily-teaching webp + `srcset` via Supabase Storage transforms
- **C13** Prefetch `/chat` chunk + warm Supabase auth from landing
- **G26** `react-helmet-async` per-route SEO + branded OG image
- **G28** JSON-LD Organization + FAQPage on landing

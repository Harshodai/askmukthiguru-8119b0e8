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
- [x] Three-stage distress detection (Keyword, LLM, Semantic)
- [x] Compassionate distress routing (RAG-integrated)
- [x] Qdrant retry-with-backoff resilience
- [x] Spiritual guardrail false-positive protection

## P1 — Trust (1 sprint)

- [ ] **A2** Edge function `chat-rate-limit` (sliding window, auth=20/min)
- [ ] **A3** PII redaction middleware in FastAPI logs
- [ ] **A5** Global session-expired toast + redirect
- [ ] **M42** Cookie/consent banner (DPDP + GDPR)
- [ ] **M43** Edge functions: `export-my-data`, `delete-my-account`

## P2 — Quality gate (1 sprint)

- [ ] **B6** RAGAS thresholds wired into `make eval`; CI fails below cut-offs
- [ ] **B7** Citation grounding: drop URLs absent from retrieved chunk metadata
- [ ] **B8** Semantic-cache hit-rate KPI on admin Overview
- [ ] **B9** A/B prompt shadow mode in admin Prompts page
- [ ] **J34** Down-vote → `golden_questions` clustering nightly job
- [ ] **K35** Playwright e2e: signup → chat → stream → meditation → admin upload → realtime

## P3 — Performance (1 sprint)

- [ ] **C10** TTFT / total-latency / tok-s metrics on `/api/chat/stream` (target TTFT p50 < 800 ms)
- [ ] **C11** Lazy-load `AdminShell` (`React.lazy`) — est. −300 KB on `/chat`
- [ ] **C12** Daily-teaching image transforms (webp, srcset)
- [ ] **C13** Prefetch `/chat` chunk + warm Supabase auth on landing
- [ ] **C14** `React.memo` on `<ChatMessage>` markdown render
- [ ] **H30** PWA via `vite-plugin-pwa` (with `/~oauth` denylist)

## P4 — UX delight (1 sprint)

- [ ] **D16** Inline rename + destructive confirm in conversation sidebar
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

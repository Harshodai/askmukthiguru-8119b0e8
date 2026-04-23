

# Plan: Surface Serene Mind Everywhere + Land the Reports Honestly

## Scope clarity (read first)

The two uploaded reports are about the **Python FastAPI backend** (Sarvam vs Ollama, vLLM, GPU costs, JWT, multilingual prompts, YouTube ingestion). This Lovable project only contains the **React frontend** — I cannot run vLLM, deploy GPUs, or edit `backend/`. So this plan does only the frontend-implementable subset and ships the rest as a developer TODO doc, with `verified_report.md` winning on every conflict (per your answer).

---

## Part A — Serene Mind: make it reachable from anywhere

Today Serene Mind opens from: chat sidebar, chat input chip, distress detection in the chat reply, `/practices/serene-mind`, and the landing CTA. It is **not** reachable from `/`, `/profile`, or other app pages, and the modal has no audio/video — only the breathing animation.

**A1. Promote `SereneMindModal` to a global, app-wide component**
- Create `src/components/common/SereneMindProvider.tsx` — a context provider that owns `isOpen` state and renders `SereneMindModal` once, at the root.
- Mount it in `src/App.tsx` so the modal is available on every route.
- Expose `useSereneMind()` returning `{ open, close, toggle }` for any component.
- `ChatInterface.tsx` switches from local state to the context (drop the duplicate modal mount; keep the input chip and distress-trigger logic, but call `open()`).

**A2. Global header trigger (every page)**
- In `AppShell.tsx`, add a small flame button left of the Search button: `<Button variant="ghost" size="sm">🔥 Serene Mind</Button>` that calls `open()`. Mobile: icon-only.

**A3. Command Palette trigger (⌘K)**
- In `CommandPalette.tsx`, add a top "Quick actions" group with a "Start Serene Mind meditation" item that calls `open()` and closes the palette. Visible from any page.

**A4. Enrich `SereneMindModal` with audio + video options (the `/chat` UX gap)**
The current modal has only the animated flame. Best UX: keep the flame as default, and add a tab strip at the top:
- **Tab 1 — Guided breathing** (current animation, untouched)
- **Tab 2 — Audio guidance** — embeds the Serene Mind YouTube (`igSp4H0OWLE`) with `controls=1` but visually styled as an audio bar (16:9 iframe wrapped in a slim container, dark themed). Includes "Open in YouTube" link.
- **Tab 3 — Watch video** — full 16:9 YouTube embed (`youtube-nocookie.com/embed/igSp4H0OWLE?modestbranding=1&rel=0`).

Tab choice is remembered per-session in component state. The breathing-session tracking (`startMeditationSession` / `completeMeditationSession`) keeps firing only when the breathing tab is active and Play is pressed — audio/video tabs are passive and do not log a session, to keep stats meaningful.

**A5. Distress flow polish on `/chat`**
When `intent === 'DISTRESS'` and `meditationStep > 0`, the modal now opens directly to the **Audio guidance** tab so a stressed user can listen to Sri Preethaji's voice immediately rather than start a 3-minute breathing timer. The flame breathing remains one tap away.

---

## Part B — Land the two reports

**B1. Consolidated developer roadmap (Markdown, in repo, not in app)**
Create a single source of truth at:

```text
docs/
└── architecture/
    ├── README.md                       ← index + how to read these
    ├── backend-roadmap.md               ← consolidated, conflict-resolved
    ├── source-report.md                 ← original report.md verbatim
    └── source-verified-report.md        ← original verified_report.md verbatim
```

`backend-roadmap.md` will:
- State up front: "Where these two sources disagree, `verified_report.md` is authoritative."
- Group every recommendation under: **Critical / High / Medium**, **Frontend (this repo)** vs **Backend (`backend/` repo)**, with effort estimate.
- For each backend item, link to the exact section in the source files.
- Replace fabricated facts from `report.md` (Sarvam-2B model, ₹55K–2.5L GPU costs, wrong HF org `sarvam-ai`, `@EkamOfficial` channel) with the verified facts from `verified_report.md` (Sarvam API is **free per token**, repo is `sarvamai/sarvam-30b`, A100 80GB is ₹220/hr, IndiaAI subsidised GPU is ₹65/hr, only `@PreetiKrishna` is verified).

**B2. Frontend-only items extracted from the reports — implemented now**
From the reports, only these recommendations are implementable in this React codebase. I will do them:

1. **22-language picker for the Indic UI** — `LanguageSelector.tsx` currently supports 4 (en/hi/te/ml). Expand the list to the 22 scheduled Indian languages plus English (matching the Sarvam model's claimed coverage), gated by Web Speech API capability detection. Languages without browser STT/TTS get a small "voice not supported in your browser" badge but still work for chat text.
2. **Citation rendering improvements** — `ChatMessage.tsx` currently shows citations as raw markdown links inside the bubble. Render them as a separate "Sources" footer card with favicon + truncated title, matching what `aiService.ts` already returns in `response.citations`.
3. **Rate-limit + auth-required error states** — when the backend returns 401 or 429 (which it will once backend implements `verified_report.md` §5), `aiService.ts` should surface a toast with a friendly message ("You're sending messages quickly, please wait a moment") instead of falling back silently to placeholder. Add `errorCode` to the `AIResponse` type.
4. **Connection mode pill** — small badge in `AppShell` header showing `Offline Mode` / `Connected to Guru` / `Reconnecting…` based on `checkConnection()`, polled every 30s. Helps users understand when the placeholder responses kick in.

**B3. Backend items — written as TODO, NOT implemented (out of scope of this repo)**
Captured in `backend-roadmap.md` as actionable tickets, not done here:
- Swap Ollama → Sarvam API via `langchain-sarvamcloud` (verified package)
- JWT auth + Redis rate limiting on `/api/chat`
- Replace `mrm8488/distilroberta-finetuned-depression` with a multilingual distress classifier
- Multilingual system prompts (only after testing whether Sarvam handles Indic input natively)
- Automated YouTube channel sync (only `@PreetiKrishna` confirmed; others to be verified)
- Semantic cache (Redis), MMR diversity reranking
- Observability via Opik or Phoenix; evals via DeepEval/Ragas

---

## File-by-file changes (frontend)

| File | Change |
|------|--------|
| `src/components/common/SereneMindProvider.tsx` | **New.** Context + global modal mount. |
| `src/components/chat/SereneMindModal.tsx` | Add tab strip (Breathing / Audio / Video), accept optional `initialTab` prop. |
| `src/App.tsx` | Wrap routes in `<SereneMindProvider>`. |
| `src/components/chat/ChatInterface.tsx` | Remove local modal, use `useSereneMind()`; on distress open with `initialTab="audio"`. |
| `src/components/chat/DesktopSidebar.tsx` | Quick-access button calls `useSereneMind().open()` instead of prop. |
| `src/components/layout/AppShell.tsx` | Header flame button + connection-mode pill. |
| `src/components/common/CommandPalette.tsx` | "Start Serene Mind" quick action. |
| `src/components/chat/LanguageSelector.tsx` | Expand to 22 Indic languages with capability detection. |
| `src/components/chat/ChatMessage.tsx` | Render citations as a "Sources" card. |
| `src/lib/aiService.ts` | Add `errorCode` to `AIResponse`; differentiate 401/429 responses. |
| `src/test/SereneMindProvider.test.tsx` | **New.** Verify open/close + initialTab. |
| `src/test/CommandPalette.test.tsx` | **New (or extend).** Verify Serene Mind action fires. |
| `src/test/LanguageSelector.test.tsx` | Update for 22-language list. |
| `docs/architecture/README.md` | **New.** |
| `docs/architecture/backend-roadmap.md` | **New.** Consolidated, conflict-resolved roadmap. |
| `docs/architecture/source-report.md` | **New.** Verbatim copy. |
| `docs/architecture/source-verified-report.md` | **New.** Verbatim copy. |

## Verification after implementation
- `npm run build` passes with zero warnings.
- `npm test` passes (existing 27 tests + 2 new test files).
- Manual: open ⌘K from `/`, `/profile`, `/practices` → Serene Mind action visible and works. Click flame in header on any route → modal opens. On `/chat`, send a distress-style message in placeholder mode → confirm modal opens to the Audio tab when backend returns DISTRESS intent (placeholder mode just verifies the wiring with a manual test trigger button that we will hide behind `import.meta.env.DEV`).


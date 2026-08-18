
## YouTube and external research findings — 2026-08-18

### Agent memory and graph-memory videos
- `https://www.youtube.com/watch?v=qiBib0ap0KM` (Building Graph Memory for AI Agents with LangGraph & Neo4j) describes a dual-memory design: thread-scoped short-term memory plus user-scoped long-term memory in Neo4j. Memory nodes use a key, namespace derived from user/thread identity, value, and timestamp. Retrieval is user-scoped, ordered by timestamp, and injected into a dynamically rebuilt system prompt. The demonstrated privacy test changes the user ID and verifies that memories do not leak across users. The video emphasizes an explicit write/read path and UI testing across session restarts.
- `https://www.youtube.com/watch?v=fEQlTt7vDb0` (Shape agent memory with ontologies), `https://www.youtube.com/watch?v=JGFoTQt4GA0` (Actionable Knowledge for Agents with Context Graphs), and `https://www.youtube.com/watch?v=W2HVdB4Jbjs` (Architecting Agent Memory) were launched in parallel; the first two long-running analyses had not completed at the time of this note. Their analysis outputs must not be treated as complete until their saved result files show completion.

### AI chat UX search findings
- `https://www.youtube.com/watch?v=YNJvm7t3yq8` (Why Your AI UX Is Broken) was selected for first-hand analysis; its analysis was launched and was still running at note time.
- Search results also identified `https://www.youtube.com/watch?v=bppkpufBJsI` (10 UX Patterns Every AI Chat Interface Needs) and `https://www.metacto.com/blogs/ai-chat-ux-patterns-production` as relevant secondary sources. The result snippet specifically highlighted three interruption reasons during streaming: stop, edit, and retry.
- Official memory-control reference: `https://openai.com/index/memory-and-new-controls-for-chatgpt/`.

### Local implementation observations
- `prepare_user_memory` in `backend/app/orchestrator_utils.py` already merges Second Brain, profile memory, semantic memory, and a fresh persona summary, but uses two separate 200ms timeouts and injects Second Brain text as plain bullets without scores, freshness, provenance, or an explicit untrusted-data boundary.
- `SecondBrainService.personal_context` ranks by embedding rank, confidence, and creation time, then touches chosen items. It is user-scoped and encrypted, but the chat prompt path does not expose confidence/recency metadata to the model.
- `ChatInterface` has streaming, AbortController stop, partial stream checkpoints, citations, regenerate, inline edit, scroll tracking, and responsive composer logic. `ChatComposer` enforces a 2 MB attachment limit while parent logic tracks a separate 10 MB aggregate/content limit, creating policy drift.
- `src/index.css` hard-applies `font-family: 'Inter', system-ui, sans-serif` to `body`, while `src/styles/design-tokens.css` defines font variables. The token font system is not the effective global font source unless these are connected explicitly.

## Visual browser check — local `/chat`

The local chat page loads and prerenders successfully. The first-visit flow presents a practice-intent modal before the composer, then the main chat surface exposes the sidebar, source/transparency controls, language selector, assistant switcher, voice input, starter prompts, and a responsive composer. The visual pass confirmed a visible `0 memory` indicator in the sidebar and a large empty-state welcome surface. The top bar shows a temporary “Guru is waking up” warning, while the cookie banner and daily-teaching prompt occupy the lower-right area; these are functional but can compete with the primary chat action on first load.

The composer presents a single-line compact input at rest, a clear send/stop swap, and responsive action affordances. The typography visually follows the dark sanctuary palette, but the browser pass alone cannot prove loaded-font identity; the token import and `var(--font-sans)` changes are therefore verified via TypeScript/build rather than visual inspection alone.

## Real local chat-turn check

A real local question was submitted successfully from the composer. The UI immediately displayed the user bubble, an active “Searching …”/pipeline state, and a visible Stop control, confirming the expected streaming affordance. After the local backend failed to respond, the UI rendered a bounded `ERR_UNKNOWN` / “Failed to fetch” error with Retry last message and Details controls rather than leaving an endless spinner. The page also exposed copy, read-aloud, save-to-memory, save-as-note, share, edit-and-resend, provenance, and groundedness controls on the assistant message.

The local backend failure is an environment/integration issue, not a frontend compile failure: the browser was served by Vite on port 4173 while no compatible local API endpoint was available. The experience is functionally recoverable, but the error state would be more Claude/Manus-like if it included a concise next-step message and if the backend health/dependency status were surfaced before the user submits.

## Visual knowledge-graph check

The local `/knowledge-graph` page renders its search field, Explore action, zoom/reset/settings controls, and the graph canvas shell. With the local backend unavailable, the page remained at “Loading wisdom map…” and showed no visible demo/fallback graph. This contradicts the repository guidance that the public graph should never show a blank/loading-only state when the backend is cold. The next safe fix is to add a bounded loading timeout with a clearly labeled demo/fallback graph plus a retry action, while preserving the real-data path when the backend responds.

## Visual Second Brain check

Opening `/second-brain` while unauthenticated correctly redirects to `/auth`. The auth surface is visually coherent and exposes sign-in, sign-up, password recovery, diagnostics, and privacy links. A full end-to-end Second Brain UI check requires an authenticated session; no credentials were requested or entered. The code path is therefore reviewed statically and the unauthenticated privacy boundary is confirmed visually, but authenticated vault provisioning, unlock, recall, forget, and export still need a dedicated logged-in E2E run before being considered fully verified.

## Wisdom Map fallback recheck

After the fix, the local Wisdom Map no longer remains blank when the backend is unavailable. Within the bounded fallback window it renders a 10-node, 11-relationship guided example, labels the view as an example map, and exposes a visible Retry live map action. The graph canvas, zoom controls, reset control, settings control, type legend, and concept labels remain usable. This closes the previously observed cold-backend loading stall for the public graph surface.

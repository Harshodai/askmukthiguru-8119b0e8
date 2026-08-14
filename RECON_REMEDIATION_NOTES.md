# Remediation reconnaissance

## Repository/deployment alignment
- Selected repository: `Harshodai/askmukthiguru-8119b0e8`
- Checked out branch: `main`
- HEAD at reconnaissance: `9743d89e (build(env): add .env.production for production client bundle configuration)`
- The repo is not the Manus `client/src` + `server/routers.ts` template assumed by the earlier plan. It is a root `src/` React frontend with a Python FastAPI backend under `backend/app`.
- Frontend uses React Router (`BrowserRouter`/`HashRouter`) and Vite. `src/main.tsx` is client-only `createRoot`; `index.html` is a static Vite shell. Page metadata is mutated client-side by `src/hooks/usePageMeta.ts`.

## Exact route findings
- `src/App.tsx` defines `/notebooks`, `/knowledge-graph`, and `/second-brain` but has no `/wisdom-map` or `/reflections` aliases.
- `/auth/diagnostics` is mounted only inside `!import.meta.env.PROD`, which explains the production 404 despite `AuthDiagnosticsPage.tsx` existing.
- Catch-all `*` renders `NotFound` client-side; HTTP-level SSR/404 behavior is not implemented in the React entry.
- `src/components/layout/AppShell.tsx` provides persistent nav only for `/`, `/chat`, `/practices`, `/profile`; it has no origin-aware back/close/breadcrumb contract.
- `src/components/chat/DesktopSidebar.tsx` hardcodes bare `navigate('/practices')`, `navigate('/notebooks')`, `navigate('/knowledge-graph')`, and `navigate('/second-brain')` calls without `returnTo`, conversation ID, or query state.
- The same bare-navigation pattern exists in `src/components/chat/MobileConversationSheet.tsx`.
- `src/pages/KnowledgeGraphPage.tsx` has a local `navigate(-1)` close handler with `/chat` fallback, but no explicit origin state.
- `src/pages/StudyNotebookPage.tsx` renders an H1 but uses `AppShell` without a title/back contract; no close/back action is present.
- `src/pages/SecondBrainPage.tsx` calls `secondBrainApi.provision()` and `listItems()` on load. Failures only trigger destructive toasts; there is no persistent inline retry/error state. It renders its own H1.

## Chat/grounding findings from repository overview
- `backend/app/api/chat.py`: `/api/chat` and `/api/chat/v2` expose citations, answer_evidence, guidance_plan; the SSE poller emits a `done` event with empty `{}` at completion, so final metadata may be dropped.
- `backend/app/chat_engine.py`: non-stream and stream contracts are asymmetric. Streaming final chunks include citations but not the richer evidence envelope. `_coerce_citations` can downgrade citation dictionaries to strings.
- `backend/app/pipeline/result.py`: `PipelineResult`, `AnswerEvidence`, `TeachingAttribution`, and `GuidancePlan` already model evidence/source data.
- `backend/app/pipeline/stages/glue_stages.py`: assembles citations_verified, orphan_citations_stripped, answer_evidence, and guidance_plan; sourced answers become `Guidance inspired by retrieved teachings`, no-citation answers become `Reflective guidance`.
- `backend/app/evidence_support.py`: source_count <= 0 maps to `Limited support`; this should be used to prevent zero-source answers from appearing fully grounded.
- `src/components/chat/ChatInterface.tsx`: streamed final message commit captures answerEvidence, guidancePlan, citations; Serene Mind gating is frontend-state-driven around lines 1157–1220.
- `src/components/chat/ChatMessage.tsx`: provenance panel falls back to `Reflective guidance without a direct source link` when citations are absent; generic transparency label is not tied to a strict grounding state.
- `src/pages/ChatPage.tsx`: only sr-only H1; it also owns continue-where-you-left-off dialog driven by `last_conversation_id`.

## Required next reconnaissance reads
- `src/components/chat/MobileConversationSheet.tsx`
- `src/pages/KnowledgeGraphPage.tsx`
- `src/pages/ChatPage.tsx`
- `src/components/chat/ChatInterface.tsx` around streaming/gating lines
- `src/components/chat/ChatMessage.tsx` around evidence rendering
- `src/hooks/usePageMeta.ts`, `src/main.tsx`, `index.html`
- `backend/app/api/chat.py`, `backend/app/chat_engine.py`, `backend/app/pipeline/result.py`, `backend/app/pipeline/stages/glue_stages.py`, `backend/app/evidence_support.py`
- Existing test config and route/chat tests

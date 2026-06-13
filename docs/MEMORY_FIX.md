# Memory Layer — Why it isn't updating and how to fix it

_Last updated: 2026-06-13_

## TL;DR

`src/lib/memoryApi.ts` calls `${VITE_BACKEND_URL}/api/memory/*` — the self-hosted
FastAPI memory router. **That backend is not deployed to Lovable production**, so
every call either 404s or is silently swallowed (`getCore`, `getSummaries`,
`getRelevant`, `getConversations` all return `[]` / `null` on error).

The Supabase tables `guru_core_memory`, `guru_memories`, and
`guru_session_summaries` already exist with correct RLS — nothing client-side
writes to them, so the Memory tab on `/profile` always looks empty.

Fix = move the memory layer onto Lovable Cloud (Supabase + a tiny edge function
for embeddings) and keep the `memoryApi` surface stable so `MemoryManager.tsx`
and `ChatHeader.tsx` keep working unchanged.

---

## 1. New edge function — `memory-embed`

Path: `supabase/functions/memory-embed/index.ts`

- Verify JWT, read `auth.uid()` (reject with 401 if missing).
- Input: `{ text: string }`.
- Call **Lovable AI Gateway** `/v1/embeddings` with
  `model: "google/gemini-embedding-001"` and the raw text.
- The Supabase column is `vector(1024)`; Gemini returns 3072 dims. Either:
  - Change the column to `vector(3072)` (recommended, drops/recreates the HNSW
    index) **or**
  - Truncate/pad the returned vector to 1024 dims (works but loses fidelity).
- Return `{ embedding: number[] }`. Never expose `LOVABLE_API_KEY`.

Reference: `<ai-embeddings>` snippet in agent context, OpenAI-compatible call.

## 2. Refactor `src/lib/memoryApi.ts` to talk to Supabase directly

| Method | New backing |
| --- | --- |
| `add(text)` | invoke `memory-embed` → `insert into guru_memories (user_id, content, embedding, source='explicit')` |
| `list(page, pageSize)` | `select … from guru_memories order by created_at desc` (RLS scopes to user) |
| `forget(id)` | `delete from guru_memories where id=…` |
| `getCore()` | `select * from guru_core_memory limit 1` |
| `setCore(text)` | upsert `guru_core_memory` (new method; used by Profile) |
| `getSummaries(limit)` | `select … from guru_session_summaries order by created_at desc limit n` |
| `getRelevant(query, k)` | invoke `memory-embed` → call existing `match_user_memories` RPC |
| `getConversations(limit)` | derive from `conversations` + last message; drop dead endpoint |

Keep the same `MemoryApiError` shape so callers don't change.

## 3. Auto-extract memories from chat

This is the **real** "memory not updating" the user feels: nothing fires after
an assistant turn.

New edge function `supabase/functions/memory-extract/index.ts`:

- Input: `{ user_message, assistant_message, conversation_id }`.
- Prompts Lovable AI (`google/gemini-2.5-flash`) with a system message:
  > Extract 0–3 stable first-person facts about the seeker from this exchange.
  > Return JSON `{ facts: string[] }`. Skip if nothing durable was shared.
- For each fact: embed via `memory-embed` and insert with `source='extracted'`.
- **Dedup**: before insert, run `match_user_memories(embedding, 1, 0.92)` and
  skip if similarity ≥ 0.92.

Call it fire-and-forget from `ChatInterface.tsx` after every assistant response
completes streaming (`onDone` of `sendMessageStreaming`). Failures must be
silent — memory is best-effort.

## 4. Inject memories into the chat prompt

Before sending a user turn:

1. Call `memoryApi.getRelevant(userText, 5)`.
2. Prepend a `[Seeker context]` block to the system prompt sent to `guru-chat`.
3. When ≥1 memory was used, render a small **"🧠 Memory used"** chip in the
   assistant message footer; tapping it opens a popover listing the
   memory snippets.

In `supabase/functions/guru-chat/index.ts`, accept an optional
`seeker_context: string` field on the request, validate it as text only, and
prepend it to the existing system prompt (after the trusted persona block,
**never** replacing it — guards against prompt injection).

## 5. Profile page additions

In `MemoryManager.tsx`:

- New "Core memory" card at the top — single textarea (≤2048 chars) that calls
  `memoryApi.setCore(text)`. This is the slow-moving stable identity ("I'm a
  software engineer in Bengaluru, daily meditator…").
- Show source badges on episodic memories (`explicit` vs `extracted`).
- Add a "What did I share recently?" tab that lists the last 10
  `guru_session_summaries`.

## 6. Validation checklist

- [ ] Sign in, send a message → within ~3s a new row appears in `guru_memories`
      for that user (check via Backend → SQL).
- [ ] Send a related question → "🧠 Memory used" chip appears on the reply.
- [ ] Refresh `/profile` → MemoryManager shows the new memory.
- [ ] Click "Forget" → row deleted, list updates.
- [ ] Sign out → MemoryManager shows "Sign in to see memories", no console
      errors.
- [ ] Network tab: zero calls to `VITE_BACKEND_URL/api/memory/*` once the
      refactor lands.

## 7. Migration of existing data

There is no production data in `guru_memories` yet (the write path was never
live). No migration needed beyond resizing the embedding column to 3072 dims if
you keep the Gemini default.

## 8. Out of scope (for this fix)

- Cross-tab realtime memory sync — single-tab refresh is enough for v1.
- Nightly memory decay / consolidation — leave as a future cron edge function.
- Multimodal memories (images/audio) — text only for now.

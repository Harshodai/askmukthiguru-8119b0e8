# Memory Layer — Why it isn't updating and how to fix it

_Updated: 2026-10-21 (consent- and embedding-contract audit)_

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

## 1. Edge function — `memory-embed` (current contract)

Path: `supabase/functions/memory-embed/index.ts`

- Verify JWT; reject requests without a valid signed-in user.
- Input: `{ text: string }`, maximum 8,000 characters.
- Generate vectors only with the same BGE-M3 embedding space used by Python
  retrieval and the existing `guru_memories.embedding vector(1024)` schema.
- Configure `OLLAMA_URL` to a reachable Ollama-compatible BGE-M3 embedding
  endpoint. The function validates that every dimension is finite and the vector
  contains exactly 1024 dimensions.
- If the endpoint is absent, times out, or returns an unexpected dimension,
  fail closed. Never truncate, pad, or substitute another embedding model:
  equal dimensions do not make model vector spaces compatible.
- Return `{ embedding: number[], backend: "ollama" }`; never expose server secrets.

The Edge runtime cannot reach a developer laptop through `localhost`; configure
a private/reachable deployment endpoint before enabling memory enrichment.

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

The current opt-in path queues `pending_extractions` after a genuinely
completed, non-blocked, non-incognito response. It is gated by
`VITE_MEMORY_EXTRACTION_ENABLED=true` and only queues when the current consent
receipt can be read. The background `memory-extract-drain` worker rechecks the
exact original receipt before/after provider calls, uses an atomic lease, scopes
deduplication by user and tenant, validates extraction output, and clears the
plaintext payload on terminal outcomes. Consent revocation or a later re-grant
does not authorize old queued text. Keep the feature disabled until the required
Edge secrets/schedule and a real end-to-end consent/erasure smoke test are done.

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

## Embedding model invariant (required)

The legacy `guru_memories.embedding` column is `vector(1024)`, and the Python
memory retrieval pipeline uses BAAI/BGE-M3. Vector length alone is not enough:
embeddings generated by Gemini and BGE-M3 must not be mixed in one searchable
index. The Edge Function `_shared/embed.ts` therefore uses BGE-M3 only and
fails closed unless `OLLAMA_URL` points to a reachable Ollama-compatible
`/v1/embeddings` endpoint serving `bge-m3`. Configure the secret in each
deployed Edge Function environment; `localhost` on a managed Edge runtime is
not the developer's laptop. If this endpoint is unavailable, memory extraction
is not persisted instead of writing incompatible vectors. Verify an actual
1024-dimensional response and a semantic retrieval round trip before enabling
the worker in production.

## Required Edge Function deployment checks

- Deploy `memory-extract-drain` with `verify_jwt = false` only because the
  handler independently requires `x-cron-secret`; do not remove that check.
  The Supabase platform JWT gate runs before the handler, but the supported
  `pg_cron/pg_net` pattern sends an API key header rather than a user JWT.
- Set a high-entropy `CRON_SECRET` with `supabase secrets set CRON_SECRET=...`.
  Store the same value in Supabase Vault under `memory_extraction_cron_secret`;
  store the project URL and publishable key as `memory_extraction_project_url`
  and `memory_extraction_apikey`. Do not commit the values.
- Schedule the worker using the Vault values. Example (run once in the target
  database after creating the three Vault secrets):

```sql
SELECT cron.schedule(
  'memory-extract-drain',
  '* * * * *',
  $$
  SELECT net.http_post(
    url := (SELECT decrypted_secret FROM vault.decrypted_secrets
            WHERE name = 'memory_extraction_project_url')
           || '/functions/v1/memory-extract-drain',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'apikey', (SELECT decrypted_secret FROM vault.decrypted_secrets
                 WHERE name = 'memory_extraction_apikey'),
      'x-cron-secret', (SELECT decrypted_secret FROM vault.decrypted_secrets
                        WHERE name = 'memory_extraction_cron_secret')
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 30000
  );
  $$
);
```

Do not certify the worker as active until a real scheduled invocation is
visible in Edge Function logs and a consented test job reaches a scrubbed
terminal state. The repository environment does not have the production
Vault secrets, so no live invocation is claimed here.

# Backend Integration Spec — Custom Assistants & Notes

Lovable Cloud side is done. This document is the contract the Python/FastAPI backend must implement so the new **Custom Assistants / Sub-Modules** and **Notes** features work end-to-end without regressing any existing chat behavior.

---

## 1. New Supabase tables (already created)

| Table | Purpose |
|---|---|
| `public.notes` | User notes (title, body, tags, source_message_id, source_conversation_id, is_favorite). RLS scoped to `auth.uid()`. |
| `public.assistants` | Curated personas. Fields: `slug, name, description, avatar_url, system_prompt, starter_questions jsonb, knowledge_tags text[], visibility (public|link|private), invite_code, created_by`. |
| `public.assistant_access` | `(user_id, assistant_id)` grants for link-gated/private assistants. |
| `public.conversations.assistant_id` | New nullable FK so each conversation is bound to one assistant. |

Seeded slugs: `general`, `relationship`, `sky` (link-gated).

The backend does **not** need to touch these tables for the MVP — the frontend reads/writes via PostgREST + RLS directly. The backend only needs to **receive** the assistant context on each chat request and use it for retrieval filtering + system prompt override.

---

## 2. `POST /api/chat` — additive fields

Frontend will start sending these optional fields on every chat request. The backend must accept them, default safely when absent (preserving today's behavior), and never 4xx if they're missing.

```json
{
  "messages": [...],
  "user_message": "...",
  "meditation_step": null,

  // NEW — optional
  "assistant": {
    "slug": "relationship",
    "system_prompt": "You are a relationship guide rooted in...",
    "knowledge_tags": ["relationship", "connection"]
  }
}
```

### Backend requirements

1. **System prompt override**: if `assistant.system_prompt` is present, replace the default persona prompt in the pipeline's prompt assembly with this value (or prepend it). Keep all safety / Serene Mind / disclaimer prompt layers intact.
2. **Knowledge filtering**: if `assistant.knowledge_tags` is non-empty, filter Qdrant retrieval to chunks whose `metadata.tags` intersect with the supplied tags.
   - Add a `tags text[]` payload field to `kb_sources` / chunk metadata if not already present.
   - When `knowledge_tags` is empty or absent → retrieve across all corpora (today's behavior).
3. **SKY corpus isolation**: chunks ingested as SKY must carry `tags: ["sky", "private"]`. The `general` and `relationship` assistants must **never** retrieve SKY chunks. Implement as a hard filter at the Qdrant query layer: if `"sky"` is not in the request's `knowledge_tags`, exclude any chunk whose tags contain `"sky"`.
4. **Telemetry**: log `assistant_slug` on every `chat_queries` row so admin can break down quality per assistant.
5. **Backwards compatibility**: requests without an `assistant` block must behave exactly as today.

---

## 3. Ingestion: tagging existing + new content

The ingestion pipeline (`backend/ingest/pipeline.py`) needs a `tags: list[str]` parameter:

```python
IngestionPipeline.ingest_url(url, tags=["sky"], visibility="private")
```

- Persist tags into the Qdrant chunk payload (`payload.tags`) and into `kb_sources.tags` (add column if missing).
- Default tags = `["general"]` for backwards compatibility.
- Add a CLI flag `--tags sky,private` to `scripts/ingestion/bulk_ingest_*.py`.

For the **ingestion UI** (`/ingest/`), add a tag multi-select so curators can route content to specific assistants at ingest time.

---

## 4. Invite redemption (optional backend support)

Frontend redeems `sky-...` invite codes through a future Supabase edge function (`redeem-assistant-invite`) — backend Python does **not** need to handle this. Document only.

---

## 5. Notes — backend not required

Notes are pure CRUD via Supabase + RLS. The backend never touches `public.notes`.

If later we want server-side note enrichment (auto-tagging from LLM, semantic search), expose:

```
POST /api/notes/auto-tag    { body: string } → { tags: string[] }
POST /api/notes/search       { query: string } → { note_ids: string[] }
```

Out of MVP scope.

---

## 6. Testing & non-regression checklist

Before shipping:

- [ ] `POST /api/chat` without `assistant` → identical responses to today (run `backend/benchmarks/smoke_doctrine.py`).
- [ ] `POST /api/chat` with `assistant.knowledge_tags=["sky"]` against a corpus lacking SKY chunks → returns gracefully with "no teachings found yet" path, never 500.
- [ ] `POST /api/chat` with `assistant.knowledge_tags=["general"]` → no SKY chunks appear in retrieval.
- [ ] `chat_queries.assistant_slug` column is populated.
- [ ] All existing tests under `backend/tests/` still pass.

---

## 7. Rollout order (recommended)

1. Deploy backend changes that **accept** the optional `assistant` block but ignore filtering (logs slug only).
2. Re-ingest a small SKY pilot with `tags=["sky"]`.
3. Enable filtering. Verify smoke tests.
4. Open SKY invite codes to pilot users.

---

## 8. Pointers in the existing codebase

| Concern | File |
|---|---|
| Chat request schema | `backend/app/contracts/` (add optional `AssistantContext`) |
| Prompt assembly | `backend/rag/prompts.py`, `backend/rag/nodes/generation.py` (`context_engineer`) |
| Retrieval filtering | `backend/services/qdrant_service.py` (`search` filter param) |
| Ingestion tags | `backend/ingest/pipeline.py`, `backend/services/qdrant_service.py` upsert |
| Telemetry write | `backend/app/telemetry_sink.py` (add `assistant_slug` column) |

Keep changes additive and behind feature flags where reasonable so nothing else breaks.

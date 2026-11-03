-- ============================================================================
-- REVERT: Drop guru_memories.source_conversation_id. NOTE: the stored link back
-- to the originating conversation is lost; the memory text itself is untouched.
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
--
-- REVERT:
-- ALTER TABLE public.guru_memories DROP CONSTRAINT IF EXISTS guru_memories_source_conversation_id_len;
-- ALTER TABLE public.guru_memories DROP COLUMN IF EXISTS source_conversation_id;
-- ============================================================================

-- Per-memory provenance for the Profile memory list and the personal Wisdom Map.
--
-- The extraction queue already carries the conversation id of the chat turn a
-- fact came from (pending_extractions.payload.conversation_id), but the insert
-- into guru_memories dropped it, so the UI could not link a memory to its
-- origin. This column stores it. It is NULL for every memory written before this
-- migration and for explicit/manual memories: the UI shows "source unavailable"
-- for those and never guesses a link.
--
-- No backfill, no index (read only as part of the row), no policy change: the
-- existing user_id/tenant_id RLS already scopes the row, and the value lives and
-- dies with the memory row (forget, consent withdrawal and account erasure
-- delete the row, so no orphaned pointer survives).
--
-- ORDER: apply this migration BEFORE deploying the memory-extract and
-- memory-extract-drain edge functions that write the column. Both functions
-- retry the insert without the column when it is missing, so a late migration
-- degrades to "source unavailable" instead of losing memories.

ALTER TABLE public.guru_memories
  ADD COLUMN IF NOT EXISTS source_conversation_id text;

ALTER TABLE public.guru_memories
  DROP CONSTRAINT IF EXISTS guru_memories_source_conversation_id_len;
ALTER TABLE public.guru_memories
  ADD CONSTRAINT guru_memories_source_conversation_id_len
  CHECK (source_conversation_id IS NULL OR char_length(source_conversation_id) <= 200);

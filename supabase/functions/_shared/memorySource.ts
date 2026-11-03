/**
 * Provenance helpers for memories written by the extraction functions.
 *
 * `guru_memories.source_conversation_id` records which chat conversation a fact
 * came from so the UI can link back to it. The value comes from a client request,
 * so it is bounded and character-restricted before it is stored; anything that
 * does not look like an id is dropped and the memory keeps no source (the UI then
 * shows "source unavailable"). Never invent or default a value.
 */

const SOURCE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/;

export function sanitizeSourceConversationId(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return SOURCE_ID_PATTERN.test(trimmed) ? trimmed : null;
}

/** Postgres undefined_column (42703) or PostgREST schema-cache miss (PGRST204). */
export function isMissingColumnError(error: { code?: string } | null | undefined): boolean {
  return error?.code === "42703" || error?.code === "PGRST204";
}

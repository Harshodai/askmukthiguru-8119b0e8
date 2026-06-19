/**
 * Resolve which message anchor to scroll to when resuming a chat.
 *
 * Contract:
 *  - Prefers the explicit `lastMessageId` if it exists in the list.
 *  - Falls back to the last message id when missing or not found.
 *  - Returns `null` if the list is empty.
 *
 * Pure function — unit-testable, no DOM access. The caller does the
 * `document.querySelector('[data-message-id="…"]')` lookup.
 */
export interface ResumeMessageRef {
  id: string;
}

export const resolveResumeAnchor = (
  messages: ReadonlyArray<ResumeMessageRef>,
  lastMessageId: string | null | undefined,
): string | null => {
  if (!messages.length) return null;
  if (lastMessageId) {
    const hit = messages.find((m) => m.id === lastMessageId);
    if (hit) return hit.id;
    // Deleted / unknown id — gracefully fall through.
  }
  return messages[messages.length - 1].id;
};

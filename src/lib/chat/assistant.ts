/**
 * Reads the selected assistant slug from localStorage and builds the minimal
 * client request field. Prompts, retrieval tags, corpus scope, and access are
 * resolved server-side; no assistant configuration is trusted from the client.
 */
export function buildAssistantContext(): { assistant?: { slug: string } } {
  try {
    if (typeof window === 'undefined') return {};
    const slug = window.localStorage.getItem('askmukthi.assistant.slug');
    if (!slug || slug === 'general') return {};
    return { assistant: { slug } };
  } catch {
    return {};
  }
}

import { supabase } from '@/integrations/supabase/client';

/**
 * Reads selected assistant from localStorage (set by useAssistants hook) and
 * builds an optional payload field. Backend treats missing assistant as today's default.
 * Cached briefly so we don't hit Supabase on every request.
 */
let cachedAssistant: { slug: string; system_prompt: string; knowledge_tags: string[]; ts: number } | null = null;

export function buildAssistantContext(): { assistant?: { slug: string; system_prompt: string; knowledge_tags: string[] } } {
  try {
    if (typeof window === 'undefined') return {};
    const slug = window.localStorage.getItem('askmukthi.assistant.slug');
    if (!slug || slug === 'general') return {};
    if (cachedAssistant && cachedAssistant.slug === slug && Date.now() - cachedAssistant.ts < 60_000) {
      const { ts: _ts, ...rest } = cachedAssistant;
      return { assistant: rest };
    }
    // Fire-and-forget refresh; synchronous return uses last cache or skips field.
    void (async () => {
      const { data } = await supabase
        .from('assistants')
        .select('slug, system_prompt, knowledge_tags')
        .eq('slug', slug)
        .maybeSingle();
      if (data) {
        cachedAssistant = {
          slug: data.slug,
          system_prompt: data.system_prompt ?? '',
          knowledge_tags: data.knowledge_tags ?? [],
          ts: Date.now(),
        };
      }
    })();
    if (cachedAssistant && cachedAssistant.slug === slug) {
      const { ts: _ts, ...rest } = cachedAssistant;
      return { assistant: rest };
    }
    return {};
  } catch {
    return {};
  }
}

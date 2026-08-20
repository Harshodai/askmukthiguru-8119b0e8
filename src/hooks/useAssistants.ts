import { useCallback, useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { BACKEND_URL } from "@/lib/backendUrl";

export type AssistantVisibility = "public" | "link" | "private";

export interface Assistant {
  id: string;
  slug: string;
  name: string;
  description: string;
  avatar_url: string | null;
  starter_questions: string[];
  visibility: AssistantVisibility;
}

const SELECTED_KEY = "askmukthi.assistant.slug";
const catalogUrl = `${BACKEND_URL}/api/assistants`;

/**
 * Fetch only the server-authorized assistant catalog. Prompts, invite codes,
 * corpus scope, and retrieval tags are intentionally not exposed here.
 */
export function useAssistants() {
  const [assistants, setAssistants] = useState<Assistant[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSlug, setSelectedSlugState] = useState<string>(() => {
    if (typeof window === "undefined") return "general";
    return window.localStorage.getItem(SELECTED_KEY) ?? "general";
  });

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const { data } = await supabase.auth.getSession();
        const headers: HeadersInit = data.session?.access_token
          ? { Authorization: `Bearer ${data.session.access_token}` }
          : {};
        const response = await fetch(catalogUrl, { headers });
        if (!response.ok) throw new Error(`Assistant catalog failed: ${response.status}`);
        const payload = (await response.json()) as { assistants?: Assistant[] };
        if (active) setAssistants(Array.isArray(payload.assistants) ? payload.assistants : []);
      } catch {
        if (active) setAssistants([]);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const setSelectedSlug = useCallback((slug: string) => {
    setSelectedSlugState(slug);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SELECTED_KEY, slug);
    }
  }, []);

  const selected =
    assistants.find((a) => a.slug === selectedSlug) ??
    assistants.find((a) => a.slug === "general") ??
    assistants[0] ??
    null;

  return { assistants, selected, selectedSlug, setSelectedSlug, loading };
}

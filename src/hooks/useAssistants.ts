import { useCallback, useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";

export type AssistantVisibility = "public" | "link" | "private";

export interface Assistant {
  id: string;
  slug: string;
  name: string;
  description: string;
  avatar_url: string | null;
  system_prompt: string;
  starter_questions: string[];
  knowledge_tags: string[];
  visibility: AssistantVisibility;
}

const SELECTED_KEY = "askmukthi.assistant.slug";

/**
 * useAssistants — fetches assistants the current user is allowed to see
 * (public + granted via assistant_access + own). Persists selected slug
 * to localStorage so it survives reloads.
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
      const { data, error } = await supabase
        .from("assistants")
        .select("id, slug, name, description, avatar_url, system_prompt, starter_questions, knowledge_tags, visibility")
        .order("visibility", { ascending: true })
        .order("name", { ascending: true });
      if (!active) return;
      if (error) {
        setAssistants([]);
      } else {
        setAssistants(
          (data ?? []).map((a: any) => ({
            ...a,
            starter_questions: Array.isArray(a.starter_questions)
              ? a.starter_questions
              : [],
            knowledge_tags: a.knowledge_tags ?? [],
          })) as Assistant[],
        );
      }
      setLoading(false);
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

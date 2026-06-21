import { useCallback, useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";

export interface Note {
  id: string;
  user_id: string;
  title: string;
  body: string;
  tags: string[];
  source_message_id: string | null;
  source_conversation_id: string | null;
  is_favorite: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateNoteInput {
  title?: string;
  body: string;
  tags?: string[];
  source_message_id?: string | null;
  source_conversation_id?: string | null;
}

/**
 * useNotes — CRUD over `public.notes` scoped to current user via RLS.
 * Falls back to empty list when not signed in (no localStorage fallback by design;
 * notes are an authenticated feature surfaced from Profile).
 */
export function useNotes() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    const { data: sessionData } = await supabase.auth.getSession();
    if (!sessionData.session) {
      setNotes([]);
      setLoading(false);
      return;
    }
    const { data, error: err } = await supabase
      .from("notes")
      .select("*")
      .order("updated_at", { ascending: false });
    if (err) {
      setError(err.message);
      setNotes([]);
    } else {
      setNotes((data ?? []) as Note[]);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createNote = useCallback(
    async (input: CreateNoteInput): Promise<Note | null> => {
      const { data: sessionData } = await supabase.auth.getSession();
      const userId = sessionData.session?.user.id;
      if (!userId) return null;

      const title =
        input.title?.trim() ||
        input.body.split("\n")[0]?.slice(0, 80) ||
        "Untitled";

      const { data, error: err } = await supabase
        .from("notes")
        .insert({
          user_id: userId,
          title,
          body: input.body,
          tags: input.tags ?? [],
          source_message_id: input.source_message_id ?? null,
          source_conversation_id: input.source_conversation_id ?? null,
        })
        .select("*")
        .single();

      if (err) {
        setError(err.message);
        return null;
      }
      setNotes((prev) => [data as Note, ...prev]);
      return data as Note;
    },
    [],
  );

  const updateNote = useCallback(
    async (id: string, patch: Partial<CreateNoteInput & { is_favorite: boolean }>) => {
      const { data, error: err } = await supabase
        .from("notes")
        .update(patch)
        .eq("id", id)
        .select("*")
        .single();
      if (err) {
        setError(err.message);
        return null;
      }
      setNotes((prev) =>
        prev.map((n) => (n.id === id ? (data as Note) : n)).sort(
          (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
        ),
      );
      return data as Note;
    },
    [],
  );

  const deleteNote = useCallback(async (id: string) => {
    const { error: err } = await supabase.from("notes").delete().eq("id", id);
    if (err) {
      setError(err.message);
      return false;
    }
    setNotes((prev) => prev.filter((n) => n.id !== id));
    return true;
  }, []);

  return { notes, loading, error, refresh, createNote, updateNote, deleteNote };
}

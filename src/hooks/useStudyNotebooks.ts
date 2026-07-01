import { useState, useCallback, useEffect } from "react";

export interface StudyNotebook {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
}

export type NotebookCitation = string | { url: string; title?: string; quote?: string; channel_name?: string };

export interface NotebookItem {
  id: string;
  notebook_id: string;
  query: string;
  answer: string;
  citations: NotebookCitation[];
  source_episode_id: string | null;
  created_at: string;
}

function errMsg(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback;
}

async function getToken(): Promise<string | null> {
  try {
    const { supabase } = await import("@/integrations/supabase/client");
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  } catch {
    return null;
  }
}

const BASE = (import.meta.env.VITE_BACKEND_URL || "http://localhost:8000") + "/api";

export function useStudyNotebooks() {
  const [notebooks, setNotebooks] = useState<StudyNotebook[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const headers: Record<string, string> = { Accept: "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${BASE}/notebooks`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as StudyNotebook[];
      setNotebooks(data ?? []);
    } catch (e: unknown) {
      setError(errMsg(e, "Failed to load notebooks"));
      setNotebooks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createNotebook = useCallback(async (title: string): Promise<StudyNotebook | null> => {
    try {
      const token = await getToken();
      const headers: Record<string, string> = {
        Accept: "application/json",
        "Content-Type": "application/json",
      };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${BASE}/notebooks`, {
        method: "POST",
        headers,
        body: JSON.stringify({ title }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as StudyNotebook;
      setNotebooks((prev) => [data, ...prev]);
      return data;
    } catch (e: unknown) {
      setError(errMsg(e, "Failed to create notebook"));
      return null;
    }
  }, []);

  const deleteNotebook = useCallback(async (id: string): Promise<boolean> => {
    try {
      const token = await getToken();
      const headers: Record<string, string> = { Accept: "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${BASE}/notebooks/${id}`, { method: "DELETE", headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setNotebooks((prev) => prev.filter((n) => n.id !== id));
      return true;
    } catch (e: unknown) {
      setError(errMsg(e, "Failed to delete notebook"));
      return false;
    }
  }, []);

  const addItem = useCallback(
    async (
      notebookId: string,
      item: { query: string; answer: string; citations?: NotebookCitation[]; source_episode_id?: string | null }
    ): Promise<NotebookItem | null> => {
      try {
        const token = await getToken();
        const headers: Record<string, string> = {
          Accept: "application/json",
          "Content-Type": "application/json",
        };
        if (token) headers["Authorization"] = `Bearer ${token}`;
        const res = await fetch(`${BASE}/notebooks/${notebookId}/items`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            query: item.query,
            answer: item.answer,
            citations: item.citations ?? [],
            source_episode_id: item.source_episode_id ?? null,
          }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as NotebookItem;
      } catch (e: unknown) {
        setError(errMsg(e, "Failed to add item"));
        return null;
      }
    },
    []
  );

  const listItems = useCallback(async (notebookId: string): Promise<NotebookItem[]> => {
    try {
      const token = await getToken();
      const headers: Record<string, string> = { Accept: "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${BASE}/notebooks/${notebookId}/items`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return (await res.json()) as NotebookItem[];
    } catch (e: unknown) {
      setError(errMsg(e, "Failed to load items"));
      return [];
    }
  }, []);

  return { notebooks, loading, error, refresh, createNotebook, deleteNotebook, addItem, listItems };
}
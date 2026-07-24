import { useState, useCallback, useEffect, useRef } from "react";
import { supabase } from "@/integrations/supabase/client";

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
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  } catch {
    return null;
  }
}

import { BACKEND_URL_OR_LOCAL } from "@/lib/backendUrl";
const BASE = BACKEND_URL_OR_LOCAL + "/api";

const DEFAULT_DEMO_NOTEBOOKS: StudyNotebook[] = [
  { id: 'nb-1', user_id: 'demo-user', title: '🪷 Beautiful State Reflections & Teachings', created_at: new Date().toISOString() },
  { id: 'nb-2', user_id: 'demo-user', title: '🧘 Sacred Breathwork & Serene Mind Practice Notes', created_at: new Date().toISOString() },
  { id: 'nb-3', user_id: 'demo-user', title: '✨ Sri Preethaji & Sri Krishnaji Doctrine Insights', created_at: new Date().toISOString() },
];

export function useStudyNotebooks() {
  const [notebooks, setNotebooks] = useState<StudyNotebook[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    if (isMounted.current) {
      setLoading(true);
      setError(null);
    }
    try {
      const token = await getToken();
      const headers: Record<string, string> = { Accept: "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${BASE}/notebooks`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as StudyNotebook[];
      if (isMounted.current) {
        setNotebooks(Array.isArray(data) ? data : []);
      }
    } catch {
      if (isMounted.current) {
        setNotebooks(DEFAULT_DEMO_NOTEBOOKS);
      }
    } finally {
      if (isMounted.current) {
        setLoading(false);
      }
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
      const items = (await res.json()) as NotebookItem[];
      return Array.isArray(items) ? items : [];
    } catch {
      return getSampleItems(notebookId);
    }
  }, []);

function getSampleItems(id: string): NotebookItem[] {
  return [
    {
      id: `item-${id}-1`,
      notebook_id: id,
      query: 'What is the nature of the Beautiful State?',
      answer: 'The Beautiful State is a state of inner connection, joy, love, compassion, and vitality. When you are not in a beautiful state, your default state is stress.',
      citations: ['Sri Preethaji — The Four Sacred Keys', 'Ekam Wisdom Corpus Vol 1'],
      source_episode_id: null,
      created_at: new Date().toISOString(),
    },
    {
      id: `item-${id}-2`,
      notebook_id: id,
      query: 'How does Serene Mind sacred breathwork dissolve anxiety?',
      answer: 'Through rhythmic 4-4-4-4 breathing, the autonomic nervous system shifts from sympathetic fight-or-flight to parasympathetic calm, quieting self-centric chatter.',
      citations: ['Sri Krishnaji — Awakening to Peace'],
      source_episode_id: null,
      created_at: new Date().toISOString(),
    }
  ];
}

  return { notebooks, loading, error, refresh, createNotebook, deleteNotebook, addItem, listItems };
}
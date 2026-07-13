import { useState, useCallback } from 'react';
import { supabase } from '@/integrations/supabase/client';

import { BACKEND_URL } from '@/lib/backendUrl';

export interface AskState {
  result: string | null;
  error: string | null;
  loading: boolean;
}

export interface UseAskDataReturn extends AskState {
  ask: (question: string, kpiContext?: string) => Promise<void>;
  reset: () => void;
}

async function apiPost(path: string, body: unknown) {
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;
  const response = await fetch(`${BACKEND_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`API error ${response.status}: ${errText}`);
  }
  return response.json();
}

export function useAskData(): UseAskDataReturn {
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const ask = useCallback(async (question: string, kpiContext?: string) => {
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await apiPost('/api/admin/ask', {
        question,
        kpi_context: kpiContext ?? '',
      });
      if (data?.response) setResult(data.response);
      else setError(data?.error ?? 'Empty response.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setResult(null);
    setError(null);
    setLoading(false);
  }, []);

  return { result, error, loading, ask, reset };
}

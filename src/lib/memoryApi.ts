/**
 * Memory API client — talks to the self-hosted FastAPI backend memory layer.
 *
 * The backend lives at VITE_BACKEND_URL (Track B of the memory plan). Memory
 * tables live in self-hosted Postgres+pgvector next to FastAPI, NOT in Lovable
 * Cloud. Auth is via Supabase JWT forwarded as a Bearer token.
 *
 * All endpoints are user-scoped server-side via the JWT.
 */

import { supabase } from '@/integrations/supabase/client';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || '';
const MEMORY_BASE = BACKEND_URL ? `${BACKEND_URL}/api/memory` : '/api/memory';

export interface GuruMemory {
  id: string;
  claim: string;
  confidence: number;
  /** ISO timestamp */
  last_seen: string;
  /** ISO timestamp */
  created_at: string;
  /** 0..1, decays nightly */
  decay_score: number;
  source: 'extracted' | 'explicit';
}

export interface CoreMemory {
  profile: {
    name?: string;
    language?: string;
    practice_level?: 'beginner' | 'intermediate' | 'committed' | 'advanced';
    dominant_themes?: string[];
    [k: string]: unknown;
  };
  updated_at: string;
}

export interface MemoryListResponse {
  memories: GuruMemory[];
  total: number;
  page: number;
  page_size: number;
}

export interface SessionSummary {
  id: string;
  session_id: string;
  summary: string;
  created_at: string;
}

export interface RelevantMemory {
  id: string;
  content: string;
  similarity: number;
  created_at: string;
}

export interface ConversationContinuity {
  session_id: string;
  started_at: string;
  key_insights?: string[];
  follow_up_suggestions?: string[];
}

export type MemoryApiErrorCode =
  | 'unauthorized'
  | 'not_configured'
  | 'network'
  | 'server_error'
  | 'feature_disabled';

export class MemoryApiError extends Error {
  code: MemoryApiErrorCode;
  status?: number;
  constructor(code: MemoryApiErrorCode, message: string, status?: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function authHeaders(): Promise<HeadersInit> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) {
    throw new MemoryApiError('unauthorized', 'Sign in to access your memories.');
  }
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  };
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401 || res.status === 403) {
    throw new MemoryApiError('unauthorized', 'Session expired.', res.status);
  }
  if (res.status === 404) {
    // Backend memory router not deployed yet — treat as disabled.
    throw new MemoryApiError(
      'feature_disabled',
      'Memory layer is not enabled on the backend.',
      404,
    );
  }
  if (!res.ok) {
    let detail = `Backend returned ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail ?? body?.message ?? detail;
    } catch {
      // ignore
    }
    throw new MemoryApiError('server_error', detail, res.status);
  }
  return res.json() as Promise<T>;
}

export const memoryApi = {
  isConfigured(): boolean {
    // If neither VITE_BACKEND_URL nor relative /api is plausibly serving the
    // memory router, callers should treat the feature as disabled.
    return Boolean(BACKEND_URL);
  },

  async list(page = 1, pageSize = 50): Promise<MemoryListResponse> {
    if (!this.isConfigured()) {
      throw new MemoryApiError('not_configured', 'Backend URL not set.');
    }
    try {
      const res = await fetch(
        `${MEMORY_BASE}/list?page=${page}&page_size=${pageSize}`,
        { headers: await authHeaders() },
      );
      return handle<MemoryListResponse>(res);
    } catch (err) {
      if (err instanceof MemoryApiError) throw err;
      throw new MemoryApiError('network', 'Could not reach memory service.');
    }
  },

  async getCore(): Promise<CoreMemory | null> {
    if (!this.isConfigured()) return null;
    try {
      const res = await fetch(`${MEMORY_BASE}/core`, {
        headers: await authHeaders(),
      });
      if (res.status === 404) return null;
      return handle<CoreMemory>(res);
    } catch (err) {
      if (err instanceof MemoryApiError && err.code === 'feature_disabled') {
        return null;
      }
      throw err;
    }
  },

  async forget(memoryId: string): Promise<void> {
    if (!this.isConfigured()) {
      throw new MemoryApiError('not_configured', 'Backend URL not set.');
    }
    const res = await fetch(`${MEMORY_BASE}/forget`, {
      method: 'POST',
      headers: await authHeaders(),
      body: JSON.stringify({ memory_id: memoryId }),
    });
    await handle<{ ok: boolean }>(res);
  },

  async add(text: string): Promise<GuruMemory> {
    if (!this.isConfigured()) {
      throw new MemoryApiError('not_configured', 'Backend URL not set.');
    }
    const trimmed = text.trim();
    if (!trimmed) {
      throw new MemoryApiError('server_error', 'Memory text cannot be empty.');
    }
    const res = await fetch(`${MEMORY_BASE}/add`, {
      method: 'POST',
      headers: await authHeaders(),
      body: JSON.stringify({ text: trimmed }),
    });
    return handle<GuruMemory>(res);
  },
};

/**
 * Memory API — Supabase-native client layer.
 *
 * Replaces the old FastAPI-dependent implementation. All reads/writes go directly
 * to Supabase tables or invoke edge functions. No VITE_BACKEND_URL required.
 *
 * Embedding is handled server-side by the `memory-embed` edge function which
 * auto-routes between Lovable AI Gateway and local Ollama — the client never
 * touches an embedding model directly.
 */

import { supabase as supabaseTyped } from '@/integrations/supabase/client';
import { BACKEND_URL } from './backendUrl';
import type { SupabaseClient } from '@supabase/supabase-js';
// Generated Supabase types do not yet include the guru_* memory tables.
// Keep the dynamic table boundary contained while retaining the official client API.
const supabase = supabaseTyped as unknown as SupabaseClient;


// ── Types ─────────────────────────────────────────────────────────────────

export interface GuruMemory {
  id: string;
  /** The remembered fact — maps to the `content` DB column. */
  content: string;
  source: 'extracted' | 'explicit';
  created_at: string;
  /** Optional enrichment fields written by some pipelines; not always present. */
  claim?: string;
  decay_score?: number;
  confidence?: number;
}

export interface CoreMemory {
  id: string;
  /** Plain text, ≤2048 chars. Whole-person stable identity. */
  content: string;
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
}

export interface PersonaResponse {
  content: string;
  updated_at: string;
}

export interface UserSkill {
  id: string;
  name: string;
  description: string;
  proficiency: number;
  practice_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationContinuity {
  session_id: string;
  started_at: string;
}

export interface KGNodeAnalytics {
  degree: number;
  betweenness: number;
  closeness: number;
  pagerank: number;
  hits_hub: number;
  hits_authority: number;
}

export interface KGNode {
  id: string;
  label: string;
  type: string;
  teacher?: string | null;
  state_category?: string | null;
  content?: string | null;
  analytics?: KGNodeAnalytics | null;
  community?: number;
}

export interface KGEdge {
  source: string;
  target: string;
  label?: string | null;
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

// ── Helpers ───────────────────────────────────────────────────────────────

async function requireSession() {
  const { data } = await supabase.auth.getSession();
  if (!data.session) {
    throw new MemoryApiError('unauthorized', 'Sign in to access your memories.');
  }
  return data.session;
}

/** Invoke a Supabase edge function with the user's JWT. */
async function invokeEdgeFn<T>(
  fn: string,
  body: Record<string, unknown>,
): Promise<T> {
  const { data, error } = await supabaseTyped.functions.invoke(fn, { body });
  if (error) {
    throw new MemoryApiError('server_error', error.message);
  }
  return data as T;
}

// BACKEND_URL imported from ./backendUrl

/**
 * Fallback save path: the FastAPI backend embeds server-side with the local
 * model. Needed because local/dev Supabase stacks often run without an edge
 * runtime, which makes `memory-embed` unreachable and broke every add.
 */
async function addViaBackend(text: string, accessToken: string, cause: unknown): Promise<GuruMemory> {
  if (!BACKEND_URL) {
    throw cause instanceof MemoryApiError
      ? cause
      : new MemoryApiError('server_error', 'Memory service unavailable.');
  }
  const res = await fetch(`${BACKEND_URL}/api/memory/add`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    throw new MemoryApiError(
      res.status === 401 ? 'unauthorized' : 'server_error',
      `Memory save failed (${res.status}).`,
    );
  }
  const saved = await res.json();
  return {
    id: saved.id,
    content: saved.claim ?? text,
    source: saved.source ?? 'explicit',
    created_at: saved.created_at || new Date().toISOString(),
  } as GuruMemory;
}

// ── Public API ─────────────────────────────────────────────────────────────

export const memoryApi = {
  /**
   * Always true — Supabase is always available to authenticated users.
   * (The old FastAPI-backed version returned false when VITE_BACKEND_URL was unset.)
   */
  isConfigured(): boolean {
    return true;
  },

  /** List all episodic memories for the current user, newest first. */
  async list(page = 1, pageSize = 50): Promise<MemoryListResponse> {
    await requireSession();
    const from = (page - 1) * pageSize;
    const to = from + pageSize - 1;

    const { data, error, count } = await supabase
      .from('guru_memories')
      .select('id, content, source, created_at', { count: 'exact' })
      .order('created_at', { ascending: false })
      .range(from, to);

    if (error) throw new MemoryApiError('server_error', error.message);

    return {
      memories: (data ?? []) as GuruMemory[],
      total: count ?? 0,
      page,
      page_size: pageSize,
    };
  },

  /**
   * Add an explicit memory — embeds server-side via `memory-embed` edge function
   * (which auto-routes to Lovable Gateway or local Ollama).
   */
  async add(text: string): Promise<GuruMemory> {
    const session = await requireSession();
    const trimmed = text.trim();
    if (!trimmed) throw new MemoryApiError('server_error', 'Memory text cannot be empty.');

    // All durable writes go through the backend's live consent receipt check.
    // A direct Supabase INSERT would bypass that application-level check when
    // the edge embedding function happened to be available.
    return addViaBackend(
      trimmed,
      session.access_token,
      new MemoryApiError(
        'not_configured',
        'The consent-authoritative memory API is required for saving memories.',
      ),
    );
  },

  /** Delete a memory by ID. RLS ensures users can only delete their own. */
  async forget(memoryId: string): Promise<void> {
    await requireSession();
    const { error } = await supabase
      .from('guru_memories')
      .delete()
      .eq('id', memoryId);
    if (error) throw new MemoryApiError('server_error', error.message);
  },

  /** Correct a memory through the ownership-checked backend path. */
  async edit(memoryId: string, text: string): Promise<void> {
    const session = await requireSession();
    if (!BACKEND_URL) throw new MemoryApiError("not_configured", "Memory correction is unavailable.");
    const res = await fetch(`${BACKEND_URL}/api/memory/edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.access_token}` },
      body: JSON.stringify({ memory_id: memoryId, text: text.trim() }),
    });
    if (!res.ok) throw new MemoryApiError(res.status === 401 ? "unauthorized" : "server_error", `Memory correction failed (${res.status}).`, res.status);
  },

  /** Read the server-authoritative consent receipt for the signed-in user. */
  async hasConsent(): Promise<boolean> {
    const session = await requireSession();
    if (!BACKEND_URL) throw new MemoryApiError('not_configured', 'Consent status is unavailable.');
    const res = await fetch(`${BACKEND_URL}/api/memory/consent`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
    if (!res.ok) {
      throw new MemoryApiError(
        res.status === 401 ? 'unauthorized' : 'server_error',
        `Consent status could not be checked (${res.status}).`,
        res.status,
      );
    }
    const result = await res.json() as { granted?: boolean };
    return result.granted === true;
  },

  /** Record explicit consent before the first memory save (backend consent-receipt table). */
  async recordConsent(granted: boolean, consentVersion = 'memory-v1'): Promise<void> {
    const session = await requireSession();
    if (!BACKEND_URL) throw new MemoryApiError("not_configured", "Consent recording is unavailable.");
    const res = await fetch(`${BACKEND_URL}/api/memory/consent`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.access_token}` },
      body: JSON.stringify({ granted, consent_version: consentVersion }),
    });
    if (!res.ok) throw new MemoryApiError(res.status === 401 ? "unauthorized" : "server_error", `Consent recording failed (${res.status}).`, res.status);
  },

  /** Erase memory and saved notebook content from every known backend store. */
  async deleteAll(): Promise<void> {
    const session = await requireSession();
    if (!BACKEND_URL) throw new MemoryApiError("not_configured", "Memory erasure is unavailable.");
    const res = await fetch(`${BACKEND_URL}/api/memory/all`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
    const result = await res.json().catch(() => null) as
      | { status?: string; failures?: unknown[] }
      | null;
    // The server reports per-store failures in a 200 body so the caller must
    // inspect the deletion receipt, not just HTTP status. Never toast success
    // when any memory plane (including Q/A notebook payloads) remains unconfirmed.
    if (!res.ok || result?.status !== "completed") {
      const failedStores = Array.isArray(result?.failures)
        ? result.failures.length
        : 0;
      const status = res.ok ? 503 : res.status;
      const detail = failedStores > 0 ? ` (${failedStores} store(s) not confirmed)` : "";
      throw new MemoryApiError(
        res.status === 401 ? "unauthorized" : "server_error",
        `Memory erasure could not be confirmed${detail}.`,
        status,
      );
    }
  },

  /** Erase all episodic reflections while preserving explicitly configured core facts. */
  async forgetAllReflections(): Promise<number> {
    const session = await requireSession();
    if (!BACKEND_URL) throw new MemoryApiError("not_configured", "Reflection erasure is unavailable.");
    const res = await fetch(`${BACKEND_URL}/api/memory/reflections`, {
      method: "DELETE", headers: { Authorization: `Bearer ${session.access_token}` },
    });
    if (!res.ok) throw new MemoryApiError(res.status === 401 ? "unauthorized" : "server_error", `Reflection erasure failed (${res.status}).`, res.status);
    const data = await res.json() as { deleted?: number };
    return data.deleted ?? 0;
  },

  /** Get the current user's core (stable identity) memory, or null if unset. */
  async getCore(): Promise<CoreMemory | null> {
    const session = await supabase.auth.getSession();
    if (!session.data.session) return null;

    const { data, error } = await supabase
      .from('guru_core_memory')
      .select('id, content, updated_at')
      .order('updated_at', { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error) {
      console.error('[memoryApi] getCore error', error.message);
      return null;
    }
    return data as CoreMemory | null;
  },

  /** Upsert the core memory (single-row per user). */
  async setCore(text: string): Promise<CoreMemory> {
    const session = await requireSession();
    const trimmed = text.trim().slice(0, 2048);
    if (!trimmed) throw new MemoryApiError('server_error', 'Core memory content cannot be empty.');
    if (!BACKEND_URL) {
      throw new MemoryApiError('not_configured', 'The consent-authoritative memory API is unavailable.');
    }

    const res = await fetch(`${BACKEND_URL}/api/memory/core`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ content: trimmed }),
    });
    if (!res.ok) {
      throw new MemoryApiError(
        res.status === 401 ? 'unauthorized' : 'server_error',
        `Core memory save failed (${res.status}).`,
        res.status,
      );
    }
    return (await res.json()) as CoreMemory;
  },

  /** Get recent session summaries. */
  async getSummaries(limit = 5): Promise<SessionSummary[]> {
    const session = await supabase.auth.getSession();
    if (!session.data.session) return [];

    const { data, error } = await supabase
      .from('guru_session_summaries')
      .select('id, session_id, summary, created_at')
      .order('created_at', { ascending: false })
      .limit(limit);

    if (error) {
      console.error('[memoryApi] getSummaries error', error.message);
      return [];
    }
    return (data ?? []) as SessionSummary[];
  },

  /**
   * Semantic search for memories relevant to `query`.
   * Embeds server-side (auto-routes to Gateway or Ollama), then calls
   * the `match_user_memories` RPC via the `memory-embed` edge function.
   */
  async getRelevant(query: string, limit = 5): Promise<RelevantMemory[]> {
    const session = await supabase.auth.getSession();
    if (!session.data.session || !query.trim()) return [];

    try {
      // Get embedding server-side
      const { embedding } = await invokeEdgeFn<{ embedding: number[]; backend: string }>(
        'memory-embed',
        { text: query.trim() },
      );

      // Call the pgvector RPC
      const { data, error } = await supabase.rpc('match_user_memories', {
        p_query_embedding: embedding as unknown as string,
        p_k: limit,
        p_min_sim: 0.6,
      });

      if (error) {
        console.error('[memoryApi] getRelevant rpc error', error.message);
        return [];
      }
      return (data ?? []) as RelevantMemory[];
    } catch (e) {
      console.error('[memoryApi] getRelevant error', e);
      return [];
    }
  },

  /** Get the user's personal knowledge graph (memories + ontology concepts).
   *  With auth: full graph (User + Memories + Concepts + edges).
   *  Without auth: public ontology view (Concepts/Teachers/Practices only).
   */
  async getKnowledgeGraph(view = 'personal'): Promise<{ nodes: KGNode[]; edges: KGEdge[] }> {
    const BACKEND = BACKEND_URL;
    if (!BACKEND) return { nodes: [], edges: [] };

    const session = await supabase.auth.getSession();
    const headers: Record<string, string> = {};
    if (session.data.session?.access_token) {
      headers['Authorization'] = `Bearer ${session.data.session.access_token}`;
    }

    try {
      const res = await fetch(`${BACKEND}/api/memory/knowledge-graph?view=${view}`, { headers });
      if (!res.ok) return { nodes: [], edges: [] };
      return await res.json();
    } catch {
      return { nodes: [], edges: [] };
    }
  },

  /** Export the knowledge graph as a standalone interactive HTML file. */
  async exportKnowledgeGraph(view = 'personal', title = 'Wisdom Map'): Promise<Blob | null> {
    const BACKEND = BACKEND_URL;
    if (!BACKEND) return null;

    const session = await supabase.auth.getSession();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (session.data.session?.access_token) {
      headers['Authorization'] = `Bearer ${session.data.session.access_token}`;
    }

    try {
      const res = await fetch(`${BACKEND}/api/memory/knowledge-graph/export`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ view, title }),
      });
      if (!res.ok) return null;
      return await res.blob();
    } catch {
      return null;
    }
  },

  /** Get recent conversation sessions (derives from chat_sessions table). */
  async getConversations(limit = 3): Promise<ConversationContinuity[]> {
    const session = await supabase.auth.getSession();
    if (!session.data.session) return [];

    const { data, error } = await supabase
      .from('chat_sessions')
      .select('id, created_at')
      .order('created_at', { ascending: false })
      .limit(limit);

    if (error) {
      console.error('[memoryApi] getConversations error', error.message);
      return [];
    }

    return (data ?? []).map((row: { id: string; created_at: string }) => ({
      session_id: row.id,
      started_at: row.created_at,
    }));
  },

  /** Get the L3 generated persona Markdown. */
  async getPersona(): Promise<PersonaResponse> {
    const BACKEND = BACKEND_URL;
    if (!BACKEND) return { content: '', updated_at: '' };

    const session = await supabase.auth.getSession();
    const headers: Record<string, string> = {};
    if (session.data.session?.access_token) {
      headers['Authorization'] = `Bearer ${session.data.session.access_token}`;
    }

    try {
      const res = await fetch(`${BACKEND}/api/memory/persona`, { headers });
      if (!res.ok) return { content: '', updated_at: '' };
      return (await res.json()) as PersonaResponse;
    } catch {
      return { content: '', updated_at: '' };
    }
  },

  /** Regenerate the L3 persona from recent L1 atoms. */
  async regeneratePersona(): Promise<PersonaResponse & { status: string }> {
    const BACKEND = BACKEND_URL;
    if (!BACKEND) return { content: '', updated_at: '', status: 'error' };

    const session = await supabase.auth.getSession();
    const headers: Record<string, string> = {};
    if (session.data.session?.access_token) {
      headers['Authorization'] = `Bearer ${session.data.session.access_token}`;
    }

    try {
      const res = await fetch(`${BACKEND}/api/memory/persona/regenerate`, {
        method: 'POST',
        headers,
      });
      if (!res.ok) return { content: '', updated_at: '', status: 'error' };
      return (await res.json()) as PersonaResponse & { status: string };
    } catch {
      return { content: '', updated_at: '', status: 'error' };
    }
  },

  /** List auto-generated skills. */
  async getSkills(): Promise<UserSkill[]> {
    const BACKEND = BACKEND_URL;
    if (!BACKEND) return [];

    const session = await supabase.auth.getSession();
    const headers: Record<string, string> = {};
    if (session.data.session?.access_token) {
      headers['Authorization'] = `Bearer ${session.data.session.access_token}`;
    }

    try {
      const res = await fetch(`${BACKEND}/api/memory/skills`, { headers });
      if (!res.ok) return [];
      return (await res.json()) as UserSkill[];
    } catch {
      return [];
    }
  },

  /** Regenerate skills from recent L1 atoms. */
  async regenerateSkills(): Promise<UserSkill[]> {
    const BACKEND = BACKEND_URL;
    if (!BACKEND) return [];

    const session = await supabase.auth.getSession();
    const headers: Record<string, string> = {};
    if (session.data.session?.access_token) {
      headers['Authorization'] = `Bearer ${session.data.session.access_token}`;
    }

    try {
      const res = await fetch(`${BACKEND}/api/memory/skills/regenerate`, {
        method: 'POST',
        headers,
      });
      if (!res.ok) return [];
      const data = await res.json();
      return (data.skills ?? []) as UserSkill[];
    } catch {
      return [];
    }
  },

  /** On-demand full reflection: refreshes persona + skills from recent atoms. */
  async reflect(): Promise<{ status: string; persona: string; skills: UserSkill[] }> {
    const BACKEND = BACKEND_URL;
    if (!BACKEND) return { status: 'error', persona: '', skills: [] };

    const session = await supabase.auth.getSession();
    const headers: Record<string, string> = {};
    if (session.data.session?.access_token) {
      headers['Authorization'] = `Bearer ${session.data.session.access_token}`;
    }

    try {
      const res = await fetch(`${BACKEND}/api/memory/reflect`, { method: 'POST', headers });
      if (!res.ok) return { status: 'error', persona: '', skills: [] };
      return await res.json();
    } catch {
      return { status: 'error', persona: '', skills: [] };
    }
  },
};

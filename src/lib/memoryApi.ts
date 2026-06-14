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

// Generated Supabase types don't yet include the guru_* memory tables.
// Cast to `any` for those queries — RLS still enforces auth/row scoping.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const supabase = supabaseTyped as any;

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

export interface ConversationContinuity {
  session_id: string;
  started_at: string;
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

    // Step 1: Get embedding from server (never exposes API key to client)
    const { embedding } = await invokeEdgeFn<{ embedding: number[]; backend: string }>(
      'memory-embed',
      { text: trimmed },
    );

    // Step 2: Insert into DB — RLS scopes to auth.uid()
    const { data, error } = await supabase
      .from('guru_memories')
      .insert({
        user_id: session.user.id,
        content: trimmed,
        embedding: embedding as unknown as string,
        source: 'explicit',
      })
      .select('id, content, source, created_at')
      .single();

    if (error) throw new MemoryApiError('server_error', error.message);
    return data as GuruMemory;
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

    // Try update first (faster path if row exists)
    const existing = await this.getCore();
    if (existing) {
      const { data, error } = await supabase
        .from('guru_core_memory')
        .update({ content: trimmed, updated_at: new Date().toISOString() })
        .eq('id', existing.id)
        .select('id, content, updated_at')
        .single();
      if (error) throw new MemoryApiError('server_error', error.message);
      return data as CoreMemory;
    }

    const { data, error } = await supabase
      .from('guru_core_memory')
      .insert({
        user_id: session.user.id,
        content: trimmed,
      })
      .select('id, content, updated_at')
      .single();
    if (error) throw new MemoryApiError('server_error', error.message);
    return data as CoreMemory;
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
};

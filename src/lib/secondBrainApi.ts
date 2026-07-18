/**
 * Second Brain API — client for the Mukthi Vault (owner-blind encrypted
 * per-user knowledge graph). Unlike memoryApi.ts, this always goes through
 * the FastAPI backend (BACKEND_URL) rather than Supabase tables directly —
 * the crypto (DEK/KEK unwrap) has to happen server-side, in-memory, per
 * request. See backend/services/second_brain/SECOND_BRAIN.md.
 */

import { getAccessToken } from './chat/auth';
import { BACKEND_URL } from './backendUrl';

export interface BrainItem {
  id: string;
  kind: 'reflection' | 'entity' | 'preference' | 'relationship' | 'journal';
  text: string;
  confidence: number;
  created_at: number;
  access_count: number;
}

export interface VaultStatus {
  user_id: string;
  wrap_mode: 'server_wrapped' | 'session_unlock';
  created: boolean;
}

export class SecondBrainApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

export async function deriveBrainUnlock(passphrase?: string): Promise<string | undefined> {
  if (!passphrase) return undefined;
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(passphrase));
  return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, "0")).join("");
}

async function authedFetch<T>(
  path: string,
  options: RequestInit = {},
  unlockPassphrase?: string,
): Promise<T> {
  if (!BACKEND_URL) {
    throw new SecondBrainApiError('Second Brain requires the backend to be configured.');
  }
  const token = await getAccessToken();
  if (!token) {
    throw new SecondBrainApiError('Sign in to access your Second Brain.', 401);
  }
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
    ...(options.headers as Record<string, string> | undefined),
  };
  if (unlockPassphrase) {
    const derived = await deriveBrainUnlock(unlockPassphrase);
    if (derived) {
      headers['X-Brain-Unlock'] = derived;
    }
  }
  const res = await fetch(`${BACKEND_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new SecondBrainApiError(
      detail?.detail || `Second Brain request failed (${res.status}).`,
      res.status,
    );
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const secondBrainApi = {
  async provision(): Promise<VaultStatus> {
    return authedFetch<VaultStatus>('/api/brain/vault', { method: 'POST' });
  },

  async enableSessionUnlock(passphrase: string): Promise<{ user_id: string; wrap_mode: string }> {
    return authedFetch('/api/brain/vault/session-unlock', {
      method: 'POST',
      body: JSON.stringify({ passphrase }),
    });
  },

  /** Irreversible: destroys the vault key, making every stored item permanently undecryptable. */
  async shred(): Promise<{ user_id: string; shredded: boolean }> {
    return authedFetch('/api/brain/vault', { method: 'DELETE' });
  },

  async addItem(
    kind: BrainItem['kind'],
    text: string,
    unlockPassphrase?: string,
  ): Promise<{ id: string }> {
    return authedFetch(
      '/api/brain/items',
      { method: 'POST', body: JSON.stringify({ kind, text, confidence: 0.8 }) },
      unlockPassphrase,
    );
  },

  async listItems(unlockPassphrase?: string): Promise<BrainItem[]> {
    return authedFetch('/api/brain/items?limit=200', {}, unlockPassphrase);
  },

  async forgetItem(itemId: string): Promise<{ forgotten: boolean }> {
    return authedFetch(`/api/brain/items/${encodeURIComponent(itemId)}`, { method: 'DELETE' });
  },

  async exportBrain(unlockPassphrase?: string): Promise<unknown> {
    return authedFetch('/api/brain/export', {}, unlockPassphrase);
  },
};

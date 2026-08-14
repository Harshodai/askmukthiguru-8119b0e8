import type { CapabilityManifest, ChatRequest, ChatResponse } from './types';

const API_BASE = (process.env.EXPO_PUBLIC_API_URL || '').replace(/\/$/, '');

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE) throw new Error('EXPO_PUBLIC_API_URL is not configured');
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export function getCapabilities(): Promise<CapabilityManifest> {
  return apiFetch<CapabilityManifest>('/api/capabilities');
}

export function sendChat(request: ChatRequest): Promise<ChatResponse> {
  return apiFetch<ChatResponse>('/api/chat', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

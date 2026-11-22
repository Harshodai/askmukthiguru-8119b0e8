import { BACKEND_URL } from '@/lib/backendUrl';

export interface WhatsAppStatus {
  linked: boolean;
  masked_phone: string | null;
  sync_history_consent: boolean;
  memory_write_consent: boolean;
  linked_at: string | null;
  return_url?: string | null;
}

export const DISCONNECTED_WHATSAPP: WhatsAppStatus = {
  linked: false, masked_phone: null, sync_history_consent: false,
  memory_write_consent: false, linked_at: null,
};
const CHALLENGE_KEY = 'pending_whatsapp_token';
const CHALLENGE_TTL_MS = 15 * 60 * 1000;

/** Retain only an opaque, expiring challenge, never a website session. */
export function rememberWhatsAppChallenge(code: string, now = Date.now()): boolean {
  if (!/^[A-Za-z0-9_-]{16,256}$/.test(code)) return false;
  sessionStorage.setItem(CHALLENGE_KEY, JSON.stringify({ code, expiresAt: now + CHALLENGE_TTL_MS }));
  return true;
}

export function readWhatsAppChallenge(now = Date.now()): string {
  try {
    const raw = sessionStorage.getItem(CHALLENGE_KEY);
    if (!raw) return '';
    const saved = JSON.parse(raw);
    if (typeof saved.code === 'string' && /^[A-Za-z0-9_-]{16,256}$/.test(saved.code)
      && typeof saved.expiresAt === 'number' && saved.expiresAt > now
      && saved.expiresAt <= now + CHALLENGE_TTL_MS) return saved.code;
  } catch { /* Invalid or legacy unbounded challenges must not be reused. */ }
  clearWhatsAppChallenge();
  return '';
}

export function clearWhatsAppChallenge(): void {
  sessionStorage.removeItem(CHALLENGE_KEY);
  for (const key of ['intendedPath', 'auth_redirect_path']) {
    if (sessionStorage.getItem(key)?.startsWith('/link-whatsapp')) sessionStorage.removeItem(key);
  }
}

/** A server response must never send a signed-in browser to an arbitrary URL. */
export function safeWhatsAppReturnUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.hostname !== 'wa.me' || url.port
      || url.username || url.password || !/^\/[1-9]\d{6,14}$/.test(url.pathname)) return null;
    return `https://wa.me${url.pathname}?text=START`;
  } catch { return null; }
}

export function normalizeWhatsAppStatus(data: unknown): WhatsAppStatus {
  if (!data || typeof data !== 'object' || !('linked' in data) || typeof data.linked !== 'boolean') {
    throw new Error('Unable to confirm WhatsApp connection status. Please try again.');
  }
  const row = data as Record<string, unknown>;
  if (!row.linked) return { ...DISCONNECTED_WHATSAPP };
  if (typeof row.masked_phone !== 'string' || !row.masked_phone.trim()) {
    throw new Error('Unable to confirm the connected number. Please try again.');
  }
  return {
    linked: true, masked_phone: row.masked_phone,
    sync_history_consent: row.sync_history_consent === true,
    memory_write_consent: row.memory_write_consent === true,
    linked_at: typeof row.linked_at === 'string' ? row.linked_at : null,
    return_url: safeWhatsAppReturnUrl(row.return_url),
  };
}

export async function whatsappRequest(
  path: string, token: string, body?: Record<string, unknown>, signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) controller.abort();
  const timer = setTimeout(abort, 15000);
  try {
    const response = await fetch(`${BACKEND_URL}/api/whatsapp/link/${path}`, {
      method: body ? 'POST' : 'GET',
      headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error('WhatsApp connection service is unavailable. Please try again.');
    const data: unknown = await response.json();
    if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('Unable to confirm this change. Please try again.');
    return data as Record<string, unknown>;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('WhatsApp connection check timed out. Please try again.');
    if (error instanceof TypeError || error instanceof SyntaxError) throw new Error('WhatsApp connection service is unavailable. Please try again.');
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}
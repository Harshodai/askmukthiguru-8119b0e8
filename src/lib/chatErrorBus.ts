import type { MessageError, MessageErrorKind } from '@/lib/chatStorage';

export interface ChatBusError {
  id: string;
  kind: MessageErrorKind;
  title: string;
  summary: string;
  detail?: string;
  /** Error code shown in friendly panel (AUTH_401, RATE_429, …). */
  code: string;
  /** Concrete next step the user should take. */
  nextStep: string;
  /** id of the chat message that owns this error, if any. */
  messageId?: string;
  retryable: boolean;
  /** epoch ms */
  at: number;
}

type Listener = (err: ChatBusError | null) => void;

const listeners = new Set<Listener>();
let current: ChatBusError | null = null;
let lastKey = '';
let lastAt = 0;

export const CODE_BY_KIND: Record<MessageErrorKind, { code: string; nextStep: string }> = {
  unauthorized: { code: 'AUTH_401', nextStep: 'Sign in again to continue. Your draft is saved.' },
  rate_limited: { code: 'RATE_429', nextStep: 'Wait ~30 seconds, then retry your message.' },
  server_error: { code: 'MODEL_5XX', nextStep: 'The model is recovering. Retry in a moment.' },
  network: { code: 'NET_OFFLINE', nextStep: 'Check your connection, then retry.' },
  timeout: { code: 'TIME_OUT', nextStep: 'The Guru took too long. Retry — answers may need another attempt.' },
  backend_down: { code: 'BACKEND_DOWN', nextStep: 'The Guru is offline. Please try again shortly.' },
  connection_refused: { code: 'CONN_REFUSED', nextStep: 'Connection refused by server. Retry in a moment.' },
  dns_failure: { code: 'DNS_FAIL', nextStep: 'Could not resolve the server address. Check your network.' },
  telemetry_failed: { code: 'TELEMETRY_FAILED', nextStep: 'Usage metrics may be incomplete — this does not affect your chat.' },
  unknown: { code: 'ERR_UNKNOWN', nextStep: 'Retry. If it persists, copy the technical detail and share with support.' },
};

export const chatErrorBus = {
  subscribe(fn: Listener): () => void {
    listeners.add(fn);
    fn(current);
    return () => listeners.delete(fn);
  },
  publish(err: Omit<ChatBusError, 'id' | 'at' | 'code' | 'nextStep'> & { code?: string; nextStep?: string }): void {
    const key = `${err.kind}|${err.title}|${err.messageId ?? ''}`;
    const now = Date.now();
    if (key === lastKey && now - lastAt < 5000) return;
    lastKey = key;
    lastAt = now;
    const mapped = CODE_BY_KIND[err.kind] ?? CODE_BY_KIND.unknown;
    current = {
      id: `${now}-${Math.random().toString(36).slice(2, 8)}`,
      at: now,
      code: err.code ?? mapped.code,
      nextStep: err.nextStep ?? mapped.nextStep,
      ...err,
    };
    listeners.forEach((l) => l(current));
  },
  publishFromMessage(messageError: MessageError, messageId?: string): void {
    chatErrorBus.publish({
      kind: messageError.kind,
      title: messageError.title,
      summary: messageError.description,
      detail: messageError.detail,
      messageId,
      retryable: messageError.kind !== 'telemetry_failed' && messageError.actionLabel !== 'sign_in' && messageError.actionLabel !== 'reload',
    });
  },
  dismiss(): void {
    current = null;
    listeners.forEach((l) => l(null));
  },
  get(): ChatBusError | null {
    return current;
  },
};

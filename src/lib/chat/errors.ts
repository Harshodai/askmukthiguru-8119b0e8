import type { MessageError } from '@/lib/chatStorage';
import type { AIErrorCode } from './types';

export function httpStatusToErrorCode(
  status: number,
  bodyQuotaExceeded?: boolean,
  bodyErrorCode?: unknown,
): AIErrorCode {
  if (bodyErrorCode === 'conversation_context_exhausted' || bodyErrorCode === 'context_exhausted') {
    return 'context_exhausted';
  }
  if (status === 401 || status === 403) return 'unauthorized';
  if (status === 504 || status === 408) return 'timeout';
  if (status === 429) return bodyQuotaExceeded ? 'quota_exceeded' : 'rate_limited';
  if (status >= 500) return 'server_error';
  return 'unknown';
}

export type BuiltChatError = MessageError;

export function buildMessageError(
  code: AIErrorCode | string | undefined,
  message?: string,
  status?: number,
): MessageError {
  const normalized = code as AIErrorCode;
  switch (normalized) {
    case 'context_exhausted':
      return {
        kind: 'context_exhausted',
        title: 'Conversation context limit reached',
        description: 'This conversation has reached its safe context limit. Start a new chat to continue.',
        retryable: false,
        actionLabel: 'new_chat',
        detail: message,
      };
    case 'unauthorized':
      return {
        kind: 'unauthorized',
        title: 'Sign-in required',
        description: 'Please sign in again to continue this conversation.',
        retryable: false,
        actionLabel: 'sign_in',
        detail: message,
      };
    case 'rate_limited':
      return {
        kind: 'rate_limited',
        title: 'Please try again shortly',
        description: 'The service is temporarily rate-limited.',
        retryable: true,
        actionLabel: 'retry',
        detail: message,
      };
    case 'quota_exceeded':
      return {
        kind: 'quota_exceeded',
        title: 'Free-message limit reached',
        description: 'Sign in or try again when your message allowance is available.',
        retryable: false,
        actionLabel: 'sign_in',
        detail: message,
      };
    case 'timeout':
      return {
        kind: 'timeout',
        title: 'The response took too long',
        description: 'Please retry your message.',
        retryable: true,
        actionLabel: 'retry',
        detail: message,
      };
    case 'server_error':
      return {
        kind: 'server_error',
        title: 'Something went wrong',
        description: 'The Guru could not complete this response. Please retry.',
        retryable: true,
        actionLabel: 'retry',
        detail: message,
      };
    case 'network':
      return {
        kind: 'network',
        title: 'Connection problem',
        description: 'The Guru could not be reached. Check your connection and retry.',
        retryable: true,
        actionLabel: 'retry',
        detail: message,
      };
    default:
      return {
        kind: 'unknown',
        title: 'Something went wrong',
        description: 'The response could not be completed. Please retry.',
        retryable: true,
        actionLabel: 'retry',
        detail: status ? `HTTP ${status}` : message,
      };
  }
}

import { describe, expect, it } from 'vitest';
import { buildMessageError, httpStatusToErrorCode } from '@/lib/chat/errors';

describe('chat context exhaustion errors', () => {
  it('maps the stable backend error code to a context exhaustion state', () => {
    expect(httpStatusToErrorCode(409, false, 'conversation_context_exhausted')).toBe('context_exhausted');
  });

  it('creates a non-retryable new-chat action', () => {
    const error = buildMessageError(
      'context_exhausted',
      'This conversation has reached its safe context limit.',
    );

    expect(error.kind).toBe('context_exhausted');
    expect(error.retryable).toBe(false);
    expect(error.actionLabel).toBe('new_chat');
    expect(error.description).toContain('new chat');
  });
});

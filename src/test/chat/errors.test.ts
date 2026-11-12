import { describe, it, expect } from 'vitest';
import { httpStatusToErrorCode, buildMessageError } from '@/lib/chat/errors';
import type { AIErrorCode } from '@/lib/chat/types';

describe('chat/errors', () => {
  const cases: [number, AIErrorCode][] = [
    [200, 'unknown'],
    [400, 'unknown'],
    [401, 'unauthorized'],
    [403, 'unauthorized'],
    [429, 'rate_limited'],
    [408, 'timeout'],
    [500, 'server_error'],
    [502, 'server_error'],
    [504, 'timeout'],
  ];

  it.each(cases)('maps %i to %s', (status, expected) => {
    expect(httpStatusToErrorCode(status)).toBe(expected);
  });

  it('includes crisis helpline message across terminal server and network errors', () => {
    const error500 = buildMessageError('server_error', 'Internal error', 500);
    expect(error500.description).toContain('Tele-MANAS');

    const error503 = buildMessageError('server_error', 'Busy', 503);
    expect(error503.description).toContain('Tele-MANAS');

    const errorTimeout = buildMessageError('timeout', 'Gateway timeout', 504);
    expect(errorTimeout.description).toContain('Tele-MANAS');

    const errorNetwork = buildMessageError('network', 'Failed to fetch');
    expect(errorNetwork.description).toContain('Tele-MANAS');

    const errorStream = buildMessageError('stream_interrupted', 'Stream broke');
    expect(errorStream.description).toContain('Tele-MANAS');
  });

  it('builds non-terminal client errors without leaking sensitive developer detail', () => {
    const errorAuth = buildMessageError('unauthorized', 'token_expired', 401);
    expect(errorAuth.kind).toBe('unauthorized');
    expect(errorAuth.title).toBe('Sign-in required');

    const errorQuota = buildMessageError('quota_exceeded', 'out_of_credits', 429);
    expect(errorQuota.kind).toBe('quota_exceeded');

    const errorContext = buildMessageError('context_exhausted', 'tokens_exceeded');
    expect(errorContext.kind).toBe('context_exhausted');
  });
});

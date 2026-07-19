import { describe, it, expect } from 'vitest';
import { httpStatusToErrorCode } from '@/lib/chat/errors';
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
});

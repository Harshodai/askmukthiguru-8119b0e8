import { describe, it, expect, vi } from 'vitest';

vi.mock('@/lib/chatStorage', () => ({
  guruResponses: ['Response A', 'Response B', 'Response C'],
}));

import { getPlaceholderResponse, placeholderReply } from '@/lib/chat/placeholder';

describe('chat/placeholder', () => {
  it('returns one of the configured guru responses', () => {
    const response = getPlaceholderResponse();
    expect(['Response A', 'Response B', 'Response C']).toContain(response);
  });

  it('placeholderReply waits then returns a response', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const promise = placeholderReply();
    await vi.advanceTimersByTimeAsync(1500);
    const result = await promise;
    expect(result.content).toContain('Response');
    vi.useRealTimers();
  });
});

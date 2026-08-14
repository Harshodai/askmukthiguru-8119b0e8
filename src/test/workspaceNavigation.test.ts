import { describe, expect, it, vi } from 'vitest';
import {
  buildChatOwnedPath,
  getChatOrigin,
  isSafeReturnPath,
  returnToOrigin,
} from '@/lib/workspaceNavigation';

describe('workspace navigation contract', () => {
  it('carries the originating conversation into Chat-owned routes', () => {
    expect(buildChatOwnedPath('/notebooks', { conversationId: 'conv-123' })).toBe(
      '/notebooks?returnTo=%2Fchat&conversation=conv-123',
    );
  });

  it('preserves concept query only for the knowledge graph', () => {
    expect(buildChatOwnedPath('/knowledge-graph', { conversationId: 'conv-1', conceptQuery: 'beautiful state' })).toBe(
      '/knowledge-graph?returnTo=%2Fchat&conversation=conv-1&q=beautiful+state',
    );
    expect(buildChatOwnedPath('/second-brain', { conceptQuery: 'private' })).toBe('/second-brain?returnTo=%2Fchat');
  });

  it('rejects unsafe or unknown return paths', () => {
    expect(isSafeReturnPath('/chat')).toBe(true);
    expect(isSafeReturnPath('/profile')).toBe(false);
    expect(isSafeReturnPath('//evil.example')).toBe(false);
  });

  it('returns to Chat with the same conversation and replaces the child history entry', () => {
    const navigate = vi.fn();
    returnToOrigin(navigate, { search: '?returnTo=%2Fchat&conversation=conv-9' });
    expect(navigate).toHaveBeenCalledWith('/chat?conversation=conv-9', { replace: true });
  });

  it('falls back to Chat for direct workspace visits', () => {
    const navigate = vi.fn();
    returnToOrigin(navigate, { search: '' });
    expect(navigate).toHaveBeenCalledWith('/chat', { replace: true });
  });

  it('parses origin state without trusting arbitrary values', () => {
    expect(getChatOrigin({ search: '?returnTo=%2Fchat&conversation=conv-2' })).toEqual({
      returnTo: '/chat',
      conversationId: 'conv-2',
      conceptQuery: undefined,
    });
  });
});

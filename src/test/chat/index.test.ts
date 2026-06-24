import { describe, it, expect } from 'vitest';
import * as aiService from '@/lib/aiService';
import * as chat from '@/lib/chat';

describe('chat index re-exports match legacy aiService surface', () => {
  it('exports all public runtime members from aiService via chat/', () => {
    const legacyNames = Object.keys(aiService).sort();
    const chatNames = Object.keys(chat).sort();
    expect(chatNames).toEqual(legacyNames);
  });

  it('re-exports type names are importable from both paths', () => {
    // Type-only exports compile away; this test ensures the imports do not throw.
    expect(typeof aiService.sendMessage).toBe('function');
    expect(typeof chat.sendMessage).toBe('function');
  });
});

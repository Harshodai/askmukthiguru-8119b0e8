import { describe, it, expect, beforeEach, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getItem: vi.fn(),
  setItem: vi.fn(),
}));

vi.stubGlobal('localStorage', {
  getItem: mocks.getItem,
  setItem: mocks.setItem,
  removeItem: vi.fn(),
  clear: vi.fn(),
  length: 0,
  key: vi.fn(),
});

// Import after stubbing localStorage so getInitialLanguage sees the mock.
import { setAIProvider, getAIConfig, setLanguage } from '@/lib/chat/config';

describe('chat/config', () => {
  beforeEach(() => {
    mocks.getItem.mockReturnValue(null);
    setAIProvider({
      provider: 'custom',
      endpoint: '/api/chat',
      language: 'en',
      systemPrompt: 'Test prompt',
    });
  });

  it('updates provider and endpoint', () => {
    setAIProvider({ provider: 'placeholder' });
    const cfg = getAIConfig();
    expect(cfg.provider).toBe('placeholder');
    expect(cfg.endpoint).toBe('/api/chat');
  });

  it('returns a copy of config so callers cannot mutate internal state', () => {
    const cfg = getAIConfig();
    cfg.language = 'fr';
    expect(getAIConfig().language).toBe('en');
  });

  it('persists language change to localStorage profile', () => {
    mocks.getItem.mockReturnValue(JSON.stringify({ preferredLanguage: 'en', name: 'Seeker' }));
    setLanguage('hi');
    expect(mocks.setItem).toHaveBeenCalledWith(
      'askmukthiguru_profile',
      JSON.stringify({ preferredLanguage: 'hi', name: 'Seeker' }),
    );
    expect(getAIConfig().language).toBe('hi');
  });

  it('ignores localStorage errors when setting language', () => {
    mocks.getItem.mockImplementation(() => {
      throw new Error('bad');
    });
    expect(() => setLanguage('ta')).not.toThrow();
  });
});

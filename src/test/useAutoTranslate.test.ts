import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAutoTranslate } from '@/hooks/useAutoTranslate';

vi.mock('@/lib/chat/transport', () => ({
  translateText: vi.fn(),
}));

import { translateText } from '@/lib/chat/transport';

describe('useAutoTranslate backend translation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns original text when language is en', async () => {
    const { result } = renderHook(() => useAutoTranslate({ languageCode: 'en' }));
    await act(async () => {
      const out = await result.current.translateToEnglish('namaste');
      expect(out).toBe('namaste');
    });
    expect(translateText).not.toHaveBeenCalled();
  });

  it('calls translateText with correct target/source for hindi to english', async () => {
    vi.mocked(translateText).mockResolvedValueOnce('hello');
    const { result } = renderHook(() => useAutoTranslate({ languageCode: 'hi' }));
    await act(async () => {
      const out = await result.current.translateToEnglish('namaste');
      expect(out).toBe('hello');
    });
    expect(translateText).toHaveBeenCalledWith('namaste', 'en-IN', 'hi-IN');
  });

  it('caches identical input and calls backend once', async () => {
    vi.mocked(translateText).mockResolvedValueOnce('hello');
    const { result } = renderHook(() => useAutoTranslate({ languageCode: 'hi' }));
    await act(async () => result.current.translateToEnglish('namaste'));
    await act(async () => result.current.translateToEnglish('namaste'));
    expect(translateText).toHaveBeenCalledTimes(1);
  });

  it('returns original text and sets lastError on backend failure', async () => {
    vi.mocked(translateText).mockRejectedValueOnce(new Error('backend down'));
    const { result } = renderHook(() => useAutoTranslate({ languageCode: 'te' }));
    await act(async () => {
      const out = await result.current.translateToEnglish('nandri');
      expect(out).toBe('nandri');
    });
    expect(result.current.lastError).toContain('backend down');
  });
});

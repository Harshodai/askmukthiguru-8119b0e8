import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useVoiceInput } from '@/hooks/useVoiceInput';

describe('useVoiceInput', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns supported=false when MediaRecorder absent', () => {
    const orig = (globalThis as { MediaRecorder?: unknown }).MediaRecorder;
    try {
      delete (globalThis as { MediaRecorder?: unknown }).MediaRecorder;
      const { result } = renderHook(() => useVoiceInput());
      expect(result.current.supported).toBe(false);
    } finally {
      (globalThis as { MediaRecorder?: unknown }).MediaRecorder = orig;
    }
  });

  it('start sets error when not supported', async () => {
    const orig = (globalThis as { MediaRecorder?: unknown }).MediaRecorder;
    try {
      delete (globalThis as { MediaRecorder?: unknown }).MediaRecorder;
      const { result } = renderHook(() => useVoiceInput());
      await act(async () => {
        await result.current.start();
      });
      expect(result.current.error).toBe('Voice input not supported');
    } finally {
      (globalThis as { MediaRecorder?: unknown }).MediaRecorder = orig;
    }
  });

  it('reset clears transcript and error', () => {
    const { result } = renderHook(() => useVoiceInput());
    act(() => {
      result.current.setTranscript('hi');
    });
    act(() => result.current.reset());
    expect(result.current.transcript).toBe('');
    expect(result.current.error).toBeNull();
  });
});

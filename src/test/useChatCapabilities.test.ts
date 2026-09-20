import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  LOCAL_CHAT_CAPABILITIES,
  resolveChatCapabilities,
  readCachedCapabilities,
  writeCachedCapabilities,
  resetCapabilitiesCache,
  useChatCapabilities,
  CAPABILITIES_CACHE_KEY,
  CAPABILITIES_CACHE_TTL_MS,
} from '@/hooks/useChatCapabilities';

describe('resolveChatCapabilities', () => {
  it('keeps working local controls when no trusted manifest is available', () => {
    expect(resolveChatCapabilities()).toEqual(LOCAL_CHAT_CAPABILITIES);
  });

  it('hides only actions explicitly unavailable or disabled by policy', () => {
    expect(
      resolveChatCapabilities({
        features: {
          serene_mind: 'unavailable',
          guided_meditation: 'available',
          text_attachments: 'disabled_by_policy',
          voice_input: 'available',
          ocr: 'unavailable',
          video_attachments: 'disabled_by_policy',
        },
      }),
    ).toEqual({
      sereneMind: false,
      guidedMeditation: true,
      textAttachments: false,
      documentAttachments: true,
      imageAttachments: true,
      audioAttachments: true,
      videoAttachments: false,
      ocr: false,
      voiceInput: true,
      googleSso: true,
      pushNotifications: true,
    });
  });
});

describe('useChatCapabilities caching & hook', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    resetCapabilitiesCache();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    resetCapabilitiesCache();
    vi.unstubAllGlobals();
  });

  it('reads and writes to localStorage cache with TTL', () => {
    expect(readCachedCapabilities()).toBeNull();

    const customCapabilities = {
      ...LOCAL_CHAT_CAPABILITIES,
      sereneMind: false,
    };
    writeCachedCapabilities(customCapabilities);

    const cached = readCachedCapabilities();
    expect(cached).toEqual(customCapabilities);

    // Expired cache returns null
    const expiredPayload = {
      capabilities: customCapabilities,
      timestamp: Date.now() - (CAPABILITIES_CACHE_TTL_MS + 1000),
    };
    window.localStorage.setItem(CAPABILITIES_CACHE_KEY, JSON.stringify(expiredPayload));
    expect(readCachedCapabilities()).toBeNull();

    resetCapabilitiesCache();
    expect(readCachedCapabilities()).toBeNull();
  });

  it('serves cached capabilities on hook mount without fetching from network', async () => {
    const customCapabilities = {
      ...LOCAL_CHAT_CAPABILITIES,
      ocr: false,
    };
    writeCachedCapabilities(customCapabilities);

    const { result } = renderHook(() => useChatCapabilities());

    expect(result.current.capabilities).toEqual(customCapabilities);
    expect(result.current.manifestReady).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('fetches from network when cache is absent and populates cache', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ready: true,
        capabilities: {
          features: {
            serene_mind: 'available',
            ocr: 'unavailable',
          },
        },
      }),
    });

    const { result } = renderHook(() => useChatCapabilities());

    await waitFor(() => expect(result.current.manifestReady).toBe(true));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.capabilities.ocr).toBe(false);

    // Verify written to cache
    const cached = readCachedCapabilities();
    expect(cached).not.toBeNull();
    expect(cached?.ocr).toBe(false);
  });

  it('rejects malformed cached capabilities and falls back to null', () => {
    // Missing keys or non-boolean values
    const malformedPayload = {
      capabilities: { sereneMind: "true", guidedMeditation: true },
      timestamp: Date.now(),
    };
    window.localStorage.setItem(CAPABILITIES_CACHE_KEY, JSON.stringify(malformedPayload));
    expect(readCachedCapabilities()).toBeNull();
  });
});

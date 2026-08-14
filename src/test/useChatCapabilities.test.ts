import { describe, expect, it } from 'vitest';
import { LOCAL_CHAT_CAPABILITIES, resolveChatCapabilities } from '@/hooks/useChatCapabilities';

describe('resolveChatCapabilities', () => {
  it('keeps working local controls when no trusted manifest is available', () => {
    expect(resolveChatCapabilities()).toEqual(LOCAL_CHAT_CAPABILITIES);
  });

  it('hides only actions explicitly unavailable or disabled by policy', () => {
    expect(resolveChatCapabilities({ features: {
      serene_mind: 'unavailable',
      guided_meditation: 'available',
      text_attachments: 'disabled_by_policy',
      voice_input: 'available',
    } })).toEqual({
      sereneMind: false,
      guidedMeditation: true,
      textAttachments: false,
      voiceInput: true,
      googleSso: true,
      pushNotifications: true,
    });
  });
});

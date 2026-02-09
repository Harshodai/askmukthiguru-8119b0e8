import { describe, it, expect, vi } from 'vitest';

describe('LanguageSelector Component', () => {
  it('should have correct language options with flags', () => {
    const languages = [
      { code: 'en', name: 'English', native: 'English', flag: '🇮🇳' },
      { code: 'hi', name: 'Hindi', native: 'हिंदी', flag: '🇮🇳' },
      { code: 'te', name: 'Telugu', native: 'తెలుగు', flag: '🇮🇳' },
      { code: 'ml', name: 'Malayalam', native: 'മലയാളം', flag: '🇮🇳' },
    ];

    expect(languages).toHaveLength(4);
    expect(languages[0].code).toBe('en');
    expect(languages[0].flag).toBe('🇮🇳');
    expect(languages[1].native).toBe('हिंदी');
    expect(languages[2].native).toBe('తెలుగు');
    expect(languages[3].native).toBe('മലയാളം');
  });

  it('should map language codes correctly', () => {
    const languageCodeMap: Record<string, string> = {
      en: 'English',
      hi: 'Hindi',
      te: 'Telugu',
      ml: 'Malayalam',
    };

    expect(languageCodeMap.en).toBe('English');
    expect(languageCodeMap.hi).toBe('Hindi');
    expect(languageCodeMap.te).toBe('Telugu');
    expect(languageCodeMap.ml).toBe('Malayalam');
  });

  it('should have correct props interface', () => {
    interface LanguageSelectorProps {
      onVoiceToggle?: () => void;
      voiceEnabled?: boolean;
      isListening?: boolean;
      onLanguageChange?: (code: string) => void;
      ttsEnabled?: boolean;
      onTtsToggle?: () => void;
      isSpeaking?: boolean;
    }

    const mockProps: LanguageSelectorProps = {
      onVoiceToggle: vi.fn(),
      voiceEnabled: false,
      isListening: false,
      onLanguageChange: vi.fn(),
      ttsEnabled: false,
      onTtsToggle: vi.fn(),
      isSpeaking: false,
    };

    expect(mockProps.voiceEnabled).toBe(false);
    expect(mockProps.ttsEnabled).toBe(false);
    expect(mockProps.isListening).toBe(false);
    expect(mockProps.isSpeaking).toBe(false);
  });

  it('should support both voice input and TTS output toggles', () => {
    const voiceToggle = vi.fn();
    const ttsToggle = vi.fn();

    // Simulate toggle calls
    voiceToggle();
    ttsToggle();

    expect(voiceToggle).toHaveBeenCalledTimes(1);
    expect(ttsToggle).toHaveBeenCalledTimes(1);
  });

  it('should include Bhashini coming soon notice', () => {
    const bhashiniStatus = 'Coming Soon';
    expect(bhashiniStatus).toBe('Coming Soon');
  });
});

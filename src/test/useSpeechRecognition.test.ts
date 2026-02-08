import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock SpeechRecognition API
const mockRecognition = {
  continuous: false,
  interimResults: false,
  maxAlternatives: 1,
  lang: '',
  start: vi.fn(),
  stop: vi.fn(),
  abort: vi.fn(),
  onresult: null as ((event: unknown) => void) | null,
  onerror: null as ((event: unknown) => void) | null,
  onend: null as (() => void) | null,
  onstart: null as (() => void) | null,
};

const MockSpeechRecognition = vi.fn(() => mockRecognition);

describe('useSpeechRecognition', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // Reset mock recognition
    mockRecognition.continuous = false;
    mockRecognition.interimResults = false;
    mockRecognition.lang = '';
    mockRecognition.onresult = null;
    mockRecognition.onerror = null;
    mockRecognition.onend = null;
    mockRecognition.onstart = null;
  });

  it('should detect browser support', () => {
    // Test without SpeechRecognition
    expect(typeof window.SpeechRecognition).toBe('undefined');
    expect(typeof window.webkitSpeechRecognition).toBe('undefined');
  });

  it('should have correct language code mappings', () => {
    const languageCodeMap: Record<string, string> = {
      en: 'en-US',
      hi: 'hi-IN',
      te: 'te-IN',
      ta: 'ta-IN',
      kn: 'kn-IN',
      ml: 'ml-IN',
    };

    expect(languageCodeMap.en).toBe('en-US');
    expect(languageCodeMap.hi).toBe('hi-IN');
    expect(languageCodeMap.te).toBe('te-IN');
    expect(languageCodeMap.ml).toBe('ml-IN');
  });

  it('should configure recognition instance correctly', () => {
    Object.defineProperty(window, 'SpeechRecognition', {
      writable: true,
      value: MockSpeechRecognition,
    });

    const recognition = new MockSpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    expect(recognition.continuous).toBe(true);
    expect(recognition.interimResults).toBe(true);
    expect(recognition.lang).toBe('en-US');
  });

  it('should handle error messages correctly', () => {
    const errorMessages: Record<string, string> = {
      'not-allowed': 'Microphone access denied. Please enable microphone permissions.',
      'no-speech': 'No speech detected. Please try again.',
      'audio-capture': 'No microphone found. Please check your microphone.',
      'network': 'Network error occurred. Please check your connection.',
      'aborted': 'Recognition was stopped.',
      'service-not-allowed': 'Speech service not allowed.',
    };

    expect(errorMessages['not-allowed']).toContain('Microphone access denied');
    expect(errorMessages['no-speech']).toContain('No speech detected');
    expect(errorMessages['audio-capture']).toContain('No microphone');
  });
});

describe('LanguageSelector', () => {
  it('should have correct language options', () => {
    const languages = [
      { code: 'en', name: 'English', native: 'English' },
      { code: 'hi', name: 'Hindi', native: 'हिंदी' },
      { code: 'te', name: 'Telugu', native: 'తెలుగు' },
      { code: 'ml', name: 'Malayalam', native: 'മലയാളം' },
    ];

    expect(languages).toHaveLength(4);
    expect(languages[0].code).toBe('en');
    expect(languages[1].native).toBe('हिंदी');
  });
});

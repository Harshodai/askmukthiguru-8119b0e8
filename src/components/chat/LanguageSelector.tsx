import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import i18n from '@/i18n';
import { Globe, Mic, MicOff, Volume2, VolumeX, AlertCircle, ChevronDown, Languages } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { setLanguage } from '@/lib/aiService';
import { useToast } from '@/hooks/use-toast';
// ScrollArea removed in favor of native scrollable div to prevent Radix popover collapsing

interface Language {
  code: string;
  name: string;
  native: string;
  /** BCP-47 tag used for Web Speech APIs */
  bcp47: string;
}

// 22 scheduled Indian languages + English. Aligned with Sarvam-30B's claimed coverage.
const MASTER_LANGUAGES: Language[] = [
  { code: 'en', name: 'English (India)', native: 'English', bcp47: 'en-IN' },
  { code: 'hi', name: 'Hindi', native: 'हिन्दी', bcp47: 'hi-IN' },
  { code: 'bn', name: 'Bengali', native: 'বাংলা', bcp47: 'bn-IN' },
  { code: 'te', name: 'Telugu', native: 'తెలుగు', bcp47: 'te-IN' },
  { code: 'mr', name: 'Marathi', native: 'मराठी', bcp47: 'mr-IN' },
  { code: 'ta', name: 'Tamil', native: 'தமிழ்', bcp47: 'ta-IN' },
  { code: 'ur', name: 'Urdu', native: 'اُردُو', bcp47: 'ur-IN' },
  { code: 'gu', name: 'Gujarati', native: 'ગુજરાતી', bcp47: 'gu-IN' },
  { code: 'kn', name: 'Kannada', native: 'ಕನ್ನಡ', bcp47: 'kn-IN' },
  { code: 'ml', name: 'Malayalam', native: 'മലയാളം', bcp47: 'ml-IN' },
  { code: 'or', name: 'Odia', native: 'ଓଡ଼ିଆ', bcp47: 'or-IN' },
  { code: 'pa', name: 'Punjabi', native: 'ਪੰਜਾਬੀ', bcp47: 'pa-IN' },
  { code: 'as', name: 'Assamese', native: 'অসমীয়া', bcp47: 'as-IN' },
  { code: 'mai', name: 'Maithili', native: 'मैथिली', bcp47: 'mai-IN' },
  { code: 'sa', name: 'Sanskrit', native: 'संस्कृतम्', bcp47: 'sa-IN' },
  { code: 'ks', name: 'Kashmiri', native: 'کٲشُر', bcp47: 'ks-IN' },
  { code: 'ne', name: 'Nepali', native: 'नेपाली', bcp47: 'ne-NP' },
  { code: 'sd', name: 'Sindhi', native: 'سنڌي', bcp47: 'sd-IN' },
  { code: 'kok', name: 'Konkani', native: 'कोंकणी', bcp47: 'kok-IN' },
  { code: 'doi', name: 'Dogri', native: 'डोगरी', bcp47: 'doi-IN' },
  { code: 'mni', name: 'Manipuri', native: 'মৈতৈলোন্', bcp47: 'mni-IN' },
  { code: 'sat', name: 'Santali', native: 'ᱥᱟᱱᱛᱟᱲᱤ', bcp47: 'sat-IN' },
  { code: 'brx', name: 'Bodo', native: 'बड़ो', bcp47: 'brx-IN' },
];

export const LANGUAGES: Language[] = MASTER_LANGUAGES.filter((lang) => {
  return ['en', 'hi', 'te', 'kn', 'ta', 'mr'].includes(lang.code);
});

/**
 * Flag emoji per language code. Used to make the pill visually rich.
 * A few rare scheduled languages share the 🇮🇳 flag.
 */
export const LANGUAGE_FLAGS: Record<string, string> = {
  en:  '🇮🇳',
  hi:  '🇮🇳',
  bn:  '🇮🇳',
  te:  '🇮🇳',
  mr:  '🇮🇳',
  ta:  '🇮🇳',
  ur:  '🇮🇳',
  gu:  '🇮🇳',
  kn:  '🇮🇳',
  ml:  '🇮🇳',
  or:  '🇮🇳',
  pa:  '🇮🇳',
  as:  '🇮🇳',
  mai: '🇮🇳',
  sa:  '🇮🇳',
  ks:  '🇮🇳',
  ne:  '🇳🇵',
  sd:  '🇮🇳',
  kok: '🇮🇳',
  doi: '🇮🇳',
  mni: '🇮🇳',
  sat: '🇮🇳',
  brx: '🇮🇳',
};

/**
 * Short display label for the pill (≤ 6 chars). For English show "EN";
 * for other languages show their 2-char code uppercased so the pill is compact.
 * The full native name appears in the popover list.
 */
const pillLabel = (lang: Language): string => {
  if (lang.code === 'en') return 'EN';
  // For common langs show their native short-form
  const SHORT: Record<string, string> = {
    hi: 'हिन्', te: 'తె', ta: 'த', bn: 'বাং', mr: 'मरा',
    gu: 'ગુ', kn: 'ಕ', ml: 'മ', pa: 'ਪੰ', ur: 'اُردُو',
    or: 'ওড়',  as: 'অস', ne: 'ने',
  };
  return SHORT[lang.code] ?? lang.code.toUpperCase();
};

interface LanguageSelectorProps {
  onVoiceToggle?: () => void;
  voiceEnabled?: boolean;
  isListening?: boolean;
  onLanguageChange?: (code: string) => void;
  ttsEnabled?: boolean;
  onTtsToggle?: () => void;
  isSpeaking?: boolean;
  /** Currently selected language code (controlled). */
  value?: string;
  compact?: boolean;
}

/** Detect which languages have at least one TTS voice available in this browser. */
const detectTtsVoices = (): Set<string> => {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return new Set();
  const voices = window.speechSynthesis.getVoices();
  const supported = new Set<string>();
  voices.forEach((v) => {
    const tag = v.lang.toLowerCase();
    LANGUAGES.forEach((l) => {
      if (tag.startsWith(l.code) || tag.startsWith(l.bcp47.toLowerCase())) {
        supported.add(l.code);
      }
    });
  });
  // English is universally supported as a baseline
  supported.add('en');
  return supported;
};

export const LanguageSelector = ({
  onVoiceToggle,
  voiceEnabled,
  isListening,
  onLanguageChange,
  ttsEnabled,
  onTtsToggle,
  isSpeaking,
  value,
  compact,
}: LanguageSelectorProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [internalLang, setInternalLang] = useState('en');
  const [search, setSearch] = useState('');
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const selectedLanguage = value ?? internalLang;
  const [voiceCapable, setVoiceCapable] = useState<Set<string>>(new Set(['en']));
  const { toast } = useToast();
  const { t } = useTranslation();

  const [coords, setCoords] = useState<{ bottom: number; left: number; maxHeight: number } | null>(null);

  const updatePosition = useCallback(() => {
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      const viewportWidth = window.innerWidth;
      const margin = 8;
      
      const bottom = viewportHeight - rect.top + margin;
      
      let left = rect.left;
      const menuWidth = Math.min(320, viewportWidth - 24); // 20rem is 320px
      
      // Clamp left to avoid overflowing the right side of the screen
      if (left + menuWidth > viewportWidth - 12) {
        left = Math.max(12, viewportWidth - menuWidth - 12);
      }
      
      const maxHeight = rect.top - margin - 20; // 20px padding from the top
      setCoords({ bottom, left, maxHeight });
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      updatePosition();
      window.addEventListener('resize', updatePosition);
      window.addEventListener('scroll', updatePosition, true);
    }
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [isOpen, updatePosition]);

  useEffect(() => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    const update = () => setVoiceCapable(detectTtsVoices());
    update();
    window.speechSynthesis.onvoiceschanged = update;
    return () => {
      if (window.speechSynthesis) window.speechSynthesis.onvoiceschanged = null;
    };
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
        // Restore focus to the trigger for keyboard users
        requestAnimationFrame(() => triggerRef.current?.focus());
        return;
      }
      // Focus trap: keep Tab cycling inside the open popover
      if (event.key === 'Tab') {
        const popover = popoverRef.current;
        if (!popover) return;
        const focusables = popover.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement;
        if (event.shiftKey && active === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && active === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen]);

  const handleLanguageChange = (code: string) => {
    const lang = LANGUAGES.find((l) => l.code === code);
    setInternalLang(code);
    setLanguage(code);
    onLanguageChange?.(code);
    setIsOpen(false);

    toast({
      title: '🌐 Language Changed',
      description: `Now using ${lang?.name} (${lang?.native})`,
      duration: 2500,
    });
  };

  const currentLang = LANGUAGES.find((l) => l.code === selectedLanguage);
  const filteredLanguages = useMemo(() => {
    if (!search.trim()) return LANGUAGES;
    const q = search.toLowerCase();
    return LANGUAGES.filter((l) =>
      l.name.toLowerCase().includes(q) ||
      l.native.toLowerCase().includes(q) ||
      l.code.toLowerCase().includes(q)
    );
  }, [search]);

  const renderLanguageRows = (showVoiceBadges: boolean) => (
    <>
      {filteredLanguages.map((lang) => {
        const isSelected = selectedLanguage === lang.code;
        const hasVoice = voiceCapable.has(lang.code);
        return (
          <button
            key={lang.code}
            onClick={() => handleLanguageChange(lang.code)}
            className={`w-full px-3 py-3 text-left hover:bg-ojas/10 transition-colors flex items-center gap-3 ${
              isSelected ? 'bg-ojas/15' : ''
            }`}
            role="option"
            aria-selected={isSelected}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-2 flex-wrap">
                <span
                  className={`font-semibold truncate ${
                    lang.code === 'en' ? 'text-base' : 'text-lg'
                  } ${isSelected ? 'text-ojas' : 'text-foreground'}`}
                  lang={lang.bcp47}
                >
                  {lang.native}
                </span>
                <span className="text-muted-foreground text-sm truncate">
                  {lang.name}
                </span>
              </div>
              {showVoiceBadges && (
                hasVoice ? (
                  <span className="inline-flex items-center gap-1 mt-0.5 text-[10px] text-prana/90 font-medium">
                    <Volume2 className="w-2.5 h-2.5" />
                    Local Voice Enabled
                  </span>
                ) : lang.code === 'en' ? (
                  <span className="inline-flex items-center gap-1 mt-0.5 text-[10px] text-muted-foreground">
                    <AlertCircle className="w-2.5 h-2.5" />
                    Voice not supported in this browser
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 mt-0.5 text-[10px] text-ojas/90 font-medium">
                    <Volume2 className="w-2.5 h-2.5" />
                    Cloud Voice (Sarvam)
                  </span>
                )
              )}
            </div>
            {isSelected && (
              <span className="w-2 h-2 rounded-full bg-ojas flex-shrink-0" />
            )}
          </button>
        );
      })}
      {filteredLanguages.length === 0 && (
        <div className="px-4 py-6 text-center text-sm text-muted-foreground">
          No language matches "{search}"
        </div>
      )}
    </>
  );

  if (compact) {
    const flag = LANGUAGE_FLAGS[selectedLanguage] ?? '🌐';
    const lang = LANGUAGES.find((l) => l.code === selectedLanguage);
    const label = lang ? pillLabel(lang) : selectedLanguage.toUpperCase();
    const isNonEnglish = selectedLanguage !== 'en';

    return (
      <div className="flex items-center gap-1">
        <div className="relative">
          <motion.button
            ref={triggerRef}
            data-tour="language-selector"
            onClick={(e) => {
              e.stopPropagation();
              setIsOpen(!isOpen);
            }}
            className={`flex items-center gap-1.5 px-2.5 h-9 rounded-full transition-all font-semibold border ${
              isNonEnglish ? 'text-sm' : 'text-xs'
            } ${
              isNonEnglish
                ? 'bg-ojas/10 border-ojas/30 text-ojas hover:bg-ojas/20'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/60 border-transparent'
            }`}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            aria-haspopup="listbox"
            aria-expanded={isOpen}
            aria-label={`Selected language: ${lang?.name ?? selectedLanguage}. Click to change.`}
            title={`Language: ${lang?.name ?? selectedLanguage}`}
          >
            <span className="text-sm leading-none">{flag}</span>
            <span className={`font-medium ${isNonEnglish ? 'text-base leading-none' : ''}`}>{label}</span>
            {isNonEnglish && (
              <span className="flex items-center gap-0.5 text-[9px] font-bold text-ojas/80 bg-ojas/10 px-1 rounded">
                <Languages className="w-2.5 h-2.5" />
                AUTO
              </span>
            )}
            <ChevronDown className={`w-3 h-3 opacity-50 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
          </motion.button>

          <AnimatePresence>
            {isOpen && (
              <>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="fixed inset-0 z-[90]"
                  onClick={() => setIsOpen(false)}
                />
                <motion.div
                  initial={{ opacity: 0, y: 8, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 8, scale: 0.95 }}
                  transition={{ duration: 0.15, ease: 'easeOut' }}
                  ref={popoverRef}
                  className="absolute bottom-full left-0 mb-2 z-[100] flex flex-col overflow-hidden rounded-2xl border border-border bg-popover shadow-2xl w-72 max-w-[calc(100vw-2rem)]"
                  style={{ maxHeight: Math.min(360, coords?.maxHeight ?? 360) }}
                  role="listbox"
                  aria-label="Select language"
                >
                  {/* Header */}
                  <div className="px-3 pt-3 pb-2 border-b border-border bg-card/95">
                    <div className="flex items-center gap-2 mb-2">
                      <Globe className="w-3.5 h-3.5 text-ojas" />
                      <span className="text-xs font-semibold text-foreground">Select Language</span>
                    </div>
                    <input
                      type="text"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder={t('language.searchPlaceholder', { count: LANGUAGES.length })}
                      className="w-full px-3 py-1.5 text-sm rounded-lg bg-muted/40 border border-border focus:outline-none focus:border-ojas/50 text-foreground placeholder:text-muted-foreground"
                      autoFocus
                    />
                  </div>

                  {/* Language list */}
                  <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin">
                    <div className="py-1">{renderLanguageRows(false)}</div>
                  </div>

                  {/* Translation notice footer */}
                  <div className="px-3 py-2 border-t border-border bg-muted/30 flex items-start gap-2">
                    <Languages className="w-3.5 h-3.5 text-ojas flex-shrink-0 mt-0.5" />
                    <p className="text-[10px] text-muted-foreground leading-relaxed">
                      {t('language.translationNotice')}
                    </p>
                  </div>
                </motion.div>
              </>
            )}
          </AnimatePresence>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <div className="relative">
        <motion.button
          ref={triggerRef}
          onClick={(e) => {
            e.stopPropagation();
            setIsOpen(!isOpen);
          }}
          className="flex items-center gap-2 px-3 py-2 min-h-[44px] rounded-full bg-card hover:bg-ojas/10 border border-border hover:border-ojas/30 transition-all text-sm shadow-sm"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-label={t('language.ariaLabel', { name: currentLang?.name ?? 'English' })}
        >
          <Globe className="w-4 h-4 text-ojas" />
          <span className="text-foreground font-medium hidden sm:inline">
            {currentLang?.native || 'English'}
          </span>
          <span className="text-foreground font-medium sm:hidden text-base">
            {currentLang?.code.toUpperCase()}
          </span>
        </motion.button>

        <AnimatePresence>
          {isOpen && (
            <>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-[90]"
                onClick={() => setIsOpen(false)}
              />
              <motion.div
                initial={{ opacity: 0, y: -10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -10, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                ref={popoverRef}
                className="absolute bottom-full left-0 mb-2 w-72 max-w-[calc(100vw-2rem)] max-h-[min(60vh,420px)] flex flex-col bg-popover border border-border rounded-xl shadow-2xl z-[100] overflow-hidden"
                role="listbox"
                aria-label="Select language"
              >
                <div className="px-3 py-2 border-b border-border bg-card sticky top-0 z-10">
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={t('language.searchPlaceholder', { count: LANGUAGES.length })}
                    className="w-full px-3 py-2 text-sm rounded-lg bg-muted/40 border border-border focus:outline-none focus:border-ojas/50 text-foreground placeholder:text-muted-foreground"
                    autoFocus
                  />
                </div>
                <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin">
                  <div className="py-1">
                    {renderLanguageRows(true)}
                  </div>
                </div>
                <div className="px-4 py-2.5 text-xs text-muted-foreground border-t border-border bg-muted/30">
                  <span className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-prana animate-pulse" />
                    <span>{t('language.supportedCount', { count: LANGUAGES.length })}</span>
                  </span>
                </div>
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </div>

      {/* TTS Toggle */}
      {onTtsToggle && (
        <motion.button
          onClick={onTtsToggle}
          className={`relative p-2.5 min-h-[44px] min-w-[44px] rounded-full transition-all border ${
            ttsEnabled
              ? 'bg-prana/20 border-prana/40 text-prana shadow-md'
              : 'bg-card border-border text-muted-foreground hover:bg-muted hover:border-prana/30 shadow-sm'
          }`}
          title={ttsEnabled ? 'Disable voice output' : 'Enable voice output'}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          aria-label={ttsEnabled ? 'Disable voice output' : 'Enable voice output'}
        >
          {isSpeaking && (
            <motion.span
              className="absolute inset-0 rounded-full bg-prana/30"
              animate={{ scale: [1, 1.3, 1], opacity: [0.5, 0, 0.5] }}
              transition={{ duration: 1, repeat: Infinity, ease: 'easeInOut' }}
            />
          )}
          {ttsEnabled ? (
            <Volume2 className="w-5 h-5 relative z-10" />
          ) : (
            <VolumeX className="w-5 h-5 relative z-10" />
          )}
        </motion.button>
      )}

      {/* Voice Mode Toggle */}
      <motion.button
        onClick={onVoiceToggle}
        className={`relative p-2.5 min-h-[44px] min-w-[44px] rounded-full transition-all border ${
          voiceEnabled
            ? 'bg-ojas/20 border-ojas/40 text-ojas shadow-md'
            : 'bg-card border-border text-muted-foreground hover:bg-muted hover:border-ojas/30 shadow-sm'
        }`}
        title={voiceEnabled ? 'Stop recording' : 'Start voice input'}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        aria-label={voiceEnabled ? 'Stop recording' : 'Start voice input'}
      >
        {isListening && (
          <>
            <motion.span
              className="absolute inset-0 rounded-full bg-ojas/30"
              animate={{ scale: [1, 1.4, 1], opacity: [0.6, 0, 0.6] }}
              transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
            />
            <motion.span
              className="absolute inset-0 rounded-full bg-ojas/20"
              animate={{ scale: [1, 1.6, 1], opacity: [0.4, 0, 0.4] }}
              transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut', delay: 0.2 }}
            />
          </>
        )}
        {voiceEnabled ? (
          <MicOff className="w-5 h-5 relative z-10" />
        ) : (
          <Mic className="w-5 h-5 relative z-10" />
        )}
      </motion.button>
    </div>
  );
};

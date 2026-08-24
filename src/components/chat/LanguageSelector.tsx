import { useState, useEffect, useRef, useCallback } from 'react';
import { Globe, Mic, MicOff, Volume2, VolumeX, ChevronDown, Languages } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { setLanguage } from '@/lib/aiService';
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
  { code: 'hinglish', name: 'Hinglish', native: 'हिंग्लिश', bcp47: 'en-IN' },
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
  return ['en', 'hi', 'te', 'kn', 'ta', 'mr', 'bn', 'gu', 'ml', 'ur', 'pa', 'or', 'as', 'sa'].includes(lang.code);
});



/**
 * Short display label for the pill (≤ 6 chars). For English show "EN";
 * for other languages show their 2-char code uppercased so the pill is compact.
 * The full native name appears in the popover list.
 */
const pillLabel = (lang: Language): string => {
  if (lang.code === 'en') return 'EN';
  // For common langs show their native short-form
  const SHORT: Record<string, string> = {
    hinglish: 'Hing', hi: 'हिन्', te: 'తె', ta: 'த', bn: 'বাং', mr: 'मरा',
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
  const { i18n } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [internalLang, setInternalLang] = useState<string>(() => i18n?.language || 'en');
  const [focusedIndex, setFocusedIndex] = useState<number>(0);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const selectedLanguage = value ?? internalLang;
  
  const [voiceCapable, setVoiceCapable] = useState<Set<string>>(new Set(['en']));
  const { t } = useTranslation();

  const [coords, setCoords] = useState<{ bottom: number; left: number; maxHeight: number } | null>(null);

  const updatePosition = useCallback(() => {
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      const viewportWidth = window.innerWidth;
      const margin = 8;
      
      const bottom = Math.max(12, viewportHeight - rect.top + margin);
      
      let left = rect.left;
      const menuWidth = Math.min(320, viewportWidth - 24);
      
      if (left + menuWidth > viewportWidth - 12) {
        left = Math.max(12, viewportWidth - menuWidth - 12);
      }
      
      const availableAbove = rect.top - margin - 20;
      const maxHeight = Math.max(0, Math.min(320, availableAbove));
      setCoords({ bottom, left, maxHeight });
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      updatePosition();
      const selectedIdx = LANGUAGES.findIndex((l) => l.code === selectedLanguage);
      const initialIdx = selectedIdx >= 0 ? selectedIdx : 0;
      setFocusedIndex(initialIdx);
      // Move real DOM focus onto the selected option so roving tabindex is
      // consistent from the moment the popover opens (not just after a
      // keypress) — itemRefs are only populated once the list has rendered.
      requestAnimationFrame(() => itemRefs.current[initialIdx]?.focus());

      const handleScroll = (e: Event) => {
        // Do not update/re-render if the scroll event is inside our own dropdown list
        if (popoverRef.current && popoverRef.current.contains(e.target as Node)) {
          return;
        }
        updatePosition();
      };

      window.addEventListener('resize', updatePosition);
      window.addEventListener('scroll', handleScroll, true);
      return () => {
        window.removeEventListener('resize', updatePosition);
        window.removeEventListener('scroll', handleScroll, true);
      };
    }
  }, [isOpen, updatePosition, selectedLanguage]);

  useEffect(() => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    const update = () => setVoiceCapable(detectTtsVoices());
    update();
    window.speechSynthesis.onvoiceschanged = update;
    return () => {
      if (window.speechSynthesis) window.speechSynthesis.onvoiceschanged = null;
    };
  }, []);

  const handleLanguageChange = useCallback((code: string) => {
    setInternalLang(code);
    setLanguage(code);
    onLanguageChange?.(code);
    setIsOpen(false);
  }, [onLanguageChange]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
        requestAnimationFrame(() => triggerRef.current?.focus());
        return;
      }

      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setFocusedIndex((prev) => {
          const next = (prev + 1) % LANGUAGES.length;
          itemRefs.current[next]?.focus();
          itemRefs.current[next]?.scrollIntoView({ block: 'nearest' });
          return next;
        });
        return;
      }

      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setFocusedIndex((prev) => {
          const next = (prev - 1 + LANGUAGES.length) % LANGUAGES.length;
          itemRefs.current[next]?.focus();
          itemRefs.current[next]?.scrollIntoView({ block: 'nearest' });
          return next;
        });
        return;
      }

      if (event.key === 'Home') {
        event.preventDefault();
        setFocusedIndex(0);
        itemRefs.current[0]?.focus();
        itemRefs.current[0]?.scrollIntoView({ block: 'nearest' });
        return;
      }

      if (event.key === 'End') {
        event.preventDefault();
        const last = LANGUAGES.length - 1;
        setFocusedIndex(last);
        itemRefs.current[last]?.focus();
        itemRefs.current[last]?.scrollIntoView({ block: 'nearest' });
        return;
      }

      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        const selected = LANGUAGES[focusedIndex];
        if (selected) {
          handleLanguageChange(selected.code);
        }
        return;
      }

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
  }, [isOpen, focusedIndex, handleLanguageChange]);

  const currentLang = LANGUAGES.find((l) => l.code === selectedLanguage);

  // ponytail: flat list, no search — LANGUAGES is a compact priority set, a search
  // box was pure friction (matches a compact picker pattern).
  // Add search back only if LANGUAGES grows past ~12 entries.
  const renderLanguageRows = () => (
    <>
      {LANGUAGES.map((lang, idx) => {
        const isSelected = selectedLanguage === lang.code;
        const isFocused = focusedIndex === idx;
        return (
          <button
            key={lang.code}
            ref={(el) => {
              itemRefs.current[idx] = el;
            }}
            onClick={() => handleLanguageChange(lang.code)}
            onFocus={() => setFocusedIndex(idx)}
            tabIndex={isFocused ? 0 : -1}
            className={`w-full min-h-[48px] px-3 py-2 text-left hover:bg-ojas/10 transition-colors flex items-center gap-3 ${
              isSelected ? 'bg-ojas/15' : ''
            } ${isFocused ? 'ring-1 ring-ojas/50 bg-ojas/10' : ''}`}
            role="option"
            aria-selected={isSelected}
          >
            <div
              className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors ${
                isSelected ? 'bg-ojas/20 text-ojas' : 'bg-muted/60 text-muted-foreground'
              }`}
            >
              <Globe className="w-4 h-4" />
            </div>
            <div className="flex-1 min-w-0">
              <span
                className={`block font-medium truncate ${
                  lang.code === 'en' ? 'text-sm' : 'text-base'
                } ${isSelected ? 'text-ojas' : 'text-foreground'}`}
                lang={lang.bcp47}
              >
                {lang.native}
              </span>
              <span className="block text-xs text-muted-foreground truncate">
                {lang.name}
              </span>
            </div>
            {isSelected && (
              <span className="w-2.5 h-2.5 rounded-full bg-ojas flex-shrink-0" />
            )}
          </button>
        );
      })}
    </>
  );

  if (compact) {
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
              if (!isOpen) updatePosition();
              setIsOpen(!isOpen);
            }}
            className={`flex items-center gap-1.5 px-2.5 h-9 min-h-[44px] min-w-[44px] rounded-full transition-all font-semibold border ${
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
            <Globe className="w-3.5 h-3.5 flex-shrink-0 opacity-80" aria-hidden="true" />
            <span className={`font-medium ${isNonEnglish ? 'text-base leading-none' : ''}`}>{label}</span>
            {isNonEnglish && (
              <span className="flex items-center gap-1 text-[10px] font-bold text-ojas/90 bg-ojas/10 px-1.5 py-0.5 rounded">
                <Languages className="w-2.5 h-2.5" />
                AUTO
              </span>
            )}
            <ChevronDown className={`w-3 h-3 opacity-50 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
          </motion.button>

          <AnimatePresence>
            {isOpen && coords && (
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
                  className="fixed z-[100] flex flex-col overflow-hidden rounded-2xl border border-border bg-popover shadow-2xl w-72 max-w-[calc(100vw-2rem)]"
                  style={{ bottom: coords.bottom, left: coords.left, maxHeight: Math.min(320, coords.maxHeight) }}
                  role="listbox"
                  aria-label="Select language"
                >
                  {/* Header */}
                  <div className="px-3 py-2.5 border-b border-border bg-card/95 flex items-center gap-2">
                    <Globe className="w-3.5 h-3.5 text-ojas" />
                    <span className="text-xs font-semibold text-foreground">Select Language</span>
                  </div>

                  {/* Language list */}
                  <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin">
                    <div className="py-1">{renderLanguageRows()}</div>
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
            if (!isOpen) updatePosition();
            setIsOpen(!isOpen);
          }}
          className="flex items-center gap-2 px-3 py-2 min-h-[44px] min-w-[44px] rounded-full bg-card hover:bg-ojas/10 border border-border hover:border-ojas/30 transition-all text-sm shadow-sm"
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
          {isOpen && coords && (
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
                className="fixed w-72 max-w-[calc(100vw-2rem)] flex flex-col bg-popover border border-border rounded-2xl shadow-2xl z-[100] overflow-hidden"
                style={{ bottom: coords.bottom, left: coords.left, maxHeight: Math.min(320, coords.maxHeight) }}
                role="listbox"
                aria-label="Select language"
              >
                <div className="px-3 py-2.5 border-b border-border bg-card flex items-center gap-2">
                  <Globe className="w-3.5 h-3.5 text-ojas" />
                  <span className="text-xs font-semibold text-foreground">Select Language</span>
                </div>
                <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin">
                  <div className="py-1">
                    {renderLanguageRows()}
                  </div>
                </div>
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

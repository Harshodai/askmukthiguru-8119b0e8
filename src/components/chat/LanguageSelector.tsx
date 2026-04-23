import { useState, useEffect } from 'react';
import { Globe, Mic, MicOff, Volume2, VolumeX, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { setLanguage } from '@/lib/aiService';
import { useToast } from '@/hooks/use-toast';
import { ScrollArea } from '@/components/ui/scroll-area';

interface Language {
  code: string;
  name: string;
  native: string;
  /** BCP-47 tag used for Web Speech APIs */
  bcp47: string;
}

// 22 scheduled Indian languages + English. Aligned with Sarvam-30B's claimed coverage.
export const LANGUAGES: Language[] = [
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

interface LanguageSelectorProps {
  onVoiceToggle?: () => void;
  voiceEnabled?: boolean;
  isListening?: boolean;
  onLanguageChange?: (code: string) => void;
  ttsEnabled?: boolean;
  onTtsToggle?: () => void;
  isSpeaking?: boolean;
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
}: LanguageSelectorProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedLanguage, setSelectedLanguage] = useState('en');
  const [voiceCapable, setVoiceCapable] = useState<Set<string>>(new Set(['en']));
  const { toast } = useToast();

  useEffect(() => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    const update = () => setVoiceCapable(detectTtsVoices());
    update();
    window.speechSynthesis.onvoiceschanged = update;
    return () => {
      if (window.speechSynthesis) window.speechSynthesis.onvoiceschanged = null;
    };
  }, []);

  const handleLanguageChange = (code: string) => {
    const lang = LANGUAGES.find((l) => l.code === code);
    setSelectedLanguage(code);
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

  return (
    <div className="flex items-center gap-2">
      <div className="relative">
        <motion.button
          onClick={(e) => {
            e.stopPropagation();
            setIsOpen(!isOpen);
          }}
          className="flex items-center gap-2 px-3 py-2 min-h-[44px] rounded-full bg-card hover:bg-ojas/10 border border-border hover:border-ojas/30 transition-all text-sm shadow-sm"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
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
                className="absolute bottom-full left-0 mb-2 w-72 bg-card border border-border rounded-xl shadow-xl z-[100] overflow-hidden"
                role="listbox"
              >
                <ScrollArea className="max-h-72">
                  <div className="py-1">
                    {LANGUAGES.map((lang) => {
                      const isSelected = selectedLanguage === lang.code;
                      const hasVoice = voiceCapable.has(lang.code);
                      return (
                        <button
                          key={lang.code}
                          onClick={() => handleLanguageChange(lang.code)}
                          className={`w-full px-4 py-2.5 text-left text-sm hover:bg-ojas/10 transition-colors flex items-center gap-3 ${
                            isSelected ? 'bg-ojas/15' : ''
                          }`}
                          role="option"
                          aria-selected={isSelected}
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-baseline gap-2">
                              <span
                                className={`font-medium truncate ${
                                  isSelected ? 'text-ojas' : 'text-foreground'
                                }`}
                              >
                                {lang.native}
                              </span>
                              <span className="text-muted-foreground text-xs truncate">
                                {lang.name}
                              </span>
                            </div>
                            {!hasVoice && (
                              <span className="inline-flex items-center gap-1 mt-0.5 text-[10px] text-muted-foreground">
                                <AlertCircle className="w-2.5 h-2.5" />
                                Voice not supported in this browser
                              </span>
                            )}
                          </div>
                          {isSelected && (
                            <span className="w-2 h-2 rounded-full bg-ojas flex-shrink-0" />
                          )}
                        </button>
                      );
                    })}
                  </div>
                </ScrollArea>
                <div className="px-4 py-2.5 text-xs text-muted-foreground border-t border-border bg-muted/30">
                  <span className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-prana animate-pulse" />
                    <span>22 Indic languages</span>
                    <span className="ml-auto px-1.5 py-0.5 rounded bg-ojas/20 text-ojas text-[10px] font-medium">
                      Sarvam-ready
                    </span>
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

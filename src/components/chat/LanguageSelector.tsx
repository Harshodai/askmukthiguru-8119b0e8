import { useState } from 'react';
import { Globe, Mic, Volume2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { setLanguage } from '@/lib/aiService';

const languages = [
  { code: 'en', name: 'English', native: 'English' },
  { code: 'hi', name: 'Hindi', native: 'हिंदी' },
  { code: 'te', name: 'Telugu', native: 'తెలుగు' },
  { code: 'ta', name: 'Tamil', native: 'தமிழ்' },
  { code: 'kn', name: 'Kannada', native: 'ಕನ್ನಡ' },
  { code: 'ml', name: 'Malayalam', native: 'മലയാളം' },
];

interface LanguageSelectorProps {
  onVoiceToggle?: () => void;
  voiceEnabled?: boolean;
}

export const LanguageSelector = ({ onVoiceToggle, voiceEnabled }: LanguageSelectorProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedLanguage, setSelectedLanguage] = useState('en');

  const handleLanguageChange = (code: string) => {
    setSelectedLanguage(code);
    setLanguage(code);
    setIsOpen(false);
  };

  const currentLang = languages.find((l) => l.code === selectedLanguage);

  return (
    <div className="flex items-center gap-2">
      {/* Language Dropdown */}
      <div className="relative">
        <motion.button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-2 px-3 py-2 rounded-full bg-ojas/10 hover:bg-ojas/20 border border-ojas/20 hover:border-ojas/30 transition-all text-sm"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          <Globe className="w-4 h-4 text-ojas" />
          <span className="text-foreground font-medium">{currentLang?.native || 'EN'}</span>
        </motion.button>

        <AnimatePresence>
          {isOpen && (
            <>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-40"
                onClick={() => setIsOpen(false)}
              />
              <motion.div 
                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 10, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                className="absolute bottom-full left-0 mb-2 w-48 bg-card border border-border rounded-xl shadow-lg z-50 overflow-hidden"
              >
                <div className="py-2">
                  {languages.map((lang) => (
                    <button
                      key={lang.code}
                      onClick={() => handleLanguageChange(lang.code)}
                      className={`w-full px-4 py-2.5 text-left text-sm hover:bg-ojas/10 transition-colors flex items-center justify-between ${
                        selectedLanguage === lang.code ? 'bg-ojas/15 text-ojas' : 'text-foreground'
                      }`}
                    >
                      <span className="font-medium">{lang.native}</span>
                      <span className="text-muted-foreground text-xs">{lang.name}</span>
                    </button>
                  ))}
                </div>
                <div className="px-4 py-2.5 text-xs text-muted-foreground border-t border-border bg-muted/30">
                  <span className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-prana animate-pulse" />
                    Bhashini (Coming Soon)
                  </span>
                </div>
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </div>

      {/* Voice Mode Toggle */}
      <motion.button
        onClick={onVoiceToggle}
        className={`p-2.5 rounded-full transition-all border ${
          voiceEnabled
            ? 'bg-ojas/20 border-ojas/30 text-ojas'
            : 'bg-muted/50 border-border text-muted-foreground hover:bg-muted hover:border-ojas/20'
        }`}
        title={voiceEnabled ? 'Voice mode on' : 'Enable voice mode'}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        {voiceEnabled ? (
          <Volume2 className="w-4 h-4" />
        ) : (
          <Mic className="w-4 h-4" />
        )}
      </motion.button>
    </div>
  );
};

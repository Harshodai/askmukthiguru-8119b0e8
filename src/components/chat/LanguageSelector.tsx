import { useState, useEffect } from 'react';
import { Globe, Mic, MicOff } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { setLanguage } from '@/lib/aiService';
import { useToast } from '@/hooks/use-toast';

const languages = [
  { code: 'en', name: 'English', native: 'English' },
  { code: 'hi', name: 'Hindi', native: 'हिंदी' },
  { code: 'te', name: 'Telugu', native: 'తెలుగు' },
  { code: 'ml', name: 'Malayalam', native: 'മലയാളം' },
];

interface LanguageSelectorProps {
  onVoiceToggle?: () => void;
  voiceEnabled?: boolean;
  isListening?: boolean;
  onLanguageChange?: (code: string) => void;
}

export const LanguageSelector = ({ 
  onVoiceToggle, 
  voiceEnabled, 
  isListening,
  onLanguageChange 
}: LanguageSelectorProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedLanguage, setSelectedLanguage] = useState('en');
  const { toast } = useToast();

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = () => {
      if (isOpen) setIsOpen(false);
    };
    
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [isOpen]);

  const handleLanguageChange = (code: string) => {
    const lang = languages.find(l => l.code === code);
    setSelectedLanguage(code);
    setLanguage(code);
    onLanguageChange?.(code);
    setIsOpen(false);
    
    toast({
      title: 'Language Changed',
      description: `Switched to ${lang?.name || code}`,
      duration: 2000,
    });
  };

  const currentLang = languages.find((l) => l.code === selectedLanguage);

  return (
    <div className="flex items-center gap-3">
      {/* Language Dropdown */}
      <div className="relative">
        <motion.button
          onClick={(e) => {
            e.stopPropagation();
            setIsOpen(!isOpen);
          }}
          className="flex items-center gap-2 px-4 py-2.5 min-h-[44px] rounded-full bg-card hover:bg-ojas/10 border border-border hover:border-ojas/30 transition-all text-sm shadow-sm"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          <Globe className="w-4 h-4 text-ojas" />
          <span className="text-foreground font-medium">{currentLang?.native || 'English'}</span>
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
                className="absolute top-full left-0 mt-2 w-52 bg-card border border-border rounded-xl shadow-xl z-[100] overflow-hidden"
              >
                <div className="py-2">
                  {languages.map((lang) => (
                    <button
                      key={lang.code}
                      onClick={() => handleLanguageChange(lang.code)}
                      className={`w-full px-4 py-3 text-left text-sm hover:bg-ojas/10 transition-colors flex items-center justify-between ${
                        selectedLanguage === lang.code ? 'bg-ojas/15 text-ojas' : 'text-foreground'
                      }`}
                    >
                      <span className="font-medium">{lang.native}</span>
                      <span className="text-muted-foreground text-xs">{lang.name}</span>
                    </button>
                  ))}
                </div>
                <div className="px-4 py-3 text-xs text-muted-foreground border-t border-border bg-muted/30">
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
        className={`relative p-3 min-h-[44px] min-w-[44px] rounded-full transition-all border ${
          voiceEnabled
            ? 'bg-ojas/20 border-ojas/40 text-ojas shadow-md'
            : 'bg-card border-border text-muted-foreground hover:bg-muted hover:border-ojas/30 shadow-sm'
        }`}
        title={voiceEnabled ? 'Stop recording' : 'Start voice input'}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        {/* Recording pulse animation */}
        {isListening && (
          <>
            <motion.span
              className="absolute inset-0 rounded-full bg-ojas/30"
              animate={{
                scale: [1, 1.4, 1],
                opacity: [0.6, 0, 0.6],
              }}
              transition={{
                duration: 1.5,
                repeat: Infinity,
                ease: 'easeInOut',
              }}
            />
            <motion.span
              className="absolute inset-0 rounded-full bg-ojas/20"
              animate={{
                scale: [1, 1.6, 1],
                opacity: [0.4, 0, 0.4],
              }}
              transition={{
                duration: 1.5,
                repeat: Infinity,
                ease: 'easeInOut',
                delay: 0.2,
              }}
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
